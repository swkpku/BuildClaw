# Setup Guide

## Prerequisites
- Python 3.11+
- An Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- A Telegram account

## 1. Create a Telegram bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you (looks like `123456789:ABCdef...`)

## 2. Get your Telegram user ID

1. Message **@userinfobot** on Telegram
2. It replies with your numeric user ID (e.g. `123456789`)

## 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `TELEGRAM_TOKEN` — the token from BotFather
- `ANTHROPIC_API_KEY` — your Anthropic key
- `ALLOWED_USER_IDS` — your numeric Telegram user ID

## 4. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Run

```bash
python bot.py
```

You should see:
```
Workspace : /Users/yourname/assistant-workspace
Authorized: {123456789}
Model     : claude-sonnet-4-6
Bot running. Press Ctrl+C to stop.
```

Open Telegram, message your bot, and it should respond.

## 6. Keep it running (optional)

To run persistently in the background, use `screen`, `tmux`, or a systemd service:

```bash
# Simple background run
nohup python bot.py > bot.log 2>&1 &

# Or with screen
screen -S assistant
python bot.py
# Ctrl+A, D to detach
```

## Commands

| Command | Action |
|---------|--------|
| Any text | Chat with Claude |
| `/reset` | Clear conversation history |

## What the assistant can access

The assistant is limited to your **workspace directory** (default: `~/assistant-workspace`).

It **cannot** access:
- `.ssh`, `.gnupg`, `.aws`, `.gcloud`, `.kube`, `.docker`
- Any file matching: `credentials`, `.env`, `id_rsa`, `private_key`, `.secret`, `.npmrc`, `.netrc`
- Anything outside the workspace directory

It **can**:
- Read and write files inside the workspace
- Run shell commands inside the workspace (30-second timeout)
- List directories inside the workspace
