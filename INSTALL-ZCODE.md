# strictlybetter on ZCode

strictlybetter is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw, Pi, DeepSeek Harness, and ZCode. [ZCode](https://z.ai)'s extension model is Claude Code-compatible by construction — manifest fallthrough `.zcode-plugin/plugin.json` → `.claude-plugin/plugin.json` → `.codex-plugin/plugin.json`, the shared `hooks/hooks.json`, `SKILL.md` skills, `AGENTS.md` — so the port is one manifest, the format switch that already lives inside the shared hook scripts, and documentation. No adapter code.

> Verified **statically** against the ZCode 3.9-line runtime bundle installed on the verifying machine (desktop app, `zcode.cjs` dated 2026-08-28), plus an execution matrix of the shared hooks on 2026-09-03. ZCode ships no CLI here and the marketplace install is a GUI action, so **no live session and no plugin install were run**; the user's live `~/.zcode/cli/config.json` was not touched. Itemised in [honest status](#honest-status-of-the-zcode-glue).

## What ships for ZCode

```
.zcode-plugin/plugin.json      # the priority manifest (identity only; components discover by convention)
hooks/hooks.json + hooks/*.sh  # SHARED — session-start.sh switches to the JSON shape when ZCODE_PLUGIN_ROOT is set
skills/, agents/, scripts/sb.py   # SHARED
```

## Install

### Route A · plugin marketplace (recommended)

ZCode reads this repository as a marketplace (it consumes `.claude-plugin/marketplace.json`):

1. **Settings → Plugin Management → Discover**, press **`+`**, add `https://github.com/nagisanzenin/researchloop`.
2. Select **strictlybetter**, click **Install**.
3. Restart ZCode (or start a new session) so skills re-scan.

You get, with zero config: the eight skills as `/strictlybetter`, `/run`, `/status`, … (namespaced `/strictlybetter:run` on builds that namespace plugin skills — both resolve to the same skill); the four hooks from the shared `hooks/hooks.json` (plugin-contributed hooks enable the runner automatically); the engine resolved through `$ZCODE_PLUGIN_ROOT`, first in the skills' waterfall.

### Route B · clone + symlink

```sh
git clone https://github.com/nagisanzenin/researchloop ~/.agents/strictlybetter
SKILLS="$HOME/.agents/skills"        # or ~/.zcode/skills for a ZCode-only install
mkdir -p "$SKILLS"
for s in strictlybetter orient metrics run status distill stop bench; do
  if [ -e "$SKILLS/$s" ] && [ ! -L "$SKILLS/$s" ]; then echo "strictlybetter: $SKILLS/$s exists — move it aside"; continue; fi
  ln -sfn ~/.agents/strictlybetter/skills/$s "$SKILLS/$s"
done
export SB_ROOT="$HOME/.agents/strictlybetter"     # no plugin-root variable on this route; the waterfall reads SB_ROOT
```

The nudge on Route B is wired through `~/.zcode/cli/config.json`, where the flag is mandatory and there is no plugin context — so the format is forced:

```json
{
  "hooks": {
    "enabled": true,
    "events": {
      "SessionStart": [
        { "matcher": "startup|resume|clear|compact",
          "hooks": [ { "type": "command", "command": "SB_HOOK_FORMAT=json \"/Users/you/.agents/strictlybetter/hooks/session-start.sh\"" } ] }
      ],
      "PreToolUse": [
        { "matcher": "Edit|MultiEdit|Write|NotebookEdit",
          "hooks": [ { "type": "command", "command": "\"/Users/you/.agents/strictlybetter/hooks/frozen-guard.sh\"", "timeout": 5 } ] }
      ]
    }
  }
}
```

Absolute paths (the hook environment does not expand `~`). The env assignment sits **outside** the quoted path token — that exact line was executed under `sh -c` and `zsh -c` and produced the JSON shape (the fused-token form `"\"SB_HOOK_FORMAT=json /path\""` is `command not found`, silently — omniplugin pitfall #23).

## The hook contract on ZCode, precisely

ZCode's runner parses a command hook's stdout **only if it starts with `{`**, and records non-JSON stdout as a *failed* run. `hooks/session-start.sh` therefore emits `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}` whenever `ZCODE_PLUGIN_ROOT` is present (ZCode exports it beside the legacy `CLAUDE_PLUGIN_ROOT`) or `SB_HOOK_FORMAT=json` is forced, and plain text otherwise. One registration, one script, two shapes — it cannot double-deliver.

| Hook | On ZCode |
|---|---|
| SessionStart (`startup\|resume\|clear\|compact`) | the one-line campaign nudge, JSON shape; `compact` is in the runtime's matcher vocabulary |
| PreToolUse guard | the runtime has the exit-2 branch (`exitCode===2` → block) and `permissionDecision`; `frozen-guard.sh` exits 2 with the reason on stderr — the same contract as Claude Code, **not exercised in a live session** |
| Stop driver | the runtime carries `stop_hook_active` and `decision==="block"`; `stop-driver.sh`'s output matches — **not exercised live** |
| PreCompact | **not an event on this build** (the bundle knows SessionStart, PreToolUse, PostToolUse, Stop, UserPromptSubmit); unknown events are warned and skipped. The SessionStart `compact` matcher re-anchors after compaction instead |

## Subagents on ZCode

Declared plugin `agents/` register as diagnostic entries, not executable named types, on this line. Spawn the generic Agent tool's fresh-context child and point it at the file: `Read $ZCODE_PLUGIN_ROOT/agents/sb-judge.md and follow it exactly. Judge the experiment described in <payload path>. Return only the verdict JSON.` Freshness comes from the Agent tool's process boundary; blindness from passing the payload by path and keeping dialogue out of the prompt. Never a fork/inherit mode for the judge. Tiers are not pinned.

## Verify

```sh
python3 <root>/scripts/sb.py selftest                            # 61/61
cd <repo with a running campaign>
<root>/hooks/session-start.sh                                     # no vars → plain text (Claude Code behavior)
ZCODE_PLUGIN_ROOT=<root> <root>/hooks/session-start.sh            # ZCode plugin ctx → {"hookSpecificOutput"…}
SB_HOOK_FORMAT=json <root>/hooks/session-start.sh                 # config-file route → same JSON
```

## Honest status of the ZCode glue

**Verified on 2026-09-03:**

- Static, from the installed runtime bundle: manifest fallthrough strings `.zcode-plugin/plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`; `hooks/hooks.json` discovery (`join("hooks","hooks.json")`); events SessionStart/PreToolUse/PostToolUse/Stop/UserPromptSubmit (no PreCompact); `ZCODE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` (and the `_PROJECT_DIR` pair) exported; `hookSpecificOutput`/`additionalContext`, `permissionDecision`, `stop_hook_active`, `decision==="block"`, the exit-2 hook branch; matcher vocabulary includes `compact`.
- Execution matrix against a real pyfix campaign: plain → text; `ZCODE_PLUGIN_ROOT` set → JSON; `SB_HOOK_FORMAT=json` → JSON; bogus root → self-resolved and delivered; outside a repository → zero bytes, exit 0; the documented config line under `sh -c` and `zsh -c` → JSON. Guard exit 2 / Stop block JSON / PreCompact pins all produced from the shell.

**Not verified:** the marketplace install (GUI), a live session, the guard and Stop hooks through ZCode's runner, `/strictlybetter` vs `/strictlybetter:run` spelling on your build, Agent-tool children. Drift shows up as a missing surface, not a crash. Report what you see.
