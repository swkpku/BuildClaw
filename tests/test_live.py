"""
test_live.py — Live integration tests using real Anthropic API.

Calls run_agent() directly with real API keys from .env.
Exercises every tool block: files, shell, memory, web search.

Run:  pytest tests/test_live.py -v -s
Cost: ~$0.05-0.10 per full run (real API calls)

Requires: .env with ANTHROPIC_API_KEY, TELEGRAM_TOKEN, ALLOWED_USER_IDS
"""

import os
import sys
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch

# Load .env from project root
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Point to the bot module — use BOT_MODULE_PATH env var if set (e.g. from run_skill_test.sh),
# otherwise fall back to the reference implementation.
bot_path = os.environ.get("BOT_MODULE_PATH", str(PROJECT_ROOT / "examples" / "telegram"))
sys.path.insert(0, bot_path)

import anthropic
import bot

USER_ID = next(iter(bot.ALLOWED_USER_IDS))


def call_agent_with_retry(user_id, message, retries=3):
    """Call run_agent with retry on transient API errors."""
    for attempt in range(retries):
        try:
            return bot.run_agent(user_id, message)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                bot.conversations.pop(user_id, None)  # clear failed history
                continue
            raise


@pytest.fixture(autouse=True)
def temp_workspace(tmp_path):
    """Override WORKSPACE and SYSTEM_PROMPT to use a temp dir."""
    new_prompt = bot.SYSTEM_PROMPT.replace(str(bot.WORKSPACE), str(tmp_path))
    with patch.object(bot, "WORKSPACE", tmp_path), \
         patch.object(bot, "SYSTEM_PROMPT", new_prompt):
        tmp_path.mkdir(exist_ok=True)
        yield tmp_path
    bot.conversations.clear()


# ── Chat (foundation) ────────────────────────────────────────────────────────

class TestChat:
    """Basic Claude conversation — no tools needed."""

    def test_simple_question(self):
        reply = call_agent_with_retry(USER_ID, "What is 2 + 2? Reply with just the number.")
        assert "4" in reply

    def test_conversation_memory_within_session(self):
        call_agent_with_retry(USER_ID, "My name is TestBot9000. Remember that.")
        reply = call_agent_with_retry(USER_ID, "What is my name?")
        assert "TestBot9000" in reply


# ── Files block ──────────────────────────────────────────────────────────────

class TestFilesBlock:
    """Tests that Claude can read, write, and list files via tools."""

    def test_write_and_read_file(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Write the text 'hello from test' to {temp_workspace}/test_output.txt. "
            f"Then read it back and tell me the contents."
        )
        assert "hello from test" in reply

    def test_list_directory(self, temp_workspace):
        (temp_workspace / "notes.txt").write_text("test")
        (temp_workspace / "data.json").write_text("{}")

        reply = call_agent_with_retry(
            USER_ID,
            f"List the files in {temp_workspace}. Just list the filenames."
        )
        assert "notes.txt" in reply
        assert "data.json" in reply

    def test_blocked_path_rejected(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Read the file {temp_workspace}/.ssh/id_rsa"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "denied", "cannot", "can't", "not allowed", "restricted"])


# ── Shell block ──────────────────────────────────────────────────────────────

class TestShellBlock:
    """Tests that Claude can run shell commands in the workspace."""

    def test_echo_command(self):
        reply = call_agent_with_retry(
            USER_ID,
            "Run the shell command: echo 'shell_test_12345'. Tell me the exact output."
        )
        assert "shell_test_12345" in reply

    def test_pwd_is_workspace(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            "Run the shell command: pwd. Tell me the result."
        )
        assert str(temp_workspace) in reply


# ── Web block (if duckduckgo-search installed) ───────────────────────────────

class TestWebBlock:
    """Tests web search functionality."""

    def _has_web_tool(self):
        return any(t["name"] == "web_search" for t in bot.TOOL_DEFINITIONS)

    def test_web_search(self):
        if not self._has_web_tool():
            pytest.skip("web block not present in bot.py")
        reply = call_agent_with_retry(
            USER_ID,
            "Search the web for 'Python programming language official site' and tell me the URL."
        )
        assert "python" in reply.lower()


# ── Memory block (if present) ────────────────────────────────────────────────

class TestMemoryBlock:
    """Tests the persistent memory tool."""

    def _has_memory_tool(self):
        return any(t["name"] == "remember" for t in bot.TOOL_DEFINITIONS)

    def test_remember_and_recall(self):
        if not self._has_memory_tool():
            pytest.skip("memory block not present in bot.py")
        call_agent_with_retry(USER_ID, "Remember that my favorite color is purple.")
        reply = call_agent_with_retry(USER_ID, "What is my favorite color? Use the recall tool.")
        assert "purple" in reply.lower()


# ── Security ─────────────────────────────────────────────────────────────────

class TestSecurityLive:
    """Verify that security constraints hold under real Claude reasoning."""

    def test_cannot_read_outside_workspace(self):
        reply = call_agent_with_retry(USER_ID, "Read the file /etc/passwd")
        lower = reply.lower()
        assert any(w in lower for w in ["block", "outside", "cannot", "can't", "not allowed", "denied", "restricted"])

    def test_cannot_read_env_file(self, temp_workspace):
        (temp_workspace / ".env").write_text("SECRET=leaked")
        reply = call_agent_with_retry(
            USER_ID,
            f"Read the file {temp_workspace}/.env"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "cannot", "can't", "denied", "restricted"])

    def test_cannot_read_ssh_key(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Read {temp_workspace}/.ssh/id_rsa"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "cannot", "can't", "denied", "restricted"])
