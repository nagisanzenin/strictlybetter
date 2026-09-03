"""End-to-end: the real engine CLI on the pyfix fixture, through subprocess.

Asserts only timing-robust outcomes (integrity, judge schema, guardrail regressions,
ledger/report/provenance shape). Timing-dependent acceptance is measured by
bench/run_bench.py, not asserted here.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "scripts", "sb.py")
FIX = os.path.join(ROOT, "tests", "fixtures")


def sb(repo, *args, check=True, stdin=None):
    p = subprocess.run([sys.executable, SB, "--repo", repo] + list(args), capture_output=True, text=True, input=stdin, timeout=900)
    if check and p.returncode != 0:
        raise AssertionError(f"sb {' '.join(args)} rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def last_json(p):
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise AssertionError("no JSON line in output:\n" + p.stdout)


class PyfixCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp(prefix="sb-fixtest-")
        cls.repo = os.path.join(cls.td, "pyfix")
        out = subprocess.run([sys.executable, os.path.join(FIX, "make_fixture.py"), "pyfix", cls.repo], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        sb(cls.repo, "init")
        cards = os.path.join(FIX, "pyfix", "fixture-cards")
        for f in sorted(os.listdir(cards)):
            sb(cls.repo, "card", "add", "--file", os.path.join(cards, f))
        spec = {"id": "fixtest", "goals": ["bench_ms"], "guardrails": ["tests_failed", "bench_checksum"], "diagnostics": ["loc"],
                "budget": {"experiments": 8}, "plateau_patience": 3}
        cp = os.path.join(cls.td, "campaign.json")
        json.dump(spec, open(cp, "w"))
        sb(cls.repo, "campaign", "start", "--file", cp, "--repeats", "3")

    def test_01_baseline_has_sigma_and_levels(self):
        b = json.load(open(os.path.join(self.repo, ".strictlybetter", "baseline.json")))
        self.assertIsNotNone(b["bench_ms"]["sigma"])
        self.assertIn("screen", b["bench_ms"]["levels"])
        self.assertIn("full", b["bench_ms"]["levels"])
        self.assertIn("confirm", b["bench_ms"]["levels"])
        self.assertTrue(b["bench_checksum"]["levels"]["confirm"]["median"].count("=") == 3)  # per-seed canonical form

    def test_02_probe_monotonic(self):
        p = sb(self.repo, "card", "probe", "bench_checksum", check=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(last_json(p)["monotonic"])

    def test_03_frozen_edit_is_caught_and_guard_denies(self):
        hp = os.path.join(self.td, "h1.json")
        json.dump({"operator": "config", "target": "bench.py", "hypothesis": "cheat", "predicted": {"bench_ms": "-99%"}}, open(hp, "w"))
        info = last_json(sb(self.repo, "prereg", "--file", hp))
        wt = info["worktree"]
        # guard: the hook path
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(wt, "bench.py")}})
        p = sb(self.repo, "guard", "--stdin", check=False, stdin=payload)
        self.assertEqual(p.returncode, 2)
        self.assertIn("frozen", p.stderr)
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(wt, "slowlib", "core.py")}})
        self.assertEqual(sb(self.repo, "guard", "--stdin", check=False, stdin=payload).returncode, 0)
        # gate-time integrity
        with open(os.path.join(wt, "bench.py"), "a") as f:
            f.write("\nprint('METRIC bench_ms=0.001')\n")
        p = sb(self.repo, "submit", info["id"], check=False)
        self.assertEqual(p.returncode, 1)
        sub = last_json(p)
        self.assertFalse(sub["ok"])
        self.assertTrue(any(v.startswith("frozen:bench.py") for v in sub["violations"]))
        sb(self.repo, "discard", info["id"], "--reason", "integrity")

    def test_04_wrong_output_is_a_guardrail_regression(self):
        hp = os.path.join(self.td, "h2.json")
        json.dump({"operator": "algorithmic", "target": "slowlib/core.py", "hypothesis": "set()", "predicted": {"bench_ms": "-10%"}}, open(hp, "w"))
        info = last_json(sb(self.repo, "prereg", "--file", hp))
        core = os.path.join(info["worktree"], "slowlib", "core.py")
        s = open(core).read()
        old = "    unique = []\n    for item in items:\n        if item not in unique:  # linear scan of the growing result list\n            unique.append(item)\n    return unique\n"
        self.assertIn(old, s)
        open(core, "w").write(s.replace(old, "    return list(set(items))\n"))
        self.assertTrue(last_json(sb(self.repo, "submit", info["id"]))["ok"])
        sb(self.repo, "measure", info["id"], "--fidelity", "screen")
        jd = json.loads(sb(self.repo, "judge", info["id"]).stdout.splitlines()[0])
        self.assertEqual(jd["verdict"], "discard")
        self.assertTrue(jd["reason"].startswith("regression:"), jd)
        sb(self.repo, "discard", info["id"], "--reason", jd["reason"], "--archive")
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".strictlybetter", "archive", info["id"] + ".diff")))

    def test_05_judge_verdict_schema(self):
        hp = os.path.join(self.td, "h3.json")
        json.dump({"operator": "docs", "target": "slowlib/core.py", "hypothesis": "comment", "predicted": {"bench_ms": "-1%"}}, open(hp, "w"))
        info = last_json(sb(self.repo, "prereg", "--file", hp))
        with open(os.path.join(info["worktree"], "slowlib", "core.py"), "a") as f:
            f.write("\n# noop\n")
        sb(self.repo, "submit", info["id"])
        vp = os.path.join(self.td, "v.json")
        json.dump({"verdict": "clean", "reasoning": "smuggled"}, open(vp, "w"))
        p = sb(self.repo, "judge-verdict", info["id"], "--file", vp, check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("forbidden", p.stderr)
        sb(self.repo, "discard", info["id"], "--reason", "manual")

    def test_06_status_next_report(self):
        st = json.loads(sb(self.repo, "status", "--json").stdout)
        self.assertEqual(st["campaign"], "fixtest")
        self.assertGreaterEqual(st["experiments"], 3)
        nx = json.loads(sb(self.repo, "next", "--json", "--seed", "1").stdout)
        self.assertIn("operator_mix", nx)
        self.assertEqual(nx["goals"], ["bench_ms"])
        rep = sb(self.repo, "report").stdout
        self.assertIn("# strictlybetter campaign report", rep)
        self.assertIn("Discarded", rep)
        self.assertEqual(sb(self.repo, "session-start").stdout.count("\n"), 1)

    def test_07_doctor_and_ledger(self):
        p = sb(self.repo, "ledger", "experiments")
        self.assertGreaterEqual(len(p.stdout.strip().splitlines()), 3)
        p = sb(self.repo, "doctor", check=False)
        self.assertIn("git: ok", p.stdout)


if __name__ == "__main__":
    unittest.main()
