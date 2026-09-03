#!/usr/bin/env python3
"""Mutation check (RELEASE_PROTOCOL.md section 4.5): a check that still passes when its fix is
reverted is theatre. For every row of the standing mutation table that can be applied textually,
this script copies scripts/sb.py (plus .claude-plugin/plugin.json so the version pin runs) into a
scratch tree, applies ONE mutation, runs `python3 <copy> selftest`, and records whether the
selftest went red and whether the check the table names is among the FAIL lines.

Each mutation asserts that its anchor text occurs exactly the expected number of times in the
engine; a mutation whose anchor drifted is reported as NOT APPLIED and fails the run, because a
stale row in the table is itself a defect. An unmutated control copy must be green and must print
the `version pinned to plugin.json` line, or the run is invalid (exit 2).

Verdicts per row:
  RED (FAIL lines)   the selftest printed at least one FAIL line and exited non-zero
  RED (crash)        the selftest exited non-zero without a summary line (a traceback is red too)
  GREEN              the selftest passed: the mutation is NOT caught (a finding, exit 1)
`named check red?` says whether every check the table names for that row actually failed; a row
with no named check prints `(none named)` and is judged on the selftest colour alone.

Usage:
    python3 tests/mutation_check.py [--jobs 4] [--only NAME_SUBSTRING] [--list]

Exit 0 when every applied mutation is caught, 1 when any mutation survives or fails to apply,
2 when the control is not green. Nothing here modifies the repository.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "scripts", "sb.py")
MANIFEST = os.path.join(ROOT, ".claude-plugin", "plugin.json")
CHECKLIST = os.path.join(ROOT, "templates", "judge-checklist.md")
MAIN_GUARD = 'if __name__ == "__main__":\n'


# ----------------------------------------------------------------------------------------
# The mutations. `old`/`new` is an exact-text replacement with an expected occurrence count;
# `insert_after` appends text right after the anchor; `append` inserts module-level code before
# the __main__ guard (so it overrides an earlier definition at call time).
# ----------------------------------------------------------------------------------------
MUTATIONS = [
    {"name": "flattering: improved = delta > 0", "cls": "1 flattering",
     "old": 'res["improved"] = delta > thr', "new": 'res["improved"] = delta > 0', "count": 2,
     "expect": ["goal within noise is inconclusive"]},
    {"name": "flattering: compare_metric always improved", "cls": "1 flattering",
     "append": '\n# MUTATION: compare_metric flatters every comparison\n_sb_orig_compare_metric = compare_metric\n\n\n'
               'def compare_metric(*a, **k):\n    r = _sb_orig_compare_metric(*a, **k)\n    r["improved"] = True\n    r["inconclusive"] = False\n    return r\n\n\n',
     "expect": ["goal within noise is inconclusive"]},
    {"name": "regression: `if regressed:` -> `if False:` in decide", "cls": "2 regression",
     "old": "    if regressed:\n", "new": "    if False:\n", "count": 1,
     "expect": ["decide regression beats improvement", "guardrail regression discards a big goal win"]},
    {"name": "regression: validity wall ignored in decide", "cls": "2 regression",
     "old": '    if invalid and walls.get("validity", True):\n', "new": "    if False:\n", "count": 1,
     "expect": ["decide invalid"]},
    {"name": "judge: extra-keys rejection deleted in cmd_judge_verdict", "cls": "3 judge",
     "old": '    if extra:\n        raise SBError(f"verdict has forbidden fields', "new": '    if False:\n        raise SBError(f"verdict has forbidden fields', "count": 1,
     "expect": ["verdict schema forbids extra fields"]},
    {"name": "stale sigma: missing-sigma halt disabled in campaign_start", "cls": "4 stale sigma",
     "old": '!= "equal" and e.get("sigma") is None:', "new": '!= "equal" and False:', "count": 1,
     "expect": []},
    {"name": "stale sigma: sigma_of returns 0", "cls": "4 stale sigma",
     "insert_after": 'n in {2, 3}: sample stdev; n < 2: unknown."""\n', "text": "    return 0.0\n", "count": 1,
     "expect": ["sigma_of n=3 is stdev", "sigma_of n>=4 is MAD-scaled", "sigma_of single"]},
    {"name": "holdout: confirm measures without holdout (paired and unpaired paths)", "cls": "5 holdout",
     "old": 'walls.get("holdout", True))', "new": "False)", "count": 2,
     "expect": ["confirm used the holdout seeds"]},
    {"name": "guard: frozen path allowed", "cls": "6 guard",
     "old": 'return False, f"frozen path', "new": 'return True, f"frozen path', "count": 1,
     "expect": ["guard denies frozen path"]},
    {"name": "guard: state files allowed", "cls": "6 guard",
     "old": 'return False, "state files', "new": 'return True, "state files', "count": 2,
     "expect": ["guard denies state file"]},
    {"name": "guard: guard_decision allows everything", "cls": "6 guard",
     "insert_after": '    """Return (allow: bool, reason: str)."""\n', "text": '    return True, "mutated: guard allows everything"\n', "count": 1,
     "expect": ["guard denies frozen path", "guard denies main tree during campaign", "guard denies state file"]},
    {"name": "validity: timer-divergence check disabled", "cls": "validity",
     "old": '    if instr_saved >= WALL_DIVERGENCE_MIN_SHARE * wall_base and', "new": '    if False and', "count": 1,
     "expect": ["timer divergence flags a lying instrument"]},
    {"name": "ledger: torn line re-raised in read_jsonl", "cls": "7 ledger",
     "old": "                except json.JSONDecodeError:\n                    continue  # a torn line never bricks a read path\n",
     "new": "                except json.JSONDecodeError:\n                    raise\n", "count": 1,
     "expect": ["torn ledger line tolerated"]},
    {"name": "budget: experiments charged after worktree_new in cmd_prereg", "cls": "8 budget",
     "old": '    add_spend(c, experiments=1)  # budget updated before work starts\n    home.save_campaign(c)\n    commit = c["head_commit"]\n    parent_member = None\n',
     "new": '    commit = c["head_commit"]\n    parent_member = None\n    add_spend(c, experiments=1)  # MUTATION: charged after the work\n    home.save_campaign(c)\n', "count": 1,
     "expect": ["budget charged before worktree creation"]},
    {"name": "label: dollars n/a marker dropped", "cls": "9 label",
     "old": '"dollars_est": (round(dollars, 4) if not spent.get("dollars_unknown") else "n/a (tokens not reported)"),', "new": '"dollars_est": round(dollars, 4),', "count": 1,
     "expect": ["unreported tokens make dollars n/a"]},
    {"name": "label: report drops the word `estimated`", "cls": "9 label",
     "old": '(estimated from reported tokens at the campaign', "new": '(from reported tokens at the campaign', "count": 1,
     "expect": ["report labels dollars as estimated"]},
    {"name": "absence: import socket", "cls": "absence",
     "old": "import argparse\n", "new": "import argparse\nimport socket\n", "count": 1,
     "expect": ["no network imports"]},
    {"name": "integrity: frozen-path check disabled in cmd_submit", "cls": "integrity",
     "old": "        if matches_any(f, fp):\n", "new": "        if False:\n", "count": 1,
     "expect": ["integrity catches frozen edit"]},
    {"name": "integrity: submit ok regardless of violations", "cls": "integrity",
     "old": '    ok = not violations if c.get("walls", {}).get("frozen_guard", True) else True\n', "new": "    ok = True\n", "count": 1,
     "expect": ["integrity catches frozen edit"]},
    {"name": "version: VERSION changed alone", "cls": "version", "version": True,
     "expect": ["version pinned to plugin.json"]},
    {"name": "test: sign-flip p forced to 0 (every candidate significant)", "cls": "1 flattering",
     "old": '    return {"p": p, "stat": (obs if alternative != "less" else -obs), "n": r, "exact": exact, "min_p": 2.0 ** (-r)}',
     "new": '    return {"p": 0.0, "stat": (obs if alternative != "less" else -obs), "n": r, "exact": exact, "min_p": 2.0 ** (-r)}', "count": 1,
     "expect": ["sign-flip: symmetric pairs give p ~ 0.5", "sign-flip: all-zero pairs give p = 1"]},
    {"name": "alpha: per-test alpha ignores the budget", "cls": "1 flattering",
     "old": '    if mult == "bonferroni" and k > 0:\n        return alpha / k', "new": '    if False:\n        return alpha / k', "count": 1,
     "expect": ["alpha per test is alpha over the budget", "alpha bookkeeping at start"]},
    {"name": "power gate disabled", "cls": "4 stale sigma",
     "old": '            if 2.0 ** (-r_total) > a_look and not args.allow_underpowered:', "new": '            if False:', "count": 1,
     "expect": ["underpowered goal halts at start"]},
    {"name": "pairs: invalid members not dropped", "cls": "5 holdout",
     "old": '        if a.get("valid") and b.get("valid") and isinstance(a.get("value"), float) and isinstance(b.get("value"), float):', "new": '        if True:', "count": 1,
     "expect": ["pairs align by index and drop invalid members"]},
    {"name": "ladder: first-accept audit never fires", "cls": "1 flattering",
     "old": '        first = len(c["accepted_ids"]) == 1', "new": '        first = False', "count": 1,
     "expect": ["proxy ladder: first accept triggers an audit"]},
    {"name": "ladder: real ratchet moves without an audit verdict", "cls": "1 flattering",
     "old": '            if m["verdict"] in ("confirmed", "direction") and m.get("head_median") is not None:', "new": '            if m.get("head_median") is not None:', "count": 1,
     "expect": ["proxy ladder: audit compares head vs last audited commit on the real instrument"]},
    {"name": "ladder: discard audit sampling disabled", "cls": "5 holdout",
     "old": '        if draw < rate:', "new": '        if False:', "count": 1,
     "expect": ["proxy ladder: discard is audited at the sampled rate"]},
    {"name": "ladder: proxy trust never validates", "cls": "9 label",
     "old": '            new = "validated"', "new": '            new = "provisional"', "count": 2,
     "expect": ["proxy ladder: trust becomes validated after enough agreeing audits"]},
    {"name": "kappa: kappa_eff ignores diff_lines", "cls": "1 flattering",
     "old": "    return kappa * (1.0 + LAMBDA_COMPLEXITY * math.log(1.0 + max(0, diff_lines) / DIFF_REF_LINES)) + NEW_DEP_PENALTY * max(0, new_deps)\n",
     "new": "    return kappa + NEW_DEP_PENALTY * max(0, new_deps)\n", "count": 1,
     "expect": ["kappa_eff grows with diff"]},
    {"name": "leak: redact is a no-op", "cls": "5 holdout",
     "insert_after": '    for audit but are not surfaced to the experimenter-facing views."""\n', "text": "    return dict(rec)\n", "count": 1,
     "expect": ["discarded confirm numbers redacted"]},
]


