# strictlybetter on Pi

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. The core is the same everywhere: `skills/` (Agent Skills `SKILL.md`), `agents/*.md`, and the dependency-free `scripts/sb.py`. This file covers the [Pi](https://pi.dev)-specific glue.

> **Pi is not installed on the verifying machine, so nothing here was run against a live pi.** The extension was exercised through a fake host (14 checks in `__tests__/pi.test.ts`) and, with real subprocess execution, against a real campaign; the prompt templates passed a strict-YAML frontmatter check. The shape follows engram's pi port, verified there on pi 0.83.0 and 0.74.2. Itemised in [honest status](#honest-status-of-the-pi-glue).

## What ships for Pi

```
package.json → "pi": { extensions, skills, prompts }   # the manifest key pi reads; everything else in the repo is ignored
pi/strictlybetter.ts          # extension: exports SB_ROOT + the campaign nudge + the frozen-path guard (tool_call)
pi/prompts/*.md               # /strictlybetter, /sb-orient, /sb-metrics, /sb-run, /sb-status, /sb-distill, /sb-stop, /sb-bench
skills/, agents/, scripts/sb.py   # SHARED
```

## Requirements

- pi ≥ 0.74 (the extension uses `before_agent_start`'s injected-message return and the `tool_call` block return).
- Node ≥ 22.19 for current pi; on Node 20 npm serves pi's `legacy-node20` line.
- `python3` on PATH.

## Install

```bash
pi install git:github.com/nagisanzenin/researchloop
```

Pi clones the repo to `~/.pi/agent/git/github.com/nagisanzenin/researchloop`, runs `npm install` there (the package has **zero dependencies**, so nothing is installed), and registers the package. `pi update` tracks the default branch. A local clone works too: `pi install /path/to/researchloop`.

## Invoking

| You want | Type |
|---|---|
| the front door | `/strictlybetter <what to improve>` — or just say "improve this repo's benchmark" |
| one cycle | `/sb-run` |
| status / stop / distill / orient / metrics / bench | `/sb-status` `/sb-stop` `/sb-distill` `/sb-orient` `/sb-metrics` `/sb-bench` |
| a skill explicitly | `/skill:run`, `/skill:status`, … |

The prompt templates carry the `sb-` prefix so generic names (`run`, `status`, `stop`) cannot shadow a pi built-in (omniplugin R5); the skills themselves keep their names and are listed in the system prompt as Agent Skills.

## What the extension does

- **`SB_ROOT`** — exported into pi's process env at load; pi's bash tool spawns children from `process.env`, so the skills' engine-resolution block finds the engine from any shell. An existing `SB_ROOT` in your shell wins (a dev override).
- **The nudge** — on session start (launch, `/new`, `/resume`, `/reload`) it runs `sb.py --repo <cwd> session-start` fire-and-forget (pi awaits `session_start` handlers, so nothing here blocks startup). If a campaign is running or halted in the cwd: one TUI notice and one injected message on your first prompt. Otherwise total silence. Inert in `-p` / `--mode json` and in children (`SB_CHILD=1`).
- **The guard** — on every `edit` / `write` tool call, if `<cwd>/.strictlybetter/campaign.json` (or `$SB_HOME/campaign.json`) exists, it runs `sb.py guard <path>`; exit 2 returns `{ block: true, reason }` and pi refuses the edit with the engine's reason. No campaign → python never starts. Any failure → allow (the fail-open shape of this hook class; `sb submit` re-checks integrity at gate time). The guard stays **on** in children: an experimenter child must be denied the instrument exactly like the parent.
- **No Stop driver** — pi has no Stop event; drive unattended runs with `sb drive --command 'pi -p "/sb-run"' --cycles 20` (templates expand in print mode).

## Subagents on Pi

Pi ships no subagent tool by design, but a fresh process is a fresh context. The skills' "spawn `sb-judge`" becomes a non-interactive pi run through the bash tool:

```bash
SB_CHILD=1 pi --no-session --no-skills --no-context-files -p \
  "Read $SB_ROOT/agents/sb-judge.md and follow it exactly as your operating instructions.
   Judge the strictlybetter experiment described in <repo>/.strictlybetter/inbox/judge-e0007.json.
   Write the four-key verdict JSON to <repo>/.strictlybetter/inbox/verdict-e0007.json with the write tool — nothing else."
```

`SB_CHILD=1` keeps the nudge out of the child; `--no-context-files` keeps the project's AGENTS.md out; leave extensions on (model providers arrive as extensions, and the guard must run in experimenter children). Collect results **from the file**, never stdout. Experimenter tiers are not pinned (pi has no per-run effort) — pass `--model` if you want a different model per tier, and record the tier with `sb cost … --tier`.

## Verify the install

```bash
python3 ~/.pi/agent/git/github.com/nagisanzenin/researchloop/scripts/sb.py selftest   # 61/61
pi config                    # strictlybetter listed with skills/extension/prompts enabled
pi                           # type /  — strictlybetter, sb-run, … in the picker
```

## Honest status of the Pi glue

**Verified on 2026-09-03 without pi** (bun 1.3.9 as the TypeScript runtime):

- `__tests__/pi.test.ts` (fake host): `SB_ROOT` exported and an existing value respected; the nudge probe runs `python3 sb.py --repo <cwd> session-start`, injects once as a `strictlybetter-nudge` message and never twice; inert without a UI, with `SB_CHILD`, and on a killed probe; the guard's fast path (no campaign → no exec), deny on exit 2 with the engine's reason, allow on exit 0 and on an exec that throws.
- The same extension with **real** `execFile` against a pyfix campaign: `tool_call edit …/wt/e0001/bench.py` → `{"block":true,"reason":"strictlybetter guard: denied edit to …/bench.py: frozen path (bench.py): the instrument cannot be edited during a campaign"}`; a worktree source edit → allowed; `session_start` → notify + the injected nudge with the live campaign line.
- All eight `pi/prompts/*.md` frontmatter values are double-quoted and parse as strict YAML (omniplugin pitfall #18).

**Not verified:** anything on a live pi — package discovery from `package.json`'s `pi` key, template expansion, the `tool_call` event name and its `{ block, reason }` return shape (taken from pi's documented extension API, not from a version-exact `.d.ts`; if the event does not exist the registration is a harmless no-op), the child-spawn transport, `pi update`. If you run pi, `pi install /path/to/researchloop` and an issue with what you see closes this gap for everyone.
