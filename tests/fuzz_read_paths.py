#!/usr/bin/env python3
"""Fuzz gate (RELEASE_PROTOCOL.md section 4.7): read paths degrade, they never brick.

Builds one small VALID state home in-process with the engine's own functions (Home, save_card,
save_campaign, save_baseline, save_ratchet, save_bandit, ledger_add), then for N random states
resets the home, applies ONE corruption to ONE file, and runs every read command handler
in-process with stdout/stderr captured:

    status, next, report, budget, ledger view|tail|experiments, card list|validate|show,
    campaign show, profile show, inheritance show, worktree path|list, guard (argv and --stdin),
    session-start, doctor, drive (one cycle of `true`), and distill-stats (mutating, read-heavy;
    always run last within a state).

A crash is any exception other than sb.SBError escaping a handler, or a handler that does not
return within --timeout seconds. SystemExit is counted separately as an "exit" (section 4.7
accepts it) and is not a crash. The pristine state is run first as a control: a crash there
aborts with exit 2, because the fixture itself would be wrong.

Corruption families (weights in FAMILIES): ledger.jsonl (torn line, garbage line, duplicated
events, unknown events, non-dict data, non-object lines, non-string ids, wrong-typed fields,
shuffled order, a non-UTF-8 byte), campaign.json, baseline.json, ratchet.json, bandit.json, a
metric card, profile.json (each: delete a key, wrong-type a value at a random depth including
NaN/Infinity/huge ints, whole-file replacement with a list/string/number/null/{}, empty file,
garbage bytes, non-UTF-8 bytes, truncation, concatenated objects, absurd nesting depth), and a
small misc family (inheritance.md as a directory, reports/ as a file).

Usage:
    python3 tests/fuzz_read_paths.py --states 500 [--seed 1] [--timeout 10]
    python3 tests/fuzz_read_paths.py --seed 1 --replay 137        # re-run one state verbosely
    python3 tests/fuzz_read_paths.py --states 500 --keep DIR      # copy each crashing home to DIR

Exit 0 when M == 0, exit 1 otherwise. Prints `fuzz: N states, M crashes` as the last line.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "scripts", "sb.py")


def load_sb():
    spec = importlib.util.spec_from_file_location("sb", SB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sb = load_sb()

# ----------------------------------------------------------------------------------------
# Pristine state, built with the engine's own writers
# ----------------------------------------------------------------------------------------
COMMIT = "0123456789abcdef0123456789abcdef01234567"
ACCEPTED = "89abcdef0123456789abcdef0123456789abcdef"


def build_pristine(td):
    repo = os.path.join(td, "repo")
    os.makedirs(repo)
    # the engine's own git wrapper: it disables the user's global hooks, which would otherwise run on every commit
    sb.git(["init", "-q", "-b", "main"], repo)
    sb.git(["config", "user.email", "f@f"], repo)
    sb.git(["config", "user.name", "fuzz"], repo)
    with open(os.path.join(repo, "work.py"), "w") as f:
        f.write("N = 40\n")
    sb.git(["add", "-A"], repo)
    sb.git(["-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"], repo)
    home = sb.Home(repo=repo, home=os.path.join(repo, ".strictlybetter"))
    home.ensure()
    noise = {"sigma": 0.5, "samples": 5, "method": "mad-scaled", "measured_at": COMMIT, "environment_fingerprint": sb.env_fingerprint()}
    probe = {"monotonic": True, "detail": "40 -> 60", "at": sb.now_iso(), "commit": COMMIT}
    cards = [
        {"id": "score", "kind": "goal", "direction": "minimize", "unit": "ms", "measure": {"command": "python3 bench.py", "parse": "metric-line:score", "timeout_s": 60},
         "fidelity": {"screen": {"repeats": 1}, "confirm": {"repeats": 3, "max_repeats": 5, "holdout": {"kind": "env", "var": "SB_SEED", "values": [7, 8, 9]}}},
         "integrity": {"frozen_paths": ["bench.py", "tests/"]}, "gaming_risks": ["edit bench"], "contention_safe": True, "acceptance": {"kappa": 2.5, "tolerance_sigma": 1.0},
         "degradation": {"apply": "true"}, "noise": noise, "probe": probe},
        {"id": "tests_failed", "kind": "guardrail", "direction": "minimize", "measure": {"command": "python3 tests/t.py", "parse": "metric-line:tests_failed", "timeout_s": 60},
         "integrity": {"frozen_paths": ["tests/"]}, "gaming_risks": ["delete tests"], "contention_safe": True, "acceptance": {"tolerance_sigma": 0}, "noise": noise, "probe": probe},
        {"id": "checks", "kind": "guardrail", "direction": "equal", "measure": {"command": "python3 bench.py", "parse": "metric-line:checks", "timeout_s": 60},
         "gaming_risks": ["hard-code"], "contention_safe": True, "noise": {**noise, "sigma": 0.0}, "probe": probe},
        {"id": "loc", "kind": "diagnostic", "direction": "minimize", "measure": {"command": "wc -l work.py", "parse": "regex:(\\d+)", "timeout_s": 30},
         "gaming_risks": ["diagnostic only"], "contention_safe": True},
    ]
    for cd in cards:
        sb.validate_card(cd)
        home.save_card(cd)
    walls = {k: True for k in sb.WALL_KEYS}
    c = {
        "id": "fuzz", "goals": ["score"], "guardrails": ["tests_failed", "checks"], "diagnostics": ["loc"],
        "composition": "pareto", "oec_weights": {}, "budget": {"experiments": 10, "hours": 1.0, "dollars": 5.0},
        "spent": {"experiments": 3, "wall_s": 12.5, "dollars": 0.02, "tokens_in": 1000, "tokens_out": 200},
        "plateau_patience": 3, "protected_paths": ["secrets/"], "frozen_paths": [], "branch": "sb/fuzz", "status": "running", "halt_reason": None,
        "walls": walls, "iteration_cap": 200, "max_parallel": 2, "distill_every": 8,
        "false_promotion_budget": {"window": sb.FP_WINDOW, "max_fraction": sb.FP_MAX_FRACTION}, "pricing": dict(sb.DEFAULT_PRICING),
        "started_at": sb.now_iso(), "base_commit": COMMIT, "head_commit": ACCEPTED, "exploration_level": 0, "since_last_accept": 1,
        "accepted_ids": ["e0001"], "acceptances_since_rotation": 1, "consecutive_integrity": 0, "consecutive_gamed": 0, "consecutive_errors": 0,
        "screen_repeats_multiplier": 1, "screen_untrusted": False, "next_id": 4, "holdout_override": {}, "notes": "", "archetype_priors": {},
        "frozen_paths_effective": ["bench.py", "tests/"], "eval_hash": "e" * 64, "mde": {"score": 0.05}, "confirmed_effects": [0.2], "holdout_gaps": [0.1],
        "last_distill": {"at": sb.now_iso(), "experiments": 2, "decision": "continue"},
    }
    home.save_campaign(c)

    def lvl(med, sig, n=5, secs=0.1):
        return {"median": med, "sigma": sig, "n": n, "values": [med] * n, "secs_per_run": secs, "invalid": []}

    b = {
        "score": {"levels": {"screen": lvl(40.0, 0.5), "confirm": lvl(40.0, 0.5)}, "best": 40.0, "sigma": 0.5, "commit": ACCEPTED, "env_fingerprint": sb.env_fingerprint(), "measured_at": sb.now_iso(), "quarantined": False},
        "tests_failed": {"levels": {"screen": lvl(0.0, 0.0), "confirm": lvl(0.0, 0.0)}, "best": 0.0, "sigma": 0.0, "commit": ACCEPTED, "env_fingerprint": sb.env_fingerprint(), "measured_at": sb.now_iso(), "quarantined": False},
        "checks": {"levels": {"screen": lvl("None=ok", 0.0, 1), "confirm": lvl("7=ok|8=ok|9=ok", 0.0, 3)}, "best": "7=ok|8=ok|9=ok", "sigma": 0.0, "commit": ACCEPTED, "env_fingerprint": sb.env_fingerprint(), "measured_at": sb.now_iso(), "quarantined": False},
        "loc": {"levels": {"screen": lvl(1.0, 0.0, 1), "confirm": lvl(1.0, 0.0, 1)}, "best": 1.0, "sigma": 0.0, "commit": ACCEPTED, "env_fingerprint": sb.env_fingerprint(), "measured_at": sb.now_iso(), "quarantined": False},
    }
    home.save_baseline(b)
    home.save_ratchet({"score": {"best": 40.0, "sigma": 0.5, "commit": ACCEPTED, "campaign": "fuzz", "direction": "minimize"}})
    home.save_bandit({"operators": {"algorithmic": {"alpha": 4, "beta": 3, "attempts": 2, "accepts": 1, "effect_sum": 0.2, "cost_s": 1.0},
                                    "config": {"alpha": 2, "beta": 4, "attempts": 1, "accepts": 0, "effect_sum": 0.0, "cost_s": 0.5}}})
    sb.write_json_atomic(home.profile_path, {"archetypes": [{"id": "python-lib", "confidence": 0.9}], "commands": {"test": "true", "build": ""},
                                             "purpose": "fuzz fixture", "protected_paths": ["secrets/"], "constraints": [], "written_at": sb.now_iso(), "commit": COMMIT})
    with open(home.p("inheritance.md"), "w") as f:
        f.write("# inheritance\n\n## What worked\n\n- nothing yet\n")
    # ledger: one accepted, one discarded, one open experiment, plus campaign events
    L = home.ledger_add
    L("campaign", "start", {"id": "fuzz", "goals": ["score"], "guardrails": ["tests_failed", "checks"], "walls": walls, "commit": COMMIT, "eval_hash": "e" * 64})
    L("campaign", "baseline", {"commit": COMMIT, "metrics": ["score", "tests_failed", "checks", "loc"], "repeats": 5, "levels": ["screen", "confirm"]})
    comp = {"id": "score", "kind": "goal", "direction": "minimize", "valid": True, "value": 20.0, "baseline": 40.0, "sigma": 0.5, "delta": 20.0, "delta_sigma": 40.0,
            "rel": 0.5, "improved": True, "regressed": False, "inconclusive": False, "threshold": 1.5, "note": None, "se_factor": 0.73}
    meas = {"score": {"n": 1, "n_valid": 1, "values": [20.0], "invalid": [], "secs_total": 0.1, "median": 20.0, "sigma": None, "valid": True, "fidelity": "screen"},
            "tests_failed": {"n": 1, "n_valid": 1, "values": [0.0], "invalid": [], "secs_total": 0.1, "median": 0.0, "sigma": None, "valid": True, "fidelity": "screen"},
            "checks": {"n": 1, "n_valid": 1, "values": ["ok"], "invalid": [], "secs_total": 0.1, "median": "None=ok", "sigma": 0.0, "valid": True, "fidelity": "screen"}}
    for eid, op, hyp in (("e0001", "algorithmic", "halve N"), ("e0002", "config", "tweak"), ("e0003", "caching", "memo")):
        L(eid, "prereg", {"campaign": "fuzz", "operator": op, "target": "work.py", "hypothesis": hyp, "predicted": {"score": "-10%"}, "expected_diff_size": "small",
                          "mechanism": "", "prereg_hash": "abcd1234abcd1234", "worktree": home.p("wt", eid), "base_commit": COMMIT, "exploration_level": 0})
        L(eid, "submit", {"commit": ACCEPTED if eid == "e0001" else "f" * 40, "diff_hash": "0123456789abcdef", "diff_lines": 4, "new_deps": [], "files": ["work.py"],
                          "integrity_ok": True, "integrity_violations": []})
        L(eid, "measure", {"fidelity": "screen", "results": meas, "wall_s": 0.3})
        L(eid, "cost", {"tokens_in": 500, "tokens_out": 100, "wall_s": 3.0, "dollars": 0.005, "tier": "low", "estimated": True})
    L("e0001", "judge", {"level": "screen", "verdict": "promote", "reason": "improved:score", "improved": ["score"], "regressed": [], "invalid": [], "score": None,
                         "anomaly": False, "kappa_eff": 2.56, "comparisons": [comp]})
    L("e0001", "verdict", {"verdict": "clean", "pattern": "", "evidence": "", "recommended_check": "", "judge": "sb-judge"})
    L("e0001", "confirm", {"verdict": "accept", "reason": "improved:score", "level": "confirm", "rounds": 1, "anomaly_extra_repeats": False, "screen_effect": 0.5,
                           "confirm_effect": 0.48, "comparisons": [comp], "results": meas, "kappa_eff": 2.56})
    L("e0001", "accept", {"reason": "confirmed", "accepted_commit": ACCEPTED, "branch": "sb/fuzz"})
    L("e0002", "judge", {"level": "screen", "verdict": "discard", "reason": "regression:tests_failed", "improved": [], "regressed": ["tests_failed"], "invalid": [],
                         "score": None, "anomaly": False, "kappa_eff": 2.56, "comparisons": [comp]})
    L("e0002", "confirm", {"verdict": "discard", "reason": "noise", "level": "confirm", "rounds": 2, "comparisons": [comp], "results": meas, "confirm_effect": 0.01})
    L("e0002", "discard", {"reason": "regression:tests_failed", "archived": True, "archive_key": "config|work.py"})
    L("e0003", "retry", {"level": "screen"})
    L("campaign", "explore", {"level": 1})
    os.makedirs(home.p("wt", "e0003"), exist_ok=True)
    with open(home.p("archive", "e0002.diff"), "w") as f:
        f.write("--- a/work.py\n+++ b/work.py\n")
    return repo, home.path


def snapshot(home_path):
    files = {}
    for dp, dn, fn in os.walk(home_path):
        for name in fn:
            p = os.path.join(dp, name)
            with open(p, "rb") as f:
                files[os.path.relpath(p, home_path)] = f.read()
    return files


def reset(home_path, files):
    shutil.rmtree(home_path, ignore_errors=True)
    for d in ["metrics", "wt", "archive", "holdout", "inbox", "tmp", "cache", "reports", os.path.join("wt", "e0003")]:
        os.makedirs(os.path.join(home_path, d), exist_ok=True)
    for rel, data in files.items():
        p = os.path.join(home_path, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


# ----------------------------------------------------------------------------------------
# Corruption recipes. Each returns a one-line, reproducible description.
# ----------------------------------------------------------------------------------------
WRONG_VALUES = [None, "", "garbage", "0", "-1", 0, -1, 3.5, float("inf"), float("-inf"), float("nan"), True, False, [], [1, 2], ["x"], {}, {"a": 1}, 10 ** 30, -(10 ** 30)]


def jrepr(v):
    try:
        return json.dumps(v)
    except (TypeError, ValueError):
        return repr(v)


def json_paths(obj, prefix=(), depth=0):
    if depth > 4:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield prefix + (k,)
            yield from json_paths(v, prefix + (k,), depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield prefix + (i,)
            yield from json_paths(v, prefix + (i,), depth + 1)


def jpath(p):
    return "$" + "".join(f"[{x}]" if isinstance(x, int) else f".{x}" for x in p)


def get_at(obj, p):
    for x in p:
        obj = obj[x]
    return obj


def set_at(obj, p, v):
    parent = get_at(obj, p[:-1])
    parent[p[-1]] = v


def del_at(obj, p):
    parent = get_at(obj, p[:-1])
    del parent[p[-1]]


def mutate_json_tree(obj, rng):
    """One structural mutation on a parsed JSON document. Returns (new_obj, description)."""
    paths = list(json_paths(obj))
    op = rng.choice(["delete", "wrongtype", "wrongtype", "wrongtype", "swap-container", "root"])
    if op == "root" or not paths:
        v = rng.choice([[], [1, 2], "garbage", 0, None, True, {}, {"garbage": 1}])
        return v, f"set $ = {jrepr(v)}"
    p = rng.choice(paths)
    if op == "delete":
        del_at(obj, p)
        return obj, f"delete {jpath(p)}"
    if op == "swap-container":
        cur = get_at(obj, p)
        if isinstance(cur, dict):
            v = list(cur.values())
        elif isinstance(cur, list):
            v = {str(i): x for i, x in enumerate(cur)}
        else:
            v = [cur]
        set_at(obj, p, v)
        return obj, f"set {jpath(p)} = {jrepr(v)[:80]}"
    v = rng.choice(WRONG_VALUES)
    set_at(obj, p, v)
    return obj, f"set {jpath(p)} = {jrepr(v)}"


def corrupt_json_file(path, rng):
    rel = os.path.basename(path)
    kind = rng.choices(["tree", "tree", "tree", "tree", "file"], k=1)[0]
    with open(path, "rb") as f:
        raw = f.read()
    if kind == "tree":
        obj = json.loads(raw.decode("utf-8"))
        obj, desc = mutate_json_tree(obj, rng)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=isinstance(obj, dict))
        return f"{rel}: {desc}"
    fk = rng.choice(["empty", "garbage", "non-utf8", "truncate", "concat", "deep", "whitespace", "bom"])
    if fk == "empty":
        data, desc = b"", "empty file"
    elif fk == "garbage":
        data, desc = b"{\x00\xff not json", "garbage bytes"
    elif fk == "non-utf8":
        data, desc = raw[:-2] + b'\xff\xfe' + raw[-2:] if len(raw) > 2 else b'"\xff"', "non-UTF-8 byte inside otherwise valid JSON"
        if not raw.strip().startswith(b"{"):
            data = b'"\xff"'
        else:
            data = b'{"\xff": 1, ' + raw.strip()[1:] if raw.strip() != b"{}" else b'{"\xff": 1}'
    elif fk == "truncate":
        k = rng.randrange(1, max(2, len(raw)))
        data, desc = raw[:k], f"truncate at byte {k}"
    elif fk == "concat":
        data, desc = raw + raw, "two JSON documents concatenated"
    elif fk == "deep":
        data, desc = b"[" * 100000 + b"]" * 100000, "100000-deep nested list"
    elif fk == "whitespace":
        data, desc = b"   \n\t  ", "whitespace only"
    else:
        data, desc = b"\xef\xbb\xbf" + raw, "UTF-8 BOM prefix"
    with open(path, "wb") as f:
        f.write(data)
    return f"{rel}: {desc}"


def corrupt_ledger(path, rng):
    with open(path, "rb") as f:
        raw = f.read()
    lines = raw.decode("utf-8").splitlines()
    k = rng.randrange(len(lines))
    ev = json.loads(lines[k])
    op = rng.choice(["torn-mid", "torn-mid", "garbage-line", "dup-line", "dup-all", "unknown-event", "data-nondict", "line-nonobject", "id-nonstring",
                     "field-mutate", "field-mutate", "field-mutate", "shuffle", "non-utf8", "nul-byte", "missing-key", "event-nonstring", "huge-line", "ts-wrong"])
    if op == "torn-mid":
        cut = rng.randrange(1, len(lines[k]))
        lines[k] = lines[k][:cut]
        desc = f"truncate line {k + 1} ({ev.get('event')}) at char {cut}"
    elif op == "garbage-line":
        lines.insert(k, "{garbage, not json")
        desc = f"insert garbage line before line {k + 1}"
    elif op == "dup-line":
        lines.insert(k, lines[k])
        desc = f"duplicate line {k + 1} ({ev.get('id')}/{ev.get('event')})"
    elif op == "dup-all":
        lines = lines + lines
        desc = "duplicate the entire ledger"
    elif op == "unknown-event":
        ev["event"] = rng.choice(["zzz", "", "prereg2", "ACCEPT"])
        lines.insert(k + 1, json.dumps(ev))
        desc = f"append unknown event {jrepr(ev['event'])} for {ev.get('id')} after line {k + 1}"
    elif op == "data-nondict":
        ev["data"] = rng.choice(["str", 5, None, [], [1], True])
        lines[k] = json.dumps(ev)
        desc = f"line {k + 1} ({ev.get('id')}/{ev.get('event')}): data = {jrepr(ev['data'])}"
    elif op == "line-nonobject":
        v = rng.choice(["[1, 2]", "42", '"x"', "null", "true", "[]", "{}"])
        lines[k] = v
        desc = f"replace line {k + 1} with {v}"
    elif op == "id-nonstring":
        ev["id"] = rng.choice([5, ["e1"], {"a": 1}, None, True, 3.5])
        lines[k] = json.dumps(ev)
        desc = f"line {k + 1} ({ev.get('event')}): id = {jrepr(ev['id'])}"
    elif op == "event-nonstring":
        ev["event"] = rng.choice([5, ["accept"], {"a": 1}, None])
        lines[k] = json.dumps(ev)
        desc = f"line {k + 1} ({ev.get('id')}): event = {jrepr(ev['event'])}"
    elif op == "missing-key":
        key = rng.choice(["id", "event", "data", "ts"])
        ev.pop(key, None)
        lines[k] = json.dumps(ev)
        desc = f"line {k + 1}: delete key {key}"
    elif op == "ts-wrong":
        ev["ts"] = rng.choice([5, None, [], "not a time"])
        lines[k] = json.dumps(ev)
        desc = f"line {k + 1}: ts = {jrepr(ev['ts'])}"
    elif op == "field-mutate":
        if not isinstance(ev.get("data"), dict) or not ev["data"]:
            ev["data"] = rng.choice(["str", 5, None, [1]])
            desc = f"line {k + 1} ({ev.get('id')}/{ev.get('event')}): data = {jrepr(ev['data'])}"
        else:
            ev["data"], d = mutate_json_tree(ev["data"], rng)
            desc = f"line {k + 1} ({ev.get('id')}/{ev.get('event')}): data {d}"
        lines[k] = json.dumps(ev)
    elif op == "shuffle":
        rng.shuffle(lines)
        desc = "shuffle all lines (event order lost)"
    elif op == "non-utf8":
        with open(path, "wb") as f:
            f.write(raw + b'{"ts": "x", "id": "e0001", "event": "cost", "data": {"tier": "\xff"}}\n')
        return "ledger.jsonl: append a line with a non-UTF-8 byte"
    elif op == "nul-byte":
        with open(path, "wb") as f:
            f.write(raw[:len(raw) // 2] + b"\x00" + raw[len(raw) // 2:])
        return "ledger.jsonl: NUL byte at the midpoint"
    else:  # huge-line
        ev["data"] = {"blob": "x" * 1_000_000}
        lines.insert(k + 1, json.dumps(ev))
        desc = f"append a 1 MB event for {ev.get('id')} after line {k + 1}"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return "ledger.jsonl: " + desc


def corrupt_misc(home_path, rng):
    op = rng.choice(["inheritance-dir", "reports-file", "metrics-json-dir", "metrics-junk", "card-file-missing", "stop-dir"])
    if op == "inheritance-dir":
        p = os.path.join(home_path, "inheritance.md")
        os.remove(p)
        os.makedirs(p)
        return "misc: inheritance.md is a directory"
    if op == "reports-file":
        p = os.path.join(home_path, "reports")
        shutil.rmtree(p, ignore_errors=True)
        with open(p, "w") as f:
            f.write("x")
        return "misc: reports is a regular file"
    if op == "metrics-json-dir":
        os.makedirs(os.path.join(home_path, "metrics", "dirlike.json"))
        return "misc: metrics/dirlike.json is a directory"
    if op == "metrics-junk":
        with open(os.path.join(home_path, "metrics", "bad id!.json"), "w") as f:
            f.write("{}")
        return "misc: metrics/'bad id!.json' (id fails the id regex, content {})"
    if op == "card-file-missing":
        os.remove(os.path.join(home_path, "metrics", "score.json"))
        return "misc: metrics/score.json deleted while campaign.json still names it"
    p = os.path.join(home_path, "STOP")
    os.makedirs(p)
    return "misc: STOP is a directory"


FAMILIES = [("ledger", 26), ("campaign", 24), ("baseline", 12), ("card", 12), ("profile", 9), ("bandit", 8), ("ratchet", 4), ("misc", 5)]


def corrupt(home_path, rng):
    fam = rng.choices([f for f, _ in FAMILIES], weights=[w for _, w in FAMILIES], k=1)[0]
    if fam == "ledger":
        return corrupt_ledger(os.path.join(home_path, "ledger.jsonl"), rng)
    if fam == "card":
        mid = rng.choice(["score", "tests_failed", "checks", "loc"])
        return "metrics/" + corrupt_json_file(os.path.join(home_path, "metrics", f"{mid}.json"), rng)
    if fam == "misc":
        return corrupt_misc(home_path, rng)
    return corrupt_json_file(os.path.join(home_path, f"{fam}.json"), rng)


# ----------------------------------------------------------------------------------------
# Read paths and the in-process runner
# ----------------------------------------------------------------------------------------
def read_paths(repo, home_path):
    return [
        ["status"], ["status", "--json"],
        ["next"], ["next", "--json", "--seed", "1"],
        ["report"], ["budget"],
        ["ledger", "view", "e0001"], ["ledger", "view", "e0002"], ["ledger", "view", "e0002", "--unredacted"], ["ledger", "tail", "-n", "5"], ["ledger", "experiments"],
        ["card", "list"], ["card", "validate", "score"], ["card", "validate", "checks"], ["card", "show", "score"],
        ["campaign", "show"], ["profile", "show"], ["inheritance", "show"],
        ["worktree", "path", "e0003"], ["worktree", "list"],
        ["guard", os.path.join(repo, "work.py")], ["guard", os.path.join(home_path, "wt", "e0003", "bench.py")], ["guard", "--stdin"],
        ["session-start"], ["doctor"],
        ["drive", "--command", "true", "--cycles", "1", "--timeout", "5"],
        ["distill-stats", "--json"],  # mutating; keep last
    ]


GUARD_STDIN = json.dumps({"session_id": "s1", "tool_name": "Edit", "tool_input": {"file_path": "wt/e0003/bench.py"}})


class FuzzTimeout(BaseException):
    pass


def _on_alarm(signum, frame):
    raise FuzzTimeout()


@contextlib.contextmanager
def alarm(seconds):
    if not hasattr(signal, "setitimer"):
        yield
        return
    old = signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


_PARSER = None


def run_handler(repo, home_path, argv, timeout):
    """Returns (status, detail). status in ok|sberror|exit|crash|hang."""
    global _PARSER
    if _PARSER is None:
        _PARSER = sb.build_parser()
    home = sb.Home(repo=repo, home=home_path)
    args = _PARSER.parse_args(argv)
    handler = sb.HANDLERS[args.cmd]
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    if argv[-1] == "--stdin":
        sys.stdin = io.StringIO(GUARD_STDIN)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), alarm(timeout):
            try:
                handler(home, args)
                return "ok", ""
            except sb.SBError as e:
                return "sberror", str(e)
            except SystemExit as e:
                return "exit", str(e.code)
            except FuzzTimeout:
                return "hang", f"no return within {timeout}s"
            except BaseException:
                return "crash", traceback.format_exc()
    finally:
        sys.stdin = old_stdin


def signature(detail, status):
    """Root-cause key: (exception type, innermost engine frame as function:line)."""
    if status == "hang":
        return ("hang", "")
    lines = detail.strip().splitlines()
    exc = lines[-1].split(":")[0] if lines else "?"
    frame = ""
    for l in reversed(lines):
        m = re.search(r'sb\.py", line (\d+), in (\w+)', l)
        if m:
            frame = f"{m.group(2)}:{m.group(1)}"
            break
    return (exc, frame)


def handler_label(argv):
    if len(argv) > 1 and not argv[1].startswith(("-", "/")):
        return argv[0] + " " + argv[1]
    return argv[0]


def run_state(i, seed, timeout):
    """One fuzz state on this process's home. Returns (i, recipe, [(argv, status, detail)])."""
    repo, home_path, pristine, paths = _W["repo"], _W["home"], _W["pristine"], _W["paths"]
    rng = random.Random(f"{seed}:{i}")
    reset(home_path, pristine)
    recipe = corrupt(home_path, rng)
    results = []
    for argv_ in paths:
        st, detail = run_handler(repo, home_path, argv_, timeout)
        results.append((argv_, st, detail))
    return i, recipe, results