def apply_mutation(src, m):
    """Return (mutated_src, note). Raises ValueError when the anchor is missing or its count is off."""
    if m.get("version"):
        mm = re.search(r'^VERSION = "([^"]+)"$', src, re.M)
        if not mm:
            raise ValueError("VERSION line not found")
        return src.replace(mm.group(0), 'VERSION = "0.0.0-mutant"', 1), f'VERSION {mm.group(1)} -> 0.0.0-mutant'
    if "append" in m:
        if src.count(MAIN_GUARD) != 1:
            raise ValueError("__main__ guard not found exactly once")
        return src.replace(MAIN_GUARD, m["append"] + MAIN_GUARD, 1), "module-level override appended"
    anchor = m.get("old") or m["insert_after"]
    n = src.count(anchor)
    if n != m["count"]:
        raise ValueError(f"anchor found {n} time(s), expected {m['count']}: {anchor[:60]!r}")
    if "old" in m:
        return src.replace(anchor, m["new"]), f"{n} replacement(s)"
    return src.replace(anchor, anchor + m["text"]), f"inserted after anchor ({n})"


def make_tree(base, name, src):
    tree = os.path.join(base, re.sub(r"[^A-Za-z0-9_.-]+", "-", name)[:60])
    os.makedirs(os.path.join(tree, "scripts"))
    os.makedirs(os.path.join(tree, ".claude-plugin"))
    os.makedirs(os.path.join(tree, "templates"))
    with open(os.path.join(tree, "scripts", "sb.py"), "w", encoding="utf-8") as f:
        f.write(src)
    shutil.copy(MANIFEST, os.path.join(tree, ".claude-plugin", "plugin.json"))
    if os.path.exists(CHECKLIST):
        shutil.copy(CHECKLIST, os.path.join(tree, "templates", "judge-checklist.md"))
    return tree


