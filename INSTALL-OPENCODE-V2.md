# strictlybetter on OpenCode (1.x and the 2.0 beta)

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. The core is the same everywhere: `skills/`, `agents/*.md`, `hooks/*.sh`, and the dependency-free `scripts/sb.py`. This file covers the OpenCode-specific glue — the only port that needed real adapter code, because OpenCode loads npm plugins from a cache its discovery never scans.

> Verified against a live **OpenCode 1.18.23** (the V1 line) on 2026-09-03, plugin route and skills-only route, plus a 17-check adapter suite and the hook adapters driven against a real campaign. **OpenCode 2.0 (`opencode2`) is not installed on the verifying machine**: the V2 adapter follows the contract engram shipped and verified on `opencode2 v0.0.0-next-17444`, and every V2 registration is feature-detected, but it has not been run here. Receipts in [honest status](#honest-status-of-the-opencode-glue).

## What ships for OpenCode

```
package.json                  # npm face of the repo: main/./server → entry.ts, ./v2 → v2.ts (also carries the `pi` key)
.opencode-plugin/entry.ts     # combined { id, server, setup } — V1 calls server(), V2 calls setup()
.opencode-plugin/index.ts     # V1: self-extract + first-run bridge + the four hook adapters
.opencode-plugin/v2.ts        # V2: setup(ctx) — location-wrapped workspace, domain reload, session/shell/tool hooks
.opencode-plugin/install.ts   # self-extract with sha256 ownership: never overwrites a file you edited
.opencode-plugin/agents.ts    # Claude agents → OpenCode subagents (lowercase tools map, mutating tools denied)
hooks/*.ts                    # V1 hook adapters; each runs the sibling hooks/*.sh script
hooks/*.sh, skills/, agents/, scripts/sb.py   # SHARED
__tests__/opencode.test.ts    # `bun test __tests__` — 17 checks, zero dependencies
```

Zero `@opencode-ai/*` imports anywhere: the adapter loads with the SDK absent or reshuffled.

## Install

### Route A — plugin (skills, commands, subagents, hooks)

In any `opencode.json` / `opencode.jsonc` (project or `~/.config/opencode/`):

```jsonc
{
  "plugin":  ["opencode-strictlybetter"],          // V1 (OpenCode 1.x)
  "plugins": ["opencode-strictlybetter"]           // V2 (opencode2) — same package; keep both while you run both
}
```

Until the npm package is published, pin the git source or a local clone instead: `"plugin": ["git+https://github.com/nagisanzenin/strictlybetter.git"]` or `"plugin": ["/absolute/path/to/strictlybetter"]` (V2 local checkouts must point at the entry file: `".../strictlybetter/.opencode-plugin/v2.ts"`). Do **not** write `"opencode-strictlybetter/v2"` — V2 parses that as a GitHub spec.

First start self-extracts `skills/` (with `_shared/`), transformed `agents/`, and generated `commands/` into `.opencode/` (or `~/.config/opencode/` when the project has no opencode config) and, on V1, bridges them into the running config so `/strictlybetter`, `/sb-run` and the subagents work in that same session; V2 reloads its domains instead. Later sessions use disk discovery.

### Route B — skills only (zero adapter code)

```jsonc
{ "skills": { "paths": ["~/strictlybetter/skills"] } }
```

plus `export SB_ROOT=~/strictlybetter` in the shell that starts OpenCode. Eight skills, no commands, no subagents, no hooks — the whole loop still runs (the skills spawn agents through OpenCode's `task` tool only if agents are registered; on this route say so and drive the loop by hand or with `sb drive`).

## What the adapter does

| Concern | Mechanism |
|---|---|
| the engine | **never extracted** — every shell gets `SB_ROOT` (and `OPENCODE_PLUGIN_ROOT`) pointing at the package root, which the skills' resolution waterfall reads; one engine per installed version, no stale copy |
| skills | extracted to `.opencode/skills/` (V1 bridge: `cfg.skills.paths`) |
| commands | generated `commands/strictlybetter.md` + `commands/sb-{orient,metrics,run,status,distill,stop,bench}.md` — prefixed so `run`/`status`/`stop` cannot collide with a host built-in; each loads the skill by name. Regenerated only while they carry the generated marker; your own file with that name is never touched |
| subagents | `agents/*.md` → `mode: subagent`, `hidden: true`, `tools:` translated to OpenCode's lowercase names with **every mutating tool the agent did not list set to false** (`sb-judge` → `read: true, edit/write/bash/patch: false`). `effort:` has no OpenCode equivalent: the three experimenter tiers run at the session model's effort — record the tier with `sb cost … --tier` regardless |
| nudge | V1 `experimental.chat.system.transform` (first call per session) / V2 session `context` hook (once per sessionID) → `hooks/session-start.sh` |
| **guard** | V1 `tool.execute.before`: for `edit`/`write` the adapter builds the Claude-shaped payload and pipes it to `hooks/frozen-guard.sh`; **exit 2 throws**, which blocks the tool call with the engine's reason. V2: registered on `tool` `execute.before` if the beta exposes it (feature-detected, unverified) |
| pins | V1 `experimental.session.compacting` → `hooks/pre-compact.sh` into the compaction context. V2: no verified equivalent (dropped; skills re-anchor from `sb status` anyway) |
| Stop driver | **none** — OpenCode has no Stop hook. Drive unattended runs from a terminal: `sb drive --command 'opencode run "Load and follow the run skill for one strictlybetter cycle"' --cycles 20` |
| updates | `npm update` / re-pin; on a version bump extraction refreshes only files whose on-disk sha256 still equals the one it wrote — edited files are preserved and listed in the OpenCode log (`WARNING — N file(s) preserved`) |

V2 never trusts `process.cwd()`: plugins run in a background service shared across projects, so `setup` reads the workspace from the `{ location, data }` wrapper of `agent.list()` / `command.list()`, and extracts only into a location that owns an opencode config file (or is the global config dir). No location → hooks-only, no disk writes.

## Invoking

| You want | Type |
|---|---|
| the front door | `/strictlybetter <what to improve>` |
| one cycle | `/sb-run` |
| status / stop / distill / orient / metrics / bench | `/sb-status` `/sb-stop` `/sb-distill` `/sb-orient` `/sb-metrics` `/sb-bench` |
| the skills directly | the `skill` tool with `run`, `status`, … (all eight are listed) |

## Verify the install

```bash
python3 <package-root>/scripts/sb.py selftest     # 61/61 — same engine everywhere
opencode debug skill | grep '"name": "\(strictlybetter\|run\)"'
opencode debug agent sb-judge                      # mode: subagent
ls .opencode/commands                              # strictlybetter.md sb-run.md …
bun test __tests__                                 # in a clone: 17 pass
```

## Honest status of the OpenCode glue

**Verified live on OpenCode 1.18.23 (2026-09-03), throwaway project, local-path plugin:**

- `opencode debug config` after the first start: `skills.paths` bridged to `.opencode/skills`; seven `sb-*` agents bridged; eight commands (`strictlybetter`, `sb-*`); `sb-judge` = `{mode: subagent, hidden: true, tools: {read: true, edit: false, write: false, bash: false, patch: false}}`.
- `.opencode/` held `skills/` (incl. `_shared/`), seven transformed agents, eight commands, `.strictlybetter-version.jsonc`; `scripts/` was not extracted.
- `opencode debug skill` listed all eight skills from `.opencode/skills/…/SKILL.md`; `opencode debug agent sb-judge` resolved it as `mode: subagent`.
- Route B (`skills.paths` → the clone): all eight listed from the clone, `_shared` not offered.
- `bun test __tests__`: 17 pass — entry shapes, tool map, agent transform (idempotent, quoted description), extraction + ownership rules on a version bump, V1 bridge once-only, shell env, V2 extraction/reload/hooks/dispose, hooks-only when no location.
- The V1 hook adapters against a real pyfix campaign: `tool.execute.before` threw `strictlybetter guard: denied edit to …/bench.py: frozen path` and allowed a worktree source edit; the nudge landed in `output.system`; the pins landed in `output.context`.
- The host-side surfaces the adapter relies on exist in this binary: `tool.execute.before`, `experimental.session.compacting`, `shell.env`, `experimental.chat.system.transform`, `skills.paths`.

**Not verified:** OpenCode 2.0 (not installed) — `setup()` never ran on a real V2 host, and the V2 guard hook is a guess behind feature detection; a model-driven session on either line (subagent spawning, the `task` tool honoring `hidden`); the npm package (`opencode-strictlybetter` is unclaimed and unpublished — the release protocol's npm step is owed). One platform side effect worth knowing: OpenCode 1.18 installs `@opencode-ai/plugin` scaffolding into `~/.config/opencode/` the first time any plugin loads; that is OpenCode's doing, not the adapter's. If anything misbehaves, open an issue with what you see.
