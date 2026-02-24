#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run_skill_test.sh — Full skill-to-bot integration test
#
# What it does:
#   1. Creates a temp directory
#   2. Copies .env into it
#   3. Installs skills into a temp Claude config
#   4. Runs claude with /build to generate a fresh bot.py
#   5. Runs the security + e2e test suites against the generated bot.py
#   6. Runs live integration tests (real Anthropic API calls)
#   7. Cleans up
#
# Usage:
#   ./tests/run_skill_test.sh
#
# Requirements:
#   - claude CLI installed and authenticated
#   - .env file at project root with valid API keys
#   - Python 3.11+ with venv support
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WORK_DIR=$(mktemp -d "/tmp/buildclaw_test_${TIMESTAMP}_XXXXXX")

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${BOLD}[test]${NC} $1"; }
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

cleanup() {
    log "Cleaning up $WORK_DIR"
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# ── Preflight checks ────────────────────────────────────────────────────────

log "Preflight checks..."

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    fail ".env not found at project root"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    fail "claude CLI not found. Install: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    fail "python3 not found"
    exit 1
fi

pass "All preflight checks passed"

# ── Step 1: Set up temp workspace ────────────────────────────────────────────

log "Setting up workspace at $WORK_DIR"
cp "$PROJECT_ROOT/.env" "$WORK_DIR/.env"

# ── Step 2: Install skills to temp Claude config ─────────────────────────────

log "Installing skills..."
TEMP_SKILLS="$WORK_DIR/.claude_skills"
mkdir -p "$TEMP_SKILLS/build" "$TEMP_SKILLS/audit" "$TEMP_SKILLS/test"
cp "$PROJECT_ROOT/skills/build/SKILL.md" "$TEMP_SKILLS/build/SKILL.md"
cp "$PROJECT_ROOT/skills/audit/SKILL.md" "$TEMP_SKILLS/audit/SKILL.md"
cp "$PROJECT_ROOT/skills/test/SKILL.md"  "$TEMP_SKILLS/test/SKILL.md"
pass "Skills installed"

# ── Step 3: Generate bot.py via Claude ───────────────────────────────────────

log "Running /build skill via Claude to generate bot.py..."
log "This calls the real Anthropic API and may take 30-60 seconds."

cd "$WORK_DIR"

# Run claude non-interactively, providing all choices upfront
# Unset CLAUDECODE to allow running inside a Claude Code session (e.g. during dev)
env -u CLAUDECODE claude -p "
Read the skill file at $TEMP_SKILLS/build/SKILL.md and follow its instructions exactly.

Generate a bot.py in the current directory with these choices:
- Blocks: files, shell, memory, web
- Soul: Default (helpful, concise, professional)

Also generate .env.example and requirements.txt as the skill instructs.
Do not ask me any questions — use the choices above.
" --max-turns 15 --dangerously-skip-permissions 2>&1 | while IFS= read -r line; do
    echo "  [claude] $line"
done

if [ ! -f "$WORK_DIR/bot.py" ]; then
    fail "Claude did not generate bot.py"
    echo "Contents of $WORK_DIR:"
    ls -la "$WORK_DIR"
    exit 1
fi

LINES=$(wc -l < "$WORK_DIR/bot.py" | tr -d ' ')
pass "bot.py generated ($LINES lines)"

# ── Step 4: Syntax check ────────────────────────────────────────────────────

log "Checking Python syntax..."
python3 -c "
import py_compile, sys
try:
    py_compile.compile('$WORK_DIR/bot.py', doraise=True)
    print('  Syntax OK')
except py_compile.PyCompileError as e:
    print(f'  Syntax error: {e}')
    sys.exit(1)
"
pass "Syntax check passed"

# ── Step 5: Set up venv and install deps ─────────────────────────────────────

log "Setting up Python environment..."
python3 -m venv "$WORK_DIR/.venv"
"$WORK_DIR/.venv/bin/pip" install -q pytest pytest-asyncio 2>&1 | tail -1

if [ -f "$WORK_DIR/requirements.txt" ]; then
    "$WORK_DIR/.venv/bin/pip" install -q -r "$WORK_DIR/requirements.txt" 2>&1 | tail -1
else
    warn "No requirements.txt generated — installing base deps"
    "$WORK_DIR/.venv/bin/pip" install -q anthropic python-telegram-bot python-dotenv ddgs 2>&1 | tail -1
fi
pass "Dependencies installed"

# ── Step 6: Run security tests against generated bot.py ──────────────────────

log "Running security tests against generated bot.py..."

# Copy the test files next to the generated bot.py
cp "$PROJECT_ROOT/examples/telegram/test_security.py" "$WORK_DIR/test_security.py"
cp "$PROJECT_ROOT/examples/telegram/test_e2e.py" "$WORK_DIR/test_e2e.py"

cd "$WORK_DIR"
# Source .env for the test run
set -a
source "$WORK_DIR/.env"
set +a

if "$WORK_DIR/.venv/bin/pytest" test_security.py test_e2e.py -v 2>&1; then
    pass "Security + e2e tests passed against generated bot.py"
else
    fail "Security or e2e tests FAILED against generated bot.py"
    warn "The skill generated code that doesn't match tested patterns."
    warn "Compare generated bot.py with examples/telegram/bot.py"
    exit 1
fi

# ── Step 7: Run live integration tests ───────────────────────────────────────

log "Running live integration tests (real API calls)..."
log "This costs ~\$0.05-0.10 in API usage."

if BOT_MODULE_PATH="$WORK_DIR" "$WORK_DIR/.venv/bin/pytest" "$PROJECT_ROOT/tests/test_live.py" -v -s 2>&1; then
    pass "Live integration tests passed"
else
    fail "Live integration tests FAILED"
    exit 1
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  All tests passed. Skill generates working code.${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════${NC}"
echo ""
echo "  Generated bot.py: $LINES lines"
echo "  Workspace: $WORK_DIR (will be cleaned up)"
