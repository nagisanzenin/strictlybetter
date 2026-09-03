---
name: orient
description: "Orient strictlybetter on this repository: spawn the orienteer once, verify build/test/lint/bench commands by running them, store the profile. Use when strictlybetter has no profile yet, the toolchain changed, or the user asks to re-orient / refresh the project profile."
argument-hint: "[--refresh]"
---

# /strictlybetter:orient — ORIENT

One agent reads the repo the way a senior engineer would on day one and returns a profile.
You validate it, hand it to the engine, and show it. No questions.

```bash
# Resolve the engine. RUN THIS BLOCK VERBATIM — do not substitute a path you guessed.
# Order: ZCode's plugin root (ZCode also exports the legacy CLAUDE_PLUGIN_ROOT, so its own
# var is checked first), Claude Code, Codex, an explicit checkout (SB_ROOT), the Claude Code
# plugin cache (newest version), and LAST the working tree's git toplevel (a contributor
# running inside the strictlybetter checkout). First one that holds scripts/sb.py wins.
SB_PY=""
SB_CACHE="$(find "$HOME/.claude/plugins/cache" -maxdepth 5 -path '*/strictlybetter/*/scripts/sb.py' 2>/dev/null | sort | tail -n 1)"
for d in "${ZCODE_PLUGIN_ROOT:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CODEX_PLUGIN_ROOT:-}" "${SB_ROOT:-}" \
         "${SB_CACHE%/scripts/sb.py}" "$(git rev-parse --show-toplevel 2>/dev/null)"; do
  [ -n "$d" ] && [ -f "$d/scripts/sb.py" ] && SB_PY="$d/scripts/sb.py" && break
done
if [ -z "$SB_PY" ]; then
  echo "strictlybetter: engine not found — set SB_ROOT to your strictlybetter checkout" >&2
  return 2 2>/dev/null || exit 2   # FAIL CLOSED: proceeding would run `python3 ""`
fi
SB_ROOT="${SB_PY%/scripts/sb.py}"
SB_REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
sb() { python3 "$SB_PY" --repo "$SB_REPO" "$@"; }   # a FUNCTION, not a string: zsh does not
SB=sb                                                 # word-split "$SB"; both shells run `sb`
$SB --version | grep -q '^sb 1\.' || { echo "strictlybetter: engine did not answer (expected sb 1.x)" >&2; return 2 2>/dev/null || exit 2; }   # major version only; exact patch level is not asserted
```

## 0 · Re-anchor (never trust conversational memory)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

## 1 · Prepare

```bash
$SB init                                  # idempotent; creates .strictlybetter/ and inbox/
ls "$SB_ROOT/archetypes/"                 # the packs the orienteer matches against
```

If a profile already exists (`"profile": true`) and the user did not ask for a refresh, show
`$SB_REPO/.strictlybetter/profile.md` and stop.

> If the Agent tool does not offer the `strictlybetter:sb-*` type, use the fallback spawn shape in `skills/_shared/subagents.md` (a general agent told to Read the agent file first).

## 2 · Spawn the orienteer (once)

Spawn `sb-orienteer` (Claude Code agent type `strictlybetter:sb-orienteer`) with exactly
this task text, paths absolute:

> Orient the repository at `<SB_REPO>` for strictlybetter. Archetype packs are in `<SB_ROOT>/archetypes/`. Write the profile JSON to `<SB_REPO>/.strictlybetter/inbox/profile.json`. Return `DONE <path>`.

It runs the build, test, lint, and bench commands it proposes, once each, and records the
exit codes. Expect one to three minutes; say so before spawning.

## 3 · Validate and store

```bash
P="$SB_REPO/.strictlybetter/inbox/profile.json"
python3 - "$P" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert isinstance(d.get("archetypes"), list) and d["archetypes"], "archetypes: non-empty list required"
assert isinstance(d.get("commands"), dict), "commands: object required"
assert isinstance(d.get("purpose"), str) and d["purpose"].strip(), "purpose: required"
print("profile ok:", [a.get("id") if isinstance(a, dict) else a for a in d["archetypes"]])
PY
$SB profile write --file "$P"
```

A `BLOCKED:` return or a failed assertion: print it, spawn the orienteer once more with
the same task text, and if it fails again stop and tell the user what the orienteer could
not determine. Never write a profile by hand.

## 4 · Show it

Print at most 12 lines from `$SB_REPO/.strictlybetter/profile.md`: the purpose, the
archetypes with confidence, the verified commands with their exit codes, and the proposed
protected paths. Then return to the caller (the front door continues to metrics) or stop.
