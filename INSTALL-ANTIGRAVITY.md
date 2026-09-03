# strictlybetter on Google Antigravity (agy)

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. This file covers the Antigravity glue, which is three lines: Antigravity discovers everything by directory convention.

> **`agy` is not installed on the verifying machine; nothing here was run against Antigravity.** The manifest matches the shape omniplugin recorded from the official schema on 2026-07-18 (`name` required, `description`, `additionalProperties: false`); the schema URL itself returned 404 on 2026-09-03, so it could not be re-checked. Itemised in [honest status](#honest-status-of-the-antigravity-glue).

## What ships for Antigravity

```
plugin.json                    # {"$schema", "name", "description"} — nothing else, by schema
skills/                        # SHARED — discovered by convention; skills auto-derive slash commands
agents/                        # SHARED — discovered by convention (frontmatter dialect differs; see below)
scripts/sb.py                  # SHARED — ships because agy stages the entire repository
```

No `commands/` (Antigravity has no such concept, and a root `commands/` would leak into Claude Code — omniplugin pitfall #2), no root `hooks.json` (Antigravity's hook schema is its own and was not researched against a live binary; shipping an unverified hook file would be a port by analogy).

## Install

```bash
agy plugin install https://github.com/nagisanzenin/researchloop
export SB_ROOT="$HOME/.gemini/antigravity-cli/plugins/strictlybetter"   # add to your shell rc
```

Antigravity stages the whole repository under `~/.gemini/antigravity-cli/plugins/<name>/` and sets **no plugin-root variable**. The skills' resolution waterfall has no Antigravity landmark either (it checks `ZCODE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, `CODEX_PLUGIN_ROOT`, `SB_ROOT`, the Claude Code cache, the git toplevel), so `SB_ROOT` is an install step, not an option: without it every skill fails closed with "engine not found — set SB_ROOT". Update = reinstall.

## Invoking

`/strictlybetter`, `/orient`, `/metrics`, `/run`, `/status`, `/distill`, `/stop`, `/bench` — skill-derived slash commands, plus intent triggering from the descriptions. Whether any of these names collides with an agy built-in is unknown.

## What degrades here

| Surface | On Antigravity |
|---|---|
| nudge | none — no session-start hook was shipped |
| guard | gate-time only: `sb submit` refuses an experiment that touched a frozen or protected path; there is no pre-edit deny |
| Stop driver | none — `sb drive --command '<agy one-shot command>'` from a terminal |
| PreCompact pins | none — skills re-anchor from `sb status` on every invocation |
| subagents | `agents/` is discovered by convention, but Antigravity's frontmatter keys differ from Claude's (`tools:`/`effort:` may be ignored). If a Claude-format agent cannot be spawned, the skill must stop and say so — there is no mode where the orchestrator judges its own promoted diff. Tiers are not pinned |
| state | `<repo>/.strictlybetter/` |

## Verify

```bash
agy --version
agy plugin validate ~/.gemini/antigravity-cli/plugins/strictlybetter     # a green validator is not a live run
python3 ~/.gemini/antigravity-cli/plugins/strictlybetter/scripts/sb.py selftest   # 61/61
```

## Honest status of the Antigravity glue

**Verified on 2026-09-03:** `plugin.json` is valid JSON with exactly the three keys; the repo ships no root path Antigravity would misread and none that bleeds into another platform (audited in `docs/12-platforms.md`).

**Not verified:** everything else — install, skill-derived commands, whether `_shared/` is skipped, subagent spawnability, and the engine actually being shelled out to. What would close it: `agy --version`, the validate output, a `/strictlybetter` transcript showing `sb --version` printing `sb 1.0.0`, and one `sb-judge` spawn returning the four-key verdict. Open an issue with those and this file gets its receipts.
