#!/usr/bin/env bash
# strictlybetter frozen-path guard (PreToolUse: Edit|MultiEdit|Write|NotebookEdit).
# The ONE hook whose purpose is to deny. While a campaign is running, the engine denies
# edits to frozen paths (the instrument), protected paths, harness state, and anything
# outside an experiment worktree under .strictlybetter/wt/<id>/. Exit 2 denies the tool
# call and shows the engine's one-line reason to the model; anything else exits 0.
# Fast path: no campaign.json under the project dir (or under any parent of the edited
# file's directory, up to 6 levels) means no campaign and python is never started.
# The raw hook payload goes to the engine on STDIN, never on argv.
set -u
PAYLOAD="$(cat 2>/dev/null || true)"
[ -n "$PAYLOAD" ] || exit 0
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
REPO=""
if [ -n "${SB_HOME:-}" ] && [ -f "$SB_HOME/campaign.json" ]; then
  REPO="$PROJ"
elif [ -f "$PROJ/.strictlybetter/campaign.json" ]; then
  REPO="$PROJ"
else
  # Approximate extraction, used ONLY to decide whether to start python. A path the sed
  # cannot read falls through to exit 0, the same as "no campaign here".
  FP="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$FP" ] || FP="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"notebook_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$FP" ] || exit 0
  D="$(dirname -- "$FP")"
  case "$D" in /*) ;; *) D="$PROJ/$D" ;; esac
  i=0
  while [ "$i" -le 6 ] && [ -n "$D" ] && [ "$D" != "/" ] && [ "$D" != "." ]; do
    # A worktree checkout may carry a committed copy of .strictlybetter/campaign.json;
    # the real state home is the one that is NOT inside .strictlybetter/wt/.
    case "$D" in
      */.strictlybetter/wt/*|*/.strictlybetter/wt) ;;
      *) if [ -f "$D/.strictlybetter/campaign.json" ]; then REPO="$D"; break; fi ;;
    esac
    D="$(dirname -- "$D")"
    i=$((i + 1))
  done
  [ -n "$REPO" ] || exit 0
fi
command -v python3 >/dev/null 2>&1 || exit 0
ROOT="${ZCODE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/sb.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/sb.py" ] || exit 0
ERR="$(printf '%s' "$PAYLOAD" | python3 "$ROOT/scripts/sb.py" --repo "$REPO" guard --stdin 2>&1 >/dev/null)"
RC=$?
if [ "$RC" -eq 2 ]; then
  printf '%s\n' "${ERR:-strictlybetter guard: denied}" | tr -d '\000-\010\013-\037' | head -n 3 >&2
  exit 2
fi
exit 0
