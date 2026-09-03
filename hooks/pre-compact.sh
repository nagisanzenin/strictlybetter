#!/usr/bin/env bash
# strictlybetter PreCompact pins. When a campaign is running, print at most six plain
# lines that must survive summarization: campaign id, branch and head, the one sentence
# that keeps the orchestrator honest, the frozen paths, and where edits are allowed.
# Silent otherwise. Degrades to silence on any failure. Reads the engine's own brief
# (`sb next --json`), never conversational memory.
set -u
cat >/dev/null 2>&1 || true                                  # drain the hook payload
command -v python3 >/dev/null 2>&1 || exit 0
ROOT="${ZCODE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/sb.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/sb.py" ] || exit 0
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -d "$PROJ" ] || exit 0
if [ -z "${SB_HOME:-}" ] && [ ! -f "$PROJ/.strictlybetter/campaign.json" ]; then exit 0; fi
PROG="$(cat <<'PY'
import json, sys
try:
    b = json.loads(sys.stdin.read() or "{}")
except Exception:
    sys.exit(0)
if not isinstance(b, dict) or b.get("status") != "running":
    sys.exit(0)
def clean(x, n):
    s = "".join(ch for ch in str(x) if ch >= " " or ch == "\t")
    return s if len(s) <= n else s[: n - 3] + "..."
frozen = ", ".join(clean(p, 60) for p in (b.get("frozen_paths") or [])) or "(none declared)"
print(f"[strictlybetter PIN] campaign {clean(b.get('campaign'), 80)} is RUNNING on branch {clean(b.get('branch'), 80)} at {clean(b.get('head_commit'), 40)[:8]}; goals {clean(b.get('goals'), 120)}.")
print("You never compute a statistic and never write baseline.json; the engine does. Re-read `sb next` before acting.")
print(f"Frozen paths (the instrument; any edit is denied): {clean(frozen, 400)}")
print("Edits happen only inside .strictlybetter/wt/<id>/ by an sb-experimenter agent after `sb prereg`; the guard hook denies everything else.")
print("Continue with the strictlybetter run skill (/strictlybetter:run): one cycle = sb next -> prereg -> experimenter -> submit -> measure -> judge -> confirm -> accept|discard.")
PY
)"
( cd -- "$PROJ" 2>/dev/null && python3 "$ROOT/scripts/sb.py" next --json 2>/dev/null ) | python3 -c "$PROG" 2>/dev/null | head -n 6 || true
exit 0
