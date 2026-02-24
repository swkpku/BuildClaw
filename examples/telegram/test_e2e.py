"""
test_e2e.py — End-to-end tests for bot.py

Tests the full pipeline: agent loop, tool dispatch, Telegram handlers,
conversation management, and configuration validation.

Mocks the Anthropic API and Telegram objects — no real API keys needed.

Run: pytest test_e2e.py -v
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from types import SimpleNamespace

# Patch env vars before importing bot
os.environ.setdefault("TELEGRAM_TOKEN", "test_token_not_real")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test_not_real")
os.environ.setdefault("ALLOWED_USER_IDS", "123456789")

import bot


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_tool_results(messages):
    """Extract tool_result entries from the message history passed to Anthropic."""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict):
                if content[0].get("type") == "tool_result":
                    return content
    return []


# ── Helpers to build mock Anthropic responses ────────────────────────────────

def make_text_response(text):
    """Simulate a Claude response that just returns text (end_turn)."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[block],
        stop_reason="end_turn",
    )


def make_tool_use_response(tool_name, tool_input, tool_use_id="toolu_test_123"):
    """Simulate a Claude response that calls a tool."""
    block = SimpleNamespace(
        type="tool_use",
        name=tool_name,
        input=tool_input,
        id=tool_use_id,
    )
    return SimpleNamespace(
        content=[block],
        stop_reason="tool_use",
    )


# ── Agent loop ───────────────────────────────────────────────────────────────

class TestRunAgent:
    """Tests for the full run_agent() agentic loop."""

    def test_simple_text_response(self):
        """Agent returns text directly when Claude says end_turn."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = make_text_response("Hello!")

        with patch.object(bot, "client", mock_client):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Hi")

        assert result == "Hello!"

    def test_tool_call_then_text(self, tmp_path):
        """Agent calls a tool, feeds result back, then returns text."""
        # Create a file for the tool to read
        test_file = tmp_path / "notes.txt"
        test_file.write_text("my secret notes")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            # First call: Claude wants to read a file
            make_tool_use_response("read_file", {"path": str(test_file)}),
            # Second call: Claude returns text after seeing file contents
            make_text_response("Your notes say: my secret notes"),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Read my notes")

        assert "my secret notes" in result
        assert mock_client.messages.create.call_count == 2

    def test_tool_call_with_blocked_path(self, tmp_path):
        """Agent tries to read a blocked path — tool returns Blocked, Claude handles it."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            make_tool_use_response("read_file", {"path": str(tmp_path / ".ssh" / "id_rsa")}),
            make_text_response("I can't access that file — it's blocked for security."),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Read my SSH key")

        assert "blocked" in result.lower() or "can't" in result.lower()

        # Verify the tool result sent back to Claude contains "Blocked"
        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        tool_results = find_tool_results(second_call_messages)
        assert len(tool_results) > 0
        assert "Blocked" in tool_results[0]["content"]

    def test_write_file_via_tool(self, tmp_path):
        """Agent writes a file through tool dispatch."""
        target = tmp_path / "output.txt"

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            make_tool_use_response("write_file", {
                "path": str(target),
                "content": "hello from agent",
            }),
            make_text_response("File written successfully."),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Write hello to output.txt")

        assert target.read_text() == "hello from agent"

    def test_shell_via_tool(self, tmp_path):
        """Agent runs a shell command through tool dispatch."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            make_tool_use_response("shell", {"command": "echo hello"}),
            make_text_response("The command output was: hello"),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Run echo hello")

        # Verify shell tool was called and result sent back
        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        tool_results = find_tool_results(second_call_messages)
        assert len(tool_results) > 0
        assert "hello" in tool_results[0]["content"]

    def test_list_dir_via_tool(self, tmp_path):
        """Agent lists directory through tool dispatch."""
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "subdir").mkdir()

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            make_tool_use_response("list_dir", {"path": ""}),
            make_text_response("Your workspace contains file1.txt and subdir/"),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "List my files")

        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        tool_results = find_tool_results(second_call_messages)
        assert len(tool_results) > 0
        assert "file1.txt" in tool_results[0]["content"]
        assert "subdir" in tool_results[0]["content"]

    def test_unknown_tool_handled(self):
        """Agent handles an unknown tool name gracefully."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            make_tool_use_response("nonexistent_tool", {}),
            make_text_response("Sorry, that tool isn't available."),
        ]

        with patch.object(bot, "client", mock_client):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Do something weird")

        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        tool_results = find_tool_results(second_call_messages)
        assert len(tool_results) > 0
        assert "Unknown tool" in tool_results[0]["content"]

    def test_unexpected_stop_reason(self):
        """Agent returns message for unexpected stop_reason."""
        mock_client = MagicMock()
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="partial")],
            stop_reason="max_tokens",
        )
        mock_client.messages.create.return_value = resp

        with patch.object(bot, "client", mock_client):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Write me an essay")

        assert "unexpected stop_reason" in result.lower()

    def test_multi_tool_call_in_single_response(self, tmp_path):
        """Agent handles multiple tool calls in one response."""
        (tmp_path / "a.txt").write_text("content_a")
        (tmp_path / "b.txt").write_text("content_b")

        block_a = SimpleNamespace(
            type="tool_use", name="read_file",
            input={"path": str(tmp_path / "a.txt")}, id="toolu_a",
        )
        block_b = SimpleNamespace(
            type="tool_use", name="read_file",
            input={"path": str(tmp_path / "b.txt")}, id="toolu_b",
        )
        multi_tool_resp = SimpleNamespace(
            content=[block_a, block_b],
            stop_reason="tool_use",
        )

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            multi_tool_resp,
            make_text_response("Both files read."),
        ]

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "WORKSPACE", tmp_path):
            bot.conversations.clear()
            result = bot.run_agent(123456789, "Read a.txt and b.txt")

        # Check both tool results were sent back
        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        tool_results = find_tool_results(second_call_messages)
        assert len(tool_results) == 2
        assert "content_a" in tool_results[0]["content"]
        assert "content_b" in tool_results[1]["content"]


