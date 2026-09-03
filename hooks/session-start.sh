#!/usr/bin/env bash
# strictlybetter re-anchor hook: surfaces a running or halted campaign at session start.
# ONE registration (hooks/hooks.json), consumed differently per platform:
#   - Claude Code / Codex inject PLAIN stdout into context, so default output is plain.
#   - ZCode discards plain SessionStart stdout and parses ONLY the JSON shape
#     (hookSpecificOutput.additionalContext). ZCode exports ZCODE_PLUGIN_ROOT beside the
#     legacy CLAUDE_PLUGIN_ROOT, so that var is both the runtime tell and a working root.
#   - Hand-wired installs with no plugin-root variable set SB_HOOK_FORMAT=json themselves.
# Prints at most two lines (or nothing). Must never break a session: degrade to silence.
# The engine runs from the project dir so it resolves the repo the way the skills do.
set -u
command -v python3 >/dev/null 2>&1 || exit 0
emit_json() {
  python3 - "$1" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
}
ROOT="${ZCODE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/sb.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/sb.py" ] || exit 0
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -d "$PROJ" ] || exit 0
# Fast path: no state home under the project (and no SB_HOME override) means nothing to say.
if [ -z "${SB_HOME:-}" ] && [ ! -d "$PROJ/.strictlybetter" ]; then exit 0; fi
NUDGE="$(cd -- "$PROJ" 2>/dev/null && python3 "$ROOT/scripts/sb.py" session-start 2>/dev/null | head -n 2 | tr -d '\000-\010\013-\037' || true)"
[ -n "$NUDGE" ] || exit 0                                   # silent when nothing to say
case "${SB_HOOK_FORMAT:-}" in
  json) emit_json "$NUDGE"; exit 0 ;;
esac
if [ -n "${ZCODE_PLUGIN_ROOT:-}" ]; then                    # ZCode eats plain text; give it
  emit_json "$NUDGE"                                        # the one shape it will parse
  exit 0
fi
printf '%s\n' "$NUDGE"
exit 0
