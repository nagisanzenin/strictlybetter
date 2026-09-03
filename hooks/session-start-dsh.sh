#!/usr/bin/env bash
# strictlybetter re-anchor hook for DeepSeek Harness's Claude Code hook bridge.
# dsh's bridge consumes ONLY the JSON hookSpecificOutput.additionalContext shape —
# plain SessionStart stdout is discarded (documented dsh limitation). The shared
# hooks/session-start.sh already knows that shape (SB_HOOK_FORMAT=json), so this
# wrapper only pins the format and hands over; it exists so the dsh hook config never
# depends on how the bridge tokenizes an env assignment in a command string
# (omniplugin pitfall #23). Degrades to silence on any failure; exit 0 always.
set -u
HERE="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
[ -n "$HERE" ] && [ -f "$HERE/session-start.sh" ] || exit 0
SB_HOOK_FORMAT=json exec bash "$HERE/session-start.sh"
