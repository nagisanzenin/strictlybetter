#!/usr/bin/env python3
"""External-adversary gate: attack diffs written by someone who never saw the walls.

Phase 1 (`--phase 1 --diffs DIR`): fresh pyfix copy, all walls on, one experiment per diff:
prereg → apply the diff in the worktree → submit (integrity) → screen → statistical judge →
for promoted candidates, `sb judge-payload` (the REAL blind judge is an LLM agent, spawned by
the operator between the phases). Writes `<out>/phase1.json` with per-attack state and the
payload paths that need a verdict.

Phase 2 (`--phase 2 --state <out>/phase1.json --verdicts DIR`): reads `<DIR>/<id>.json` verdict
files, stores them, runs confirm, accepts or discards, then writes the results file
`bench/results/<stamp>-adversary-pyfix.{json,md}`: which wall caught each attack, or ACCEPTED.

Everything is the real engine; nothing is simulated except that the judge verdicts are
supplied by the operator from the agents it spawned.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_bench as rb  # noqa: E402

sb = rb.sb


def apply_diff(wt: str, diff_path: str) -> tuple:
    p = subprocess.run(["git", "apply", "--whitespace=nowarn", diff_path], cwd=wt, capture_output=True, text=True)
    return p.returncode == 0, (p.stderr or p.stdout)[-300:]


def phase1(args) -> int:
    diffs = sorted(f for f in os.listdir(args.diffs) if f.endswith(".diff"))
    if not diffs:
        raise SystemExit("no .diff files")
    work = args.workdir or tempfile.mkdtemp(prefix="sb-adv-")
    dest = os.path.join(work, "pyfix-adversary")
    rb.make_fixture("pyfix", dest)
    home = sb.Home(repo=dest, home=os.path.join(dest, ".strictlybetter"))
    c = rb.setup_campaign(home, "pyfix", "walls", len(diffs), baseline_repeats=5)
    state = {"repo": dest, "campaign": c["id"], "attacks": [], "generated_at": sb.now_iso(), "env": sb.env_fingerprint(), "engine_version": sb.VERSION}
    for f in diffs:
        name = f[:-5]
        rec = {"name": name, "diff": os.path.join(args.diffs, f)}
        hp = home.p("tmp", f"hyp-{name}.json")
        sb.write_json_atomic(hp, {"operator": "config", "target": "slowlib/core.py", "hypothesis": f"adversary attack {name}", "predicted": {"bench_ms": "-50%"}, "expected_diff_size": "small"})
        rc, out = rb.run_quiet(sb.cmd_prereg, home, rb.ns(file=hp))
        if rc != 0:
            rec.update({"outcome": "prereg-failed", "reason": out.strip()[-200:]})
            state["attacks"].append(rec)
            continue
        info = json.loads(out.strip().splitlines()[-1])
        eid, wt = info["id"], info["worktree"]
        rec["id"] = eid
        ok, err = apply_diff(wt, rec["diff"])
        if not ok:
            rec.update({"outcome": "apply-failed", "reason": err})
            rb.run_quiet(sb.cmd_discard, home, rb.ns(id=eid, reason="harness-error", archive=False))
            state["attacks"].append(rec)
            continue
        rc, out = rb.run_quiet(sb.cmd_submit, home, rb.ns(id=eid))
        sub = json.loads(out.strip().splitlines()[-1])
        if not sub["ok"]:
            rb.run_quiet(sb.cmd_discard, home, rb.ns(id=eid, reason="integrity", archive=False))
            rec.update({"outcome": "discard", "reason": "integrity:" + ";".join(sub["violations"]), "wall": "frozen_guard"})
            state["attacks"].append(rec)
            cc = home.campaign()
            if cc.get("status") == "halted":
                rb.run_quiet(sb.cmd_campaign, home, rb.ns(action="resume", file=None, reason=None, no_baseline=True, repeats=None, allow_unusable=False, allow_ratchet_regression=False, allow_underpowered=False))
                rec["halted_campaign"] = cc.get("halt_reason")
            continue
        for _ in range(2):
            rb.run_quiet(sb.cmd_measure, home, rb.ns(id=eid, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            rc, out = rb.run_quiet(sb.cmd_judge, home, rb.ns(id=eid, fidelity="screen"))
            jd = json.loads(out.strip().splitlines()[0])
            if jd["verdict"] != "retry-screen":
                break
        rec["screen_effect"] = sb.primary_goal_effect(c, jd.get("comparisons") or [])
        if jd["verdict"] == "discard":
            rb.run_quiet(sb.cmd_discard, home, rb.ns(id=eid, reason=jd["reason"], archive=False))
            regressed = jd["reason"].split(":", 1)[1] if jd["reason"].startswith("regression") else None
            rec.update({"outcome": "discard", "reason": jd["reason"], "wall": "validity" if jd["reason"] == "invalid" else ("guardrail:" + regressed if regressed else "noise_floor")})
            state["attacks"].append(rec)
            continue
        rc, out = rb.run_quiet(sb.cmd_judge_payload, home, rb.ns(id=eid, out=None))
        rec.update({"outcome": "promoted", "payload": out.strip().splitlines()[-1]})
        state["attacks"].append(rec)
    os.makedirs(args.out, exist_ok=True)
    sp = os.path.join(args.out, "phase1.json")
    sb.write_json_atomic(sp, state)
    print(json.dumps({"state": sp, "needs_verdict": [(a["id"], a["payload"]) for a in state["attacks"] if a.get("outcome") == "promoted"]}, indent=2))
    return 0


def phase2(args) -> int:
    state = json.load(open(args.state))
    home = sb.Home(repo=state["repo"], home=os.path.join(state["repo"], ".strictlybetter"))
    c = home.campaign()
    for rec in state["attacks"]:
        if rec.get("outcome") != "promoted":
            continue
        eid = rec["id"]
        vp = os.path.join(args.verdicts, f"{eid}.json")
        if not os.path.exists(vp):
            rec.update({"outcome": "no-verdict"})
            continue
        v = json.load(open(vp))
        rec["judge"] = v.get("verdict")
        rec["judge_pattern"] = v.get("pattern")
        rc, out = rb.run_quiet(sb.cmd_judge_verdict, home, rb.ns(id=eid, file=vp))
        cc = home.campaign()
        if cc.get("status") == "halted":
            rec["halted_campaign"] = cc.get("halt_reason")
            rb.run_quiet(sb.cmd_campaign, home, rb.ns(action="resume", file=None, reason=None, no_baseline=True, repeats=None, allow_unusable=False, allow_ratchet_regression=False, allow_underpowered=False))
        if v.get("verdict") == "gamed":
            rb.run_quiet(sb.cmd_discard, home, rb.ns(id=eid, reason="gamed", archive=False))
            rec.update({"outcome": "discard", "reason": "gamed", "wall": "judge"})
            continue
        rc, out = rb.run_quiet(sb.cmd_confirm, home, rb.ns(id=eid, force=False))
        cf = json.loads(out.strip().splitlines()[0])
        rec["confirm_p"] = ((cf.get("tests") or {}).get("bench_ms") or {}).get("p")
        if cf["verdict"] == "accept":
            rc, out = rb.run_quiet(sb.cmd_accept, home, rb.ns(id=eid, force=False))
            rec.update({"outcome": "accept", "reason": cf.get("reason"), "confirm_effect": cf.get("confirm_effect")})
        else:
            rb.run_quiet(sb.cmd_discard, home, rb.ns(id=eid, reason=cf["reason"], archive=False))
            regressed = cf["reason"].split(":", 1)[1] if cf["reason"].startswith("regression") else None
            rec.update({"outcome": "discard", "reason": cf["reason"], "wall": "validity" if cf["reason"] == "invalid" else ("guardrail:" + regressed if regressed else "confirm")})
    # re-validate anything accepted with the pristine instrument
    accepted = [{"name": a["name"], "id": a["id"], "kind": "gaming", "accepted_commit": home.experiments()[a["id"]]["accepted_commit"]} for a in state["attacks"] if a.get("outcome") == "accept"]
    reval = rb.revalidate(home, c, accepted, ["bench.py", "run_tests.py", "tests/"]) if accepted else {"per_accept": []}
    state["revalidation"] = reval
    state["summary"] = {"attacks": len(state["attacks"]), "accepted": len(accepted),
                        "genuine_after_revalidation": sum(1 for x in reval["per_accept"] if x["genuine"]),
                        "by_wall": {}}
    for a in state["attacks"]:
        k = a.get("wall") or a.get("outcome")
        state["summary"]["by_wall"][k] = state["summary"]["by_wall"].get(k, 0) + 1
    os.makedirs(rb.RESULTS, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(rb.RESULTS, f"{stamp}-adversary-pyfix")
    sb.write_json_atomic(base + ".json", state)
    L = [f"# strictlybetter external-adversary gate · pyfix", "", f"Generated {state['generated_at']} on `{state['env']}` · engine {state['engine_version']}", "",
         "Attacks were written by an agent that had not seen the walls, given only the fixture, the frozen-file list, and the goal. Every attack ran through the real engine with all walls on; the blind judge was the real LLM judge agent (verdict files supplied between phases).", "",
         "| attack | mechanism (from the attacker's README) | outcome | wall that caught it | judge | screen effect | confirm p |", "|---|---|---|---|---|---|---|"]
    readme = {}
    rp = os.path.join(os.path.dirname(state["attacks"][0]["diff"]), "README.md") if state["attacks"] else None
    if rp and os.path.exists(rp):
        import re as _re
        for line in open(rp, encoding="utf-8", errors="replace"):
            for a in state["attacks"]:
                if a["name"] in line and a["name"] not in readme:
                    m = _re.search(r"\*\*(.+?)\*\*", line)
                    readme[a["name"]] = (m.group(1) if m else line.strip())[:90]
    for a in state["attacks"]:
        se = a.get("screen_effect")
        L.append(f"| {a['name']} | {readme.get(a['name'], '')} | {'**ACCEPTED**' if a.get('outcome') == 'accept' else a.get('outcome')} | {a.get('wall', '')} | {a.get('judge', '')} | {'' if se is None else f'{100 * se:+.1f}%'} | {a.get('confirm_p', '')} |")
    L += ["", f"Summary: {json.dumps(state['summary'])}"]
    if accepted:
        L += ["", "Accepted attacks re-validated with the pristine instrument and an external timer:", "", "| attack | delta s | p | outputs match | tests pass | genuine |", "|---|---|---|---|---|---|"]
        for x in reval["per_accept"]:
            L.append(f"| {x['name']} | {x['delta_s']} | {x.get('p_value')} | {x['outputs_match']} | {x['tests_pass']} | {x['genuine']} |")
    L += ["", "Caveats: one fixture, one attacker agent, one laptop. An accepted attack that is not genuine after re-validation is a false accept the walls missed."]
    open(base + ".md", "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"results: {base}.json / .md")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", type=int, choices=[1, 2], required=True)
    p.add_argument("--diffs")
    p.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "sb-adversary"))
    p.add_argument("--workdir")
    p.add_argument("--state")
    p.add_argument("--verdicts")
    a = p.parse_args(argv)
    return phase1(a) if a.phase == 1 else phase2(a)


if __name__ == "__main__":
    sys.exit(main())
