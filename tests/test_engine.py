"""Unit tests for scripts/sb.py (stdlib unittest; no third-party deps).

Run:  python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "scripts", "sb.py")


def load_sb():
    spec = importlib.util.spec_from_file_location("sb", SB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sb = load_sb()
WALLS = {k: True for k in sb.WALL_KEYS}


class ParseTests(unittest.TestCase):
    def test_metric_line_last_wins(self):
        self.assertEqual(sb.parse_output("metric-line:x", "METRIC x=1\nMETRIC x=2\n"), 2.0)

    def test_metric_line_in_stderr(self):
        self.assertEqual(sb.parse_output("metric-line:x", "", "METRIC x=5"), 5.0)

    def test_metric_line_string(self):
        self.assertEqual(sb.parse_output("metric-line:h", "METRIC h=deadbeef"), "deadbeef")

    def test_regex_group(self):
        self.assertEqual(sb.parse_output(r"regex:(\d+) passed", "12 passed, 0 failed"), 12.0)

    def test_json_path(self):
        self.assertEqual(sb.parse_output("json:summary.total", 'log\n{"summary": {"total": 7}}'), 7.0)

    def test_missing_raises(self):
        with self.assertRaises(sb.SBError):
            sb.parse_output("metric-line:nope", "METRIC x=1")

    def test_unknown_spec(self):
        with self.assertRaises(sb.SBError):
            sb.parse_output("yaml:x", "")


class PathMatchTests(unittest.TestCase):
    def test_dir_prefix(self):
        self.assertTrue(sb.match_path("tests/a/b.py", "tests/"))
        self.assertFalse(sb.match_path("tests2/a.py", "tests/"))

    def test_exact_and_subtree(self):
        self.assertTrue(sb.match_path("bench.py", "bench.py"))
        self.assertTrue(sb.match_path("eval/x.py", "eval"))
        self.assertFalse(sb.match_path("evaluate.py", "eval"))

    def test_glob(self):
        self.assertTrue(sb.match_path("a/b/secret.pem", "*.pem"))
        self.assertTrue(sb.match_path("requirements-dev.txt", "requirements-*.txt"))


class AcceptanceRuleTests(unittest.TestCase):
    goal = {"id": "g", "kind": "goal", "direction": "minimize"}
    guard = {"id": "h", "kind": "guardrail", "direction": "maximize"}
    base = {"median": 100.0, "sigma": 4.0}

    def test_kappa_eff(self):
        self.assertAlmostEqual(sb.kappa_eff(2.5, 0, 0), 2.5)
        self.assertGreater(sb.kappa_eff(2.5, 500, 0), sb.kappa_eff(2.5, 50, 0))
        self.assertAlmostEqual(sb.kappa_eff(2.5, 0, 2), 4.5)

    def test_goal_threshold(self):
        c = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 89.0}, 2.5, 1.0, WALLS)
        self.assertTrue(c["improved"])           # delta 11 > 2.5*4
        c = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 91.0}, 2.5, 1.0, WALLS)
        self.assertFalse(c["improved"])          # delta 9 < 10
        self.assertTrue(c["inconclusive"])

    def test_guardrail_tolerance(self):
        c = sb.compare_metric(self.guard, self.base, {"valid": True, "median": 97.0}, 2.5, 1.0, WALLS)
        self.assertFalse(c["regressed"])         # drop 3 < 1*4
        c = sb.compare_metric(self.guard, self.base, {"valid": True, "median": 95.0}, 2.5, 1.0, WALLS)
        self.assertTrue(c["regressed"])          # drop 5 > 4

    def test_equal_direction(self):
        eq = {"id": "q", "kind": "guardrail", "direction": "equal"}
        self.assertFalse(sb.compare_metric(eq, {"median": "abc"}, {"valid": True, "median": "abc"}, 2.5, 0, WALLS)["regressed"])
        self.assertTrue(sb.compare_metric(eq, {"median": "abc"}, {"valid": True, "median": "abd"}, 2.5, 0, WALLS)["regressed"])

    def test_invalid_measurement(self):
        c = sb.compare_metric(self.goal, self.base, {"valid": False, "invalid": ["timeout"]}, 2.5, 1.0, WALLS)
        self.assertFalse(c["valid"])
        d = sb.decide({}, {"goals": ["g"], "guardrails": [], "walls": WALLS, "composition": "pareto"}, [c], "screen")
        self.assertEqual((d["verdict"], d["reason"]), ("discard", "invalid"))

    def test_naive_mode(self):
        naive = {**WALLS, "noise_floor": False}
        c = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 99.9}, 2.5, 1.0, naive)
        self.assertTrue(c["improved"])
        c = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 100.1}, 2.5, 1.0, naive)
        self.assertTrue(c["regressed"])

    def test_regression_beats_improvement(self):
        camp = {"goals": ["g"], "guardrails": ["h"], "walls": WALLS, "composition": "pareto"}
        cg = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 50.0}, 2.5, 1.0, WALLS)
        ch = sb.compare_metric(self.guard, self.base, {"valid": True, "median": 10.0}, 2.5, 1.0, WALLS)
        d = sb.decide({}, camp, [cg, ch], "confirm")
        self.assertEqual(d["verdict"], "discard")
        self.assertTrue(d["reason"].startswith("regression:h"))

    def test_oec_composition(self):
        camp = {"goals": ["g", "g2"], "guardrails": [], "walls": WALLS, "composition": "oec", "oec_weights": {"g": 1.0, "g2": 1.0}, "_kappa_eff": 2.5}
        g2 = {"id": "g2", "kind": "goal", "direction": "maximize"}
        c1 = sb.compare_metric(self.goal, self.base, {"valid": True, "median": 94.0}, 2.5, 1.0, WALLS)   # +1.5 sigma
        c2 = sb.compare_metric(g2, self.base, {"valid": True, "median": 106.0}, 2.5, 1.0, WALLS)         # +1.5 sigma
        d = sb.decide({}, camp, [c1, c2], "confirm")
        self.assertEqual(d["verdict"], "promote")   # 3.0 > 2.5 combined


class StatsTests(unittest.TestCase):
    def test_sigma(self):
        self.assertIsNone(sb.sigma_of([1.0]))
        self.assertAlmostEqual(sb.sigma_of([2.0, 4.0]), 1.4142135, places=5)

    def test_summarize_numeric_and_string(self):
        card = {"direction": "minimize"}
        s = sb.summarize([{"valid": True, "value": 1.0, "secs": 0.1}, {"valid": True, "value": 3.0, "secs": 0.1}, {"valid": False, "invalid_reason": "x", "secs": 0}], card)
        self.assertEqual(s["median"], 2.0)
        self.assertEqual(s["n_valid"], 2)
        eq = {"direction": "equal"}
        s = sb.summarize([{"valid": True, "value": "a", "secs": 0}, {"valid": True, "value": "b", "secs": 0}], eq)
        self.assertFalse(s["valid"])

    def test_gap_ratio(self):
        self.assertEqual(sb.gap_ratio(0.2, 0.1), 0.5)
        self.assertEqual(sb.gap_ratio(0.2, 0.3), 0.0)
        self.assertIsNone(sb.gap_ratio(0.0, 0.1))


class CardValidationTests(unittest.TestCase):
    def test_rejects_bad_cards(self):
        with self.assertRaises(sb.SBError):
            sb.validate_card({"id": "x", "kind": "goal", "direction": "up", "measure": {"command": "true", "parse": "metric-line:x"}})
        with self.assertRaises(sb.SBError):
            sb.validate_card({"id": "x", "kind": "goal", "direction": "minimize", "measure": {"command": "true", "parse": "yaml:x"}})
        with self.assertRaises(sb.SBError):
            sb.validate_card({"id": "bad id!", "kind": "goal", "direction": "minimize", "measure": {"command": "true", "parse": "metric-line:x"}})

    def test_fidelity_merge(self):
        card = {"id": "x", "kind": "goal", "direction": "minimize",
                "measure": {"command": "run", "parse": "metric-line:x", "env": {"A": "1"}, "timeout_s": 10},
                "fidelity": {"screen": {"env": {"A": "2"}}, "confirm": {"repeats": 3, "max_repeats": 6, "holdout": {"kind": "env", "var": "S", "values": [1]}}}}
        self.assertEqual(sb.fidelity_spec(card, "screen")["env"]["A"], "2")
        self.assertEqual(sb.fidelity_spec(card, "full")["env"]["A"], "1")
        conf = sb.fidelity_spec(card, "confirm")
        self.assertEqual((conf["repeats"], conf["max_repeats"]), (3, 6))
        self.assertEqual(conf["holdout"]["var"], "S")


class LedgerTests(unittest.TestCase):
    def test_torn_line_and_merge(self):
        with tempfile.TemporaryDirectory() as td:
            home = sb.Home(repo=td, home=os.path.join(td, ".sb"))
            home.ensure()
            home.ledger_add("e0001", "prereg", {"operator": "config", "target": "a", "hypothesis": "h", "predicted": {"m": "+1%"}})
            with open(home.ledger_path, "a") as f:
                f.write("{torn\n")
            home.ledger_add("e0001", "accept", {"reason": "confirmed", "accepted_commit": "abc"})
            recs = home.experiments()
            self.assertEqual(recs["e0001"]["verdict"], "accept")
            self.assertEqual(recs["e0001"]["operator"], "config")


class SelftestTests(unittest.TestCase):
    def test_selftest_passes(self):
        p = subprocess.run([sys.executable, SB, "selftest"], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        self.assertIn("checks passed", p.stdout)
        self.assertNotIn("FAIL", p.stdout)


if __name__ == "__main__":
    unittest.main()
