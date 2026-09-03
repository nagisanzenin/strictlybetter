#!/usr/bin/env bash
# strictlybetter Stop-hook driver (the Ralph pattern, docs/10 §10.4).
# When Claude stops while a campaign is running with budget left, print
#   {"decision":"block","reason":"..."}  (exit 0)
# and Claude Code keeps the session going with that reason as the next instruction.
# Three safeties, in order: the per-session iteration counter capped at the campaign's
# iteration_cap (default 200); a no-progress guard (three continuations in a row with no
# new experiment stop the driver); and the engine's own status (halted, ended, STOP file,
# exhausted budget all exit 0). SB_DRIVER=off disables the driver for this shell.
# NOTE on stop_hook_active: Claude Code sets it true on every stop that follows a
# continuation this hook caused. Exiting on it would allow exactly ONE extra cycle per
# user turn, which is not a driver. The counter + no-progress guard are the loop guard
# the docs recommend in its place; SB_DRIVER_HONOR_STOP_HOOK_ACTIVE=1 restores the
# one-cycle behaviour if you want it.
# All JSON is parsed by python3 (program via -c, payload on stdin); never jq, never argv.
set -u
PAYLOAD="$(cat 2>/dev/null || true)"
[ "${SB_DRIVER:-on}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
ROOT="${ZCODE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/sb.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/sb.py" ] || exit 0
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -d "$PROJ" ] || exit 0
# Fast path: nothing to drive without a campaign file.
if [ -z "${SB_HOME:-}" ] && [ ! -f "$PROJ/.strictlybetter/campaign.json" ]; then exit 0; fi
PROG="$(cat <<'PY'
import json, os, re, subprocess, sys
def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        sys.exit(0)
    if payload.get("stop_hook_active") and os.environ.get("SB_DRIVER_HONOR_STOP_HOOK_ACTIVE") == "1":
        sys.exit(0)
    sid = str(payload.get("session_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", sid):
        sys.exit(0)  # no session id, no counter, no driving
    root, proj = os.environ["SB_HOOK_ROOT"], os.environ["SB_HOOK_PROJ"]
    sb = [sys.executable, os.path.join(root, "scripts", "sb.py")]
    try:
        p = subprocess.run(sb + ["status", "--json"], cwd=proj, capture_output=True, text=True, timeout=8)
        s = json.loads(p.stdout) if p.returncode == 0 else {}
    except Exception:
        sys.exit(0)
    if not s.get("campaign") or s.get("status") != "running" or s.get("stop_requested") or s.get("budget_exhausted"):
        sys.exit(0)
    try:
        cap = int(s.get("iteration_cap") or 200)
    except (TypeError, ValueError):
        cap = 200
    stale_max = 3
    try:
        stale_max = int(os.environ.get("SB_DRIVER_STALE_MAX") or 3)
    except ValueError:
        pass
    home = os.environ.get("SB_HOME")
    if not home:
        try:
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=proj, capture_output=True, text=True, timeout=5)
            top = top.stdout.strip() if top.returncode == 0 else proj
        except Exception:
            top = proj
        home = os.path.join(top, ".strictlybetter")
    tmp = os.path.join(home, "tmp")
    os.makedirs(tmp, exist_ok=True)
    cf = os.path.join(tmp, f"driver-{sid}.count")
    st = {"iter": 0, "experiments": None, "stale": 0}
    try:
        with open(cf) as f:
            old = json.load(f)
        if isinstance(old, dict):
            st.update({k: old.get(k, st[k]) for k in st})
    except Exception:
        pass
    exps = int(s.get("experiments") or 0)
    st["iter"] = int(st.get("iter") or 0) + 1
    st["stale"] = (int(st.get("stale") or 0) + 1) if st.get("experiments") == exps else 0
    st["experiments"] = exps
    with open(cf + ".tmp", "w") as f:
        json.dump(st, f)
    os.replace(cf + ".tmp", cf)
    cid = str(s.get("campaign"))
    if st["stale"] >= stale_max:
        sys.stderr.write(f"strictlybetter driver: {stale_max} continuations without a new experiment; not continuing campaign {cid} (run /strictlybetter:run or `sb campaign end`).\n")
        sys.exit(0)
    if st["iter"] >= cap:
        sys.stderr.write(f"strictlybetter driver: iteration cap {cap} reached for this session; campaign {cid} is still running (`sb campaign end` or a new session).\n")
        sys.exit(0)
    left = s.get("budget_left") or {}
    reason = (f"strictlybetter campaign {cid} is running ({exps} experiments, {int(s.get('accepted') or 0)} accepted, "
              f"budget left {json.dumps(left, sort_keys=True)}; driver iteration {st['iter']}/{cap}). "
              "Run one more cycle: invoke the strictlybetter run skill (`/strictlybetter:run`). "
              "If the campaign is done, run `sb campaign end`.")
    print(json.dumps({"decision": "block", "reason": reason}))
try:
    main()
except SystemExit:
    raise
except Exception:
    sys.exit(0)
PY
)"
printf '%s' "$PAYLOAD" | SB_HOOK_ROOT="$ROOT" SB_HOOK_PROJ="$PROJ" python3 -c "$PROG" || true
exit 0
