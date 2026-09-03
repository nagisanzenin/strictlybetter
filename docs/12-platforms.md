# 12 · Platforms: the port ladder and what each surface degrades to

strictlybetter is one repository that installs on nine agentic platforms. The core is shared
verbatim: `skills/` (Agent Skills `SKILL.md`), `agents/*.md`, the four `hooks/*.sh`, and
`scripts/sb.py`. Each platform reads only its own glue; the core never knows the glue exists
(omniplugin R1–R10). This page is the honest map: which surface each platform gets, what
degrades where, and what was actually verified. The per-platform receipts live in
`INSTALL-<PLATFORM>.md`; the release-time table is `RELEASE_PROTOCOL.md` §7.6.

## The ladder for this plugin

- **L0 — skills + engine, manual.** Clone, point the platform at `skills/`, export `SB_ROOT`.
  The whole loop runs: orient, instrument, gate 1, cycles, gate 2. The guard is the gate-time
  integrity check in `sb submit`; the loop is driven by `sb drive --command`. Must always work.
- **L1 — commands registered.** `/strictlybetter` and the seven sub-skills surface natively.
- **L2 — ambient.** A session-start hook prints the one-line campaign nudge; a PreCompact hook
  re-pins the invariants where the host has one.
- **L3 — the walls at the tool boundary.** A pre-edit hook denies frozen paths, protected paths,
  harness state, and out-of-worktree edits *before* they happen (`sb guard`, exit 2); subagents
  run as fresh-context children (experimenters, the blind judge, the distiller).
- **L4 — the loop drives itself.** A Stop hook re-invokes one cycle while the campaign is
  running, under budget, below the iteration cap.

## Surfaces per platform

| Platform | Skills | Subagents (fresh context) | Effort tiers | Nudge | Guard | PreCompact | Stop driver | Engine root |
|---|---|---|---|---|---|---|---|---|
| Claude Code | native, `/strictlybetter:run` | `agents/*.md`, auto-delegated | pinned (`effort:`) | SessionStart | PreToolUse exit 2 | yes | Stop hook | `CLAUDE_PLUGIN_ROOT` |
| Codex | manifest, `$run` | `codex/agents/*.toml`, **explicit `$sb-judge, …`** | **pinned** (`model_reasoning_effort`) | shared hooks.json | shared hooks.json | shared hooks.json | shared hooks.json | `CLAUDE_PLUGIN_ROOT` (Codex exports the legacy name) |
| OpenCode | extracted + `/sb-run` | extracted, `mode: subagent`, mutating tools denied | not pinned | V1 system.transform / V2 session context | V1 `tool.execute.before` throw / V2 feature-detected | V1 compacting hook / V2 none | **none → `sb drive`** | `SB_ROOT` from `shell.env` |
| Hermes | `external_dirs`, `/run`; `/skill status`, `/skill stop` (collisions) | `delegate_task`, agent file by path | not pinned | `pre_llm_call` JSON, deduped | **gate-time only** | none | **none → `sb drive`** | `SB_ROOT` in `~/.hermes/.env` |
| Antigravity | convention, `/run` | `agents/` convention, dialect unverified | not pinned | none | **gate-time only** | none | **none → `sb drive`** | `SB_ROOT` exported by the user |
| OpenClaw | Codex bundle (≥ 2026.7), `/run` | `sessions_spawn` isolated, agent file by path | not pinned | hook pack on `/new`, `/reset` | **gate-time only** | none | **none → `sb drive`** | `SB_ROOT` in the Gateway env |
| Pi | `pi` manifest key, `/sb-run` + `/skill:run` | fresh `SB_CHILD=1 pi -p` process | not pinned (`--model` per tier) | extension `session_start` + `before_agent_start` | extension `tool_call` `{block}` | none | **none → `sb drive`** | `SB_ROOT` exported by the extension |
| DeepSeek Harness | symlinks in `~/.agents/skills`, `/run` | `subagent` (never `subagent_fork`) | not pinned | bridge SessionStart, JSON wrapper | bridge PreToolUse (unverified) | none | bridge Stop (unverified) | `SB_ROOT` exported by the user |
| ZCode | convention + marketplace, `/run` or `/strictlybetter:run` | generic Agent child, agent file by path | not pinned | shared hooks.json, JSON shape by format switch | shared hooks.json, exit 2 | not an event on 3.9 (`compact` matcher instead) | shared hooks.json, `decision: block` | `ZCODE_PLUGIN_ROOT` |

## What degrades, and to what

- **No pre-edit hook (Hermes, Antigravity, OpenClaw; OpenCode V2 until verified):** an experimenter
  that edits a frozen path is caught at `sb submit` (integrity check → `discard: integrity`, two in a row
  halt the campaign). The wall moves from the tool boundary to the gate; it does not disappear.
- **No Stop hook (everything but Claude Code, Codex, ZCode, and the dsh bridge):** the loop does not
  re-invoke itself. `sb drive --command '<one-shot agent command>' --cycles N` runs the platform's own
  binary once per cycle from a terminal and stops on halt, STOP, budget, or end.
