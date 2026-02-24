# BuildClaw

**Open source ideas for your personal AI assistant. You generate the code. No trust required.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/swkpku/buildclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/swkpku/buildclaw/actions/workflows/ci.yml)

---

## A different kind of open source

When AI can generate code from ideas, open source doesn't need to mean open source *code*.

It can mean open source *ideas*.

BuildClaw is a set of Claude Code skills — plain English instructions that tell Claude how to build a personal AI assistant. The skills are short, human-readable, and forkable. When you run one, your trusted tool writes the implementation in your terminal, line by line, in front of you.

**You never download code written by strangers. You generate code from ideas written by strangers, using a tool you already trust. The distinction matters.**

There is no malicious code risk. Code written by strangers doesn't exist here — only ideas do. The code that runs on your machine was created by Claude Code, in your terminal, for you specifically, the moment you ran the skill. You watched every line appear.

This is what open source looks like in the age of coding agents.

---

## The architecture

A personal AI agent has four layers. BuildClaw makes each one explicit — you choose which blocks to include before any code is written.

```
┌─────────────────────────────────────────────────────────┐
│  Channel      how messages reach your agent             │
│               → Telegram (included)                     │
├─────────────────────────────────────────────────────────┤
│  Agent loop   the Claude reasoning engine               │
│               → included, non-negotiable                │
├─────────────────────────────────────────────────────────┤
│  Tools        what your agent can do                    │
│               → you choose: files, shell, memory,       │
│                 web search, scheduled tasks             │
├─────────────────────────────────────────────────────────┤
│  Security     what it can never touch                   │
│               → hardcoded, non-negotiable               │
│               .ssh .aws .gnupg credentials id_rsa ...   │
└─────────────────────────────────────────────────────────┘
```

You pick the tools layer. Everything else is fixed. That is the whole design.

---

## What it looks like

```
$ /build

  What tools should your assistant have?
  [1] none — chat only
  [2] files — read and write files in your workspace
  [3] shell — run commands in your workspace
  [4] memory — remember facts between conversations
  [5] web — search the web
  [6] scheduler — run tasks on a schedule
  > 2, 4, 5

  What directory should it use?
  > ~/assistant-workspace

  Writing bot.py...

  BLOCKED_PATTERNS = {
      ".ssh", ".gnupg", ".aws", ".azure", ".gcloud", ".kube", ".docker",
      ".env", "credentials", ".netrc", ".npmrc",
      "id_rsa", "id_ed25519", "id_ecdsa", "private_key", ".secret",
  }

  def is_safe_path(path: str) -> bool:
      """True only if path resolves inside WORKSPACE and no blocked pattern matches."""
      ...

  def tool_read_file(path: str) -> str: ...
  def tool_write_file(path: str, content: str) -> str: ...
  def tool_remember(key: str, value: str) -> str: ...
  def tool_recall(key: str = "") -> str: ...
  def tool_web_search(query: str) -> str: ...

  [~280 lines total, written here in your terminal]

  ── Security Audit ────────────────────────────────────
  [PASS] No hardcoded secrets
  [PASS] BLOCKED_PATTERNS: .ssh .gnupg .aws .azure .gcloud ...
  [PASS] is_safe_path() guards all filesystem tools
  [PASS] Unauthorized users: silently ignored
  [PASS] History trimmed to 20 messages
  [INFO] Total lines: 284 | Dependencies: 4
  ──────────────────────────────────────────────────────

  Done. bot.py is in this directory.
  You read every line above. Ask me to explain anything.

  Next step: cp .env.example .env
```

---

## Install

```bash
# Via Claude Code plugin system
/plugin marketplace add github.com/swkpku/buildclaw
/plugin install buildclaw@buildclaw

# Or manually
git clone https://github.com/swkpku/buildclaw
cp -r buildclaw/skills/build ~/.claude/skills/build
cp -r buildclaw/skills/audit ~/.claude/skills/audit
cp -r buildclaw/skills/test ~/.claude/skills/test
```

Then:

```bash
mkdir my-assistant && cd my-assistant
claude
/build
```

---

## Skills

| Command | What it does |
|---------|--------------|
| `/build` | The Lego manual — detects current state, shows the full architecture, lets you choose what to build |
| `/audit` | Audits any `bot.py` against 15 security checks |
| `/test` | Generates and runs a pytest suite that proves your security invariants hold |

**The workflow:**

```
/build           first run: choose your blocks, get a working bot
/build           any time after: see what's built, add a new block
/audit           verify the security layer any time
/test            run 41 automated security tests
```

---

## Available blocks

| Block | Risk | What it adds |
|-------|------|--------------|
| `chat` | none | Claude conversation — always included |
| `files` | low | Read and write files inside your workspace |
| `shell` | medium | Run commands inside your workspace (30s timeout) |
| `memory` | low | Persist facts across restarts in `workspace/memory.json` |
| `web` | low-medium | Search the web via DuckDuckGo (no API key needed) |
| `scheduler` | medium | Run tasks autonomously on a schedule |
| `mcp` | variable | Connect to any MCP server (via `/build` only) |

**Hard-blocked in every generated bot** — no path containing these strings
can ever be read, written, or listed, regardless of where it resolves:

```
.ssh  .gnupg  .aws  .azure  .gcloud  .kube  .docker
.env  credentials  .netrc  .npmrc
id_rsa  id_ed25519  private_key  .secret
```

---

## Why not OpenClaw, NanoClaw, or IronClaw?

[OpenClaw](https://github.com/openclaw/openclaw) has 219,000 GitHub stars and 430,000 lines of code running on your machine with your API keys and shell access. It had a real infostealer campaign targeting its config files. Andrej Karpathy:

> *"I'm definitely a bit sus'd to run OpenClaw... giving private data and keys to 400,000 lines of code being actively attacked at scale is not appealing."*

[NanoClaw](https://github.com/qwibitai/nanoclaw) and [IronClaw](https://github.com/nearai/ironclaw) are genuinely better — smaller, with real sandboxing. But they are still code you download and run. Someone else wrote it.

BuildClaw is not an alternative implementation. It is a different answer to the question. Instead of "here is safer code to run," it offers: **here are the ideas — go generate your own code.** The skills are the open source contribution. The code is yours from the moment it exists.

---

## Reference implementation

`examples/telegram/bot.py` is 266 lines. It is what your generated bot looks like.
`examples/telegram/test_security.py` is 41 security tests, all passing. Read both before running anything.

---

## Contributing

The skills are plain English markdown files — read them before you contribute. Improving a skill prompt *is* improving the open source idea. That is the primary contribution path.

The most valuable contribution: a skill that adds a new block (new tool, new platform) following the same pattern — explicit risk explanation, security audit step, tests.

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).