# ── Conversation management ──────────────────────────────────────────────────

class TestConversationManagement:
    """Tests for history tracking and trimming."""

    def test_history_stored_per_user(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = make_text_response("ok")

        with patch.object(bot, "client", mock_client):
            bot.conversations.clear()
            bot.run_agent(111, "msg from user 111")
            bot.run_agent(222, "msg from user 222")

        assert 111 in bot.conversations
        assert 222 in bot.conversations
        assert len(bot.conversations[111]) == 2  # user + assistant
        assert len(bot.conversations[222]) == 2

    def test_history_trimmed_at_20(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = make_text_response("ok")

        with patch.object(bot, "client", mock_client):
            bot.conversations.clear()
            # Send 25 messages (each creates 2 entries: user + assistant)
            for i in range(25):
                bot.run_agent(999, f"message {i}")

        assert len(bot.conversations[999]) <= 22  # 20 + current user + assistant

    def test_system_prompt_includes_workspace(self):
        assert str(bot.WORKSPACE) in bot.SYSTEM_PROMPT

    def test_tool_definitions_not_empty(self):
        assert len(bot.TOOL_DEFINITIONS) > 0

    def test_tool_dispatch_matches_definitions(self):
        defined_names = {t["name"] for t in bot.TOOL_DEFINITIONS}
        dispatch_names = set(bot.TOOL_DISPATCH.keys())
        assert defined_names == dispatch_names, (
            f"Mismatch: defined={defined_names}, dispatch={dispatch_names}"
        )


# ── Telegram handlers ────────────────────────────────────────────────────────

def make_mock_update(user_id, text):
    """Create a mock Telegram Update with given user_id and message text."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    return update


class TestTelegramHandlers:
    """Tests for the Telegram message handlers."""

    @pytest.mark.asyncio
    async def test_authorized_user_gets_response(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = make_text_response("Hello!")

        update = make_mock_update(123456789, "Hi there")
        context = MagicMock()

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            bot.conversations.clear()
            await bot.handle_message(update, context)

        # Should have sent at least one reply (the thinking msg + actual reply)
        assert update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_unauthorized_user_gets_nothing(self):
        update = make_mock_update(999999999, "trying to hack")
        context = MagicMock()

        with patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            await bot.handle_message(update, context)

        # Should NOT have called reply_text at all
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self):
        update = make_mock_update(123456789, "")
        context = MagicMock()

        with patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            await bot.handle_message(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_clears_history(self):
        bot.conversations[123456789] = [{"role": "user", "content": "old msg"}]

        update = make_mock_update(123456789, "/reset")
        context = MagicMock()

        with patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            await bot.handle_reset(update, context)

        assert 123456789 not in bot.conversations

    @pytest.mark.asyncio
    async def test_reset_unauthorized_user_gets_nothing(self):
        update = make_mock_update(999999999, "/reset")
        context = MagicMock()

        with patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            await bot.handle_reset(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_error_returns_error_message(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")

        update = make_mock_update(123456789, "Hello")
        context = MagicMock()

        with patch.object(bot, "client", mock_client), \
             patch.object(bot, "ALLOWED_USER_IDS", {123456789}):
            bot.conversations.clear()
            await bot.handle_message(update, context)

        # Should have replied with error text
        calls = update.message.reply_text.call_args_list
        error_replies = [c for c in calls if "Error" in str(c) or "API timeout" in str(c)]
        assert len(error_replies) > 0


# ── Configuration validation ─────────────────────────────────────────────────

class TestConfiguration:
    """Tests for configuration and startup."""

    def test_allowed_user_ids_is_set_of_ints(self):
        assert isinstance(bot.ALLOWED_USER_IDS, set)
        for uid in bot.ALLOWED_USER_IDS:
            assert isinstance(uid, int)

    def test_workspace_is_path(self):
        assert isinstance(bot.WORKSPACE, Path)

    def test_model_is_string(self):
        assert isinstance(bot.MODEL, str)
        assert len(bot.MODEL) > 0

    def test_bad_user_id_raises_on_startup(self, tmp_path):
        """Non-numeric ALLOWED_USER_IDS should fail with a clear error."""
        import subprocess
        import sys

        env = os.environ.copy()
        env["TELEGRAM_TOKEN"] = "fake"
        env["ANTHROPIC_API_KEY"] = "fake"
        env["ALLOWED_USER_IDS"] = "not_a_number"

        result = subprocess.run(
            [sys.executable, "-c", "import bot"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent),
            env=env,
            timeout=10,
        )
        assert result.returncode != 0
        assert "numeric" in result.stderr.lower() or "userinfobot" in result.stderr.lower()
