# strictlybetter on OpenAI Codex

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. The core is the same everywhere — the `skills/` (Agent Skills standard `SKILL.md`), the seven `agents/*.md`, the four `hooks/*.sh`, and the dependency-free `scripts/sb.py` engine are shared verbatim. This file covers the Codex-specific glue. Claude Code users need none of this.

> Codex's plugin, skills, and hooks systems are modeled closely on Claude Code's, so most of this is 1:1. The two genuine differences are called out as **⚠ Codex difference** below. The plugin routes were exercised against **codex-cli 0.149.0-alpha.4.3** (the binary bundled with the ChatGPT desktop app) in a scratch `CODEX_HOME` on 2026-09-03; what was and was not proven is itemised in [honest status](#honest-status-of-the-codex-glue).

## What ships for Codex

```
.codex-plugin/plugin.json          # Codex plugin manifest (mirrors .claude-plugin/plugin.json; maps "skills": "./skills/"; NO hooks key — see the maintainers note)
.agents/plugins/marketplace.json   # Codex marketplace catalog (source: "./")
codex/agents/*.toml                # TOML ports of the 7 agents, bodies verbatim, effort pinned via model_reasoning_effort
scripts/install-codex.sh           # copies the TOML agents into ~/.codex/agents/ and runs the selftest
skills/                            # SHARED — the same eight skills Claude Code uses
scripts/sb.py                      # SHARED — the same engine
hooks/hooks.json + hooks/*.sh      # SHARED — SessionStart, PreToolUse guard, Stop driver, PreCompact pins (self-resolving)
```

## Install

### Route A — as a plugin (skills + hooks)

```bash
codex plugin marketplace add nagisanzenin/researchloop    # or a local clone path
codex plugin add strictlybetter@strictlybetter            # or /plugin install in-session
bash <plugin-cache-or-clone>/scripts/install-codex.sh     # the TOML agents → ~/.codex/agents/
# restart Codex / reload plugins
```

The eight skills become available as `$strictlybetter`, `$orient`, `$metrics`, `$run`, `$status`, `$distill`, `$stop`, `$bench` (Codex invokes skills by `$name` mention or via the `/skills` picker — there is no `/strictlybetter:run` slash form as on Claude Code).

### Route B — skills only (no plugin machinery)

Any Agent Skills installer works, because `skills/*/SKILL.md` is the open standard:

```bash
git clone https://github.com/nagisanzenin/researchloop ~/researchloop
npx skills add nagisanzenin/researchloop          # symlinks the skills into your agent dirs
export SB_ROOT="$HOME/researchloop"               # the skills find the engine through SB_ROOT on this route
bash ~/researchloop/scripts/install-codex.sh
```

On this route no plugin-root variable exists, so `SB_ROOT` is mandatory: the skills' engine-resolution block fails closed ("engine not found — set SB_ROOT") rather than run `python3 ""`. Hooks do not ride Route B; the guard is the gate-time `sb submit` check and the loop is driven with `sb drive --command 'codex exec "…"'`.

## The two Codex differences

### ⚠ 1 · Subagents are TOML, and explicit-invocation only

Claude Code auto-delegates to `agents/*.md` ("MUST BE USED"). Codex subagents are **TOML** and are spawned **only when asked by name**. So when a skill says "spawn `sb-judge`", on Codex you write:

```
$sb-judge, judge the strictlybetter experiment described in <repo>/.strictlybetter/inbox/judge-e0007.json. Return only the verdict JSON.
$sb-experimenter-medium, implement the strictlybetter experiment in <repo>/.strictlybetter/inbox/task-e0007.json
```

What is preserved, and how:

| Invariant | On Claude Code | On Codex |
|---|---|---|
| judge is blind and read-only | `tools: Read`, fresh context | `sandbox_mode = "read-only"`, fresh context, payload by path — the trigger is manual, the blindness is unchanged |
| experimenter tiers pinned by effort | `effort: low\|medium\|high` | `model_reasoning_effort = "low"\|"medium"\|"high"` — **Codex is the only port with per-agent effort pinning** |
| one child per judgment, payloads by file path | `skills/_shared/subagents.md` | identical; the rule is in the prose, not the platform |

The TOML bodies are `developer_instructions` copied verbatim from `agents/*.md` (a generator asserts byte equality; see the note for maintainers). Plugin-distributed TOML agents are not a documented Codex feature, which is why `install-codex.sh` copies them to `~/.codex/agents/` instead of the plugin carrying them.

### ⚠ 2 · Where state lives, and the sandbox

`sb.py` keeps every state file **inside the workspace**: `<repo>/.strictlybetter/` (worktrees under `.strictlybetter/wt/<id>/`). Codex's default `workspace-write` sandbox therefore prompts for nothing the engine does. If you point `SB_HOME` outside the repo, expect approval prompts on every state write.

## Hooks on Codex

`hooks/hooks.json` registers the same four hooks as on Claude Code: SessionStart (the one-line campaign nudge), PreToolUse `Edit|MultiEdit|Write|NotebookEdit` (the frozen-path guard, exit 2 denies), Stop (the campaign driver, `{"decision":"block"}`), PreCompact (the invariant pins). The Codex binary that was inspected carries all four event names, `hooks.json` discovery, `stop_hook_active`, `permissionDecision`, and exports **`CLAUDE_PLUGIN_ROOT`** (plus `PLUGIN_ROOT`) into hook and skill shells — it does *not* set `CODEX_PLUGIN_ROOT`, so the shared resolution waterfall reaches the engine through its second candidate. Every hook also self-resolves from its own location and degrades to silence, so a mismatch costs the feature, never the session.

## Invoking

| You want | Type |
|---|---|
| the front door | `$strictlybetter <what to improve>` |
| one cycle | `$run` |
| status / stop / distill | `$status` · `$stop` · `$distill` |
| a blind verdict | `$sb-judge, judge the strictlybetter experiment described in <payload path>. Return only the verdict JSON.` |
| the loop unattended | `sb drive --command 'codex exec "Load and follow the run skill for one strictlybetter cycle"' --cycles 20` |

## Verify the install

```bash
python3 <root>/scripts/sb.py selftest          # 61/61 checks — the same engine on every platform
codex plugin list                               # strictlybetter@strictlybetter · installed · 1.0.0
ls ~/.codex/agents/sb-*.toml                    # seven files
```

## Honest status of the Codex glue

**Verified on 2026-09-03** (codex-cli 0.149.0-alpha.4.3, scratch `CODEX_HOME`, this repository as a local marketplace):

- `codex plugin marketplace add <clone>` → `Added marketplace 'strictlybetter'`; `codex plugin list` read `.agents/plugins/marketplace.json` and listed `strictlybetter@strictlybetter`.
- `codex plugin add strictlybetter@strictlybetter --json` → `{"version": "1.0.0", "installedPath": "$CODEX_HOME/plugins/cache/strictlybetter/strictlybetter/1.0.0", …}`; the cache holds the **whole repository** (skills, `_shared/`, agents, hooks, scripts, archetypes, templates), so the shared core survives staging.
- `python3 <cache>/scripts/sb.py selftest` → `61/61 checks passed` from the staged copy.
- The seven TOML files parse (`tomllib`) and their `developer_instructions` equal the `agents/*.md` bodies byte for byte.
- Static, from the binary: `hooks` feature `stable`; event names SessionStart/PreToolUse/Stop/PreCompact present; `CLAUDE_PLUGIN_ROOT` exported (0 occurrences of `CODEX_PLUGIN_ROOT`).
- The hook scripts themselves were exercised from the shell against a real pyfix campaign (guard denied a frozen path and an out-of-worktree edit, allowed a worktree edit; Stop printed the block decision; PreCompact printed the pins).

**Not verified:** a live Codex session (the scratch home has no credentials and the user's `~/.codex` was deliberately not touched); whether plugin-bundled `hooks/hooks.json` is loaded and whether exit 2 / `decision: block` are honored end to end; `$name` skill invocation; whether this build reads `~/.codex/agents/*.toml`. Each unverified path degrades to a missing feature, never a broken session, and Route B carries the whole loop. If anything misbehaves, open an issue with what you see.

## A note for maintainers

- **Never add a `hooks` key to `.codex-plugin/plugin.json`.** Codex auto-discovers `./hooks/hooks.json`; OpenClaw, which reads this same manifest as a Codex bundle, treats `hooks` as a list of *directories* to scan for hook packs and would silently load nothing (omniplugin pitfall #13).
- `codex/agents/*.toml` are generated from `agents/*.md`. After editing an agent, regenerate the TOML (the body must stay verbatim) and re-run the byte-equality check before release; the release grep in `RELEASE_PROTOCOL.md` §6 now also covers `.codex-plugin/plugin.json`'s `version`.