def run_selftest(tree, timeout):
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, os.path.join(tree, "scripts", "sb.py"), "selftest"], capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, (e.stdout or "") if isinstance(e.stdout, str) else "", "timeout"
    secs = time.perf_counter() - t0
    fails = [l[5:].strip() for l in out.splitlines() if l.startswith("FAIL ")]
    summary = next((l for l in out.splitlines() if l.startswith("selftest:")), None)
    pinned = any("version pinned to plugin.json" in l for l in out.splitlines())
    if rc == 0 and summary:
        colour = "GREEN"
    elif fails:
        colour = "RED (FAIL lines)"
    elif rc == 124:
        colour = "RED (timeout)"
    else:
        last = (err.strip().splitlines() or ["?"])[-1]
        colour = f"RED (crash: {last[:70]})"
    return {"rc": rc, "colour": colour, "fails": fails, "summary": summary, "pinned": pinned, "secs": secs, "stderr_tail": err[-400:]}


def one(base, m, src, timeout):
    try:
        mutated, note = apply_mutation(src, m)
    except ValueError as e:
        return {**m, "applied": False, "note": str(e)}
    if mutated == src:
        return {**m, "applied": False, "note": "mutation produced identical source"}
    tree = make_tree(base, m["name"], mutated)
    r = run_selftest(tree, timeout)
    caught = r["colour"] != "GREEN"
    named = None
    if m["expect"]:
        named = all(e in r["fails"] for e in m["expect"])
    return {**m, "applied": True, "note": note, "caught": caught, "named": named, **r}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds per selftest run")
    ap.add_argument("--only", help="run only mutations whose name contains this substring")
    ap.add_argument("--list", action="store_true", help="print the mutation table and exit")
    a = ap.parse_args(argv)
    if a.list:
        for m in MUTATIONS:
            print(f"{m['cls']:14} {m['name']:60} -> {', '.join(m['expect']) or '(none named)'}")
        return 0
    if not os.path.exists(MANIFEST):
        print(f"missing {MANIFEST}: the version pin cannot run; refusing to report a green pin", file=sys.stderr)
        return 2
    with open(SB, encoding="utf-8") as f:
        src = f.read()
    todo = [m for m in MUTATIONS if not a.only or a.only.lower() in m["name"].lower()]
    base = tempfile.mkdtemp(prefix="sb-mutation-")
    try:
        # control: the unmutated copy, in the same layout, must be green and must run the version pin
        ctrl = run_selftest(make_tree(base, "control", src), a.timeout)
        print(f"control: {ctrl['colour']} · {ctrl['summary']} · version pin ran: {ctrl['pinned']} · {ctrl['secs']:.1f}s")
        if ctrl["colour"] != "GREEN" or not ctrl["pinned"]:
            print("control is not a green selftest with the version pin; the mutation run is invalid")
            print(ctrl["stderr_tail"])
            return 2
        print(f"running {len(todo)} mutation(s) with {a.jobs} worker(s) ...", file=sys.stderr)
        rows = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(one, base, m, src, a.timeout): m for m in todo}
            for fut in concurrent.futures.as_completed(futs):
                r = fut.result()
                rows.append(r)
                tag = "NOT APPLIED" if not r["applied"] else ("caught" if r["caught"] else "SURVIVED")
                print(f"  {tag:11} {r['name']}", file=sys.stderr)
        rows.sort(key=lambda r: MUTATIONS.index(next(m for m in MUTATIONS if m["name"] == r["name"])))
        w = max(len(r["name"]) for r in rows)
        print(f"\n{'mutation':{w}} | {'class':14} | {'selftest result':34} | caught? | named check red?")
        print(f"{'-' * w}-|-{'-' * 14}-|-{'-' * 34}-|---------|-----------------")
        for r in rows:
            if not r["applied"]:
                print(f"{r['name']:{w}} | {r['cls']:14} | {'NOT APPLIED: ' + r['note']:34} | n/a     | n/a")
                continue
            named = "(none named)" if r["named"] is None else ("yes" if r["named"] else "NO: " + ", ".join(e for e in r["expect"] if e not in r["fails"]))
            colour = r["colour"] + (f" {len(r['fails'])} FAIL" if r["fails"] else "")
            print(f"{r['name']:{w}} | {r['cls']:14} | {colour[:34]:34} | {'yes' if r['caught'] else 'NO':7} | {named}")
        survived = [r for r in rows if r["applied"] and not r["caught"]]
        unapplied = [r for r in rows if not r["applied"]]
        # red for the wrong reason: the named check stayed green, or (no check named) the suite merely crashed
        weak = [r for r in rows if r["applied"] and r["caught"] and (r["named"] is False or (r["named"] is None and "crash" in r["colour"]))]
        print()
        if survived:
            print("SURVIVED (selftest stayed green; the table row needs a real check):")
            for r in survived:
                print(f"  - {r['name']}  [{r['cls']}]")
        if weak:
            print("caught for the wrong reason (a crash or an unrelated check went red; the table row still needs a real check):")
            for r in weak:
                print(f"  - {r['name']}: red via {', '.join(r['fails'][:4]) or r['colour']}")
        if unapplied:
            print("NOT APPLIED (anchor drifted; fix the row or the mutation):")
            for r in unapplied:
                print(f"  - {r['name']}: {r['note']}")
        n_caught = sum(1 for r in rows if r["applied"] and r["caught"])
        print(f"mutation check: {n_caught}/{len(rows)} mutations caught, {len(survived)} survived, {len(unapplied)} not applied")
        return 1 if survived or unapplied else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