- **No effort pinning (everything but Claude Code and Codex):** the three experimenter agents are
  byte-identical apart from `effort:`, so they collapse to one; `sb cost … --tier` still records the
  operator's tier so the bandit's cost model stays comparable across platforms.
- **No registered agents (Hermes, OpenClaw, Pi, dsh, ZCode):** the child is constructed — a fresh
  context that is told to read `agents/<role>.md` and receives payloads **by path**. Fork/inherit
  modes are forbidden for the judge; if the platform's spawn mechanism is unavailable, the skill
  stops and says so. There is no mode where the orchestrator judges its own promoted diff.
- **No nudge (Antigravity):** the skills re-anchor from `sb status --json` on every invocation.
- **Engine root:** the shared waterfall is `ZCODE_PLUGIN_ROOT → CLAUDE_PLUGIN_ROOT →
  CODEX_PLUGIN_ROOT → SB_ROOT → Claude Code cache → git toplevel`, failing closed. Six platforms reach
  it through `SB_ROOT`, set by the adapter (OpenCode, Pi) or by the install steps (Hermes, Antigravity,
  OpenClaw, dsh). Static install paths were deliberately not added to the shared skills in this
  release (that edit needs the cross-platform blind read `CLAUDE.md` demands).
- **State** is always `<repo>/.strictlybetter/`, inside the workspace: no sandbox prompts on Codex or
  dsh, and one ledger whichever platform ran the cycle.

## Verification on 2026-09-03 (the honest table)

"Verified live" would mean a real session ran a full cycle on a fixture from the release tree and the
guard denied a frozen edit there. **No platform has that yet, Claude Code included.** What exists:

| Platform | Verified | Not verified |
|---|---|---|
| Claude Code | hook scripts from the shell against a pyfix campaign (nudge, JSON switch, guard deny/allow, Stop block, pins); selftest 61/61 | a release-tree cycle in a live session |
| Codex | codex-cli 0.149.0-alpha.4.3 (ChatGPT-bundled), scratch `CODEX_HOME`: marketplace add, plugin list, plugin add → 1.0.0, whole-repo cache, selftest from the cache; TOML bodies byte-equal; binary carries the four hook events and exports `CLAUDE_PLUGIN_ROOT` | a live session, hooks firing, `$name` invocation |
| OpenCode | 1.18.23 live: plugin route (8 skills, 7 agents, 8 commands bridged; `sb-judge` read-only) and `skills.paths` route (8 skills); 17 adapter checks; guard/nudge/pins through the adapter against a campaign | OpenCode 2.0 (not installed); a model session; npm publish |
| Hermes | v0.18.2 live, scratch `HERMES_HOME`: 8 skills discovered; `hermes hooks test pre_llm_call` → `{"context": …}` then `{}`; 9-case failure battery | consent flow, a session, slash collision handling, `delegate_task` |
| Pi | 14 fake-host checks; real-exec harness against a campaign (guard deny/allow, nudge inject, `SB_ROOT`); strict-YAML prompts | anything on a live pi (not installed) |
| Antigravity | manifest = the three schema keys; namespace audit | everything else (`agy` not installed; schema URL 404 today) |
| OpenClaw | 2026.3.2 isolated: `hooks install` → `sb-campaign ✓ ready`, events, python3; handler under Node delivers/silences correctly | plugin route (build predates the bundle loader), Gateway firing, chat surfaces |
| DeepSeek Harness | hook files from the shell (JSON wrapper, guard, Stop) | everything on dsh (not installed) |
| ZCode | static: manifest fallthrough, `hooks/hooks.json`, events, root vars, exit-2 and `decision: block` branches, `compact` matcher; execution matrix incl. the config-line tokenization in `sh` and `zsh` | GUI install, a session, hooks through the runner |

## Namespace-bleed audit of every root path added for the ports

`.codex-plugin/` (Codex; OpenClaw ≥ 2026.7 reads it as a bundle — intended; no `hooks` key),
`.agents/plugins/` (Codex; dsh/ZCode scan `.agents/skills` only), `codex/`, `.zcode-plugin/`, root
`plugin.json` (Antigravity only — Claude Code, ZCode, Codex, OpenClaw all look elsewhere),
`package.json` (OpenCode entry + `pi` key; zero dependencies so pi's `npm install` is a no-op;
OpenClaw 2026.3 refuses it as a native plugin, correctly), `tsconfig.json`, `.opencode-plugin/`,
`pi/`, `dsh/`, `__tests__/`, `hooks/*.ts`, `hooks/session-start-{hermes,dsh}.sh`,
`hooks/sb-campaign/` (only OpenClaw scans `hooks/*/HOOK.md`), `scripts/install-codex.sh`,
`INSTALL-*.md`. No root `commands/`, no root `hooks.json`, no `openclaw.plugin.json`.

## Open follow-ups

1. Add static fallbacks LAST in the shared waterfall (`~/.agents/strictlybetter`, the OpenClaw
   extensions dir, the pi git dir) — a shared-skill edit with the three-question blind read.
2. Grow `skills/_shared/subagents.md` into capability-branched spawn shapes (engram's pattern).
3. Publish `opencode-strictlybetter` on npm (§6.5-style release step) and claim the name.
4. Turn each "Not verified" cell green with a requester on that platform, one at a time.
