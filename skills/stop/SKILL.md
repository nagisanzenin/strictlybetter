---
name: stop
description: "Stop the strictlybetter loop at the next safe point by writing the STOP file; the Stop hook no longer continues the campaign. Use when the user says stop, pause, halt, or 'enough' about the research loop or campaign."
argument-hint: "[--resume]"
---

# /strictlybetter:stop

The kill switch. Safe point = no worktree mid-edit, ledger flushed, campaign status written.

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
$SB --version   # must print `sb 1.0.0`; anything else means this block did not run
```

## 0 · Re-anchor (never trust conversational memory)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

## 1 · Stop

```bash
$SB stop        # writes .strictlybetter/STOP
$SB status
```

Say exactly what changes: `sb prereg` refuses new experiments while the file exists, the
Stop hook sees `stop_requested` and lets the session end instead of injecting another
cycle, and experiments already in flight are finished by the current cycle (measured,
judged, accepted or discarded) rather than abandoned. The campaign's status stays
`running`; nothing is lost.

## 2 · Resume (only when asked: `--resume` or "continue the campaign")

```bash
$SB campaign resume     # removes STOP, clears the consecutive-error counters, status → running
$SB status
```

`resume` also un-halts a `halted` campaign. Say so before running it on one: a halt had a
reason (integrity twice, gamed twice, holdout gap, invalid baseline), and resuming without
reading it is how a loop repeats its failure. Then `/strictlybetter` runs the next cycle.

Ending for good is different: `$SB campaign end` writes the report and drops every
worktree; a new campaign starts at gate 1.
