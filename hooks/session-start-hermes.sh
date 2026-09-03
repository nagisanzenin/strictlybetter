#!/usr/bin/env bash
# strictlybetter re-anchor hook for Hermes Agent.
# Two modes, auto-detected:
#   hook mode (stdin carries Hermes' pre_llm_call JSON payload): emit
#     {"context": "<nudge>"} once per session, {} on every other call.
#     Register in ~/.hermes/config.yaml:
#       hooks:
#         pre_llm_call:
#           - command: "/path/to/strictlybetter/hooks/session-start-hermes.sh"
#             timeout: 15
#   plain mode (stdin empty — e.g. `hermes cron create --no-agent --script …`):
#     print the nudge as plain text (nothing when nothing to say).
# The nudge is the engine's own line: "[strictlybetter] campaign <id> running: …" or
# "… HALTED: …". It is silent unless the working directory (or SB_HOME) holds a
# strictlybetter state home with a campaign, so a Hermes session outside a research
# repo never hears from this hook.
# Contract: ambient, never nagging — at most one nudge per session, and on ANY
# failure degrade to silence, never to repetition. Exit 0 always.
set -u
command -v python3 >/dev/null 2>&1 || { printf '{}\n'; exit 0; }

payload="$(cat - 2>/dev/null || true)"

# Engine resolution: SB_ROOT (the documented Hermes route: exported from ~/.hermes/.env),
# else self-resolve from this script's location.
ROOT="${SB_ROOT:-}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/sb.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/sb.py" ] || { [ -n "$payload" ] && printf '{}\n'; exit 0; }

# The project: a `cwd` in the payload when Hermes sends one, else this process's cwd.
PROJ=""
if [ -n "$payload" ]; then
  PROJ="$(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d = json.load(sys.stdin); v = d.get("cwd") or d.get("working_directory") or ""
    print(v if isinstance(v, str) else "")
except Exception: print("")' 2>/dev/null || true)"
fi
[ -n "$PROJ" ] && [ -d "$PROJ" ] || PROJ="$PWD"

emit_nudge() {  # prints the nudge (empty when nothing to say); validated: printable, two lines max
  ( cd -- "$PROJ" 2>/dev/null && python3 "$ROOT/scripts/sb.py" session-start 2>/dev/null | head -n 2 | tr -d '\000-\010\013-\037' ) || true
}

# Fast path: no state home under the project (and no SB_HOME) means nothing to say.
if [ -z "${SB_HOME:-}" ] && [ ! -d "$PROJ/.strictlybetter" ]; then
  [ -n "$payload" ] && printf '{}\n'
  exit 0
fi

# Plain mode: no stdin payload (cron --no-agent, manual run). No JSON, no dedupe
# (each scheduled run SHOULD deliver); stdout goes to the delivery target verbatim.
if [ -z "$payload" ]; then
  emit_nudge
  exit 0
fi

# Hook mode. Dedupe key: the sanitized session id; if extraction fails, fall back
# to the parent (Hermes) PID so the guard fails CLOSED — at most one nudge per
# Hermes process — never open (one per LLM call).
session_id="$(printf '%s' "$payload" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("session_id") or "")
except Exception: print("")' 2>/dev/null | tr -c 'A-Za-z0-9_-' '_' | cut -c1-80)" || session_id=""
[ -n "$session_id" ] || session_id="pid-${PPID:-0}"

marker="${TMPDIR:-/tmp}/strictlybetter-nudge-${session_id}"
if [ -e "$marker" ]; then printf '{}\n'; exit 0; fi
# Unwritable marker dir → we could not remember having nudged, so stay silent:
# silence over repetition, per the contract.
if ! { : > "$marker"; } 2>/dev/null; then printf '{}\n'; exit 0; fi

out="$(emit_nudge)"
if [ -n "$out" ]; then
  printf '%s' "$out" | python3 -c 'import sys,json; print(json.dumps({"context": sys.stdin.read().strip()}))' 2>/dev/null || printf '{}\n'
else
  printf '{}\n'
fi
exit 0
