# strictlybetter on DeepSeek Harness (dsh)

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. This file covers the [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) glue — the thinnest port class: no adapter code, only stock dsh surfaces (`SKILL.md` bundles discovered from `~/.agents/skills`, the unmodified-Claude-Code hook bridge, and the `subagent` tool).

> **dsh is not installed on the verifying machine; nothing here was run against a live dsh.** The hook files were exercised from the shell against a real campaign and the shape follows engram's dsh port (verified there on `@deepseek-ai/dsh` 0.1.0-rc.6 with bridge 0.0.1-rc.5, 2026-08-16). dsh is a developer preview whose README promises breaking changes. Itemised in [honest status](#honest-status-of-the-dsh-glue).

## What ships for dsh

```
dsh/hooks.json                 # Claude-shaped hook config for the bridge: SessionStart (JSON wrapper), PreToolUse guard, Stop driver
dsh/cordis.patch.yml           # the insert block that enables the bridge per profile
hooks/session-start-dsh.sh     # pins SB_HOOK_FORMAT=json and runs the shared session-start.sh (the bridge discards plain stdout)
hooks/frozen-guard.sh, hooks/stop-driver.sh, skills/, agents/, scripts/sb.py   # SHARED
```

## Install

**1 · Clone into the shared agent home** (`~/.agents` — dsh reads it natively):

```sh
git clone https://github.com/nagisanzenin/strictlybetter ~/.agents/strictlybetter
```

**2 · Link the eight skills into dsh's user skill root** (guarded: `ln -sfn` into an existing real directory silently nests the link one level deep, where dsh does not look — and `run`/`status`/`stop` are generic names in a shared namespace):

```sh
mkdir -p ~/.agents/skills
for s in strictlybetter orient metrics run status distill stop bench; do
  if [ -e ~/.agents/skills/$s ] && [ ! -L ~/.agents/skills/$s ]; then
    echo "strictlybetter: ~/.agents/skills/$s already exists — move it aside first"; continue
  fi
  ln -sfn ~/.agents/strictlybetter/skills/$s ~/.agents/skills/$s
done
```

**3 · Tell the skills where the engine is.** The shared resolution waterfall has no `~/.agents` candidate and dsh sets no plugin-root variable, so export it in the environment that launches dsh:

```sh
export SB_ROOT="$HOME/.agents/strictlybetter"
```

Without it every skill fails closed with "engine not found — set SB_ROOT" (never a silent wrong engine).

**4 · The hooks (optional)** — dsh bridges Claude Code hooks. Three steps per profile you use (`web`, `headless`); order matters:

```sh
# 1 · the bridge + its out-of-closure peer (needs pnpm: `npm i -g pnpm` or corepack)
dsh plugin --profile web add @deepseek-ai/dsh-hooks-claude-code
dsh plugin --profile web add @deepseek-ai/dsh-hook-protocol
# 2 · open $DSH_HOME/profiles/web/cordis.patch.yml and REPLACE the trailing `[]`
#     with the insert block from ~/.agents/strictlybetter/dsh/cordis.patch.yml
#     (absolute paths — ~ is not expanded). Then: 3 · restart the profile.
```

An override-style entry naming an unknown id is skipped with only a warning (looks like success); appending after the template's `[]` is invalid YAML (fails loud). The shipped block uses the insert form. Verify with a hook **event**, not a clean boot: in a repository with a running campaign, the `[strictlybetter] campaign … running` line appears after your first prompt.

## What each surface gives you here

| Surface | On dsh |
|---|---|
| skills | `/strictlybetter`, `/run`, `/status`, … as whitespace-bounded `/name` tokens; the `/` menu lists user-invocable skills. (Frontmatter uses `name` + `description`, which dsh requires; `argument-hint` is ignored.) |
| nudge | SessionStart through the bridge, JSON `additionalContext` — the only shape the bridge reads (verified from the shell: the wrapper emits it) |
| guard | `dsh/hooks.json` registers PreToolUse `Edit\|MultiEdit\|Write\|NotebookEdit` → `frozen-guard.sh` (exit 2 = deny). **Unverified on dsh**: whether the bridge honors exit 2, and whether dsh's edit tools match that matcher. If not, the guard is the gate-time `sb submit` integrity check, as on every host without a pre-edit deny |
| Stop driver | `dsh/hooks.json` registers Stop → `stop-driver.sh` (`{"decision":"block"}`). **Unverified**; the terminal fallback is `sb drive --command 'npx @deepseek-ai/dsh --profile headless "load and follow the run skill for one strictlybetter cycle"'` |
| PreCompact | not offered by the bridge; skills re-anchor from `sb status` on every invocation |
| subagents | dsh registers **`subagent`** (fresh context — the only one you may use) and **`subagent_fork`** (seeds the child with this conversation — **never** for `sb-judge`: a judge that saw the experimenter's reasoning judges the argument, not the diff). Neither knows the agent files: instruct the child to `Read ~/.agents/strictlybetter/agents/sb-judge.md and follow it exactly`, pass the payload by path. Tiers are not pinned |
| state | `<repo>/.strictlybetter/`, inside the workspace — no `workspace-write` prompt for state; the worktrees live there too |

## Model / auth

dsh needs `DEEPSEEK_API_KEY` in the launching environment or in the Web UI settings; there are no bundled free models.

## Verify the install

```sh
python3 ~/.agents/strictlybetter/scripts/sb.py selftest     # 61/61
ls -l ~/.agents/skills | grep strictlybetter                # eight symlinks
cd <repo with a running campaign> && CLAUDE_PLUGIN_ROOT=~/.agents/strictlybetter ~/.agents/strictlybetter/hooks/session-start-dsh.sh
# → {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[strictlybetter] campaign … running: …"}}
```

## Honest status of the dsh glue

**Verified on 2026-09-03, from the shell only:** `dsh/hooks.json` is valid JSON; `session-start-dsh.sh` in a repository with a running pyfix campaign printed the `hookSpecificOutput.additionalContext` JSON the bridge reads (and nothing outside a repository); `frozen-guard.sh` denied a frozen path and an out-of-worktree edit with exit 2 and allowed a worktree edit; `stop-driver.sh` printed `{"decision": "block", …}` for a Claude-shaped payload and stayed silent without a session id.

**Not verified:** everything on dsh itself — skill discovery through the symlinks, the bridge loading `dsh/hooks.json`, SessionStart delivery into the session inbox, PreToolUse/Stop semantics through the bridge, the `subagent` spawn route, sandbox behavior. Each gap degrades to a missing surface, never a broken session. If you run dsh before we do, an issue report — good or bad — closes it for everyone.
