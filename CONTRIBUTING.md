# Contributing

## What this project is

BuildClaw is open source ideas, not open source code. The contribution unit is a skill file — plain English instructions that Claude Code turns into a running bot. The scope is deliberately narrow: personal AI assistant, modular blocks, every line of generated code readable.

## What good contributions look like

**Skill improvements** — The skill files in `plugins/buildclaw/skills/` are plain markdown prompts. If you find that a generated bot has a security gap, inconsistent behaviour, or missing edge case, the fix is a small edit to the relevant `SKILL.md`. These are the highest-value contributions — you are improving the open source idea.

**New blocks** — A skill that adds a new capability block (a new tool, a new platform channel) following the same pattern: explain the risk, generate the code, audit it. If it's a new channel (Discord, Slack), also add `examples/[platform]/`.

**Bug fixes in the reference implementation** — `examples/telegram/bot.py` should match what the skill generates. If you find a discrepancy, fix it.

## What to avoid

- New dependencies unless essential to the new block
- Configuration systems or env var sprawl
- Features that expand the bot's reach beyond its workspace
- Changes to the security model without a corresponding update to `SECURITY.md`

## How to submit

1. Fork the repo
2. Make your change — keep it small and focused
3. If you changed a skill file: run the skill and paste the output in your PR
4. If you changed `bot.py`: run `pytest examples/telegram/test_security.py -v`
5. Open a PR with a one-sentence description of what changed and why

No CLA required. MIT license applies to all contributions.
