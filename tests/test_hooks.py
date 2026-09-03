"""Hook replay tests: the four hook scripts driven exactly the way Claude Code drives them.

Each test runs a hook script from hooks/ through bash with CLAUDE_PLUGIN_ROOT set to this
repo and CLAUDE_PROJECT_DIR set to a throwaway pyfix fixture that has a running campaign,
feeding the JSON payload Claude Code sends on stdin. The fixture is built through the real
CLI (make_fixture.py -> sb init -> card add x4 -> campaign start --repeats 3, budget 6),
the same way tests/test_fixture_campaign.py builds its own.

Observed fail-open shape when python3 is unreachable (asserted in test_70/test_71):
  - session-start.sh, stop-driver.sh, pre-compact.sh: exit 0, print nothing.
  - frozen-guard.sh with a frozen-path payload while a campaign runs: exit 0, i.e. the edit is
    ALLOWED. With an empty PATH the script never reaches python: `cat` is missing, the payload
    reads as empty and the first guard `[ -n "$PAYLOAD" ] || exit 0` fires. With coreutils on
    PATH but no python3 it reaches `command -v python3 >/dev/null 2>&1 || exit 0` and exits 0
    there. Both are the documented fail-open of bug class 6 in RELEASE_PROTOCOL.md; these tests
    pin the shape so a change to it is a deliberate one.

Other documented behaviour pinned here rather than asserted as "correct":
  - A malformed (non-JSON) or empty PreToolUse payload exits 0 (guard --stdin finds no path).
  - stop_hook_active=true alone does not stop the driver; SB_DRIVER_HONOR_STOP_HOOK_ACTIVE=1 does.
  - The no-progress guard (SB_DRIVER_STALE_MAX, default 3) blocks on calls 1-3 with no new
    experiment and stops blocking on the 4th; a new experiment resets it.

Run:  python3 -m unittest tests.test_hooks -v
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "scripts", "sb.py")
HOOKS = os.path.join(ROOT, "hooks")
FIX = os.path.join(ROOT, "tests", "fixtures")
BASH = "/bin/bash"  # absolute on purpose: the no-python tests run with an empty PATH
STRIPPED_PREFIXES = ("SB_", "CLAUDE_", "ZCODE_", "CODEX_")


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


def hook_env(project, **extra):
    """The environment Claude Code gives a plugin hook, minus anything inherited that would steer the engine."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIPPED_PREFIXES)}
    env["CLAUDE_PLUGIN_ROOT"] = ROOT
    env["CLAUDE_PROJECT_DIR"] = project
    env.update(extra)
    return env


def run_hook(name, payload, project, env_extra=None, timeout=60):
    env = hook_env(project, **(env_extra or {}))
    data = payload if isinstance(payload, str) else json.dumps(payload)
    t0 = time.perf_counter()
    p = subprocess.run([BASH, os.path.join(HOOKS, name)], input=data, capture_output=True, text=True, env=env, cwd=project, timeout=timeout)
    p.secs = time.perf_counter() - t0
    return p


def edit_payload(path, tool="Edit", sid="s1", key="file_path"):
    return {"session_id": sid, "tool_name": tool, "tool_input": {key: path}}


def stop_payload(sid="s1", active=False):
    return {"session_id": sid, "stop_hook_active": active, "transcript_path": "/dev/null"}


