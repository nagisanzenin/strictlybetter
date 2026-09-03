# strictlybetter on Hermes Agent

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. The core is the same everywhere: `skills/` (Agent Skills `SKILL.md`), `agents/*.md`, and the dependency-free `scripts/sb.py`. This file covers the Hermes-specific glue.

> Discovery and the nudge hook were verified against a live **Hermes Agent v0.18.2** install on 2026-09-03, using a scratch `HERMES_HOME` (a copy of the real `config.yaml`; the live profile was not modified). Receipts in [honest status](#honest-status-of-the-hermes-glue).

## What ships for Hermes

```
skills/                            # SHARED — the same eight skills every platform uses
scripts/sb.py                      # SHARED — the same engine
hooks/session-start-hermes.sh      # Hermes pre_llm_call hook: the campaign nudge, once per session
agents/*.md                        # prompt sources for delegate_task (judge, experimenters, orienteer, metrologist, distiller)
```

## Install

**1 · Clone** (don't use `hermes skills install` — see the warning below):

```bash
git clone https://github.com/nagisanzenin/strictlybetter ~/strictlybetter
```

**2 · Register the skills and the engine root** — in `~/.hermes/config.yaml` under `skills:`:

```yaml
skills:
  external_dirs:
    - ~/strictlybetter/skills
```

and tell the skills where their engine lives:

```bash
echo "SB_ROOT=$HOME/strictlybetter" >> ~/.hermes/.env
```

(The skills resolve `scripts/sb.py` through `$SB_ROOT` when no platform plugin-root variable is set — and Hermes sets none. Hermes loads `~/.hermes/.env` at startup and local terminal subprocesses inherit it.)

**3 · Optional — the ambient nudge** (one line when the working directory holds a running or halted campaign; silent otherwise). Add a top-level `hooks:` block:

```yaml
hooks:
  pre_llm_call:
    - command: "/Users/you/strictlybetter/hooks/session-start-hermes.sh"   # absolute path
      timeout: 15
```

Hermes asks for consent on first use (`hermes --accept-hooks` once, or `hooks_auto_accept: true`). Until then `hermes hooks doctor` says *not allowlisted — hook will NOT fire*. The hook dedupes per session, fails closed to once-per-process when it cannot read a session id, and degrades to silence on any failure.

### ⚠ Why not `hermes skills install`?

Hermes' hub installer copies each skill folder plus only the files referenced *inside it* — unreferenced repository files are not copied. strictlybetter's skills share one repo-level engine, `skills/_shared/`, `agents/`, `archetypes/`, and `templates/`, so hub-installed copies would be skills with no engine. The clone + `external_dirs` route keeps the layout intact.

## Invoking the skills

| You want | Type | Why |
|---|---|---|
| the front door | `/strictlybetter <what to improve>` — or "improve this repo's benchmark" | slash command auto-registered from the skill |
| orient / metrics / one cycle / distill / bench | `/orient` `/metrics` `/run` `/distill` `/bench` | same |
| status, stop | **`/skill status`**, **`/skill stop`** | `/stop` is a Hermes built-in (it interrupts the agent) and `/status` matches a built-in string too; Hermes detects a clash, skips auto-registering the same-named external skill, and prints the `/skill <name>` escape hatch. Treat both as colliding until your build proves otherwise. |

Slash-skill expansion happens in the **interactive** CLI/TUI and gateway platforms. Headless `hermes chat -q "…"` passes slash commands through as literal text — say "load and follow the run skill" there instead.

## Subagents on Hermes

Hermes has real subagents: `delegate_task` children start with a completely fresh conversation. When a skill says "spawn `sb-judge`", delegate:

```
delegate_task(
  goal="Act as strictlybetter's blind judge: read ~/strictlybetter/agents/sb-judge.md and follow it exactly.",
  context="Judge the strictlybetter experiment described in <repo>/.strictlybetter/inbox/judge-e0007.json. Return only the verdict JSON."
)
```

Pass the agent file **by path** (never paste its body: two copies drift) and the payload by path (never inline — `skills/_shared/subagents.md`). What changes on Hermes: the trigger is explicit, and the judge's read-only restriction is enforced by its prompt rather than by a `tools:` list. What does not change: fresh context per child, one child per judgment. Experimenter tiers are **not** pinned here — Hermes has no per-delegation effort — so record the tier with `sb cost … --tier` as the skill says and expect all three tiers to run at the configured model's effort.

## Hooks that do not exist here

Hermes offers `pre_llm_call` only. So on Hermes: no PreToolUse guard (the frozen-path check happens at gate time in `sb submit`, which refuses the experiment), no Stop driver (drive the loop from a terminal: `sb drive --command 'hermes chat -q "load and follow the run skill for one strictlybetter cycle"' --cycles 20`), no PreCompact pins (every skill re-anchors from `sb status --json` on invocation).

## Where state lives

`<repo>/.strictlybetter/` on whatever host runs Hermes' terminal backend. On the default `local` backend that is your machine; on remote backends (Docker, SSH, Modal) clone the repo and keep the state on that host.

## Verify the install

```bash
python3 ~/strictlybetter/scripts/sb.py selftest          # 61/61, same engine everywhere
hermes skills list --source local                       # eight rows, no _shared
hermes hooks doctor                                     # script exists, executable, allowlisted
cd <a repo with a running campaign> && hermes hooks test pre_llm_call   # {"context": "[strictlybetter] campaign … running: …"}
```

## Honest status of the Hermes glue

**Verified live on v0.18.2 (2026-09-03, scratch `HERMES_HOME`):**

- `hermes skills list --source local` discovered all eight skills (`bench distill metrics orient run status stop strictlybetter`), `_shared/` correctly ignored.
- `hermes hooks list` / `hermes hooks doctor`: script found, executable, JSON smoke test gated only on consent.
- `hermes hooks test pre_llm_call` from a repository with a running pyfix campaign: first fire → `{"context": "[strictlybetter] campaign porttest running: 0 experiments, 0 accepted, budget left {'experiments': 8}. \`/strictlybetter\` continues it."}` (exit 0, parsed as the Hermes wire shape); second fire, same synthetic session → `{}` (dedupe). A nine-case shell battery also passed: plain mode delivers every run, empty session id → per-process key, garbage payload → `{}`, unwritable `TMPDIR` → `{}`, outside a repository → silence.

**Not verified:** the consent prompt and an interactive session; slash registration of the eight skills and Hermes' actual collision handling for `status`/`stop`; a `delegate_task` judge round-trip with a capable model; gateway surfaces. Reports welcome — open an issue with what you see.