_W = {}


def _init_worker(td_root):
    td = tempfile.mkdtemp(prefix="w-", dir=td_root)
    repo, home_path = build_pristine(td)
    _W.update({"repo": repo, "home": home_path, "pristine": snapshot(home_path), "paths": read_paths(repo, home_path)})


def _pool_task(job):
    i, seed, timeout = job
    return run_state(i, seed, timeout)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--states", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds per handler before it counts as a hang")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)), help="worker processes (1 = in-process)")
    ap.add_argument("--replay", type=int, help="run only this state index, verbosely, in-process")
    ap.add_argument("--keep", help="directory to copy each crashing state home into (in-process runs only)")
    ap.add_argument("--max-list", type=int, default=80, help="cap on the per-state crash listing")
    a = ap.parse_args(argv)

    td = tempfile.mkdtemp(prefix="sb-fuzz-")
    try:
        _init_worker(td)
        repo, home_path, pristine, paths = _W["repo"], _W["home"], _W["pristine"], _W["paths"]
        # control: the pristine state must not crash anywhere
        reset(home_path, pristine)
        for argv_ in paths:
            st, detail = run_handler(repo, home_path, argv_, a.timeout)
            if st in ("crash", "hang"):
                print(f"CONTROL FAILED: pristine state crashes on `sb {' '.join(argv_)}`:\n{detail}")
                return 2
        indices = [a.replay] if a.replay is not None else list(range(a.states))
        crashes = []            # (state, recipe, argv, status, detail)
        by_sig = {}             # (exc, frame) -> [crash idx]
        states_hit = set()
        exits = 0

        def absorb(i, recipe, results):
            nonlocal exits
            for argv_, st, detail in results:
                if a.replay is not None:
                    print(f"  sb {' '.join(argv_)}: {st}" + (f" ({detail.strip().splitlines()[-1]})" if detail and st != "ok" else ""))
                if st == "exit":
                    exits += 1
                if st in ("crash", "hang"):
                    crashes.append((i, recipe, argv_, st, detail))
                    states_hit.add(i)
                    by_sig.setdefault(signature(detail, st), []).append(len(crashes) - 1)

        if a.replay is not None or a.jobs <= 1:
            for i in indices:
                i, recipe, results = run_state(i, a.seed, a.timeout)
                if a.replay is not None:
                    print(f"state {i}: {recipe}")
                absorb(i, recipe, results)
                if i in states_hit and a.keep:
                    dst = os.path.join(a.keep, f"state-{i}")
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(home_path, dst)
        else:
            import multiprocessing as mp
            ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() and sys.platform != "darwin" else mp.get_context("spawn")
            with ctx.Pool(processes=a.jobs, initializer=_init_worker, initargs=(td,)) as pool:
                for i, recipe, results in pool.imap_unordered(_pool_task, [(i, a.seed, a.timeout) for i in indices], chunksize=4):
                    absorb(i, recipe, results)
        n = len(indices)
        if crashes:
            print(f"\n{'=' * 100}\n{len(by_sig)} DISTINCT CRASH SIGNATURES (exception · innermost engine frame), most frequent first\n{'=' * 100}")
            for sig, idxs in sorted(by_sig.items(), key=lambda kv: -len(kv[1])):
                first = min(idxs, key=lambda j: crashes[j][0])
                i, recipe, argv_, st, detail = crashes[first]
                handlers = sorted({handler_label(crashes[j][2]) for j in idxs})
                recipes = sorted({crashes[j][1] for j in idxs})
                print(f"\n--- {sig[0]} at {sig[1]} · {len(idxs)} occurrence(s) in {len({crashes[j][0] for j in idxs})} state(s)")
                print(f"    handlers:  {', '.join(handlers)}")
                print(f"    recipe:    {recipe}")
                for o in [r for r in recipes if r != recipe][:5]:
                    print(f"    also:      {o}")
                print(f"    reproduce: python3 tests/fuzz_read_paths.py --seed {a.seed} --replay {i}")
                print("    " + "\n    ".join(detail.strip().splitlines()[-8:]))
            print(f"\n{'=' * 100}\nALL CRASHING STATES (state · recipe · handlers)\n{'=' * 100}")
            per_state = {}
            for i, recipe, argv_, st, detail in crashes:
                per_state.setdefault(i, (recipe, set()))[1].add(handler_label(argv_))
            for k, (i, (recipe, hs)) in enumerate(sorted(per_state.items())):
                if k >= a.max_list:
                    print(f"... and {len(per_state) - k} more states (raise --max-list)")
                    break
                print(f"state {i:4d} · {recipe} · {', '.join(sorted(hs))}")
            if a.keep and (a.replay is not None or a.jobs <= 1):
                print(f"\ncrashing state homes copied under {a.keep}")
        print(f"\nfuzz: {n} states, {len(crashes)} crashes ({len(states_hit)} states affected, {len(by_sig)} distinct signatures, {exits} SystemExit returns)")
        return 1 if crashes else 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
