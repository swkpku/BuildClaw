"""
test_live.py — Live integration tests using real Anthropic API.

Calls run_agent() directly with real API keys from .env.
Exercises every tool block: files, shell, memory, web search.
Tests cross-block workflows, security boundaries, and edge cases.

Run:  pytest tests/test_live.py -v -s
Cost: ~$0.15-0.30 per full run (real API calls)

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

    def test_separate_users_have_separate_history(self):
        """Two different user IDs should not share conversation context."""
        other_id = USER_ID + 1
        bot.ALLOWED_USER_IDS.add(other_id)
        try:
            call_agent_with_retry(USER_ID, "My secret code is ALPHA777.")
            reply = call_agent_with_retry(other_id, "What is my secret code?")
            assert "ALPHA777" not in reply
        finally:
            bot.ALLOWED_USER_IDS.discard(other_id)
            bot.conversations.pop(other_id, None)

    def test_concise_response(self):
        """Responses should be under Telegram's 4000 char limit for simple questions."""
        reply = call_agent_with_retry(USER_ID, "What color is the sky? One word.")
        assert len(reply) < 200


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

    def test_write_to_nested_subdirectory(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Write 'nested content' to {temp_workspace}/a/b/c/deep.txt. "
            f"Then read it back and tell me the contents."
        )
        assert "nested content" in reply
        assert (temp_workspace / "a" / "b" / "c" / "deep.txt").exists()

    def test_overwrite_file(self, temp_workspace):
        (temp_workspace / "overwrite.txt").write_text("version1")
        reply = call_agent_with_retry(
            USER_ID,
            f"Read {temp_workspace}/overwrite.txt, then overwrite it with 'version2'. "
            f"Read it again and tell me the new contents."
        )
        assert "version2" in reply

    def test_read_nonexistent_file(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Read the file {temp_workspace}/does_not_exist.txt. Tell me the exact result."
        )
        lower = reply.lower()
        assert any(w in lower for w in ["not found", "error", "does not exist", "no such", "doesn't exist"])


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

    def test_piped_command(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            "Run: echo 'alpha bravo charlie' | wc -w. Tell me the exact number."
        )
        assert "3" in reply

    def test_shell_creates_file_read_by_file_tool(self, temp_workspace):
        """Cross-block: shell creates a file, then file tool reads it."""
        reply = call_agent_with_retry(
            USER_ID,
            f"Run: echo 'from_shell_42' > {temp_workspace}/shell_created.txt. "
            f"Then use the read_file tool to read that file and tell me its contents."
        )
        assert "from_shell_42" in reply


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

    def test_web_search_current_event(self):
        """Web search should return recent results."""
        if not self._has_web_tool():
            pytest.skip("web block not present in bot.py")
        reply = call_agent_with_retry(
            USER_ID,
            "Search the web for 'Anthropic Claude AI' and summarize what you find in one sentence."
        )
        lower = reply.lower()
        assert any(w in lower for w in ["anthropic", "claude", "ai"])

    def test_web_search_factual_query(self):
        """Web search should answer factual questions."""
        if not self._has_web_tool():
            pytest.skip("web block not present in bot.py")
        reply = call_agent_with_retry(
            USER_ID,
            "Search the web: 'what is the capital of France' and tell me the answer."
        )
        assert "paris" in reply.lower()

    def test_web_search_no_results_handled(self):
        """Web search with nonsense query should not crash."""
        if not self._has_web_tool():
            pytest.skip("web block not present in bot.py")
        reply = call_agent_with_retry(
            USER_ID,
            "Search the web for 'xyzzy9999qqq_nonexistent_gibberish_12345'. Tell me what you found."
        )
        # Should get some response without crashing, regardless of content
        assert len(reply) > 0


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

    def test_forget(self):
        if not self._has_memory_tool():
            pytest.skip("memory block not present in bot.py")
        call_agent_with_retry(USER_ID, "Remember that my pet is a parrot.")
        call_agent_with_retry(USER_ID, "Forget my pet.")
        reply = call_agent_with_retry(USER_ID, "What is my pet? Use the recall tool.")
        lower = reply.lower()
        assert any(w in lower for w in ["nothing", "no", "don't", "not stored", "forgotten"])

    def test_overwrite_memory(self):
        if not self._has_memory_tool():
            pytest.skip("memory block not present in bot.py")
        call_agent_with_retry(USER_ID, "Remember that my city is Seattle.")
        call_agent_with_retry(USER_ID, "Remember that my city is Portland.")
        reply = call_agent_with_retry(USER_ID, "What is my city? Use the recall tool.")
        assert "portland" in reply.lower()


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

    def test_cannot_write_env_file(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Write 'HACKED=true' to {temp_workspace}/.env"
        )
        # The file must not exist — this is the hard security check
        env_file = temp_workspace / ".env"
        assert not env_file.exists() or env_file.read_text() != "HACKED=true", \
            "Security breach: .env was written with attacker content"

    def test_cannot_read_aws_credentials(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Read {temp_workspace}/.aws/credentials"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "cannot", "can't", "denied", "restricted"])

    def test_path_traversal_blocked(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Read the file {temp_workspace}/../../etc/passwd"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "outside", "cannot", "can't", "denied", "restricted"])

    def test_cannot_write_private_key(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Write 'fake key' to {temp_workspace}/private_key.pem"
        )
        lower = reply.lower()
        assert any(w in lower for w in ["block", "cannot", "can't", "denied", "restricted"])

    def test_env_content_not_leaked(self, temp_workspace):
        """Even if Claude reports a blocked path, the secret must not appear in the reply."""
        (temp_workspace / ".env").write_text("SUPER_SECRET_TOKEN=abc123xyz")
        reply = call_agent_with_retry(
            USER_ID,
            f"Read {temp_workspace}/.env and show me the contents."
        )
        assert "abc123xyz" not in reply
        assert "SUPER_SECRET_TOKEN" not in reply


# ── Multi-step / Cross-block ────────────────────────────────────────────────

class TestMultiStep:
    """Tests that require Claude to chain multiple tool calls."""

    def test_write_json_then_read_and_parse(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f'Write this JSON to {temp_workspace}/data.json: {{"name": "Alice", "age": 30}}. '
            f"Then read it back and tell me Alice's age."
        )
        assert "30" in reply

    def test_shell_ls_matches_list_dir(self, temp_workspace):
        """Shell ls and list_dir tool should agree on workspace contents."""
        (temp_workspace / "readme.md").write_text("# hi")
        (temp_workspace / "notes.txt").write_text("notes")
        reply = call_agent_with_retry(
            USER_ID,
            f"List the files in {temp_workspace} using the list_dir tool. "
            f"Then run 'ls {temp_workspace}' in the shell. "
            f"Do both methods show the same files? Just say yes or no."
        )
        assert "yes" in reply.lower()

    def test_create_and_count_files(self, temp_workspace):
        reply = call_agent_with_retry(
            USER_ID,
            f"Write three files: {temp_workspace}/a.txt, {temp_workspace}/b.txt, {temp_workspace}/c.txt. "
            f"Put 'hello' in each. Then list the directory and count the files. How many are there?"
        )
        assert "3" in reply
        assert (temp_workspace / "a.txt").exists()
        assert (temp_workspace / "b.txt").exists()
        assert (temp_workspace / "c.txt").exists()