COMPACT_PAYLOAD = {"session_id": "s1", "trigger": "auto"}
START_PAYLOAD = {"session_id": "s1", "source": "startup"}


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp(prefix="sb-hooktest-")
        cls.repo = os.path.join(cls.td, "pyfix")
        # a throwaway fixture: keep the user's global git hooks (secret scanners and the like) out of its commits
        no_hooks = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0="/dev/null")
        out = subprocess.run([sys.executable, os.path.join(FIX, "make_fixture.py"), "pyfix", cls.repo], capture_output=True, text=True, env=no_hooks)
        assert out.returncode == 0, out.stderr
        sb(cls.repo, "init")
        cards = os.path.join(FIX, "pyfix", "fixture-cards")
        for f in sorted(os.listdir(cards)):
            sb(cls.repo, "card", "add", "--file", os.path.join(cards, f))
        spec = {"id": "hooktest", "goals": ["bench_ms"], "guardrails": ["tests_failed", "bench_checksum"], "diagnostics": ["loc"],
                "budget": {"experiments": 6}, "plateau_patience": 3}
        cp = os.path.join(cls.td, "campaign.json")
        with open(cp, "w") as f:
            json.dump(spec, f)
        # --allow-unusable: the hooks do not care about the MDE and this suite may share the host with other gates
        sb(cls.repo, "campaign", "start", "--file", cp, "--repeats", "3", "--allow-unusable")
        cls.home = os.path.join(cls.repo, ".strictlybetter")
        cls.eid, cls.wt = cls.prereg("hook test: frozen edit target")
        # an unrelated project dir with no campaign at all
        cls.unrelated = os.path.join(cls.td, "unrelated")
        os.makedirs(cls.unrelated)
        with open(os.path.join(cls.unrelated, "notes.py"), "w") as f:
            f.write("x = 1\n")
        # a python3 shim that records every invocation and then behaves like the real python3
        cls.shim = os.path.join(cls.td, "shim")
        os.makedirs(cls.shim)
        shim = os.path.join(cls.shim, "python3")
        with open(shim, "w") as f:
            f.write(f'#!/bin/sh\nprintf \'python3 %s\\n\' "$*" >> "$SB_TEST_MARKER"\nexec "{sys.executable}" "$@"\n')
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    @classmethod
    def tearDownClass(cls):
        try:
            sb(cls.repo, "campaign", "end", check=False)
        finally:
            shutil.rmtree(cls.td, ignore_errors=True)

    @classmethod
    def prereg(cls, hypothesis):
        hp = os.path.join(cls.td, f"h-{int(time.time() * 1000)}.json")
        with open(hp, "w") as f:
            json.dump({"operator": "config", "target": "slowlib/core.py", "hypothesis": hypothesis, "predicted": {"bench_ms": "-1%"}}, f)
        info = last_json(sb(cls.repo, "prereg", "--file", hp))
        return info["id"], info["worktree"]

    def marker_env(self, name):
        marker = os.path.join(self.td, f"marker-{name}.txt")
        if os.path.exists(marker):
            os.remove(marker)
        return marker, {"PATH": self.shim + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"), "SB_TEST_MARKER": marker}

    # ---- frozen-guard.sh -------------------------------------------------------------
    def test_10_guard_denies_frozen_file_in_worktree(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "bench.py")), self.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("frozen", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_11_guard_allows_worktree_source(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "slowlib", "core.py")), self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stderr, "")

    def test_12_guard_denies_main_tree(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.repo, "slowlib", "core.py")), self.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("outside experiment worktrees", p.stderr)

    def test_13_guard_denies_state_file(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.home, "baseline.json")), self.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("state files", p.stderr)

    def test_14_guard_allows_inbox(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.home, "inbox", "x.json")), self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_15_guard_fast_path_without_campaign_never_starts_python(self):
        marker, extra = self.marker_env("guard-fast")
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.unrelated, "notes.py")), self.unrelated, extra)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout + p.stderr, "")
        self.assertFalse(os.path.exists(marker), "python3 was started on the no-campaign fast path")
        self.assertLess(p.secs, 1.0, f"fast path took {p.secs:.2f}s")

    def test_16_guard_off_env_allows_frozen_edit(self):
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "bench.py")), self.repo, {"SB_GUARD": "off"})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_17_guard_denies_new_file_under_frozen_dir_for_write_and_notebook(self):
        # a not-yet-existing path: the engine evaluates its parent directory
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "tests", "test_new.py"), tool="Write"), self.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("frozen", p.stderr)
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "tests", "nb.ipynb"), tool="NotebookEdit", key="notebook_path"), self.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("frozen", p.stderr)

    def test_18_guard_malformed_or_empty_payload_exits_zero(self):
        """Documented fail-open: no path in the payload means nothing to deny."""
        p = run_hook("frozen-guard.sh", "this is not json", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = run_hook("frozen-guard.sh", "", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_19_guard_with_shim_python_still_denies(self):
        # the shim proves python IS started on the slow path (contrast with test_15)
        marker, extra = self.marker_env("guard-slow")
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "bench.py")), self.repo, extra)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertTrue(os.path.exists(marker))

    # ---- session-start.sh ------------------------------------------------------------
    def test_20_session_start_prints_one_plain_line_with_campaign_id(self):
        p = run_hook("session-start.sh", START_PAYLOAD, self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        self.assertEqual(len(lines), 1, p.stdout)
        self.assertIn("hooktest", lines[0])
        self.assertIn("running", lines[0])

    def test_21_session_start_zcode_emits_json_shape(self):
        p = run_hook("session-start.sh", START_PAYLOAD, self.repo, {"ZCODE_PLUGIN_ROOT": ROOT})
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        self.assertEqual(len(lines), 1, p.stdout)
        obj = json.loads(lines[0])
        self.assertEqual(obj["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("hooktest", obj["hookSpecificOutput"]["additionalContext"])

    def test_22_session_start_hook_format_json(self):
        p = run_hook("session-start.sh", START_PAYLOAD, self.repo, {"SB_HOOK_FORMAT": "json"})
        self.assertEqual(p.returncode, 0, p.stderr)
        obj = json.loads(p.stdout.strip())
        self.assertIn("hooktest", obj["hookSpecificOutput"]["additionalContext"])

    def test_23_session_start_silent_without_state_home(self):
        marker, extra = self.marker_env("start-fast")
        p = run_hook("session-start.sh", START_PAYLOAD, self.unrelated, extra)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")
        self.assertFalse(os.path.exists(marker), "python3 was started with no .strictlybetter present")

    # ---- pre-compact.sh --------------------------------------------------------------
    def test_30_pre_compact_pins_campaign_and_baseline_rule(self):
        p = run_hook("pre-compact.sh", COMPACT_PAYLOAD, self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        self.assertTrue(1 <= len(lines) <= 6, p.stdout)
        self.assertIn("hooktest", p.stdout)
        self.assertIn("baseline.json", p.stdout)
        self.assertIn("bench.py", p.stdout)  # the frozen paths line

    def test_31_pre_compact_silent_without_campaign(self):
        p = run_hook("pre-compact.sh", COMPACT_PAYLOAD, self.unrelated)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")

    # ---- stop-driver.sh --------------------------------------------------------------
    def block_of(self, p):
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        if not p.stdout.strip():
            return None
        return json.loads(p.stdout.strip())

    def test_40_stop_driver_blocks_while_running(self):
        p = run_hook("stop-driver.sh", stop_payload("s1"), self.repo)
        d = self.block_of(p)
        self.assertIsNotNone(d, "expected a block decision:\n" + p.stdout + p.stderr)
        self.assertEqual(d["decision"], "block")
        self.assertIn("hooktest", d["reason"])
        self.assertIn("strictlybetter", d["reason"])
        cf = os.path.join(self.home, "tmp", "driver-s1.count")
        self.assertTrue(os.path.exists(cf), "per-session counter file missing")
        with open(cf) as f:
            st = json.load(f)
        self.assertGreaterEqual(st["iter"], 1)
        self.assertIn(f"{st['iter']}/", d["reason"])

    def test_41_stop_driver_no_progress_guard_and_reset(self):
        sid = "stale1"
        for i in range(1, 4):
            d = self.block_of(run_hook("stop-driver.sh", stop_payload(sid), self.repo))
            self.assertIsNotNone(d, f"call {i} should still block")
            self.assertEqual(d["decision"], "block")
        p = run_hook("stop-driver.sh", stop_payload(sid), self.repo)
        self.assertIsNone(self.block_of(p), "4th call with no new experiment must not block:\n" + p.stdout)
        self.assertIn("without a new experiment", p.stderr)
        # a new experiment resets the stale counter
        self.prereg("hook test: progress resets the stale counter")
        d = self.block_of(run_hook("stop-driver.sh", stop_payload(sid), self.repo))
        self.assertIsNotNone(d, "a new experiment must re-arm the driver")
        self.assertEqual(d["decision"], "block")

    def test_42_stop_driver_iteration_cap(self):
        cf = os.path.join(self.home, "tmp", "driver-cap1.count")
        os.makedirs(os.path.dirname(cf), exist_ok=True)
        with open(cf, "w") as f:
            json.dump({"iter": 199, "experiments": None, "stale": 0}, f)
        p = run_hook("stop-driver.sh", stop_payload("cap1"), self.repo)
        self.assertIsNone(self.block_of(p), p.stdout)
        self.assertIn("iteration cap", p.stderr)

    def test_43_stop_driver_stale_max_env(self):
        sid = "stale2"
        d = self.block_of(run_hook("stop-driver.sh", stop_payload(sid), self.repo, {"SB_DRIVER_STALE_MAX": "1"}))
        self.assertIsNotNone(d)
        p = run_hook("stop-driver.sh", stop_payload(sid), self.repo, {"SB_DRIVER_STALE_MAX": "1"})
        self.assertIsNone(self.block_of(p), p.stdout)

    def test_44_stop_driver_off_env(self):
        p = run_hook("stop-driver.sh", stop_payload("off1"), self.repo, {"SB_DRIVER": "off"})
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertFalse(os.path.exists(os.path.join(self.home, "tmp", "driver-off1.count")))

    def test_45_stop_driver_stop_hook_active_only_honoured_on_request(self):
        d = self.block_of(run_hook("stop-driver.sh", stop_payload("act1", active=True), self.repo))
        self.assertIsNotNone(d, "stop_hook_active alone must not stop the driver (documented)")
        p = run_hook("stop-driver.sh", stop_payload("act2", active=True), self.repo, {"SB_DRIVER_HONOR_STOP_HOOK_ACTIVE": "1"})
        self.assertIsNone(self.block_of(p), p.stdout)

    def test_46_stop_driver_fast_path_without_campaign(self):
        marker, extra = self.marker_env("driver-fast")
        p = run_hook("stop-driver.sh", stop_payload("s1"), self.unrelated, extra)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout + p.stderr, "")
        self.assertFalse(os.path.exists(marker))

    def test_47_stop_driver_rejects_unsafe_session_id(self):
        p = run_hook("stop-driver.sh", stop_payload("../../evil"), self.repo)
        self.assertIsNone(self.block_of(p), p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "evil.count")))
        self.assertFalse(os.path.exists(os.path.join(self.td, "evil.count")))
        p = run_hook("stop-driver.sh", {"stop_hook_active": False}, self.repo)  # no session id at all
        self.assertIsNone(self.block_of(p), p.stdout)

    def test_48_stop_driver_malformed_payload(self):
        p = run_hook("stop-driver.sh", "{not json", self.repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")  # no session id -> no driving

    def test_50_stop_driver_respects_stop_file(self):
        sb(self.repo, "stop")
        try:
            p = run_hook("stop-driver.sh", stop_payload("s1"), self.repo)
            self.assertIsNone(self.block_of(p), p.stdout)
            self.assertEqual(p.stdout, "")
        finally:
            os.remove(os.path.join(self.home, "STOP"))
        d = self.block_of(run_hook("stop-driver.sh", stop_payload("s1"), self.repo))
        self.assertIsNotNone(d, "driver must resume once the STOP file is gone")

    def test_60_stop_driver_stops_when_budget_is_exhausted(self):
        for _ in range(8):
            left = json.loads(sb(self.repo, "budget").stdout)["left"]["experiments"]
            if left <= 0:
                break
            self.prereg("hook test: spend the budget")
        self.assertLessEqual(json.loads(sb(self.repo, "budget").stdout)["left"]["experiments"], 0)
        st = json.loads(sb(self.repo, "status", "--json").stdout)
        self.assertEqual(st["status"], "running")
        self.assertEqual(st["budget_exhausted"], "experiments")
        p = run_hook("stop-driver.sh", stop_payload("s1"), self.repo)
        self.assertIsNone(self.block_of(p), p.stdout)

    # ---- python3 unreachable ---------------------------------------------------------
    def no_python_paths(self):
        empty = os.path.join(self.td, "empty-path")
        os.makedirs(empty, exist_ok=True)
        tools = os.path.join(self.td, "coreutils-only")
        os.makedirs(tools, exist_ok=True)
        for name in ("cat", "sed", "head", "dirname", "tr", "git", "mkdir", "printf", "basename"):
            real = shutil.which(name)
            dst = os.path.join(tools, name)
            if real and not os.path.exists(dst):
                os.symlink(real, dst)
        return {"empty PATH": empty, "coreutils but no python3": tools}

    def test_70_hooks_exit_zero_without_python(self):
        for label, path in self.no_python_paths().items():
            extra = {"PATH": path}
            for name, payload in (("session-start.sh", START_PAYLOAD), ("stop-driver.sh", stop_payload("nopy")), ("pre-compact.sh", COMPACT_PAYLOAD)):
                p = run_hook(name, payload, self.repo, extra)
                self.assertEqual(p.returncode, 0, f"{name} [{label}]: rc={p.returncode}\n{p.stdout}\n{p.stderr}")
                self.assertEqual(p.stdout, "", f"{name} [{label}] printed: {p.stdout!r}")

    def test_71_guard_fails_open_without_python(self):
        """Observed: a frozen-path edit is ALLOWED (exit 0) when python3 cannot be found. See module docstring."""
        for label, path in self.no_python_paths().items():
            p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.wt, "bench.py")), self.repo, {"PATH": path})
            self.assertEqual(p.returncode, 0, f"[{label}] rc={p.returncode}\n{p.stdout}\n{p.stderr}")
            self.assertEqual(p.stdout, "", f"[{label}] printed: {p.stdout!r}")

    # ---- campaign ended --------------------------------------------------------------
    def test_90_hooks_after_campaign_end(self):
        sb(self.repo, "campaign", "end")
        p = run_hook("stop-driver.sh", stop_payload("s1"), self.repo)
        self.assertIsNone(self.block_of(p), p.stdout)
        p = run_hook("session-start.sh", START_PAYLOAD, self.repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        p = run_hook("pre-compact.sh", COMPACT_PAYLOAD, self.repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        # the guard stands down with the campaign: main-tree edits are allowed again
        p = run_hook("frozen-guard.sh", edit_payload(os.path.join(self.repo, "slowlib", "core.py")), self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
