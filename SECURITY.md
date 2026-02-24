# Security model

This document explains exactly what BuildClaw-generated bots do and do not protect against.

---

## What is protected

### 1. Credential exposure

Every generated bot reads secrets from a `.env` file loaded at startup. No
token, API key, or password appears in the source code. The `.env` file is
excluded from git by default.

### 2. Filesystem access

All file operations are guarded by `is_safe_path()`, which enforces two rules:

**Rule 1 — workspace boundary.**
The resolved path must be inside `WORKSPACE` (default: `~/assistant-workspace`).
A symlink that escapes the workspace is caught by `Path.resolve()`.

**Rule 2 — blocked patterns.**
The path must not contain any of these strings in any component:
```
.ssh        .gnupg      .aws        .azure      .gcloud
.kube       .docker     .env        credentials .netrc
.npmrc      id_rsa      id_ed25519  id_ecdsa    private_key
.secret
```
This is defense-in-depth: even if the workspace boundary is somehow bypassed,
credential files are still blocked by name.

### 3. Shell execution

Shell commands run with `cwd=WORKSPACE`. They cannot escape by `cd /` because
`cwd` is set at the subprocess level, not inside the shell. A 30-second timeout
prevents infinite loops. Output is capped at 4000 characters to prevent
accidental bulk data exfiltration via large command output.

### 4. Unauthorized access

Telegram message handlers check `user_id in ALLOWED_USER_IDS` as the first
operation. Unauthorized users receive no response, no error, and no log entry.
There is nothing to probe.

### 5. Conversation history

History is capped at 20 messages per user. This prevents unbounded memory
growth and limits the blast radius of a prompt injection attack (older messages
are eventually pruned).

---

## What is not protected

### The model backend

Your conversation content and any files you share are sent to Anthropic's API.
This is unavoidable if you are using Claude. If your threat model requires
zero data leaving your machine, use a local model (Ollama, LM Studio) instead.

### The generated code itself

The skill generates code; it does not verify it. Run `/audit` after
generation and read the output. If anything looks wrong, ask Claude to fix it
before running the bot.

### Prompt injection

If the assistant reads a file that contains adversarial instructions, those
instructions will be sent to Claude as part of the conversation. The workspace
boundary limits what a prompt injection attack can reach, but it cannot prevent
Claude from being manipulated by content inside the workspace. Don't put files
from untrusted sources in your workspace.

### Network access

The bot has no network allowlist. Shell commands inside the workspace can make
outbound network calls. If you want to restrict this, run the bot inside a
container with network policies, or add network filtering to the shell tool.

### Physical access

If someone has access to the machine running the bot, they can read the `.env`
file. Protect the machine.

---

## Reporting a vulnerability

- **Non-sensitive issues** (e.g. a missing blocked pattern): open a GitHub issue
- **Sensitive issues** (e.g. a bypass of `is_safe_path`): use [GitHub's private vulnerability reporting](https://github.com/swkpku/buildclaw/security/advisories/new)

Please include: what the issue is, which file it affects, and a minimal reproduction if possible.
