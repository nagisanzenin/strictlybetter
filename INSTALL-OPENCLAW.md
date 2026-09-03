# strictlybetter on OpenClaw

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. This file covers the [OpenClaw](https://docs.openclaw.ai) glue — the self-hosted gateway that puts an agent behind Discord, Telegram, WhatsApp, and friends.

> Partially verified on 2026-09-03 against the **OpenClaw 2026.3.2** installed on the verifying machine, in an isolated `OPENCLAW_STATE_DIR` + `OPENCLAW_CONFIG_PATH`. **That build predates OpenClaw's bundle loader** (its code has no `.codex-plugin` marker and `plugins install` demands `openclaw.extensions` in `package.json`), so the plugin route engram verified on 2026.7.1-2 could not be run here; the standalone hook-pack route could. Itemised in [honest status](#honest-status-of-the-openclaw-glue).

## What ships for OpenClaw

```
.codex-plugin/plugin.json     # what OpenClaw ≥ 2026.7 detects as a "Codex bundle" — skills map, NO hooks key (see maintainers note)
hooks/sb-campaign/            # OpenClaw hook pack: HOOK.md + handler.js — the campaign nudge on /new and /reset
skills/, agents/*.md, scripts/sb.py   # SHARED
```

## Requirements

- Node 22.22.3+, 24.15+, or 25.9+ (OpenClaw refuses versions in between).
- `python3` on the machine running the Gateway.

## Install

### Route A — plugin (OpenClaw ≥ 2026.7, bundle loader)

```bash
openclaw plugins install strictlybetter --marketplace nagisanzenin/researchloop   # reads .claude-plugin/marketplace.json
openclaw config set hooks.internal.enabled true      # NOT optional: without it plugin hooks are listed "ready" and never run
openclaw gateway restart
```

A local clone works too (`openclaw plugins install /path/to/researchloop`). The plugin stages under `${OPENCLAW_STATE_DIR:-~/.openclaw}/extensions/strictlybetter/`.

Then, in the Gateway's environment: `SB_ROOT=<that extensions dir>` (the skills' resolution waterfall has no OpenClaw landmark and OpenClaw sets no plugin-root variable) and `SB_REPO=<the repository you are optimizing>` (a gateway has no project directory; the nudge reads this).

### Route B — clone + hook pack (works on 2026.3.x too)

```bash
git clone https://github.com/nagisanzenin/researchloop ~/researchloop
openclaw hooks install ~/researchloop/hooks/sb-campaign     # copies the pack into $STATE/hooks/sb-campaign/
openclaw config set hooks.internal.enabled true
# Gateway env: SB_ROOT=$HOME/researchloop  SB_REPO=/path/to/the/repo
openclaw gateway restart
```

On this route the skills are not registered (no bundle loader) — drive the loop from a terminal with `sb drive --command`, and use the chat surface for `sb status`-style questions. The copied handler finds the engine through `SB_ROOT` (a copied pack has no engine at `../..`).

## The nudge

`hooks/sb-campaign` binds to **`command:new` and `command:reset`**, the only two internal hook events whose `event.messages` route back to the originating conversation. On `/new` it runs `sb.py --repo $SB_REPO session-start` and pushes the one line — `[strictlybetter] campaign <id> running: …` or `… HALTED: …` — or nothing. Every failure (no python3, no engine, no repository, timeout, frozen `messages`) is silence.

Confirm it actually registered (a `✓ ready` listing is a statement about the manifest, not the runtime):

```bash
openclaw --log-level debug gateway run | grep sb-campaign
# Registered hook: sb-campaign -> command:new, command:reset
```

## What degrades here

| Surface | On OpenClaw |
|---|---|
| guard | **gate-time only** — internal hooks have no tool-boundary deny; `sb submit` refuses experiments that touched frozen/protected paths |
| Stop driver | none — `sb drive --command '<openclaw agent one-shot>'` from a terminal |
| PreCompact | none |
| subagents | no bundle format maps `agents/`; use `sessions_spawn` with its default `context: "isolated"` (a clean child transcript — the judge's blindness by construction), task text pointing at the agent file and the payload path, then `sessions_yield`. `sessions_spawn` sits behind tool policy: `coding`/`full` include it, `messaging`/`minimal` do not — without it there is no blind judge and the skill must stop. Tiers are not pinned |
| state | `<SB_REPO>/.strictlybetter/` on the Gateway host |

## Verify

```bash
python3 <root>/scripts/sb.py selftest         # 61/61
openclaw hooks list                            # 🔬 sb-campaign ✓ ready
openclaw hooks info sb-campaign                # events, python3 satisfied
openclaw plugins doctor                        # (Route A)
```

## A note for maintainers: the manifest trap

`.codex-plugin/plugin.json` deliberately declares **no `hooks` key**. OpenClaw's bundle loader matches `.codex-plugin/plugin.json` first and, for Codex bundles, treats `hooks` as a list of *directories* to scan for hook packs — `"hooks": "./hooks/hooks.json"` would aim the scanner at a file, load nothing, and still list `hooks` as a capability. Absent, Codex auto-discovers `./hooks/hooks.json` and OpenClaw scans `./hooks/`, where `sb-campaign/` lives. Do not add `openclaw.plugin.json` either: inert under today's precedence, load-bearing the day upstream fixes it (omniplugin pitfall #12).

## Honest status of the OpenClaw glue

**Verified on 2026-09-03 (OpenClaw 2026.3.2, isolated state dir and config path):**

- `openclaw hooks install <clone>/hooks/sb-campaign` → `Installed hooks: sb-campaign`; `openclaw hooks list` → `🔬 sb-campaign ✓ ready` (source `openclaw-managed`); `openclaw hooks info sb-campaign` → events `command:new, command:reset`, requirement `python3` satisfied. So the pack format parses on this build.
- `handler.js` driven with fake events under Node: `command:new` with `SB_REPO` at a running pyfix campaign → `messages: ["[strictlybetter] campaign porttest running: 1 experiments, …"]`; a `stop` event, a frozen `messages` array, no repository, and the copied-pack shape without `SB_ROOT` → silence; the copied pack with `SB_ROOT` → delivered.

**Not verified:** the plugin route (`plugins install … --marketplace`) and Codex-bundle detection — this build has no bundle loader and `plugins install <dir>` refuses a repo without `openclaw.extensions`; the hook firing inside a real Gateway (`hooks.internal.enabled` + the `Registered hook:` log line); skills on a chat surface; `sessions_spawn`. The user's live `~/.openclaw/openclaw.json` (which is currently invalid and aborts every CLI command outside an isolated config path) was not modified. Reports from a ≥ 2026.7 Gateway welcome.
