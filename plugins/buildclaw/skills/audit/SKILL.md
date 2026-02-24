---
name: audit
description: Audit a personal assistant bot.py for security issues — use when the user wants to review or verify the security of their generated assistant
---

Perform a security audit of the personal assistant bot in the current directory.

Read `bot.py` first. Then check every item below and report the result.

---

## Checks

### Secrets
- [ ] No API keys, tokens, or passwords are hardcoded in the source
- [ ] All secrets are loaded from environment variables or `.env` file
- [ ] `.env` is listed in `.gitignore` (check if `.gitignore` exists)

### Path safety
- [ ] `BLOCKED_PATTERNS` set is defined and contains at minimum:
  `.ssh`, `.gnupg`, `.aws`, `.azure`, `.gcloud`, `.kube`, `.docker`,
  `.env`, `credentials`, `.netrc`, `.npmrc`,
  `id_rsa`, `id_ed25519`, `private_key`, `.secret`
- [ ] `is_safe_path()` (or equivalent) is called before every file read
- [ ] `is_safe_path()` is called before every file write
- [ ] File operations are rejected (not just warned) when the path fails the check

### Authorization
- [ ] `ALLOWED_USER_IDS` is read from environment, not hardcoded
- [ ] Every message handler checks user ID before processing
- [ ] Unauthorized users receive NO response (silent drop, not an error message)

### Shell execution
- [ ] Shell commands run inside a scoped directory (not the full filesystem)
- [ ] A timeout is set on all shell executions
- [ ] Shell output is capped before being sent (prevents accidental data exfiltration via large outputs)

### Conversation history
- [ ] History is capped (prevents unbounded memory growth and runaway token costs)
- [ ] History is per-user (one user cannot read another's conversation)

### Dependencies
- [ ] List all `import` statements and their purpose
- [ ] Flag any dependency that seems unnecessary or unusually broad

### Surface area
- [ ] Count total lines of code
- [ ] Note any section that is hard to understand at a glance

---

## Report format

Print the results like this:

```
── Audit Report: bot.py ──────────────────────────────────────
[PASS] No hardcoded secrets
[PASS] BLOCKED_PATTERNS: .ssh, .gnupg, .aws, .azure, .gcloud, .kube, .docker, .env, credentials, .netrc, .npmrc, id_rsa, id_ed25519, private_key, .secret
[PASS] is_safe_path() guards: read_file ✓  write_file ✓  list_dir ✓
[PASS] Unauthorized users: silently dropped
[PASS] Shell scope: ~/assistant-workspace only
[PASS] Shell timeout: 30s
[PASS] Output cap: 4000 chars
[PASS] History cap: 20 messages  (per-user)
[PASS] .gitignore present: .env excluded

── Dependencies ──────────────────────────────────────────────
  os              stdlib — environment variables
  subprocess      stdlib — shell execution
  pathlib.Path    stdlib — filesystem paths
  dotenv          loads .env file
  anthropic       Anthropic API client
  telegram        Telegram bot framework

── Surface area ──────────────────────────────────────────────
  Total lines: <N>
  Sections   : config, security, tools, agent loop, telegram handler, main

── Verdict ───────────────────────────────────────────────────
PASS — no issues found.
──────────────────────────────────────────────────────────────
```

If any check **fails**, describe the exact problem and suggest the fix.
Offer to apply any fixes immediately.
