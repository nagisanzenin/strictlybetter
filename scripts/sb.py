#!/usr/bin/env python3
"""strictlybetter engine (sb.py).

The deterministic core of the strictlybetter research loop. Stdlib only, zero
network. Owns every number: measurement, noise floors, the acceptance rule,
the ledger, the ratchet, budgets, the bandit, and the frozen-path guard.
Agents narrate; this file decides.

State home: <repo>/.strictlybetter (override with SB_HOME).

    sb init                           create the state home
    sb profile write --file p.json    store the orienteer's profile
    sb card add --file card.json      add/replace a metric card
    sb card probe <id>                monotonicity selftest (degradation must hurt)
    sb baseline [--metric ID] [-k N]  measure sigma at the campaign head
    sb campaign start --file c.json   freeze the set, hash frozen paths, branch
    sb next [--json]                  the cold-start brief for the experimenter
    sb prereg --file hyp.json         pre-register; returns id + worktree path
    sb submit <id>                    commit the worktree; integrity check
    sb measure <id> --fidelity screen measure goals + guardrails
    sb judge <id>                     statistical verdict on the screen numbers
    sb judge-payload <id>             compose the blind judge's input file (diff, prereg, numbers, risks)
    sb judge-verdict <id> --file v.json  store the blind judge's verdict
    sb confirm <id>                   clean checkout + holdout + repeats
    sb accept <id> | sb discard <id> --reason R [--archive]
    sb distill-stats [--json]         plateau, bandit, false-promotion, decision
    sb status [--json] | sb report | sb budget | sb next
    sb guard <path>                   exit 2 = deny (PreToolUse hook)
    sb session-start | sb doctor | sb selftest

Constants below are fixed before any data is seen. Do not tune them to results.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import fnmatch
import hashlib
import io
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

VERSION = "1.2.0"

# ----------------------------------------------------------------------------
# Constants (fixed before data; see docs/04 and docs/06). Do not tune to results.
# ----------------------------------------------------------------------------
KAPPA = 2.5                 # improvement must exceed KAPPA * sigma
TOLERANCE_SIGMA = 1.0       # guardrail may not drop more than this many sigma
LAMBDA_COMPLEXITY = 0.3     # kappa_eff = kappa * (1 + LAMBDA * ln(1 + lines/DIFF_REF))
DIFF_REF_LINES = 50
NEW_DEP_PENALTY = 1.0       # extra sigma required per new dependency manifest touched
PATIENCE = 8                # experiments without acceptance before exploration rises
EXPLORATION_MAX = 3
BASELINE_REPEATS = 5
CONFIRM_REPEATS = 10         # paired repeats at confirm; 2^-10 lets an exact test reach alpha/K for K <= 50 at alpha 0.05
ALPHA_CAMPAIGN = 0.05        # family-wise one-sided false-accept probability per campaign (multiplicity: bonferroni over the budget)
ALPHA_GUARDRAIL = 0.10       # one-sided evidence-of-regression alarm per guardrail per confirmation (more sensitive than the goal test)
TWO_LOOK_SPLIT = 0.5         # per-look alpha fraction for a two-stage design: Bonferroni over the two looks (valid at any alpha, slightly conservative)
POCOCK_TWO_LOOK = TWO_LOOK_SPLIT  # kept as an alias for older references
PERM_EXACT_MAX_PAIRS = 20    # exact sign-flip enumeration up to 2^20; Monte Carlo above
PERM_MC_SAMPLES = 20000
PERM_MC_SEED = 20260903
FRONTIER_MAX = 8             # frontier campaigns keep at most this many non-dominated members (crowding-distance pruning)
ANOMALY_MULT = 3.0          # effect > 3x rolling mean of confirmed effects, after plateau
FP_WINDOW = 10              # false-promotion window (promotions)
FP_MAX_FRACTION = 0.4
HOLDOUT_ROTATE_AFTER = 10   # acceptances
GAP_HALT_RATIO = 0.75       # mean (screen - confirm)/screen over last 5 accepted
GAP_MIN_N = 3
INTEGRITY_HALT_AFTER = 2    # consecutive integrity violations
GAMED_HALT_AFTER = 2        # consecutive gamed verdicts
HARNESS_ERROR_HALT_AFTER = 3
DEFAULT_ITERATION_CAP = 200
DEFAULT_PRICING = {"in_per_mtok": 5.0, "out_per_mtok": 25.0}  # estimate only
TIME_UNITS = {"ms", "s", "sec", "secs", "seconds", "ns", "us", "µs", "minutes", "min"}
MAD_MIN_N = 4               # robust sigma (1.4826 * MAD) needs at least this many repeats
MAD_SCALE = 1.4826
MAX_MDE = 0.5               # a goal whose minimum detectable effect exceeds 50% is unusable on this host
WALL_DIVERGENCE_MIN_SHARE = 0.10     # the claimed saving must be >= 10% of the process wall-clock to be checkable ...
WALL_DIVERGENCE_MIN_FRACTION = 0.25  # ... and then the wall-clock must drop by >= 25% of the claimed saving

OPERATORS = ["config", "algorithmic", "allocation", "caching", "concurrency",
             "dependency", "test-add", "bugfix", "refactor-enabling", "data",
             "model", "numerics", "docs"]
DEFAULT_PRIORS = {op: [1, 3] for op in OPERATORS}
DEFAULT_PRIORS.update({"algorithmic": [3, 3], "allocation": [2, 3], "caching": [2, 3],
                       "config": [2, 3], "bugfix": [2, 2], "test-add": [2, 2]})
DEP_MANIFESTS = ["requirements.txt", "requirements-*.txt", "pyproject.toml", "setup.py",
                 "setup.cfg", "Pipfile", "poetry.lock", "uv.lock", "Cargo.toml", "Cargo.lock",
                 "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.mod",
                 "go.sum", "Gemfile", "Gemfile.lock", "environment.yml"]
DEFAULT_PROTECTED = [".github/", ".gitlab-ci.yml", ".env", ".env.*", "*.pem", "*.key",
                     "secrets/", "LICENSE", "LICENSE.*"]
WALL_KEYS = ["validity", "noise_floor", "confirm", "holdout", "frozen_guard", "judge",
             "prereg", "anomaly_breaker", "paired"]
DISCARD_REASONS = ["noise", "regression", "integrity", "gamed", "build-failed", "timeout",
                   "budget", "invalid", "harness-error", "manual"]


class SBError(Exception):
    pass


# ----------------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------------
def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: str, default=None, expect: type | None = None):
    """Read a state file. Missing -> default (when given). Corrupt, undecodable, a directory, or the
    wrong top-level type -> SBError, never a traceback: read paths degrade, they do not brick."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        raise SBError(f"missing state file {path}")
    except (json.JSONDecodeError, UnicodeDecodeError, IsADirectoryError, PermissionError, OSError) as e:
        raise SBError(f"corrupt state file {path}: {type(e).__name__}: {str(e)[:120]}")
    if expect is not None and not isinstance(data, expect):
        raise SBError(f"corrupt state file {path}: expected {expect.__name__}, found {type(data).__name__}")
    return data


def num(x, default: float = 0.0) -> float:
    """Coerce a stored number; corrupt values count as the default instead of crashing a report."""
    try:
        v = float(x)
        if v != v or v in (math.inf, -math.inf):
            return default  # NaN / inf -> default
        return v
    except (TypeError, ValueError, OverflowError):
        return default


def write_json_atomic(path: str, data) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as e:
        raise SBError(f"cannot write {path}: {type(e).__name__}: {str(e)[:120]}")


def append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def read_jsonl(path: str) -> list:
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a torn line never bricks a read path
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
        pass
    return out


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: str, cwd: str, env: dict | None = None, timeout: float | None = None):
    """Run a shell command. Returns (rc, stdout, stderr, seconds). Never raises on rc."""
    full_env = dict(os.environ)
    if env:
        full_env.update({k: str(v) for k, v in env.items()})
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=full_env, capture_output=True,
                           text=True, timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    return rc, out, err, time.perf_counter() - t0


def git(args: list, cwd: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-c", "core.hooksPath=/dev/null"] + args, cwd=cwd,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SBError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def median(xs: list) -> float:
    return float(statistics.median(xs))


def sigma_of(xs: list) -> float | None:
    """Noise floor estimator. n >= 4: 1.4826 * MAD (robust to the one-sided load bursts that
    dominate timing on a shared machine); n in {2, 3}: sample stdev; n < 2: unknown."""
    if len(xs) < 2:
        return None
    if len(xs) >= MAD_MIN_N:
        m = statistics.median(xs)
        mad = statistics.median([abs(x - m) for x in xs])
        if mad > 0:
            return float(MAD_SCALE * mad)
    return float(statistics.stdev(xs))


def se_factor(n_new: int, n_base: int) -> float:
    """The comparison is median-of-n_new vs median-of-n_base; scale sigma to that difference."""
    return math.sqrt(1.0 / max(1, n_new) + 1.0 / max(1, n_base))


def env_fingerprint() -> str:
    return f"{platform.system().lower()}-{platform.release()}-{platform.machine()}-{os.cpu_count()}cores-py{sys.version_info.major}.{sys.version_info.minor}"


def match_path(rel: str, pattern: str) -> bool:
    """Frozen/protected path matching: 'dir/' prefix, glob, or exact file/dir."""
    rel = rel.replace(os.sep, "/").lstrip("./")
    pattern = pattern.replace(os.sep, "/")
    if pattern.endswith("/"):
        return rel.startswith(pattern) or rel == pattern.rstrip("/")
    if any(c in pattern for c in "*?["):
        return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern)
    return rel == pattern or rel.startswith(pattern + "/")


def matches_any(rel: str, patterns) -> str | None:
    if not isinstance(patterns, (list, tuple)):
        return None
    for p in patterns:
        if isinstance(p, str) and match_path(rel, p):
            return p
    return None


# ----------------------------------------------------------------------------
# Parsing metric output
# ----------------------------------------------------------------------------
def coerce_value(s: str):
    s = s.strip()
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return float(int(s))
        return float(s)
    except ValueError:
        return s  # non-numeric values are allowed for direction=equal


def parse_output(spec: str, out: str, err: str = ""):
    """Return the parsed value or raise SBError. spec: metric-line:NAME | regex:PAT | json:PATH."""
    text = out if out else ""
    if spec.startswith("metric-line:"):
        name = spec[len("metric-line:"):].strip()
        pat = re.compile(r"^\s*METRIC\s+" + re.escape(name) + r"=(\S+)\s*$", re.MULTILINE)
        found = pat.findall(text) or pat.findall(err or "")
        if not found:
            raise SBError(f"metric line 'METRIC {name}=...' not found in output")
        if len(found) > 1:
            raise SBError(f"ambiguous: 'METRIC {name}=' printed {len(found)} times (editable code may be printing a second line)")
        return coerce_value(found[-1])
    if spec.startswith("regex:"):
        pat = re.compile(spec[len("regex:"):], re.MULTILINE)
        ms = list(pat.finditer(text)) or list(pat.finditer(err or ""))
        if not ms:
            raise SBError("regex did not match output")
        if len(ms) > 1 and len({mm.group(1) if mm.groups() else mm.group(0) for mm in ms}) > 1:
            raise SBError(f"ambiguous: regex matched {len(ms)} different values")
        m = ms[-1]
        return coerce_value(m.group(1) if m.groups() else m.group(0))
    if spec.startswith("json:"):
        path = spec[len("json:"):].strip()
        data = None
        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            for line in reversed(text.splitlines()):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if data is None:
            raise SBError("no JSON object in output")
        cur = data
        for part in [p for p in path.split(".") if p]:
            if isinstance(cur, list):
                cur = cur[int(part)]
            elif isinstance(cur, dict):
                cur = cur[part]
            else:
                raise SBError(f"json path {path} not found")
        return coerce_value(str(cur))
    raise SBError(f"unknown parse spec: {spec}")


# ----------------------------------------------------------------------------
# The state home
# ----------------------------------------------------------------------------
class Home:
    def __init__(self, repo: str | None = None, home: str | None = None):
        self.repo = os.path.abspath(repo or self.find_repo(os.getcwd()))
        self.path = os.path.abspath(home or os.environ.get("SB_HOME") or os.path.join(self.repo, ".strictlybetter"))
        self._lock_fh = None

    @staticmethod
    def find_repo(start: str) -> str:
        try:
            p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                               capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.strip()
        except OSError:
            pass
        return start

    # paths
    def p(self, *parts) -> str:
        return os.path.join(self.path, *parts)

    @property
    def metrics_dir(self): return self.p("metrics")
    @property
    def wt_dir(self): return self.p("wt")
    @property
    def ledger_path(self): return self.p("ledger.jsonl")
    @property
    def campaign_path(self): return self.p("campaign.json")
    @property
    def baseline_path(self): return self.p("baseline.json")
    @property
    def ratchet_path(self): return self.p("ratchet.json")
    @property
    def bandit_path(self): return self.p("bandit.json")
    @property
    def profile_path(self): return self.p("profile.json")

    def exists(self) -> bool:
        return os.path.isdir(self.path)

    def ensure(self) -> None:
        for d in ["metrics", "wt", "archive", "holdout", "inbox", "tmp", "cache", "reports"]:
            try:
                os.makedirs(self.p(d), exist_ok=True)
            except OSError as e:
                raise SBError(f"state home {self.p(d)} is not a directory: {e}")
        gi = self.p(".gitignore")
        if not os.path.exists(gi):
            with open(gi, "w") as f:
                f.write("wt/\narchive/\ntmp/\ncache/\ninbox/\nlock\nmeasure.lock\n*.tmp.*\n")

    @contextlib.contextmanager
    def lock(self, name: str = "lock"):
        self.ensure()
        path = self.p(name)
        fh = open(path, "a+")
        try:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            yield
        finally:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            fh.close()

    # cards
    def card_path(self, mid: str) -> str:
        if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", mid):
            raise SBError(f"bad metric id: {mid!r}")
        return os.path.join(self.metrics_dir, f"{mid}.json")

    def load_card(self, mid: str) -> dict:
        path = self.card_path(mid)
        if not os.path.isfile(path):
            raise SBError(f"no metric card '{mid}' (expected {path})")
        card = read_json(path, expect=dict)
        validate_card(card)
        return card

    def list_cards(self) -> list:
        if not os.path.isdir(self.metrics_dir):
            return []
        return sorted(f[:-5] for f in os.listdir(self.metrics_dir) if f.endswith(".json") and os.path.isfile(os.path.join(self.metrics_dir, f)))

    def save_card(self, card: dict) -> None:
        write_json_atomic(self.card_path(card["id"]), card)

    # campaign / baseline / ratchet / bandit / profile
    def campaign(self) -> dict | None:
        c = read_json(self.campaign_path, default={}, expect=dict)
        if not c:
            return None
        for k in ("goals", "guardrails", "diagnostics", "accepted_ids"):
            if k not in c or c[k] is None:
                c[k] = []
            if not isinstance(c.get(k, []), list):
                raise SBError(f"corrupt campaign.json: {k} is not a list")
            if any(not isinstance(x, str) for x in c.get(k, [])):
                raise SBError(f"corrupt campaign.json: {k} holds a non-string id")
        for k in ("walls", "spent", "budget", "holdout_override", "card_hashes", "external_hashes", "mde"):
            if c.get(k) is not None and not isinstance(c.get(k), dict):
                raise SBError(f"corrupt campaign.json: {k} is not an object")
        if not isinstance(c.get("id"), str):
            raise SBError("corrupt campaign.json: id is not a string")
        return c

    def save_campaign(self, c: dict) -> None:
        write_json_atomic(self.campaign_path, c)

    def baseline(self) -> dict:
        b = read_json(self.baseline_path, default={}, expect=dict)
        return {k: v for k, v in b.items() if isinstance(v, dict) and isinstance(v.get("levels", {}), dict)}

    def save_baseline(self, b: dict) -> None:
        write_json_atomic(self.baseline_path, b)

    def ratchet(self) -> dict:
        r = read_json(self.ratchet_path, default={}, expect=dict)
        return {k: v for k, v in r.items() if isinstance(v, dict)}

    def save_ratchet(self, r: dict) -> None:
        write_json_atomic(self.ratchet_path, r)

    def bandit(self) -> dict:
        b = read_json(self.bandit_path, default={}, expect=dict)
        ops = b.get("operators")
        if not isinstance(ops, dict):
            b["operators"] = {}
        else:
            b["operators"] = {k: v for k, v in ops.items() if isinstance(v, dict)}
        return b

    def save_bandit(self, b: dict) -> None:
        write_json_atomic(self.bandit_path, b)

    def profile(self) -> dict:
        p = read_json(self.profile_path, default={}, expect=dict)
        if not p:
            return {}
        if p.get("commands") is not None and not isinstance(p.get("commands"), dict):
            p["commands"] = {}
        if p.get("protected_paths") is not None and not isinstance(p.get("protected_paths"), list):
            p["protected_paths"] = []
        p["protected_paths"] = [x for x in (p.get("protected_paths") or []) if isinstance(x, str)]
        p["commands"] = {k: v for k, v in (p.get("commands") or {}).items() if isinstance(v, (str, type(None)))}
        return p

    # ledger
    def ledger_add(self, eid: str, event: str, data: dict) -> None:
        append_jsonl(self.ledger_path, {"ts": now_iso(), "id": eid, "event": event, "data": data})

    def ledger_events(self, eid: str | None = None) -> list:
        evs = read_jsonl(self.ledger_path)
        return [e for e in evs if eid is None or e.get("id") == eid]

    def experiments(self) -> dict:
        """Merge ledger events into one record per experiment id (event-sourced)."""
        recs: dict = {}
        for e in read_jsonl(self.ledger_path):
            if not isinstance(e, dict):
                continue
            eid = e.get("id")
            if not isinstance(eid, str) or not eid or not isinstance(e.get("data"), dict):
                continue
            r = recs.setdefault(eid, {"id": eid, "events": []})
            r["events"].append(e.get("event"))
            ev = e.get("event")
            d = e["data"]
            if ev == "prereg":
                r.update({k: d.get(k) for k in ["campaign", "operator", "target", "hypothesis",
                                                 "predicted", "expected_diff_size", "mechanism",
                                                 "prereg_hash", "worktree", "base_commit", "parent_member", "ts_start"]})
                r["ts_start"] = e.get("ts")
            elif ev == "submit":
                for k in ("measures", "judge_stat", "judge", "confirm"):
                    r.pop(k, None)  # measurements and verdicts belonged to the previous commit
                r.update({k: d.get(k) for k in ["commit", "diff_hash", "diff_lines", "new_deps",
                                                 "files", "integrity_ok", "integrity_violations"]})
            elif ev == "measure":
                if isinstance(d.get("fidelity"), str) and isinstance(d.get("results"), dict):
                    r.setdefault("measures", {})[d["fidelity"]] = d["results"]
            elif ev == "judge":
                r["judge_stat"] = d
            elif ev == "verdict":
                r["judge"] = d
            elif ev == "confirm":
                r["confirm"] = d
            elif ev in ("accept", "discard"):
                r["verdict"] = ev
                r["reason"] = d.get("reason")
                r["ts_end"] = e.get("ts")
                r["accepted_commit"] = d.get("accepted_commit")
                r["archived"] = d.get("archived", False)
            elif ev == "cost":
                c = r.setdefault("cost", {"tokens_in": 0, "tokens_out": 0, "wall_s": 0.0, "dollars": 0.0})
                for k in ["tokens_in", "tokens_out", "wall_s", "dollars"]:
                    c[k] = num(c.get(k, 0)) + num(d.get(k))
                if d.get("tier"):
                    c["tier"] = d["tier"]
            elif ev == "retry":
                r["retries"] = r.get("retries", 0) + 1
        return recs


# ----------------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------------
def strip_comments(obj):
    """Drop `_comment*` keys (template annotations) recursively."""
    if isinstance(obj, dict):
        return {k: strip_comments(v) for k, v in obj.items() if not str(k).startswith("_comment")}
    if isinstance(obj, list):
        return [strip_comments(x) for x in obj]
    return obj


def validate_card(card: dict) -> None:
    if not isinstance(card, dict):
        raise SBError("card must be an object")
    for k in ["id", "kind", "direction", "measure"]:
        if k not in card:
            raise SBError(f"card missing '{k}'")
    if not isinstance(card["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", card["id"]):
        raise SBError(f"bad card id {card['id']!r}")
    if card["kind"] not in ("goal", "guardrail", "diagnostic"):
        raise SBError("card.kind must be goal|guardrail|diagnostic")
    if card["direction"] not in ("maximize", "minimize", "equal"):
        raise SBError("card.direction must be maximize|minimize|equal")
    m = card["measure"]
    if not isinstance(m, dict) or not isinstance(m.get("command"), str) or not isinstance(m.get("parse"), str):
        raise SBError("card.measure needs string command and parse")
    if not m["parse"].startswith(("metric-line:", "regex:", "json:")):
        raise SBError("card.measure.parse must start with metric-line:, regex:, or json:")
    fid = card.get("fidelity") or {}
    if not isinstance(fid, dict):
        raise SBError("card.fidelity must be an object")
    for lvl, spec in fid.items():
        if lvl not in ("screen", "full", "confirm"):
            raise SBError(f"unknown fidelity level {lvl}")
        if not isinstance(spec, dict):
            raise SBError(f"fidelity.{lvl} must be an object")
    if not isinstance(card.get("gaming_risks", []) or [], list):
        raise SBError("gaming_risks must be a list")
    for w in card.get("gaming_risks", []) or []:
        if not isinstance(w, str):
            raise SBError("gaming_risks must be strings")
    for k in ("integrity", "acceptance", "degradation", "services", "noise", "probe"):
        if card.get(k) is not None and not isinstance(card.get(k), dict):
            raise SBError(f"card.{k} must be an object")
    for k in ("frozen_paths", "external_paths"):
        v = (card.get("integrity") or {}).get(k)
        if v is not None and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise SBError(f"card.integrity.{k} must be a list of strings")
    if card.get("targets") is not None and not (isinstance(card["targets"], list) and all(isinstance(x, str) for x in card["targets"])):
        raise SBError("card.targets must be a list of repo-relative paths (the code whose change moves this metric)")


def fidelity_spec(card: dict, level: str) -> dict:
    """Merged measurement spec for a fidelity level."""
    m = dict(card["measure"])
    f = dict((card.get("fidelity") or {}).get(level) or {})
    spec = {
        "command": f.get("command", m["command"]),
        "parse": f.get("parse", m["parse"]),
        "cwd": f.get("cwd", m.get("cwd", ".")),
        "timeout_s": float(f.get("timeout_s", m.get("timeout_s", 600))),
        "env": {**(m.get("env") or {}), **(f.get("env") or {})},
        "repeats": int(f.get("repeats", 1 if level != "confirm" else CONFIRM_REPEATS)),
        "max_repeats": int(f.get("max_repeats", f.get("repeats", CONFIRM_REPEATS) if level == "confirm" else 1)),
        "holdout": f.get("holdout"),
        "expected_duration_s": f.get("expected_duration_s", m.get("expected_duration_s")),
        "allow_nonzero_exit": bool(f.get("allow_nonzero_exit", m.get("allow_nonzero_exit", False))),
        "skip": bool(f.get("skip", False)),  # confirm-only metrics (held-out test split) skip screen/full
    }
    timing = card.get("direction") != "equal" and str(card.get("unit", "")).lower() in TIME_UNITS
    # Timing metrics: one unmeasured warm-up run per level (caches, JIT, disk) and at least two
    # recorded screen runs, unless the card says otherwise. Issue #4: a warm-cache n=1 screen
    # showed -30% on a change that was -10% at confirm.
    spec["warmup"] = int(f.get("warmup", m.get("warmup", 1 if timing else 0)))
    if timing and level == "screen" and "repeats" not in f:
        spec["repeats"] = max(2, spec["repeats"])
    spec["max_repeats"] = max(spec["max_repeats"], spec["repeats"])
    band = spec.get("expected_duration_s")
    try:
        spec["expected_duration_s"] = [float(band[0]), float(band[1])] if band and len(band) == 2 else None
    except (TypeError, ValueError):
        spec["expected_duration_s"] = None  # placeholder bands ("{{budget_s}} * 0.9") are the metrologist's to resolve
    return spec


def card_sign(card: dict) -> int:
    return 1 if card["direction"] == "maximize" else (-1 if card["direction"] == "minimize" else 0)


# ----------------------------------------------------------------------------
# Measurement
# ----------------------------------------------------------------------------
_OUTPUT_CACHE: dict = {}


@contextlib.contextmanager
def services_up(svc: dict | None, checkout: str, label: str):
    """Bring up whatever a measurement needs (a database, a compose stack, a mock server), wait
    until `ready` passes, yield (ok, reason), and always tear down. Setup or readiness failure
    makes the measurement invalid, never a crash. SB_CHECKOUT points setup at the code under test."""
    if not svc or not any(svc.get(k) for k in ("setup", "ready", "teardown")):
        yield True, None
        return
    cwd = os.path.join(checkout, svc.get("cwd", ".")) if svc.get("cwd") not in (None, ".", "") else checkout
    env = {"SB_CHECKOUT": checkout, "PYTHONDONTWRITEBYTECODE": "1"}
    ok, reason = True, None
    try:
        if svc.get("setup"):
            rc, out, err, _ = run_cmd(svc["setup"], cwd=cwd, env=env, timeout=float(svc.get("setup_timeout_s", 600)))
            if rc != 0:
                ok, reason = False, f"{label}: setup failed (rc={rc}): {(err or out)[-200:].strip()}"
        if ok and svc.get("ready"):
            deadline = time.time() + float(svc.get("ready_timeout_s", 120))
            while True:
                rc, out, err, _ = run_cmd(svc["ready"], cwd=cwd, env=env, timeout=60)
                if rc == 0:
                    break
                if time.time() >= deadline:
                    ok, reason = False, f"{label}: not ready within {svc.get('ready_timeout_s', 120)}s"
                    break
                time.sleep(float(svc.get("ready_interval_s", 2)))
        yield ok, reason
    finally:
        if svc.get("teardown"):
            run_cmd(svc["teardown"], cwd=cwd, env=env, timeout=float(svc.get("teardown_timeout_s", 300)))


def measure_paired(home: Home, card: dict, level: str, cand: str, head: str, repeats: int,
                   campaign: dict | None, use_holdout: bool) -> tuple:
    """Measure the candidate and the campaign HEAD interleaved (ABBA per repeat, same holdout value
    on both sides), so a load burst or a thermal change hits both alike. Returns (candidate summary,
    head summary). This is how performance CI compares (a fresh baseline in the same job), and it
    is what removes time drift between the stored baseline and the moment of confirmation."""
    hvals = holdout_values(card, level, campaign) if use_holdout else []
    spec = fidelity_spec(card, level)
    ho = spec.get("holdout") or {}
    if hvals and ho.get("kind") == "dir" and use_holdout:
        src = home.p("holdout", ho.get("name", card["id"]))
        if os.path.isdir(src):
            for dest in (cand, head):
                shutil.copytree(src, os.path.join(dest, ho.get("dest", ho.get("name", card["id"]))), dirs_exist_ok=True)
    if card.get("direction") == "equal" and hvals:
        repeats = len(hvals)
    if not card.get("reuse_output"):
        _OUTPUT_CACHE.clear()
    runs_c, runs_h = [], []
    with measurement_lock(home, card):
        for _ in range(spec.get("warmup", 0)):
            for path in (head, cand):
                with services_up(card.get("services"), path, f"card {card['id']} services") as (ok, _why):
                    if ok:
                        measure_once(card, level, path, holdout_value=(hvals[0] if hvals else None))  # discarded warm-up
        for i in range(repeats):
            hv = hvals[i % len(hvals)] if hvals else None
            order = [("h", head), ("c", cand)] if i % 2 == 0 else [("c", cand), ("h", head)]
            for side, path in order:
                with services_up(card.get("services"), path, f"card {card['id']} services") as (ok, why):
                    rec = measure_once(card, level, path, holdout_value=hv) if ok else \
                        {"rc": None, "secs": 0.0, "value": None, "valid": False, "invalid_reason": why, "holdout": hv, "stdout_tail": "", "stderr_tail": ""}
                (runs_h if side == "h" else runs_c).append(rec)
    sc = summarize(runs_c, card)
    sc["runs"] = runs_c
    sc["fidelity"] = level
    sh = summarize(runs_h, card)
    sh["runs"] = runs_h
    sh["fidelity"] = level
    return sc, sh


def fresh_bases(home: Home, c: dict, level: str, head_results: dict) -> dict:
    """Baselines for a paired comparison: the head's FRESH median (and n), the stored k-repeat sigma."""
    b = home.baseline()
    out = {}
    for mid, sh in (head_results or {}).items():
        if not sh or not sh.get("valid"):
            continue
        stored = baseline_level(b, mid, level) or {}
        out[mid] = {"median": sh["median"], "sigma": stored.get("sigma"), "n": sh.get("n_valid") or sh.get("n") or 1,
                    "secs_per_run": (sh.get("secs_total") or 0) / max(1, sh.get("n") or 1), "fresh": True}
    return out


def invalid_summary(reason: str, level: str) -> dict:
    return {"n": 1, "n_valid": 0, "values": [], "invalid": [reason], "secs_total": 0.0, "median": None, "sigma": None,
            "valid": False, "runs": [{"rc": None, "secs": 0.0, "value": None, "valid": False, "invalid_reason": reason, "holdout": None}], "fidelity": level}


def measure_once(card: dict, level: str, checkout: str, holdout_value=None, extra_env=None) -> dict:
    spec = fidelity_spec(card, level)
    cmd = spec["command"]
    env = dict(spec["env"])
    env.update({"SB_FIDELITY": level, "SB_METRIC": card["id"], "PYTHONHASHSEED": env.get("PYTHONHASHSEED", "0"),
                "PYTHONDONTWRITEBYTECODE": "1"})  # stale .pyc (same size, same second) would measure the old code
    if extra_env:
        env.update(extra_env)
    ho = spec.get("holdout") or {}
    if holdout_value is not None:
        if ho.get("kind") == "env":
            env[ho.get("var", "SB_SEED")] = str(holdout_value)
        elif ho.get("kind") == "arg":
            cmd = cmd.replace("{holdout}", str(holdout_value))
    cwd = os.path.join(checkout, spec["cwd"]) if spec["cwd"] not in (".", "") else checkout
    # reuse_output: a card that only re-parses another card's command (a checksum next to a
    # timing) may reuse the most recent identical run in this process instead of paying twice.
    key = json.dumps([cwd, cmd, {k: v for k, v in env.items() if k != "SB_METRIC"}], sort_keys=True)
    cached = _OUTPUT_CACHE.get(key) if card.get("reuse_output") else None
    if cached is not None:
        rc, out, err, secs = cached
    else:
        rc, out, err, secs = run_cmd(cmd, cwd=cwd, env=env, timeout=spec["timeout_s"])
        _OUTPUT_CACHE[key] = (rc, out, err, secs)
        if len(_OUTPUT_CACHE) > 64:
            _OUTPUT_CACHE.pop(next(iter(_OUTPUT_CACHE)))
    rec = {"rc": rc, "secs": round(secs, 4), "value": None, "valid": True, "invalid_reason": None,
           "holdout": holdout_value, "stdout_tail": out[-800:], "stderr_tail": err[-800:]}
    try:
        rec["value"] = parse_output(spec["parse"], out, err)
    except SBError as e:
        rec["valid"] = False
        rec["invalid_reason"] = f"parse: {e}"
    if rc == 124:
        rec["valid"] = False
        rec["invalid_reason"] = "timeout"
    elif rc != 0 and not spec["allow_nonzero_exit"]:
        rec["valid"] = False
        rec["invalid_reason"] = f"exit code {rc}"
    band = spec.get("expected_duration_s")
    if rec["valid"] and band and len(band) == 2:
        lo, hi = float(band[0]), float(band[1])
        if secs < lo or secs > hi:
            rec["valid"] = False
            rec["invalid_reason"] = f"duration {secs:.3f}s outside expected band [{lo}, {hi}]"
    return rec


def summarize(runs: list, card: dict) -> dict:
    vals = [r["value"] for r in runs if r.get("valid") and r.get("value") is not None]
    invalid = [r.get("invalid_reason") for r in runs if not r.get("valid")]
    summ = {"n": len(runs), "n_valid": len(vals), "values": vals, "invalid": invalid,
            "secs_total": round(sum(r.get("secs", 0) for r in runs), 3),
            "median": None, "sigma": None, "valid": False}
    if not vals:
        return summ
    if card.get("direction") == "equal":
        # Per-holdout canonical form: an equal-direction metric may legitimately differ per
        # seed/slice, so the value is the sorted set of (holdout -> value) pairs, and it is
        # invalid only when the same holdout yields different values across repeats.
        by_h: dict = {}
        for r in runs:
            if r.get("valid") and r.get("value") is not None:
                by_h.setdefault(str(r.get("holdout")), set()).add(str(r["value"]))
        if any(len(v) > 1 for v in by_h.values()):
            summ["invalid"].append("non-deterministic value for an equal-direction metric")
            return summ
        summ["median"] = "|".join(f"{k}={next(iter(v))}" for k, v in sorted(by_h.items()))
        summ["sigma"] = 0.0
        summ["valid"] = True
        return summ
    if all(isinstance(v, float) for v in vals):
        summ["median"] = median(vals)
        summ["sigma"] = sigma_of(vals)
    else:
        svals = [str(v) for v in vals]
        summ["median"] = svals[-1]
        summ["sigma"] = 0.0 if len(set(svals)) == 1 else None
    summ["valid"] = True
    return summ


@contextlib.contextmanager
def measurement_lock(home: Home, card: dict):
    """Serialize timing-sensitive measurements (contention_safe=false)."""
    if card.get("contention_safe"):
        yield
        return
    with home.lock("measure.lock"):
        yield


def holdout_values(card: dict, level: str, campaign: dict | None) -> list:
    spec = fidelity_spec(card, level)
    ho = spec.get("holdout") or {}
    if not ho or level != "confirm":
        return []
    if campaign and campaign.get("holdout_override", {}).get(card["id"]):
        return list(campaign["holdout_override"][card["id"]])
    return list(ho.get("values") or [])


def measure_card(home: Home, card: dict, level: str, checkout: str, repeats: int,
                 campaign: dict | None = None, use_holdout: bool = True, extra_env=None) -> dict:
    hvals = holdout_values(card, level, campaign) if use_holdout else []
    spec = fidelity_spec(card, level)
    ho = spec.get("holdout") or {}
    if hvals and ho.get("kind") == "dir" and use_holdout:
        src = home.p("holdout", ho.get("name", card["id"]))
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(checkout, ho.get("dest", ho.get("name", card["id"]))), dirs_exist_ok=True)
    if card.get("direction") == "equal" and hvals:
        repeats = len(hvals)  # one canonical pass over the holdout set
    if not card.get("reuse_output"):
        _OUTPUT_CACHE.clear()  # a fresh run starts a new reuse epoch; only reuse_output cards read the cache
    runs = []
    with measurement_lock(home, card):
        with services_up(card.get("services"), checkout, f"card {card['id']} services") as (ok, why):
            if not ok:
                return invalid_summary(why, level)
            for _ in range(spec.get("warmup", 0)):
                measure_once(card, level, checkout, holdout_value=(hvals[0] if hvals else None), extra_env=extra_env)  # discarded warm-up
            for i in range(repeats):
                hv = hvals[i % len(hvals)] if hvals else None
                runs.append(measure_once(card, level, checkout, holdout_value=hv, extra_env=extra_env))
    s = summarize(runs, card)
    s["runs"] = runs
    s["fidelity"] = level
    return s


# ----------------------------------------------------------------------------
# Git worktrees and integrity
# ----------------------------------------------------------------------------
def head_commit(home: Home) -> str:
    c = home.campaign()
    if c and c.get("head_commit"):
        return c["head_commit"]
    return git(["rev-parse", "HEAD"], home.repo)


def worktree_new(home: Home, name: str, commit: str) -> str:
    home.ensure()
    path = os.path.join(home.wt_dir, name)
    if os.path.exists(path):
        worktree_drop(home, name)
    git(["worktree", "prune"], home.repo, check=False)
    git(["worktree", "add", "--detach", path, commit], home.repo)
    return path


def worktree_drop(home: Home, name: str) -> None:
    path = os.path.join(home.wt_dir, name)
    if os.path.exists(path):
        git(["worktree", "remove", "--force", path], home.repo, check=False)
        shutil.rmtree(path, ignore_errors=True)
    git(["worktree", "prune"], home.repo, check=False)


EXTERNAL_SKIP_DIRS = {".git", "__pycache__", "node_modules", "target", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build"}


def external_hash(path: str) -> str | None:
    """Content hash of an instrument that lives OUTSIDE the campaign repo (a harness in a sibling
    repo, a shared eval script). Files hash directly; directories hash every file under them
    except build and VCS directories. None when the path does not exist."""
    path = os.path.abspath(path)
    h = hashlib.sha256()
    if os.path.isfile(path):
        h.update(sha256_file(path).encode("ascii"))
        return h.hexdigest()
    if not os.path.isdir(path):
        return None
    for root_, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in EXTERNAL_SKIP_DIRS)
        for f in sorted(files):
            fp = os.path.join(root_, f)
            if os.path.islink(fp) or not os.path.isfile(fp):
                continue
            rel = os.path.relpath(fp, path)
            h.update(rel.encode("utf-8") + b"\0" + sha256_file(fp).encode("ascii") + b"\0")
    return h.hexdigest()


def external_instruments(home: Home, c: dict | None) -> list:
    """Absolute paths outside the repo that are part of the instrument: campaign-level list plus
    every card's integrity.external_paths."""
    out = []
    if c:
        out += [os.path.abspath(p) for p in (c.get("external_instruments") or [])]
        ids = list(c.get("goals", [])) + list(c.get("guardrails", [])) + list(c.get("diagnostics", []))
    else:
        ids = home.list_cards()
    for mid in ids:
        try:
            card = home.load_card(mid)
        except SBError:
            continue
        out += [os.path.abspath(p) for p in ((card.get("integrity") or {}).get("external_paths") or [])]
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def verify_external(home: Home, c: dict) -> None:
    want = c.get("external_hashes") or {}
    for path, h in want.items():
        now = external_hash(path)
        if now != h:
            halt(home, c, f"external-tampered:{path}")
            raise SBError(f"external instrument changed during the campaign: {path} (the instrument is frozen); halted")


def card_fingerprint(card: dict) -> str:
    """Hash of the measurement-relevant fields of a card (noise/probe/title are free to change)."""
    core = {k: v for k, v in card.items() if k not in ("noise", "probe", "title", "gaming_risks")}
    return sha256_text(json.dumps(core, sort_keys=True))[:16]


def verify_card_hashes(home: Home, c: dict) -> None:
    verify_external(home, c)
    want = c.get("card_hashes") or {}
    for mid, h in want.items():
        try:
            card = home.load_card(mid)
        except SBError:
            halt(home, c, f"card-missing:{mid}")
            raise SBError(f"metric card {mid} disappeared during the campaign; halted")
        if card_fingerprint(card) != h:
            halt(home, c, f"card-tampered:{mid}")
            raise SBError(f"metric card {mid} changed during the campaign (the instrument is frozen); halted")


def frozen_paths(home: Home, campaign: dict | None) -> list:
    pats = []
    if campaign:
        pats += list(campaign.get("frozen_paths") or [])
        ids = list(campaign.get("goals", [])) + list(campaign.get("guardrails", [])) + list(campaign.get("diagnostics", []))
    else:
        ids = home.list_cards()
    for mid in ids:
        try:
            card = home.load_card(mid)
        except SBError:
            continue
        pats += list((card.get("integrity") or {}).get("frozen_paths") or [])
    seen, out = set(), []
    for p in pats:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def protected_paths(home: Home, campaign: dict | None) -> list:
    pats = list(DEFAULT_PROTECTED)
    prof = home.profile()
    pats += list(prof.get("protected_paths") or [])
    if campaign:
        pats += list(campaign.get("protected_paths") or [])
    return pats


def tree_files(checkout: str) -> list:
    out = git(["ls-files", "-z"], checkout)
    return [f for f in out.split("\0") if f]


def eval_hash(checkout: str, patterns: list) -> str:
    h = hashlib.sha256()
    files = sorted(f for f in tree_files(checkout) if matches_any(f, patterns))
    for f in files:
        p = os.path.join(checkout, f)
        if os.path.isfile(p):
            h.update(f.encode("utf-8") + b"\0" + sha256_file(p).encode("ascii") + b"\0")
    return h.hexdigest()


def diff_stats(checkout: str, base: str, commit: str) -> dict:
    names = git(["diff", "--name-only", base, commit], checkout)
    files = [f for f in names.splitlines() if f.strip()]
    numstat = git(["diff", "--numstat", base, commit], checkout)
    lines = 0
    for row in numstat.splitlines():
        parts = row.split("\t")
        if len(parts) >= 2:
            for x in parts[:2]:
                if x.isdigit():
                    lines += int(x)
    new_deps = [f for f in files if any(fnmatch.fnmatch(os.path.basename(f), pat) for pat in DEP_MANIFESTS)]
    patch = git(["diff", base, commit], checkout)
    return {"files": files, "diff_lines": lines, "new_deps": new_deps, "diff_hash": sha256_text(patch)[:16], "patch": patch}


# ----------------------------------------------------------------------------
# Acceptance rule
# ----------------------------------------------------------------------------
def kappa_eff(kappa: float, diff_lines: int, new_deps: int) -> float:
    return kappa * (1.0 + LAMBDA_COMPLEXITY * math.log(1.0 + max(0, diff_lines) / DIFF_REF_LINES)) + NEW_DEP_PENALTY * max(0, new_deps)


def baseline_level(baseline: dict, mid: str, level: str, strict: bool = False) -> dict | None:
    b = baseline.get(mid)
    if not b:
        return None
    levels = b.get("levels", {})
    if level in levels:
        return levels[level]
    if strict:
        return None
    if "confirm" in levels:
        return levels["confirm"]
    if levels:
        return list(levels.values())[0]
    return None


def compare_metric(card: dict, base: dict | None, meas: dict, kappa_e: float, tol: float,
                   walls: dict) -> dict:
    """Compare one measured metric against baseline. Returns a dict with deltas and flags."""
    res = {"id": card["id"], "kind": card["kind"], "direction": card["direction"], "valid": meas.get("valid", False),
           "value": meas.get("median"), "baseline": None, "sigma": None, "delta": None,
           "delta_sigma": None, "rel": None, "improved": False, "regressed": False,
           "inconclusive": False, "threshold": None, "note": None}
    if not meas.get("valid"):
        res["note"] = "; ".join(str(x) for x in meas.get("invalid", [])) or "invalid measurement"
        return res
    if base is None or base.get("median") is None:
        res["note"] = "no baseline"
        return res
    res["baseline"] = base["median"]
    sig = base.get("sigma")
    if sig is None:
        sig = 0.0
    res["sigma"] = sig
    if card["direction"] == "equal":
        same = str(meas["median"]) == str(base["median"])
        res["delta"] = 0.0 if same else 1.0
        res["regressed"] = not same
        res["note"] = "matches baseline" if same else "differs from baseline"
        return res
    s = card_sign(card)
    try:
        delta = s * (float(meas["median"]) - float(base["median"]))
    except (TypeError, ValueError):
        res["valid"] = False
        res["note"] = "non-numeric value for a numeric metric"
        return res
    res["delta"] = delta
    denom = abs(float(base["median"])) if float(base["median"]) != 0 else None
    res["rel"] = (delta / denom) if denom else None
    n_new = int(meas.get("n_valid") or meas.get("n") or 1)
    n_base = int(base.get("n") or 1)
    res["se_factor"] = se_factor(n_new, n_base)
    if walls.get("noise_floor", True):
        thr = kappa_e * sig * res["se_factor"]
        res["threshold"] = thr
        res["delta_sigma"] = (delta / sig) if sig > 0 else (math.inf if delta > 0 else (-math.inf if delta < 0 else 0.0))
        if card["kind"] == "goal":
            res["improved"] = delta > thr
            res["regressed"] = delta < -tol * sig * res["se_factor"]
            res["inconclusive"] = (delta > 0) and not res["improved"]
        else:
            res["regressed"] = delta < -tol * sig * res["se_factor"]
            res["improved"] = delta > thr
    else:  # naive: raw comparison, no noise floor
        res["threshold"] = 0.0
        res["delta_sigma"] = (delta / sig) if sig > 0 else None
        res["improved"] = delta > 0
        res["regressed"] = delta < 0
    return res


def decide(card_map: dict, campaign: dict, comparisons: list, level: str) -> dict:
    """Aggregate per-metric comparisons into a verdict for a fidelity level."""
    walls = campaign.get("walls", {})
    goals = [c for c in comparisons if c["id"] in campaign.get("goals", [])]
    guards = [c for c in comparisons if c["id"] in campaign.get("guardrails", [])]
    invalid = [c["id"] for c in comparisons if not c["valid"] and c["id"] in campaign.get("goals", []) + campaign.get("guardrails", [])]
    out = {"level": level, "verdict": None, "reason": None, "improved": [], "regressed": [], "invalid": invalid, "score": None}
    if invalid and walls.get("validity", True):
        out["verdict"], out["reason"] = "discard", "invalid"
        return out
    regressed = [c["id"] for c in guards if c["regressed"]] + ([] if campaign.get("composition") == "frontier" else [c["id"] for c in goals if c["regressed"]])
    out["regressed"] = regressed
    if regressed:
        out["verdict"], out["reason"] = "discard", f"regression:{regressed[0]}"
        return out
    if campaign.get("composition") == "oec":
        weights = campaign.get("oec_weights") or {}
        score = 0.0
        for c in goals:
            if c["delta_sigma"] is None or c["delta_sigma"] in (math.inf, -math.inf):
                continue
            score += float(weights.get(c["id"], 1.0)) * c["delta_sigma"]
        out["score"] = score
        kap = float(campaign.get("_kappa_eff", KAPPA))
        if score > kap:
            out["verdict"], out["reason"] = "promote", "oec"
            out["improved"] = [c["id"] for c in goals if (c["delta"] or 0) > 0]
            return out
        out["verdict"], out["reason"] = ("inconclusive", "oec-below-threshold") if score > 0 else ("discard", "noise")
        return out
    improved = [c["id"] for c in goals if c["improved"]]
    out["improved"] = improved
    if improved:
        out["verdict"], out["reason"] = "promote", "improved:" + ",".join(improved)
        return out
    if any(c["inconclusive"] for c in goals):
        out["verdict"], out["reason"] = "inconclusive", "within-noise"
        return out
    out["verdict"], out["reason"] = "discard", "noise"
    return out


# ----------------------------------------------------------------------------
# Campaign helpers
# ----------------------------------------------------------------------------
def require_campaign(home: Home, running: bool = True) -> dict:
    c = home.campaign()
    if not c:
        raise SBError("no campaign; run `sb campaign start --file campaign.json`")
    if running and c.get("status") != "running":
        raise SBError(f"campaign status is '{c.get('status')}' ({c.get('halt_reason') or ''}); not running")
    return c


def stop_requested(home: Home) -> bool:
    return os.path.exists(home.p("STOP"))


def halt(home: Home, c: dict, reason: str) -> None:
    c["status"] = "halted"
    c["halt_reason"] = reason
    c["halted_at"] = now_iso()
    home.save_campaign(c)
    home.ledger_add("campaign", "halt", {"reason": reason})


def budget_left(c: dict) -> dict:
    b = c.get("budget") if isinstance(c.get("budget"), dict) else {}
    s = c.get("spent") if isinstance(c.get("spent"), dict) else {}
    left = {}
    if b.get("experiments") is not None:
        left["experiments"] = int(num(b["experiments"])) - int(num(s.get("experiments", 0)))
    if b.get("hours") is not None:
        left["hours"] = num(b["hours"]) - num(s.get("wall_s", 0)) / 3600.0
    if b.get("dollars") is not None:
        left["dollars"] = num(b["dollars"]) - num(s.get("dollars", 0))
    return left


def budget_exhausted(c: dict) -> str | None:
    for k, v in budget_left(c).items():
        if v <= 0:
            return k
    s = c.get("spent") if isinstance(c.get("spent"), dict) else {}
    if int(num(s.get("experiments", 0))) >= int(num(c.get("iteration_cap", DEFAULT_ITERATION_CAP), DEFAULT_ITERATION_CAP)):
        return "iteration_cap"
    return None


def add_spend(c: dict, **kw) -> None:
    if not isinstance(c.get("spent"), dict):
        c["spent"] = {"experiments": 0, "wall_s": 0.0, "dollars": 0.0, "tokens_in": 0, "tokens_out": 0}
    s = c["spent"]
    for k, v in kw.items():
        s[k] = num(s.get(k, 0)) + num(v)


def card_set(home: Home, c: dict) -> dict:
    ids = list(c.get("goals", [])) + list(c.get("guardrails", [])) + list(c.get("diagnostics", []))
    return {mid: home.load_card(mid) for mid in ids}


def bandit_update(home: Home, operator: str, accepted: bool, effect: float | None, cost_s: float) -> None:
    b = home.bandit()
    ops = b.setdefault("operators", {})
    prior = DEFAULT_PRIORS.get(operator, [1, 3])
    rec = ops.setdefault(operator, {"alpha": prior[0], "beta": prior[1], "attempts": 0, "accepts": 0, "effect_sum": 0.0, "cost_s": 0.0})
    rec["attempts"] += 1
    rec["cost_s"] += cost_s
    if accepted:
        rec["alpha"] += 1
        rec["accepts"] += 1
        rec["effect_sum"] += (effect or 0.0)
    else:
        rec["beta"] += 1
    home.save_bandit(b)


def bandit_mix(home: Home, batch: int, seed: int | None = None, priors: dict | None = None) -> list:
    b = home.bandit()
    ops = b.get("operators", {})
    rng = random.Random(seed)
    weights = {}
    for op in OPERATORS:
        rec = ops.get(op)
        if isinstance(rec, dict):
            a, be = num(rec.get("alpha", 1), 1.0), num(rec.get("beta", 1), 1.0)
        else:
            pr = (priors or {}).get(op) if isinstance(priors, dict) else None
            if not (isinstance(pr, list) and len(pr) == 2):
                pr = DEFAULT_PRIORS.get(op, [1, 3])
            a, be = num(pr[0], 1.0), num(pr[1], 3.0)
        weights[op] = max(1e-6, rng.betavariate(max(0.01, a), max(0.01, be)))
    picks = rng.choices(list(weights.keys()), weights=list(weights.values()), k=batch)
    counts: dict = {}
    for p in picks:
        counts[p] = counts.get(p, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def primary_goal_effect(c: dict, comparisons: list) -> float | None:
    """Relative improvement on the first goal that has a relative delta."""
    for g in c.get("goals", []):
        for comp in comparisons:
            if comp["id"] == g and comp.get("rel") is not None:
                return float(comp["rel"])
    return None


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cmd_init(home: Home, args) -> int:
    home.ensure()
    print(f"initialized {home.path}")
    return 0


def cmd_profile(home: Home, args) -> int:
    if args.action == "write":
        data = load_payload(args.file)
        for k in ["archetypes", "commands", "purpose"]:
            if k not in data:
                raise SBError(f"profile missing '{k}'")
        if not isinstance(data["archetypes"], list) or not data["archetypes"]:
            raise SBError("profile.archetypes must be a non-empty list")
        data["written_at"] = now_iso()
        data["commit"] = git(["rev-parse", "HEAD"], home.repo, check=False) or None
        home.ensure()
        write_json_atomic(home.profile_path, data)
        with open(home.p("profile.md"), "w", encoding="utf-8") as f:
            f.write(render_profile(data))
        print(f"profile written: {home.profile_path}")
        return 0
    if args.action == "show":
        print(json.dumps(home.profile(), indent=2))
        return 0
    raise SBError("profile: write|show")


def render_profile(p: dict) -> str:
    lines = ["# Project profile (strictlybetter)", ""]
    lines.append(f"**Purpose.** {p.get('purpose', '')}")
    lines.append("")
    lines.append("## Archetypes")
    for a in p.get("archetypes", []):
        if isinstance(a, dict):
            lines.append(f"- {a.get('id')} (confidence {a.get('confidence', '?')})")
        else:
            lines.append(f"- {a}")
    lines.append("")
    lines.append("## Verified commands")
    for k, v in (p.get("commands") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Constraints")
    for x in p.get("constraints", []) or []:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Protected paths (proposed)")
    for x in p.get("protected_paths", []) or []:
        lines.append(f"- `{x}`")
    lines.append("")
    if p.get("notes"):
        lines.append("## Notes")
        lines.append(str(p["notes"]))
        lines.append("")
    return "\n".join(lines)


def load_payload(path: str) -> dict:
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SBError(f"invalid JSON payload: {e}")


def cmd_card(home: Home, args) -> int:
    if args.action == "add":
        card = load_payload(args.file)
        card = strip_comments(card)
        validate_card(card)
        home.ensure()
        old = None
        try:
            old = home.load_card(card["id"])
        except SBError:
            pass
        c = home.campaign()
        if c and c.get("status") in ("running", "halted") and card["id"] in c.get("goals", []) + c.get("guardrails", []) + c.get("diagnostics", []):
            raise SBError("cannot change a campaign's metric card while it is running or halted; end the campaign first")
        if old and old.get("noise") and not card.get("noise"):
            card["noise"] = old["noise"]
        if old and old.get("probe") and not card.get("probe"):
            card["probe"] = old["probe"]
        home.save_card(card)
        print(f"card saved: {home.card_path(card['id'])}")
        return 0
    if args.action == "list":
        for mid in home.list_cards():
            card = home.load_card(mid)
            noise = card.get("noise") or {}
            probe = (card.get("probe") or {}).get("monotonic")
            print(f"{mid:24} {card['kind']:10} {card['direction']:9} sigma={noise.get('sigma')} probe={probe}")
        return 0
    if args.action == "validate":
        card = home.load_card(args.id)
        problems = []
        if card["kind"] in ("goal", "guardrail") and not (card.get("noise") or {}).get("measured_at"):
            problems.append("no measured noise (run `sb baseline`)")
        if card["kind"] in ("goal", "guardrail") and (card.get("probe") or {}).get("monotonic") is False:
            problems.append("monotonicity probe failed")
        if not card.get("gaming_risks"):
            problems.append("no gaming_risks listed")
        print(json.dumps({"id": args.id, "ok": not problems, "problems": problems}))
        return 0 if not problems else 1
    if args.action == "show":
        print(json.dumps(home.load_card(args.id), indent=2))
        return 0
    if args.action == "probe":
        return cmd_card_probe(home, args)
    raise SBError("card: add|list|validate|show|probe")


def cmd_card_probe(home: Home, args) -> int:
    card = home.load_card(args.id)
    deg = card.get("degradation") or {}
    if not deg.get("apply"):
        raise SBError("card has no degradation.apply recipe")
    commit = head_commit(home)
    name = f"_probe-{card['id']}"
    path = worktree_new(home, name, commit)
    c_probe = home.campaign()
    try:
      with services_up((c_probe or {}).get("services"), path, "campaign services") as (svc_ok, svc_why):
        if not svc_ok:
            raise SBError(f"probe cannot run: {svc_why}")
        before = measure_card(home, card, "screen", path, repeats=max(1, args.repeats), use_holdout=False)
        rc, out, err, _ = run_cmd(deg["apply"], cwd=path, env={"PYTHONDONTWRITEBYTECODE": "1"}, timeout=300)
        _OUTPUT_CACHE.clear()  # the tree changed; nothing measured before the degradation may be reused
        for root_, dirs_, _files in os.walk(path):
            for d_ in [d for d in dirs_ if d == "__pycache__"]:
                shutil.rmtree(os.path.join(root_, d_), ignore_errors=True)
        if rc != 0:
            raise SBError(f"degradation recipe failed (rc={rc}): {err[-400:]}")
        after = measure_card(home, card, "screen", path, repeats=max(1, args.repeats), use_holdout=False)
    finally:
        worktree_drop(home, name)
    ok = False
    detail = ""
    if before["valid"] and after["valid"]:
        if card["direction"] == "equal":
            ok = str(before["median"]) != str(after["median"])
            detail = f"{before['median']} -> {after['median']}"
        else:
            s = card_sign(card)
            worse = s * (float(after["median"]) - float(before["median"])) < 0
            sig = (card.get("noise") or {}).get("sigma") or before.get("sigma") or 0.0
            margin = abs(float(after["median"]) - float(before["median"]))
            ok = worse and (margin > (sig or 0.0))
            detail = f"{before['median']} -> {after['median']} (sigma {sig})"
    else:
        detail = f"invalid: before={before.get('invalid')} after={after.get('invalid')}"
    card["probe"] = {"monotonic": ok, "detail": detail, "at": now_iso(), "commit": commit}
    home.save_card(card)
    print(json.dumps({"id": card["id"], "monotonic": ok, "detail": detail}))
    return 0 if ok else 1


def cmd_baseline(home: Home, args) -> int:
    home.ensure()
    c = home.campaign()
    commit = head_commit(home)
    ids = [args.metric] if args.metric else (
        list(c.get("goals", [])) + list(c.get("guardrails", [])) + list(c.get("diagnostics", [])) if c else home.list_cards())
    if not ids:
        raise SBError("no metric cards to baseline")
    k = int(args.repeats or BASELINE_REPEATS)
    forced_levels = args.levels.split(",") if args.levels else None
    path = worktree_new(home, "_baseline", commit)
    baseline = home.baseline()
    try:
      with services_up((c or {}).get("services"), path, "campaign services") as (svc_ok, svc_why):
        if not svc_ok:
            raise SBError(f"baseline cannot run: {svc_why}")
        for mid in ids:
            card = home.load_card(mid)
            entry = baseline.get(mid) or {}
            entry.setdefault("levels", {})
            levels = forced_levels or (["screen"] + (["full"] if (card.get("fidelity") or {}).get("full") else []) + ["confirm"])
            levels = [l for l in levels if not fidelity_spec(card, l).get("skip")]
            for level in levels:
                reps = 1 if card.get("contention_safe") and card["direction"] == "equal" else k
                s = measure_card(home, card, level, path, repeats=reps, campaign=c,
                                 use_holdout=(level == "confirm" and (not c or c.get("walls", {}).get("holdout", True))))
                entry["levels"][level] = {"median": s["median"], "sigma": s["sigma"], "n": s["n_valid"],
                                          "values": s["values"], "secs_per_run": round(s["secs_total"] / max(1, s["n"]), 3),
                                          "invalid": s["invalid"]}
                print(f"{mid:22} {level:8} median={s['median']} sigma={s['sigma']} n={s['n_valid']}/{s['n']} {round(s['secs_total'], 2)}s"
                      + (f" INVALID {s['invalid']}" if not s["valid"] else ""))
            conf = entry["levels"].get("confirm") or entry["levels"].get(levels[-1])
            entry["best"] = conf.get("median") if conf else None
            entry["sigma"] = conf.get("sigma") if conf else None
            entry["commit"] = commit
            entry["env_fingerprint"] = env_fingerprint()
            entry["measured_at"] = now_iso()
            entry["quarantined"] = not (conf and conf.get("median") is not None)
            baseline[mid] = entry
            card["noise"] = {"sigma": entry["sigma"], "samples": conf.get("n") if conf else 0, "method": "mad-scaled" if (conf and (conf.get("n") or 0) >= MAD_MIN_N) else "stdev-of-repeats",
                             "measured_at": commit, "environment_fingerprint": env_fingerprint()}
            home.save_card(card)
    finally:
        worktree_drop(home, "_baseline")
    home.save_baseline(baseline)
    home.ledger_add("campaign", "baseline", {"commit": commit, "metrics": ids, "repeats": k, "levels": levels})
    print(f"baseline written: {home.baseline_path}")
    return 0


def cmd_campaign(home: Home, args) -> int:
    if args.action == "start":
        return campaign_start(home, args)
    if args.action == "show":
        print(json.dumps(home.campaign() or {}, indent=2))
        return 0
    if args.action == "end":
        c = require_campaign(home, running=False)
        c["status"] = "ended"
        c["ended_at"] = now_iso()
        home.save_campaign(c)
        for name in os.listdir(home.wt_dir) if os.path.isdir(home.wt_dir) else []:
            worktree_drop(home, name)
        home.ledger_add("campaign", "end", {"reason": args.reason or "manual"})
        write_report(home, c)
        print(f"campaign {c['id']} ended; report at {home.p('reports', c['id'] + '.md')}")
        return 0
    if args.action == "halt":
        c = require_campaign(home, running=False)
        halt(home, c, args.reason or "manual")
        print("halted")
        return 0
    if args.action == "resume":
        c = require_campaign(home, running=False)
        if c.get("status") not in ("halted", "running"):
            raise SBError("only a halted campaign can be resumed")
        c["status"] = "running"
        c["halt_reason"] = None
        c["consecutive_integrity"] = 0
        c["consecutive_gamed"] = 0
        c["consecutive_errors"] = 0
        home.save_campaign(c)
        if os.path.exists(home.p("STOP")):
            os.remove(home.p("STOP"))
        home.ledger_add("campaign", "resume", {})
        print("resumed")
        return 0
    raise SBError("campaign: start|show|end|halt|resume")


def campaign_start(home: Home, args) -> int:
    home.ensure()
    existing = home.campaign()
    if existing and existing.get("status") == "running":
        raise SBError(f"campaign {existing['id']} is running; end it first")
    spec = load_payload(args.file)
    cid = spec.get("id") or _dt.datetime.now().strftime("%Y-%m-%d-campaign")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", cid):
        raise SBError("campaign id must be [A-Za-z0-9_.-]")
    goals = list(spec.get("goals") or [])
    if not goals:
        raise SBError("campaign needs at least one goal")
    guardrails = list(spec.get("guardrails") or [])
    diagnostics = list(spec.get("diagnostics") or [])
    walls = {k: True for k in WALL_KEYS}
    walls.update({k: bool(v) for k, v in (spec.get("walls") or {}).items() if k in WALL_KEYS})
    # hygiene guardrails: any card of kind guardrail flagged hygiene, always included
    for mid in home.list_cards():
        card = home.load_card(mid)
        if card.get("hygiene") and mid not in goals and mid not in guardrails:
            guardrails.append(mid)
    # global ratchet: every past goal becomes a guardrail
    ratchet = home.ratchet()
    for mid in ratchet:
        if mid not in goals and mid not in guardrails and os.path.exists(home.card_path(mid)) and not ratchet[mid].get("demoted"):
            guardrails.append(mid)
    for mid in goals + guardrails + diagnostics:
        home.load_card(mid)
    commit = git(["rev-parse", "HEAD"], home.repo)
    branch = spec.get("branch") or f"sb/{cid}"
    c = {
        "id": cid, "goals": goals, "guardrails": guardrails, "diagnostics": diagnostics,
        "composition": spec.get("composition", "pareto"), "oec_weights": spec.get("oec_weights") or {},
        "budget": spec.get("budget") or {"experiments": 40}, "spent": {"experiments": 0, "wall_s": 0.0, "dollars": 0.0, "tokens_in": 0, "tokens_out": 0},
        "plateau_patience": int(spec.get("plateau_patience", PATIENCE)), "protected_paths": list(spec.get("protected_paths") or []),
        "frozen_paths": list(spec.get("frozen_paths") or []), "branch": branch, "status": "running", "halt_reason": None,
        "walls": walls, "iteration_cap": int(spec.get("iteration_cap", DEFAULT_ITERATION_CAP)), "max_parallel": int(spec.get("max_parallel", 2)),
        "distill_every": int(spec.get("distill_every", 8)), "false_promotion_budget": spec.get("false_promotion_budget") or {"window": FP_WINDOW, "max_fraction": FP_MAX_FRACTION},
        "pricing": spec.get("pricing") or DEFAULT_PRICING, "started_at": now_iso(), "base_commit": commit, "head_commit": commit,
        "exploration_level": 0, "since_last_accept": 0, "accepted_ids": [], "acceptances_since_rotation": 0,
        "consecutive_integrity": 0, "consecutive_gamed": 0, "consecutive_errors": 0, "screen_repeats_multiplier": 1,
        "screen_untrusted": False, "next_id": 1, "holdout_override": {}, "notes": spec.get("notes", ""),
        "archetype_priors": spec.get("archetype_priors") or {},
    }
    # frozen paths and eval hash from a clean checkout
    c["external_instruments"] = [os.path.abspath(p) for p in (spec.get("external_instruments") or [])]
    c["scope_paths"] = list(spec.get("scope_paths") or [])
    c["services"] = spec.get("services") or None
    path = worktree_new(home, "_campaign", commit)
    try:
        fp = frozen_paths(home, c)
        c["frozen_paths_effective"] = fp
        c["eval_hash"] = eval_hash(path, fp)
        ext = external_instruments(home, c)
        c["external_instruments_effective"] = ext
        c["external_hashes"] = {}
        for ep in ext:
            hh = external_hash(ep)
            if hh is None:
                raise SBError(f"external instrument not found: {ep}")
            repo_real = os.path.realpath(home.repo)
            if os.path.realpath(ep).startswith(repo_real + os.sep):
                raise SBError(f"external instrument {ep} is inside the repo; list it under frozen_paths instead")
            c["external_hashes"][ep] = hh
    finally:
        worktree_drop(home, "_campaign")
    # branch
    git(["branch", "-f", branch, commit], home.repo)
    home.save_campaign(c)
    home.ledger_add("campaign", "start", {"id": cid, "goals": goals, "guardrails": guardrails, "walls": walls, "commit": commit, "eval_hash": c["eval_hash"]})
    # baseline for metrics lacking one at this commit
    b = home.baseline()
    missing = [m for m in goals + guardrails + diagnostics if not b.get(m) or b[m].get("commit") != commit]
    if missing and not args.no_baseline:
        print(f"baselining {len(missing)} metric(s) at {commit[:8]} ...")
        ns = argparse.Namespace(metric=None, repeats=args.repeats, levels=None)
        saved = home.campaign()
        # temporarily restrict ids
        for m in missing:
            ns.metric = m
            cmd_baseline(home, ns)
        home.save_campaign(saved)
    b = home.baseline()
    if walls.get("noise_floor", True):
        for m in goals + guardrails:
            e = b.get(m) or {}
            if e.get("quarantined") or e.get("best") is None:
                halt(home, home.campaign(), f"metric {m} has no valid baseline")
                raise SBError(f"metric {m} has no valid baseline; campaign halted")
            if home.load_card(m)["direction"] != "equal" and e.get("sigma") is None:
                halt(home, home.campaign(), f"metric {m} has no measured sigma (need >=2 repeats)")
                raise SBError(f"metric {m} has no measured sigma; campaign halted")
        # a goal whose declared targets are all frozen is a control, not a goal (issue #3)
        for m in goals:
            card = home.load_card(m)
            targets = [t for t in (card.get("targets") or []) if isinstance(t, str)]
            if targets and not card.get("control"):
                fp_eff = home.campaign().get("frozen_paths_effective") or []
                pp_eff = protected_paths(home, home.campaign())
                if all(matches_any(t, fp_eff) or matches_any(t, pp_eff) for t in targets):
                    halt(home, home.campaign(), f"goal-frozen:{m}")
                    raise SBError(f"goal {m}: every declared target ({', '.join(targets)}) is frozen or protected, so no legal experiment can "
                                  f"move it. Unfreeze a target, demote the card to diagnostic, or set \"control\": true on the card to keep it as a "
                                  f"negative control. Campaign halted.")
        # minimum detectable effect per goal: the instrument must be able to see a plausible win
        mdes = {}
        for m in goals:
            card = home.load_card(m)
            if card["direction"] == "equal":
                continue
            e = b.get(m) or {}
            conf = (e.get("levels") or {}).get("confirm") or {}
            sig, med, n = e.get("sigma"), e.get("best"), int(conf.get("n") or BASELINE_REPEATS)
            r = fidelity_spec(card, "confirm")["repeats"]
            kap = float((card.get("acceptance") or {}).get("kappa", KAPPA))
            if sig is not None and med not in (None, 0):
                mdes[m] = kap * float(sig) * se_factor(r, n) / abs(float(med))
        c2 = home.campaign()
        c2["mde"] = mdes
        home.save_campaign(c2)
        for m, mde in mdes.items():
            print(f"minimum detectable effect on {m}: {100 * mde:.1f}% (sigma {b[m]['sigma']:.4g} on {b[m]['best']:.4g}, confirm repeats {fidelity_spec(home.load_card(m), 'confirm')['repeats']})")
            if mde > MAX_MDE and not args.allow_unusable:
                halt(home, home.campaign(), f"instrument-unusable:{m}:mde={mde:.2f}")
                raise SBError(f"goal {m} cannot detect effects smaller than {100 * mde:.0f}% on this host (max {100 * MAX_MDE:.0f}%); "
                              f"raise repeats (-k / confirm.repeats), reduce machine load, or pass --allow-unusable. Campaign halted.")
    # freeze the cards and record start values; a regressed HEAD may not silently become a floor
    c3 = home.campaign()
    c3["card_hashes"] = {m: card_fingerprint(home.load_card(m)) for m in goals + guardrails + diagnostics}
    c3["start_values"] = {m: (b.get(m) or {}).get("best") for m in goals + guardrails + diagnostics}
    if spec.get("composition") == "frontier":
        if len(goals) < 2:
            raise SBError("composition 'frontier' needs at least two goals")
        c3["frontier"] = [{"id": "f0", "commit": commit, "parent": None, "experiment": None, "attempts": 0,
                           "values": {g: (b.get(g) or {}).get("best") for g in goals}, "branch": branch}]
        c3["frontier_max"] = int(num(spec.get("frontier_max", FRONTIER_MAX), FRONTIER_MAX))
        c3["preference"] = spec.get("preference") if isinstance(spec.get("preference"), dict) else None
    c3["alpha"] = float(num(spec.get("alpha", ALPHA_CAMPAIGN), ALPHA_CAMPAIGN))
    c3["multiplicity"] = spec.get("multiplicity", "bonferroni")
    c3["alpha_test"] = alpha_per_test(c3)
    # power gate: with r pairs the exact test's smallest p is 2^-r; a card that cannot reach alpha_test
    # (or alpha_look in a two-stage design) can never accept anything and must not start.
    if walls.get("paired", True) and walls.get("noise_floor", True):
        for m in goals:
            card = home.load_card(m)
            if card["direction"] == "equal":
                continue
            st = (card.get("fidelity") or {}).get("confirm", {}).get("stages")
            if isinstance(st, list) and len(st) == 2:
                r_total, a_look = int(st[0]) + int(st[1]), c3["alpha_test"] * POCOCK_TWO_LOOK
            else:
                r_total, a_look = fidelity_spec(card, "confirm")["repeats"], c3["alpha_test"]
            need = math.ceil(-math.log2(a_look))
            if 2.0 ** (-r_total) > a_look and not args.allow_underpowered:
                halt(home, home.campaign(), f"underpowered:{m}:pairs={r_total}:alpha={a_look:.4g}")
                raise SBError(f"goal {m}: {r_total} confirm pairs cannot reach the per-test alpha {a_look:.4g} (smallest attainable p is 2^-{r_total} = {2.0 ** (-r_total):.4g}); "
                              f"set fidelity.confirm.repeats to at least {need} (or stages summing to it), raise alpha, shrink the experiment budget, or pass --allow-underpowered. Campaign halted.")
    home.save_campaign(c3)
    home.save_campaign(c3)
    for mid, rec in ratchet.items():
        if mid in guardrails and not rec.get("demoted") and rec.get("best") is not None:
            card = home.load_card(mid)
            e = b.get(mid) or {}
            if card["direction"] != "equal" and e.get("best") is not None:
                sgn = card_sign(card)
                tol = float((card.get("acceptance") or {}).get("tolerance_sigma", TOLERANCE_SIGMA)) * float(e.get("sigma") or 0.0)
                if sgn * (float(e["best"]) - float(rec["best"])) < -tol and not args.allow_ratchet_regression:
                    halt(home, home.campaign(), f"ratchet-regression:{mid}")
                    raise SBError(f"{mid} at HEAD ({e['best']}) is worse than the global ratchet ({rec['best']} from campaign {rec.get('campaign')}); "
                                  f"the frontier only moves outward. Fix the regression, demote the metric in ratchet.json, or pass --allow-ratchet-regression. Campaign halted.")
    print(f"campaign {cid} started on branch {branch} at {commit[:8]}; walls={','.join(k for k, v in walls.items() if v) or 'none'}")
    return 0


def cmd_prereg(home: Home, args) -> int:
    c = require_campaign(home)
    if stop_requested(home):
        raise SBError("STOP file present; not starting new experiments")
    ex = budget_exhausted(c)
    if ex:
        halt(home, c, f"budget:{ex}")
        raise SBError(f"budget exhausted ({ex}); campaign halted")
    h = load_payload(args.file)
    for k in ["operator", "target", "hypothesis", "predicted"]:
        if k not in h:
            raise SBError(f"hypothesis missing '{k}'")
    if h["operator"] not in OPERATORS:
        raise SBError(f"unknown operator {h['operator']!r}; one of {OPERATORS}")
    if not isinstance(h["predicted"], dict) or not h["predicted"]:
        raise SBError("predicted must be a non-empty object {metric: expected effect}")
    for m in h["predicted"]:
        if m not in c["goals"] + c["guardrails"] + c["diagnostics"]:
            raise SBError(f"predicted metric {m!r} is not in the campaign")
    eid = f"e{c['next_id']:04d}"
    c["next_id"] += 1
    add_spend(c, experiments=1)  # budget updated before work starts
    home.save_campaign(c)
    commit = c["head_commit"]
    parent_member = None
    if c.get("composition") == "frontier":
        cards = card_set(home, c)
        want = getattr(args, "parent", None) or (h.get("parent") if isinstance(h, dict) else None)
        member = next((m for m in frontier_active(c) if m["id"] == want), None) if want else frontier_pick_parent(cards, c)
        if member is None:
            raise SBError("frontier has no active member" + (f" named {want}" if want else ""))
        member["attempts"] = int(member.get("attempts", 0)) + 1
        commit = member["commit"]
        parent_member = member["id"]
        home.save_campaign(c)
    path = worktree_new(home, eid, commit)
    prereg_hash = sha256_text(json.dumps(h, sort_keys=True))[:16]
    data = {"campaign": c["id"], "operator": h["operator"], "target": h["target"], "hypothesis": h["hypothesis"],
            "predicted": h["predicted"], "expected_diff_size": h.get("expected_diff_size", "small"),
            "mechanism": h.get("mechanism", ""), "prereg_hash": prereg_hash, "worktree": path, "base_commit": commit,
            "exploration_level": c.get("exploration_level", 0), "parent_member": parent_member}
    home.ledger_add(eid, "prereg", data)
    print(json.dumps({"id": eid, "worktree": path, "base_commit": commit, "prereg_hash": prereg_hash, "parent_member": parent_member}))
    return 0


def experiment_record(home: Home, eid: str) -> dict:
    recs = home.experiments()
    if eid not in recs:
        raise SBError(f"unknown experiment {eid}")
    return recs[eid]


def cmd_submit(home: Home, args) -> int:
    c = require_campaign(home)
    r = experiment_record(home, eid := args.id)
    path = os.path.join(home.wt_dir, eid)
    if not os.path.isdir(path):
        raise SBError(f"worktree for {eid} missing")
    status = git(["status", "--porcelain"], path)
    if not status.strip():
        home.ledger_add(eid, "submit", {"commit": None, "integrity_ok": False, "integrity_violations": ["no changes"], "diff_lines": 0, "new_deps": [], "files": []})
        print(json.dumps({"id": eid, "ok": False, "violations": ["no changes"]}))
        return 1
    git(["add", "-A"], path)
    msg = f"{eid}: {r.get('hypothesis', '')[:200]}\n\noperator: {r.get('operator')}\ntarget: {r.get('target')}\nprereg: {r.get('prereg_hash')}"
    git(["-c", "user.name=strictlybetter", "-c", "user.email=sb@strictlybetter.local", "commit", "-q", "-m", msg], path)
    commit = git(["rev-parse", "HEAD"], path)
    ds = diff_stats(path, r["base_commit"] if r.get("base_commit") else c["head_commit"], commit)
    violations = []
    fp = c.get("frozen_paths_effective") or frozen_paths(home, c)
    pp = protected_paths(home, c)
    scope = c.get("scope_paths") or []
    for f in ds["files"]:
        if matches_any(f, fp):
            violations.append(f"frozen:{f}")
        elif matches_any(f, pp):
            violations.append(f"protected:{f}")
        elif f.startswith(".strictlybetter/"):
            violations.append(f"state:{f}")
        elif scope and not matches_any(f, scope):
            violations.append(f"scope:{f}")
    if c.get("walls", {}).get("frozen_guard", True):
        eh = eval_hash(path, fp)
        if eh != c.get("eval_hash"):
            violations.append("eval-hash-changed")
    if "dependency" != r.get("operator") and ds["new_deps"]:
        violations.append("deps:" + ",".join(ds["new_deps"]))  # allowed only for the dependency operator
    ok = not violations if c.get("walls", {}).get("frozen_guard", True) else True
    home.ledger_add(eid, "submit", {"commit": commit, "diff_hash": ds["diff_hash"], "diff_lines": ds["diff_lines"], "new_deps": ds["new_deps"],
                                    "files": ds["files"], "integrity_ok": ok, "integrity_violations": violations})
    if not ok:
        c["consecutive_integrity"] = int(c.get("consecutive_integrity", 0)) + 1
        home.save_campaign(c)
        if c["consecutive_integrity"] >= INTEGRITY_HALT_AFTER:
            halt(home, c, "integrity:" + ";".join(violations))
    else:
        c["consecutive_integrity"] = 0
        home.save_campaign(c)
    print(json.dumps({"id": eid, "ok": ok, "commit": commit, "diff_lines": ds["diff_lines"], "files": ds["files"], "violations": violations}))
    return 0 if ok else 1


def cmd_measure(home: Home, args) -> int:
    c = require_campaign(home, running=False)  # reproduction after a campaign ended is allowed
    eid = args.id
    if c.get("status") == "running":
        verify_card_hashes(home, c)
        if args.fidelity == "confirm" and not args.audit:
            raise SBError("confirm-fidelity measurement runs only inside `sb confirm` while a campaign is running (holdout must not leak); pass --audit for a human audit")
    r = experiment_record(home, eid)
    level = args.fidelity
    if not r.get("commit"):
        raise SBError(f"{eid} has no submitted commit; run `sb submit {eid}`")
    if r.get("integrity_ok") is False and c.get("walls", {}).get("frozen_guard", True):
        raise SBError(f"{eid} failed integrity; discard it")
    cards = card_set(home, c)
    checkout = os.path.join(home.wt_dir, eid)
    if level == "confirm" or not os.path.isdir(checkout):
        checkout = worktree_new(home, f"{eid}-{level}", r["commit"])
    results = {}
    t0 = time.perf_counter()
    wall = 0.0
    try:
      with services_up(c.get("services"), checkout, "campaign services") as (svc_ok, svc_why):
        ids = list(c["goals"]) + list(c["guardrails"]) + (list(c["diagnostics"]) if level != "screen" else [])
        for mid in ids:
            card = cards[mid]
            spec = fidelity_spec(card, level)
            if not svc_ok:
                results[mid] = invalid_summary(svc_why, level)
                continue
            if spec.get("skip"):
                results[mid] = {"skipped": True, "valid": True, "median": None, "sigma": None, "n": 0, "n_valid": 0, "values": [], "invalid": [], "secs_total": 0.0, "fidelity": level}
                continue
            reps = spec["repeats"]
            if level == "screen":
                reps = max(1, reps * int(c.get("screen_repeats_multiplier", 1)))
            if args.repeats:
                reps = int(args.repeats)
            s = measure_card(home, card, level, checkout, repeats=reps, campaign=c,
                             use_holdout=(level == "confirm" and c.get("walls", {}).get("holdout", True)))
            s.pop("runs", None) if not args.keep_runs else None
            results[mid] = s
    finally:
        if level == "confirm" or checkout != os.path.join(home.wt_dir, eid):
            worktree_drop(home, os.path.basename(checkout))
        wall = time.perf_counter() - t0
        add_spend(c, wall_s=wall)
        home.save_campaign(c)
    home.ledger_add(eid, "measure", {"fidelity": level, "results": {k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in results.items()}, "wall_s": round(wall, 3)})
    for mid, s in results.items():
        print(f"{eid} {level:8} {mid:22} median={s['median']} n={s['n_valid']}/{s['n']}" + (f" INVALID {s['invalid']}" if not s['valid'] else ""))
    return 0


def timer_divergence(card: dict, base: dict | None, meas: dict, comp: dict) -> str | None:
    """A time-unit goal whose instrument claims a large speedup while the process wall-clock the
    harness observed barely moved is a lying timer, not a win. Returns the invalidity note or None."""
    if not (comp.get("valid") and base and card.get("direction") == "minimize"
            and str(card.get("unit", "")).lower() in TIME_UNITS and comp.get("improved")):
        return None
    unit = str(card.get("unit", "")).lower()
    to_s = {"ms": 1e-3, "s": 1.0, "sec": 1.0, "secs": 1.0, "seconds": 1.0, "us": 1e-6, "µs": 1e-6, "ns": 1e-9, "minutes": 60.0, "min": 60.0}.get(unit)
    if to_s is None:
        return None
    try:
        instr_saved = (float(base["median"]) - float(meas["median"])) * to_s          # seconds the instrument says were saved
        wall_new = float(meas.get("secs_total", 0)) / max(1, int(meas.get("n", 1)))
        wall_base = float(base.get("secs_per_run") or 0)
        wall_saved = wall_base - wall_new
    except (TypeError, ValueError):
        return None
    if wall_base <= 0 or instr_saved <= 0:
        return None
    # Only when the claimed saving is a visible share of the process wall-clock can the wall-clock
    # confirm or deny it (a bench with 2 s of fixed setup cannot show a 5 ms saving). Then the
    # process must have got faster by at least a quarter of what the instrument claims.
    if instr_saved >= WALL_DIVERGENCE_MIN_SHARE * wall_base and wall_saved < WALL_DIVERGENCE_MIN_FRACTION * instr_saved:
        return (f"instrument claims {instr_saved:.3f}s saved per run but process wall-clock changed by {wall_saved:+.3f}s "
                f"(base {wall_base:.3f}s): timer or instrument tampering?")
    return None


def comparisons_for(home: Home, c: dict, r: dict, level: str, results: dict, bases: dict | None = None) -> tuple:
    cards = card_set(home, c)
    b = home.baseline()
    ke = kappa_eff(KAPPA, int(r.get("diff_lines") or 0), len(r.get("new_deps") or []))
    if not c.get("walls", {}).get("noise_floor", True):
        ke = 0.0
    comps = []
    for mid in list(c["goals"]) + list(c["guardrails"]):
        card = cards[mid]
        meas = results.get(mid) or {"valid": False, "invalid": ["not measured"]}
        if meas.get("skipped") or fidelity_spec(card, level).get("skip"):
            continue  # confirm-only metric: not part of this level's decision
        if level == "full" and not (card.get("fidelity") or {}).get("full"):
            continue  # this card has no full level; it is measured at confirm
        base = (bases or {}).get(mid) or baseline_level(b, mid, level, strict=(card["direction"] == "equal"))
        kap = float((card.get("acceptance") or {}).get("kappa", KAPPA))
        tol = float((card.get("acceptance") or {}).get("tolerance_sigma", TOLERANCE_SIGMA))
        ke_card = kappa_eff(kap, int(r.get("diff_lines") or 0), len(r.get("new_deps") or [])) if c.get("walls", {}).get("noise_floor", True) else 0.0
        comp = compare_metric(card, base, meas, ke_card, tol, c.get("walls", {}))
        if c.get("walls", {}).get("validity", True):
            note = timer_divergence(card, base, meas, comp)
            if note:
                comp["valid"] = False
                comp["improved"] = False
                comp["note"] = note
        comps.append(comp)
    c["_kappa_eff"] = ke
    return comps, ke


def cmd_judge(home: Home, args) -> int:
    c = require_campaign(home)
    verify_card_hashes(home, c)
    eid = args.id
    r = experiment_record(home, eid)
    level = args.fidelity or "screen"
    results = (r.get("measures") or {}).get(level)
    if not results:
        raise SBError(f"{eid} has no {level} measurement")
    comps, ke = comparisons_for(home, c, r, level, results)
    d = decide(card_set(home, c), c, comps, level)
    # retry-screen: within noise but predicted large, once
    if d["verdict"] == "inconclusive" and level == "screen":
        if int(r.get("retries", 0)) < 1:
            d["verdict"] = "retry-screen"
            home.ledger_add(eid, "retry", {"level": level})
        else:
            d["verdict"], d["reason"] = "discard", "noise"
    # anomaly breaker
    anomaly = False
    if d["verdict"] == "promote" and c.get("walls", {}).get("anomaly_breaker", True):
        eff = primary_goal_effect(c, comps)
        hist = [x for x in (c.get("confirmed_effects") or []) if x is not None]
        if eff is not None and hist and c.get("since_last_accept", 0) >= c.get("plateau_patience", PATIENCE) // 2:
            mean_eff = sum(hist) / len(hist)
            if mean_eff > 0 and eff > ANOMALY_MULT * mean_eff:
                anomaly = True
    d["anomaly"] = anomaly
    d["kappa_eff"] = ke
    d["comparisons"] = [{k: v for k, v in comp.items()} for comp in comps]
    if not c.get("walls", {}).get("confirm", True) and d["verdict"] == "promote":
        d["verdict"] = "accept-naive"
    home.ledger_add(eid, "judge", d)
    if d["verdict"] == "promote" and not c.get("walls", {}).get("judge", True):
        home.ledger_add(eid, "verdict", {"verdict": "clean", "pattern": "", "evidence": "", "recommended_check": "", "judge": "disabled"})
    print(json.dumps({k: v for k, v in d.items() if k != "comparisons"}))
    for comp in comps:
        print(f"  {comp['id']:22} {comp['kind']:9} value={comp['value']} base={comp['baseline']} delta={comp['delta']} "
              f"sigma={comp['sigma']} thr={comp['threshold']} {'IMPROVED' if comp['improved'] else ''}{'REGRESSED' if comp['regressed'] else ''}{('INVALID ' + str(comp['note'])) if not comp['valid'] else ''}")
    return 0


def cmd_judge_payload(home: Home, args) -> int:
    """Compose the blind judge's payload: diff, pre-registration, screen comparisons, the affected
    cards' gaming_risks, and the checklist path. No experimenter reasoning exists in it by construction."""
    c = require_campaign(home, running=False)
    eid = args.id
    r = experiment_record(home, eid)
    if not r.get("commit"):
        raise SBError(f"{eid} has no submitted commit")
    base = r.get("base_commit") or c["head_commit"]
    diff = git(["diff", base, r["commit"]], home.repo)
    cards = card_set(home, c)
    risks = {mid: (cards[mid].get("gaming_risks") or []) for mid in list(c["goals"]) + list(c["guardrails"])}
    js = r.get("judge_stat") or {}
    comps = [{k: v for k, v in comp.items() if k in ("id", "kind", "direction", "value", "baseline", "delta", "sigma", "threshold", "improved", "regressed", "valid", "note")}
             for comp in (js.get("comparisons") or [])]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checklist = os.path.join(root, "templates", "judge-checklist.md")
    # Shape is the contract in agents/sb-judge.md and skills/_shared/judge-protocol.md.
    payload = {"id": eid, "campaign": c["id"], "checklist": checklist if os.path.exists(checklist) else None,
               "prereg": {k: r.get(k) for k in ("operator", "target", "hypothesis", "predicted", "mechanism", "expected_diff_size", "prereg_hash")},
               "diff": {"lines": r.get("diff_lines"), "files": r.get("files"), "new_deps": r.get("new_deps"), "text": diff},
               "screen": {"verdict": js.get("verdict"), "reason": js.get("reason"), "kappa_eff": js.get("kappa_eff"), "anomaly": bool(js.get("anomaly")), "comparisons": comps},
               "gaming_risks": risks, "frozen_paths": c.get("frozen_paths_effective"), "protected_paths": protected_paths(home, c),
               "verdict_schema": {"verdict": "clean|suspicious|gamed", "pattern": "string", "evidence": "string", "recommended_check": "string"}}
    out = args.out or home.p("inbox", f"judge-{eid}.json")
    write_json_atomic(out, payload)
    print(out)
    return 0


def cmd_judge_verdict(home: Home, args) -> int:
    c = require_campaign(home)
    eid = args.id
    experiment_record(home, eid)
    v = load_payload(args.file)
    allowed = {"verdict", "pattern", "evidence", "recommended_check", "judge"}
    extra = set(v.keys()) - allowed
    if extra:
        raise SBError(f"verdict has forbidden fields: {sorted(extra)} (reasoning cannot be smuggled in)")
    if v.get("verdict") not in ("clean", "suspicious", "gamed"):
        raise SBError("verdict must be clean|suspicious|gamed")
    prev = (experiment_record(home, eid).get("judge") or {}).get("verdict")
    if prev == "gamed":
        raise SBError(f"{eid} already has a gamed verdict; it cannot be overwritten")
    v["judge"] = "sb-judge"
    home.ledger_add(eid, "verdict", v)
    if v["verdict"] == "gamed":
        c["consecutive_gamed"] = int(c.get("consecutive_gamed", 0)) + 1
        home.save_campaign(c)
        if c["consecutive_gamed"] >= GAMED_HALT_AFTER:
            halt(home, c, "gamed-twice")
    else:
        c["consecutive_gamed"] = 0
        home.save_campaign(c)
    print(json.dumps({"id": eid, "stored": v["verdict"]}))
    return 0


def cmd_confirm(home: Home, args) -> int:
    c = require_campaign(home)
    verify_card_hashes(home, c)
    eid = args.id
    r = experiment_record(home, eid)
    if c.get("multiplicity", "bonferroni") == "bonferroni" and c.get("walls", {}).get("paired", True) and c.get("walls", {}).get("noise_floor", True):
        k_budget = int(num((c.get("budget") or {}).get("experiments", 0), 0)) or int(num(c.get("iteration_cap", DEFAULT_ITERATION_CAP), DEFAULT_ITERATION_CAP))
        done = int(num(c.get("confirmations_run", 0)))
        if done >= k_budget:
            halt(home, c, f"alpha-budget-exhausted:{done}/{k_budget}")
            raise SBError(f"the campaign's alpha budget is spent: {done} confirmations already run against a pre-registered K of {k_budget}; "
                          f"a further test would break the family-wise bound. Campaign halted.")
        c["confirmations_run"] = done + 1
        home.save_campaign(c)
    js = r.get("judge_stat") or {}
    walls = c.get("walls", {})
    if js.get("verdict") not in ("promote", "accept-naive") and not args.force:
        raise SBError(f"{eid} is not promoted (judge: {js.get('verdict')})")
    if walls.get("judge", True) and not r.get("judge"):
        raise SBError(f"{eid} has no blind-judge verdict; run the judge and `sb judge-verdict`")
    if (r.get("judge") or {}).get("verdict") == "gamed":
        raise SBError(f"{eid} was judged gamed; discard it")
    if not walls.get("confirm", True):
        home.ledger_add(eid, "confirm", {"verdict": "accept", "reason": "naive:no-confirm", "level": "screen", "commit": r["commit"], "comparisons": js.get("comparisons")})
        print(json.dumps({"id": eid, "verdict": "accept", "reason": "naive:no-confirm"}))
        return 0
    cards = card_set(home, c)
    checkout = worktree_new(home, f"{eid}-confirm", r["commit"])
    paired = bool(walls.get("paired", True))
    head_checkout = worktree_new(home, f"{eid}-head", r.get("base_commit") or c["head_commit"]) if paired else None
    head_full, head_results = {}, {}
    t0 = time.perf_counter()
    try:
      with services_up(c.get("services"), checkout, "campaign services") as (svc_ok, svc_why):
        if not svc_ok:
            out = {"verdict": "discard", "reason": "invalid", "level": "confirm", "commit": r["commit"], "note": svc_why, "comparisons": [], "results": {}}
            home.ledger_add(eid, "confirm", out)
            print(json.dumps({k: v for k, v in out.items() if k not in ("comparisons", "results")}))
            return 0
        # full fidelity first when it differs from screen
        full_results = {}
        for mid in list(c["goals"]) + list(c["guardrails"]):
            card = cards[mid]
            if (card.get("fidelity") or {}).get("full") and not fidelity_spec(card, "full").get("skip"):
                if paired:
                    full_results[mid], head_full[mid] = measure_paired(home, card, "full", checkout, head_checkout, fidelity_spec(card, "full")["repeats"], c, False)
                else:
                    full_results[mid] = measure_card(home, card, "full", checkout, repeats=fidelity_spec(card, "full")["repeats"], campaign=c, use_holdout=False)
        if full_results:
            comps_full, _ = comparisons_for(home, c, r, "full", {**{m: full_results.get(m) or {"valid": False, "invalid": ["not measured"]} for m in full_results}},
                                            bases=fresh_bases(home, c, "full", head_full) if paired else None)
            dfull = decide(cards, c, comps_full, "full")
            home.ledger_add(eid, "measure", {"fidelity": "full", "results": {k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in full_results.items()}})
            goals_at_full = [g for g in c["goals"] if g in full_results]
            if not goals_at_full and dfull["verdict"] == "discard" and dfull["reason"] == "noise":
                dfull["verdict"], dfull["reason"] = "pass", "no goal measured at full; guardrails held"   # only guardrails have a full level
            if dfull["verdict"] == "discard":
                out = {"verdict": "discard", "reason": dfull["reason"], "level": "full", "commit": r["commit"], "comparisons": comps_full}
                home.ledger_add(eid, "confirm", out)
                print(json.dumps({k: v for k, v in out.items() if k != "comparisons"}))
                return 0
        # confirm: pre-registered number of pairs, optionally in two Pocock stages. No open-ended
        # "add repeats until it wins": the sample size is fixed before the data (docs/04 §4.2).
        results, stat_tests = {}, {}
        anomaly = bool(js.get("anomaly")) or (r.get("judge") or {}).get("verdict") == "suspicious"
        stages_by_card = {}
        for mid in list(c["goals"]) + list(c["guardrails"]) + list(c["diagnostics"]):
            card = cards[mid]
            spec = fidelity_spec(card, "confirm")
            if spec.get("skip"):
                continue
            st = (card.get("fidelity") or {}).get("confirm", {}).get("stages")
            if isinstance(st, list) and len(st) == 2 and all(isinstance(x, int) and x > 0 for x in st):
                stages_by_card[mid] = list(st)
            else:
                stages_by_card[mid] = [spec["max_repeats"] if anomaly else spec["repeats"]]
        looks = max(len(v) for v in stages_by_card.values()) if stages_by_card else 1
        d = {"verdict": "inconclusive"}
        rounds = 0
        for look in range(1, looks + 1):
            for mid, st in stages_by_card.items():
                if look > len(st):
                    continue
                card = cards[mid]
                reps = st[look - 1]
                if paired:
                    more, more_h = measure_paired(home, card, "confirm", checkout, head_checkout, reps, c, walls.get("holdout", True))
                    prev, prev_h = results.get(mid), head_results.get(mid)
                    if prev:
                        merged = (prev.get("runs") or []) + (more.get("runs") or [])
                        more = summarize(merged, card); more["runs"] = merged; more["fidelity"] = "confirm"
                        merged_h = (prev_h.get("runs") or []) + (more_h.get("runs") or [])
                        more_h = summarize(merged_h, card); more_h["runs"] = merged_h; more_h["fidelity"] = "confirm"
                    results[mid], head_results[mid] = more, more_h
                else:
                    more = measure_card(home, card, "confirm", checkout, repeats=reps, campaign=c, use_holdout=walls.get("holdout", True))
                    prev = results.get(mid)
                    if prev:
                        merged = (prev.get("runs") or []) + (more.get("runs") or [])
                        more = summarize(merged, card); more["runs"] = merged; more["fidelity"] = "confirm"
                    results[mid] = more
            rounds = look
            comps, ke = comparisons_for(home, c, r, "confirm", results, bases=fresh_bases(home, c, "confirm", head_results) if paired else None)
            if paired and walls.get("noise_floor", True):
                d = confirm_decision(cards, c, results, head_results, comps, look, looks)
                stat_tests = d.get("tests", {})
            else:
                d = decide(cards, c, comps, "confirm")   # unpaired or naive: the heuristic rule, no error rate claimed
                if d["verdict"] == "inconclusive":
                    d["verdict"], d["reason"] = ("inconclusive", "stage-continue") if look < looks else ("discard", "noise")
            if d["verdict"] != "inconclusive":
                break
        if d["verdict"] == "inconclusive":
            d["verdict"], d["reason"] = "discard", "noise"
        # holdout gap and effects
        screen_eff = primary_goal_effect(c, (js.get("comparisons") or []))
        conf_eff = primary_goal_effect(c, comps)
        out = {"verdict": "accept" if d["verdict"] == "promote" else "discard", "reason": d["reason"], "level": "confirm", "commit": r["commit"],
               "rounds": rounds, "anomaly_extra_repeats": anomaly, "screen_effect": screen_eff, "confirm_effect": conf_eff, "paired": paired,
               "tests": stat_tests, "alpha_campaign": d.get("alpha_campaign"), "alpha_test": d.get("alpha_test"), "alpha_look": d.get("alpha_look"), "looks": looks,
               "comparisons": comps, "results": {k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in results.items()},
               "head_results": {k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in head_results.items()}, "kappa_eff": ke}
    finally:
        worktree_drop(home, f"{eid}-confirm")
        if head_checkout:
            worktree_drop(home, f"{eid}-head")
        wall = time.perf_counter() - t0
        add_spend(c, wall_s=wall)
        home.save_campaign(c)
    home.ledger_add(eid, "confirm", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("comparisons", "results")}))
    for comp in comps:
        print(f"  {comp['id']:22} {comp['kind']:9} value={comp['value']} base={comp['baseline']} delta={comp['delta']} sigma={comp['sigma']} thr={comp['threshold']} {'IMPROVED' if comp['improved'] else ''}{'REGRESSED' if comp['regressed'] else ''}")
    return 0


def provenance_block(r: dict, conf: dict, c: dict) -> str:
    lines = ["", "--- strictlybetter provenance ---", f"experiment: {r['id']}  campaign: {c['id']}  operator: {r.get('operator')}",
             f"hypothesis: {r.get('hypothesis', '')[:300]}", f"prereg: {r.get('prereg_hash')}  diff_lines: {r.get('diff_lines')}  new_deps: {r.get('new_deps')}"]
    for comp in conf.get("comparisons") or []:
        if comp["kind"] in ("goal", "guardrail"):
            lines.append(f"{comp['id']}: {comp['baseline']} -> {comp['value']} (delta {comp['delta']}, sigma {comp['sigma']}, thr {comp['threshold']}) {'IMPROVED' if comp['improved'] else 'held'}")
    for mid, t in (conf.get("tests") or {}).items():
        if t.get("kind") == "paired-sign-flip":
            lines.append(f"test {mid}: paired sign-flip ({t.get('alternative')}), n_pairs={t.get('n_pairs')}, p={t.get('p')}, alpha={t.get('alpha')}, median_diff={t.get('median_diff')}")
    j = r.get("judge") or {}
    lines.append(f"judge: {j.get('verdict', 'n/a')} {j.get('pattern', '')}".rstrip())
    lines.append(f"confirmation: level={conf.get('level')} rounds={conf.get('rounds')} holdout={'yes' if c.get('walls', {}).get('holdout', True) else 'no'} paired={'yes' if conf.get('paired') else 'no'} kappa_eff={conf.get('kappa_eff')}")
    return "\n".join(lines) + "\n"


def cmd_accept(home: Home, args) -> int:
    c = require_campaign(home)
    eid = args.id
    r = experiment_record(home, eid)
    conf = r.get("confirm") or {}
    if r.get("verdict") in ("accept", "discard"):
        raise SBError(f"{eid} already {r['verdict']}ed")
    if r.get("integrity_ok") is not True:
        raise SBError(f"{eid} did not pass integrity at submit; it cannot be accepted")
    if not r.get("commit"):
        raise SBError(f"{eid} has no submitted commit")
    if args.force:
        if c.get("walls", {}).get("confirm", True):
            raise SBError("--force is not allowed while the confirm wall is on")
    else:
        if conf.get("verdict") != "accept":
            raise SBError(f"{eid} is not confirmed (confirm verdict: {conf.get('verdict')})")
        if conf.get("commit") and conf.get("commit") != r["commit"]:
            raise SBError(f"{eid}: confirmation was for commit {str(conf.get('commit'))[:8]}, not the submitted {r['commit'][:8]}")
    exp_commit = r["commit"]
    verify_card_hashes(home, c)
    parent = git(["rev-parse", f"{exp_commit}^"], home.repo)
    if c.get("composition") == "frontier":
        return accept_frontier(home, c, r, conf, exp_commit, parent, eid, bool(args.force))
    if parent != c["head_commit"]:
        raise SBError(f"{eid} is not a fast-forward of the campaign head ({parent[:8]} != {c['head_commit'][:8]}); discard and re-run on the new head")
    tree = git(["rev-parse", f"{exp_commit}^{{tree}}"], home.repo)
    msg = git(["log", "-1", "--format=%B", exp_commit], home.repo) + provenance_block(r, conf, c)
    env = dict(os.environ, GIT_AUTHOR_NAME="strictlybetter", GIT_AUTHOR_EMAIL="sb@strictlybetter.local",
               GIT_COMMITTER_NAME="strictlybetter", GIT_COMMITTER_EMAIL="sb@strictlybetter.local")
    p = subprocess.run(["git", "commit-tree", tree, "-p", c["head_commit"], "-m", msg], cwd=home.repo, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise SBError(f"commit-tree failed: {p.stderr}")
    new_commit = p.stdout.strip()
    git(["update-ref", f"refs/heads/{c['branch']}", new_commit, c["head_commit"]], home.repo)
    c["head_commit"] = new_commit
    # ratchet: the baseline only ever moves in the metric's good direction. A guardrail that
    # slipped within tolerance keeps its old floor (otherwise it loses one tolerance per accept
    # forever); a goal or guardrail that improved takes the new value. Sigma is the baseline's
    # (k repeats), never the candidate's 3-repeat sample.
    b = home.baseline()
    ratchet = home.ratchet()
    cards_now = card_set(home, c)
    for comp in conf.get("comparisons") or []:
        mid = comp["id"]
        if not comp.get("valid") or comp.get("value") is None:
            continue
        e = b.setdefault(mid, {"levels": {}})
        lv = e.setdefault("levels", {})
        lv.setdefault("confirm", {})
        better = (comp.get("delta") or 0) > 0 if comp["direction"] != "equal" else False
        if better or mid in c["goals"]:
            if mid in c["goals"] or better:
                lv["confirm"]["median"] = comp["value"]
                e["best"] = comp["value"]
        e["commit"] = new_commit
        e["measured_at"] = now_iso()
        res = (conf.get("results") or {}).get(mid) or {}
        if res.get("secs_total") and res.get("n"):
            lv["confirm"]["secs_per_run"] = round(float(res["secs_total"]) / max(1, int(res["n"])), 3)
        if mid in c["goals"]:
            ratchet[mid] = {"best": e["best"], "sigma": e.get("sigma"), "commit": new_commit, "campaign": c["id"], "direction": comp["direction"]}
    for mid, res in (conf.get("results") or {}).items():
        if mid in c.get("diagnostics", []) and isinstance(res, dict) and res.get("valid") and res.get("median") is not None:
            e = b.setdefault(mid, {"levels": {}})
            e.setdefault("levels", {}).setdefault("confirm", {})["median"] = res["median"]
            e["best"] = res["median"]
            e["commit"] = new_commit
    # screen-level baseline follows the accepted commit's screen numbers (goals only; floors never drift)
    scr = (r.get("measures") or {}).get("screen") or {}
    for mid, s in scr.items():
        if s.get("valid") and mid in b and mid in c["goals"]:
            b[mid].setdefault("levels", {}).setdefault("screen", {})["median"] = s.get("median")
            if s.get("secs_total") and s.get("n"):
                b[mid]["levels"]["screen"]["secs_per_run"] = round(float(s["secs_total"]) / max(1, int(s["n"])), 3)
    home.save_baseline(b)
    home.save_ratchet(ratchet)
    # bookkeeping
    c["accepted_ids"].append(eid)
    c["since_last_accept"] = 0
    c["exploration_level"] = 0
    c["acceptances_since_rotation"] = int(c.get("acceptances_since_rotation", 0)) + 1
    c.setdefault("confirmed_effects", []).append(conf.get("confirm_effect"))
    c.setdefault("holdout_gaps", []).append(gap_ratio(conf.get("screen_effect"), conf.get("confirm_effect")))
    c["consecutive_integrity"] = 0
    bandit_update(home, r.get("operator", "config"), True, conf.get("confirm_effect"), float((r.get("cost") or {}).get("wall_s", 0.0)))
    worktree_drop(home, eid)
    home.save_campaign(c)
    home.ledger_add(eid, "accept", {"reason": "forced" if args.force else "confirmed", "accepted_commit": new_commit, "branch": c["branch"]})
    # holdout rotation
    if c.get("walls", {}).get("holdout", True) and c["acceptances_since_rotation"] >= HOLDOUT_ROTATE_AFTER:
        rotate_holdout(home, c)
    # gap halt
    gaps = [g for g in c.get("holdout_gaps", []) if g is not None][-5:]
    if len(gaps) >= GAP_MIN_N and sum(gaps) / len(gaps) > GAP_HALT_RATIO:
        halt(home, c, f"holdout-gap:{sum(gaps) / len(gaps):.2f}")
    print(json.dumps({"id": eid, "accepted_commit": new_commit, "branch": c["branch"], "confirm_effect": conf.get("confirm_effect")}))
    return 0


def paired_randomization_test(diffs: list, alternative: str = "greater") -> dict:
    """Exact Fisher–Pitman sign-flip test on paired differences d_i (candidate vs head measured
    interleaved, same holdout value in each pair). Under H0 (no effect) the sign of every d_i is
    exchangeable, so the mean of the differences under all 2^r sign assignments is the exact null
    distribution. One-sided p = fraction of assignments whose mean is >= the observed mean
    (alternative "greater") or <= (alternative "less"). Distribution-free; valid for any r; the
    smallest attainable p is 2^-r, which is why the campaign-start gate checks r against alpha.
    Ties (zero differences) are kept: they neither help nor hurt, exactly as in the exact test."""
    d = [float(x) for x in diffs if x is not None and x == x]
    r = len(d)
    if r == 0:
        return {"p": None, "stat": None, "n": 0, "exact": True, "min_p": None}
    obs = sum(d) / r
    if alternative == "less":
        d = [-x for x in d]
        obs = -obs
    if r <= PERM_EXACT_MAX_PAIRS:
        count = 0
        total = 1 << r
        for mask in range(total):
            tot = 0.0
            for i in range(r):
                tot += d[i] if (mask >> i) & 1 else -d[i]
            if tot / r >= obs - 1e-12:
                count += 1
        p = count / total
        exact = True
    else:
        rng = random.Random(PERM_MC_SEED)
        count = 0
        for _ in range(PERM_MC_SAMPLES):
            tot = 0.0
            for x in d:
                tot += x if rng.random() < 0.5 else -x
            if tot / r >= obs - 1e-12:
                count += 1
        p = (count + 1) / (PERM_MC_SAMPLES + 1)
        exact = False
    return {"p": p, "stat": (obs if alternative != "less" else -obs), "n": r, "exact": exact, "min_p": 2.0 ** (-r)}


def paired_diffs(card: dict, cand: dict, head: dict) -> list:
    """Improvement per pair, signed so that positive = better for the card's direction."""
    sgn = card_sign(card)
    rc, rh = (cand.get("runs") or []), (head.get("runs") or [])
    out = []
    for a, b in zip(rc, rh):   # same index = same repeat = same holdout value
        if a.get("valid") and b.get("valid") and isinstance(a.get("value"), float) and isinstance(b.get("value"), float):
            out.append(sgn * (a["value"] - b["value"]))
    return out


def alpha_per_test(c: dict) -> float:
    """Per-confirmation one-sided alpha after multiplicity control over the PRE-REGISTERED budget."""
    alpha = float(num(c.get("alpha", ALPHA_CAMPAIGN), ALPHA_CAMPAIGN))
    mult = c.get("multiplicity", "bonferroni")
    k = int(num((c.get("budget") or {}).get("experiments", 0), 0)) or int(num(c.get("iteration_cap", DEFAULT_ITERATION_CAP), DEFAULT_ITERATION_CAP))
    if mult == "bonferroni" and k > 0:
        return alpha / k
    return alpha


def confirm_decision(cards: dict, c: dict, results: dict, head_results: dict, comps: list, look: int, looks: int) -> dict:
    """The confirmation verdict with a stated error rate. Goals: exact paired randomization test
    (one-sided, alternative = improvement) at alpha_look, AND a practical floor (card
    acceptance.min_effect_rel of the head median; default 0). Guardrails (numeric): evidence of
    regression at ALPHA_GUARDRAIL, or a median regression beyond the tolerance, blocks. Equal
    guardrails: exact match. A two-stage design spends alpha with Pocock's constant per look."""
    a_test = alpha_per_test(c)
    a_look = a_test * (POCOCK_TWO_LOOK if looks > 1 else 1.0)
    tests = {}
    regressed, improved, invalid, inconclusive = [], [], [], []
    for comp in comps:
        mid = comp["id"]
        card = cards[mid]
        if not comp.get("valid"):
            if mid in c["goals"] or mid in c["guardrails"]:
                invalid.append(mid)
            continue
        if card["direction"] == "equal":
            if comp.get("regressed"):
                regressed.append(mid)
            tests[mid] = {"kind": "exact-equality", "regressed": bool(comp.get("regressed"))}
            continue
        d = paired_diffs(card, results.get(mid) or {}, head_results.get(mid) or {})
        if not d:
            tests[mid] = {"kind": "unpaired-fallback", "note": "no paired runs; heuristic comparison used"}
            if comp.get("improved") and mid in c["goals"]:
                improved.append(mid)
            if comp.get("regressed"):
                regressed.append(mid)
            continue
        med = statistics.median(d)
        if mid in c["goals"]:
            t = paired_randomization_test(d, "greater")
            floor_rel = float(num((card.get("acceptance") or {}).get("min_effect_rel", 0.0), 0.0))
            head_med = float(comp.get("baseline") or 0.0)
            floor_abs = floor_rel * abs(head_med)
            ok_p = t["p"] is not None and t["p"] <= a_look
            ok_floor = med >= floor_abs
            tests[mid] = {"kind": "paired-sign-flip", "alternative": "improvement", "p": t["p"], "alpha": a_look, "n_pairs": t["n"], "exact": t["exact"],
                          "mean_diff": t["stat"], "median_diff": med, "min_effect_abs": floor_abs, "significant": ok_p, "practical": ok_floor}
            if ok_p and ok_floor:
                improved.append(mid)
            elif t["p"] is not None and t["stat"] is not None and t["stat"] > 0 and t["p"] < 0.5:
                inconclusive.append(mid)
            # a goal that got significantly WORSE is a regression too
            t2 = paired_randomization_test(d, "less")
            tol = float((card.get("acceptance") or {}).get("tolerance_sigma", TOLERANCE_SIGMA)) * float(comp.get("sigma") or 0.0)
            if (t2["p"] is not None and t2["p"] <= ALPHA_GUARDRAIL and med < 0) or (-med > tol and tol > 0) or (tol == 0 and med < 0 and t2["p"] is not None and t2["p"] <= ALPHA_GUARDRAIL):
                regressed.append(mid)
                tests[mid]["regression_p"] = t2["p"]
                tests[mid]["goal_regressed"] = True
        else:
            t2 = paired_randomization_test(d, "less")   # alternative: regression (improvement negative)
            tol = float((card.get("acceptance") or {}).get("tolerance_sigma", TOLERANCE_SIGMA)) * float(comp.get("sigma") or 0.0)
            reg = (t2["p"] is not None and t2["p"] <= ALPHA_GUARDRAIL and med < 0) or (tol > 0 and -med > tol) or (tol == 0 and med < 0 and all(x <= 0 for x in d) and any(x < 0 for x in d))
            tests[mid] = {"kind": "paired-sign-flip", "alternative": "regression", "p": t2["p"], "alpha": ALPHA_GUARDRAIL, "n_pairs": t2["n"], "exact": t2["exact"],
                          "median_diff": med, "tolerance_abs": tol, "regressed": bool(reg)}
            if reg:
                regressed.append(mid)
    if c.get("composition") == "oec" and not invalid:
        weights = c.get("oec_weights") or {}
        per_goal = {}
        for comp in comps:
            mid = comp["id"]
            if mid in c["goals"] and comp.get("valid") and cards[mid]["direction"] != "equal":
                d = paired_diffs(cards[mid], results.get(mid) or {}, head_results.get(mid) or {})
                hm = abs(float(comp.get("baseline") or 0.0)) or 1.0
                per_goal[mid] = [float(weights.get(mid, 1.0)) * x / hm for x in d]
        if per_goal:
            n = min(len(v) for v in per_goal.values())
            composite = [sum(v[i] for v in per_goal.values()) for i in range(n)]
            t = paired_randomization_test(composite, "greater")
            tests["__oec__"] = {"kind": "paired-sign-flip", "alternative": "weighted-composite-improvement", "p": t["p"], "alpha": a_look, "n_pairs": t["n"], "exact": t["exact"], "mean_diff": t["stat"]}
            improved = list(per_goal.keys()) if (t["p"] is not None and t["p"] <= a_look and (t["stat"] or 0) > 0) else []
            inconclusive = [] if improved else ([list(per_goal.keys())[0]] if (t["stat"] or 0) > 0 and (t["p"] or 1) < 0.5 else [])
    out = {"level": "confirm", "alpha_campaign": float(num(c.get("alpha", ALPHA_CAMPAIGN), ALPHA_CAMPAIGN)), "alpha_test": a_test, "alpha_look": a_look,
           "look": look, "looks": looks, "multiplicity": c.get("multiplicity", "bonferroni"), "tests": tests, "improved": improved, "regressed": regressed, "invalid": invalid}
    if c.get("composition") == "frontier":
        # goals may trade: a goal regression is allowed when the candidate improves another goal
        # (exact test vs its parent) and no archive member dominates it (heuristic margins).
        goal_regressed = [m for m in regressed if m in c["goals"]]
        guard_regressed = [m for m in regressed if m not in c["goals"]]
        out["goal_regressed"], out["regressed"] = goal_regressed, guard_regressed
        if invalid and c.get("walls", {}).get("validity", True):
            out["verdict"], out["reason"] = "discard", "invalid"
        elif guard_regressed:
            out["verdict"], out["reason"] = "discard", f"regression:{guard_regressed[0]}"
        elif improved:
            cand_vals = {comp["id"]: comp.get("value") for comp in comps if comp["id"] in c["goals"]}
            b = {}
            for comp in comps:
                if comp["id"] in c["goals"]:
                    b[comp["id"]] = comp.get("sigma") or 0.0
            dom = next((m for m in frontier_active(c) if dominates(cards, c["goals"], m["values"], cand_vals, b)), None)
            if dom:
                out["verdict"], out["reason"] = "discard", f"dominated:{dom['id']}"
            else:
                out["verdict"], out["reason"] = "promote", "frontier:improved:" + ",".join(improved) + (":traded:" + ",".join(goal_regressed) if goal_regressed else "")
        elif inconclusive and look < looks:
            out["verdict"], out["reason"] = "inconclusive", "stage-continue"
        else:
            out["verdict"], out["reason"] = "discard", "noise"
        return out
    if invalid and c.get("walls", {}).get("validity", True):
        out["verdict"], out["reason"] = "discard", "invalid"
    elif regressed:
        out["verdict"], out["reason"] = "discard", f"regression:{regressed[0]}"
    elif improved:
        out["verdict"], out["reason"] = "promote", "improved:" + ",".join(improved)
    elif inconclusive and look < looks:
        out["verdict"], out["reason"] = "inconclusive", "stage-continue"
    else:
        out["verdict"], out["reason"] = "discard", "noise"
    return out


def goal_value_dir(card: dict, v) -> float | None:
    """A goal value in 'higher is better' units."""
    try:
        return card_sign(card) * float(v)
    except (TypeError, ValueError):
        return None


def dominates(cards: dict, goals: list, a_vals: dict, b_vals: dict, sig: dict) -> bool:
    """Does A dominate B? A is not worse than B on any goal beyond tolerance (tau*sigma) and
    better than B on at least one goal beyond kappa*sigma. Heuristic margins on stored confirm
    medians; no error-rate claim (docs/13)."""
    better_somewhere = False
    for g in goals:
        card = cards[g]
        av, bv = goal_value_dir(card, a_vals.get(g)), goal_value_dir(card, b_vals.get(g))
        if av is None or bv is None:
            return False
        s_g = float(sig.get(g) or 0.0)
        tol = float((card.get("acceptance") or {}).get("tolerance_sigma", TOLERANCE_SIGMA)) * s_g
        kap = float((card.get("acceptance") or {}).get("kappa", KAPPA)) * s_g
        if av < bv - tol:
            return False
        if av > bv + kap:
            better_somewhere = True
    return better_somewhere


def crowding_distances(cards: dict, goals: list, members: list) -> dict:
    """NSGA-II crowding distance on normalized goal values; extremes get infinity."""
    dist = {m["id"]: 0.0 for m in members}
    if len(members) <= 2:
        return {m["id"]: math.inf for m in members}
    for g in goals:
        vals = [(goal_value_dir(cards[g], m["values"].get(g)), m["id"]) for m in members]
        vals = [(v, i) for v, i in vals if v is not None]
        if len(vals) < 2:
            continue
        vals.sort()
        lo, hi = vals[0][0], vals[-1][0]
        span = (hi - lo) or 1.0
        dist[vals[0][1]] = math.inf
        dist[vals[-1][1]] = math.inf
        for k in range(1, len(vals) - 1):
            if dist[vals[k][1]] != math.inf:
                dist[vals[k][1]] += (vals[k + 1][0] - vals[k - 1][0]) / span
    return dist


def frontier_active(c: dict) -> list:
    return [m for m in (c.get("frontier") or []) if not m.get("retired_by")]


def frontier_pick_parent(cards: dict, c: dict) -> dict | None:
    """The member with the fewest attempts; ties broken by the largest crowding distance
    (extremes first, which pushes the frontier outward). Pre-declared, deterministic."""
    active = frontier_active(c)
    if not active:
        return None
    cd = crowding_distances(cards, c["goals"], active)
    return sorted(active, key=lambda m: (int(m.get("attempts", 0)), -cd.get(m["id"], 0.0), m["id"]))[0]


def frontier_preferred(cards: dict, c: dict) -> dict | None:
    """The member `sb/<campaign>` points at: by declared preference weights on normalized goal
    values, else the knee (max of the minimum normalized improvement over the base member)."""
    active = frontier_active(c)
    if not active:
        return None
    base = next((m for m in (c.get("frontier") or []) if m.get("id") == "f0"), active[0])
    goals = c["goals"]
    weights = ((c.get("preference") or {}).get("weights") or {}) if isinstance(c.get("preference"), dict) else {}
    def norm(m, g):
        bv, mv = goal_value_dir(cards[g], base["values"].get(g)), goal_value_dir(cards[g], m["values"].get(g))
        if bv is None or mv is None:
            return 0.0
        return (mv - bv) / (abs(bv) or 1.0)
    if weights:
        return max(active, key=lambda m: sum(float(weights.get(g, 1.0)) * norm(m, g) for g in goals))
    return max(active, key=lambda m: min(norm(m, g) for g in goals))


def accept_frontier(home: Home, c: dict, r: dict, conf: dict, exp_commit: str, parent: str, eid: str, forced: bool) -> int:
    """Frontier campaigns: the accepted commit becomes a new member on branch `sb/<campaign>-f<k>`
    (a sibling of the campaign branch); members it dominates retire; the archive is pruned by
    crowding distance; `sb/<campaign>` points at the preferred member. No global ratchet is written
    (the frontier is the deliverable)."""
    cards = card_set(home, c)
    pm = next((m for m in (c.get("frontier") or []) if m["id"] == r.get("parent_member")), None)
    if pm is None or pm["commit"] != parent:
        raise SBError(f"{eid} does not descend from its recorded parent member; discard and re-run")
    tree = git(["rev-parse", f"{exp_commit}^{{tree}}"], home.repo)
    msg = git(["log", "-1", "--format=%B", exp_commit], home.repo) + provenance_block(r, conf, c)
    env = dict(os.environ, GIT_AUTHOR_NAME="strictlybetter", GIT_AUTHOR_EMAIL="sb@strictlybetter.local",
               GIT_COMMITTER_NAME="strictlybetter", GIT_COMMITTER_EMAIL="sb@strictlybetter.local")
    p = subprocess.run(["git", "commit-tree", tree, "-p", parent, "-m", msg], cwd=home.repo, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise SBError(f"commit-tree failed: {p.stderr}")
    new_commit = p.stdout.strip()
    k = 1 + max(int(m["id"][1:]) for m in c["frontier"])
    vals = {}
    sig = {}
    for comp in conf.get("comparisons") or []:
        if comp["id"] in c["goals"] and comp.get("valid"):
            vals[comp["id"]] = comp.get("value")
            sig[comp["id"]] = comp.get("sigma") or 0.0
    member = {"id": f"f{k}", "commit": new_commit, "parent": pm["id"], "experiment": eid, "attempts": 0, "values": vals,
              "branch": f"{c['branch']}-f{k}", "accepted_at": now_iso()}   # a sibling ref: git cannot nest refs under an existing branch name
    git(["branch", "-f", member["branch"], new_commit], home.repo)
    retired = []
    for m in frontier_active(c):
        if dominates(cards, c["goals"], vals, m["values"], sig):
            m["retired_by"] = member["id"]
            retired.append(m["id"])
    c["frontier"].append(member)
    # prune by crowding distance, never the extremes
    active = frontier_active(c)
    cap = int(num(c.get("frontier_max", FRONTIER_MAX), FRONTIER_MAX))
    while len(active) > cap:
        cd = crowding_distances(cards, c["goals"], active)
        victim = min(active, key=lambda m: (cd.get(m["id"], 0.0), -int(m.get("attempts", 0))))
        victim["retired_by"] = "crowding"
        retired.append(victim["id"])
        active = frontier_active(c)
    pref = frontier_preferred(cards, c)
    if pref:
        git(["branch", "-f", c["branch"], pref["commit"]], home.repo)
        c["preferred_member"] = pref["id"]
    c["head_commit"] = new_commit
    c["accepted_ids"].append(eid)
    c["since_last_accept"] = 0
    c["exploration_level"] = 0
    c.setdefault("confirmed_effects", []).append(conf.get("confirm_effect"))
    c.setdefault("holdout_gaps", []).append(gap_ratio(conf.get("screen_effect"), conf.get("confirm_effect")))
    c["consecutive_integrity"] = 0
    bandit_update(home, r.get("operator", "config"), True, conf.get("confirm_effect"), float((r.get("cost") or {}).get("wall_s", 0.0)))
    worktree_drop(home, eid)
    home.save_campaign(c)
    home.ledger_add(eid, "accept", {"reason": "forced" if forced else "confirmed", "accepted_commit": new_commit, "branch": member["branch"],
                                    "member": member["id"], "parent_member": pm["id"], "retired": retired, "preferred": c.get("preferred_member")})
    print(json.dumps({"id": eid, "accepted_commit": new_commit, "member": member["id"], "parent_member": pm["id"], "retired": retired,
                      "preferred_member": c.get("preferred_member"), "frontier_size": len(frontier_active(c)), "confirm_effect": conf.get("confirm_effect")}))
    return 0


def gap_ratio(screen_eff, conf_eff) -> float | None:
    if screen_eff is None or conf_eff is None or screen_eff <= 0:
        return None
    return max(0.0, (screen_eff - conf_eff) / screen_eff)


def rotate_holdout(home: Home, c: dict) -> None:
    rng = random.Random()
    for mid in list(c["goals"]) + list(c["guardrails"]):
        card = home.load_card(mid)
        spec = fidelity_spec(card, "confirm")
        ho = spec.get("holdout") or {}
        if ho.get("kind") in ("env", "arg") and ho.get("values"):
            n = len(ho["values"])
            c.setdefault("holdout_override", {})[mid] = [rng.randrange(1, 10**6) for _ in range(n)]
    c["acceptances_since_rotation"] = 0
    home.save_campaign(c)
    home.ledger_add("campaign", "holdout-rotate", {"metrics": list(c.get("holdout_override", {}).keys())})
    # re-baseline confirm level for goals and guardrails on the new holdout
    ns = argparse.Namespace(metric=None, repeats=None, levels="confirm")
    for mid in list(c["goals"]) + list(c["guardrails"]):
        ns.metric = mid
        try:
            cmd_baseline(home, ns)
        except SBError:
            pass


def cmd_discard(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    eid = args.id
    r = experiment_record(home, eid)
    if r.get("verdict") in ("accept", "discard"):
        raise SBError(f"{eid} already {r['verdict']}ed")
    reason = args.reason or (r.get("confirm") or {}).get("reason") or (r.get("judge_stat") or {}).get("reason") or "manual"
    if reason.split(":")[0] not in DISCARD_REASONS:
        raise SBError(f"reason must start with one of {DISCARD_REASONS}")
    archived = False
    path = os.path.join(home.wt_dir, eid)
    if args.archive and r.get("commit"):
        try:
            patch = git(["diff", r.get("base_commit") or c["head_commit"], r["commit"]], home.repo)
            with open(home.p("archive", f"{eid}.diff"), "w", encoding="utf-8") as f:
                f.write(patch)
            archived = True
        except SBError:
            pass
    worktree_drop(home, eid)
    if c.get("status") == "running":
        c["since_last_accept"] = int(c.get("since_last_accept", 0)) + 1
        if c["since_last_accept"] >= int(c.get("plateau_patience", PATIENCE)):
            if c.get("exploration_level", 0) < EXPLORATION_MAX:
                c["exploration_level"] = int(c.get("exploration_level", 0)) + 1
                c["since_last_accept"] = 0
                home.ledger_add("campaign", "explore", {"level": c["exploration_level"]})
    bandit_update(home, r.get("operator", "config"), False, None, float((r.get("cost") or {}).get("wall_s", 0.0)))
    home.save_campaign(c)
    home.ledger_add(eid, "discard", {"reason": reason, "archived": archived, "archive_key": f"{r.get('operator')}|{r.get('target')}" if archived else None})
    print(json.dumps({"id": eid, "discarded": True, "reason": reason, "archived": archived, "exploration_level": c.get("exploration_level")}))
    return 0


def cmd_cost(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    eid = args.id
    experiment_record(home, eid)
    pricing = c.get("pricing") or DEFAULT_PRICING
    tin, tout = int(args.tokens_in or 0), int(args.tokens_out or 0)
    source = "reported"
    if tin == 0 and tout == 0 and args.dollars is None and args.tier:
        # The platform reported no tokens. SB_EST_TOKENS='{"low":[in,out],"medium":[..],"high":[..]}' gives an
        # order-of-magnitude estimate per tier; without it the dollar figure is unknown, not zero (issue #6).
        try:
            est = json.loads(os.environ.get("SB_EST_TOKENS") or "{}").get(args.tier)
        except (json.JSONDecodeError, AttributeError):
            est = None
        if isinstance(est, list) and len(est) == 2:
            tin, tout = int(num(est[0])), int(num(est[1]))
            source = "env-estimate"
        else:
            source = "unknown"
    if args.dollars is not None:
        dollars = float(args.dollars)
    elif source == "unknown":
        dollars = None
    else:
        dollars = (tin * pricing["in_per_mtok"] + tout * pricing["out_per_mtok"]) / 1e6
    data = {"tokens_in": tin, "tokens_out": tout, "wall_s": float(args.wall_s or 0.0), "dollars": dollars, "tier": args.tier,
            "estimated": args.dollars is None, "token_source": source}
    home.ledger_add(eid, "cost", data)
    add_spend(c, wall_s=data["wall_s"], dollars=(dollars or 0.0), tokens_in=tin, tokens_out=tout)
    if source == "unknown":
        c.setdefault("spent", {})["dollars_unknown"] = int(num(c.get("spent", {}).get("dollars_unknown", 0))) + 1
    home.save_campaign(c)
    print(json.dumps({"id": eid, **data}))
    return 0


def stats(home: Home, c: dict) -> dict:
    recs = [r for r in home.experiments().values() if r.get("campaign") == c["id"]]
    n = len(recs)
    promoted = [r for r in recs if (r.get("judge_stat") or {}).get("verdict") in ("promote", "accept-naive")]
    accepted = [r for r in recs if r.get("verdict") == "accept"]
    discarded = [r for r in recs if r.get("verdict") == "discard"]
    fp = [r for r in promoted if r.get("verdict") == "discard"]
    reasons: dict = {}
    for r in discarded:
        key = (r.get("reason") or "?").split(":")[0]
        reasons[key] = reasons.get(key, 0) + 1
    by_op: dict = {}
    for r in recs:
        o = by_op.setdefault(str(r.get("operator") or "?"), {"attempts": 0, "accepts": 0})
        o["attempts"] += 1
        if r.get("verdict") == "accept":
            o["accepts"] += 1
    spent = c.get("spent") if isinstance(c.get("spent"), dict) else {}
    wall = num(spent.get("wall_s", 0.0))
    dollars = num(spent.get("dollars", 0.0))
    fpb = c.get("false_promotion_budget") if isinstance(c.get("false_promotion_budget"), dict) else {"window": FP_WINDOW, "max_fraction": FP_MAX_FRACTION}
    recent_prom = [r for r in promoted if r.get("verdict") in ("accept", "discard")][-max(1, int(num(fpb.get("window", FP_WINDOW), FP_WINDOW))):]
    fp_rate = (len([r for r in recent_prom if r.get("verdict") == "discard"]) / len(recent_prom)) if recent_prom else 0.0
    gaps = [num(g) for g in (c.get("holdout_gaps") if isinstance(c.get("holdout_gaps"), list) else []) if isinstance(g, (int, float))]
    effects = [num(e) for e in (c.get("confirmed_effects") if isinstance(c.get("confirmed_effects"), list) else []) if isinstance(e, (int, float))]
    return {
        "campaign": c["id"], "status": c.get("status"), "experiments": n, "promoted": len(promoted), "accepted": len(accepted),
        "discarded": len(discarded), "discard_reasons": reasons, "false_promotions": len(fp), "false_promotion_rate_window": round(fp_rate, 3),
        "screen_untrusted": bool(c.get("screen_untrusted")), "by_operator": by_op, "wall_s": round(wall, 1),
        "dollars_est": (round(dollars, 4) if not spent.get("dollars_unknown") else "n/a (tokens not reported)"),
        "dollars_unknown_experiments": int(num(spent.get("dollars_unknown", 0))),
        "wall_s_per_accept": round(wall / len(accepted), 1) if accepted else None,
        "dollars_per_accept": ((round(dollars / len(accepted), 4) if not spent.get("dollars_unknown") else "n/a") if accepted else None),
        "confirmed_effects": effects, "mean_confirmed_effect": (sum(effects) / len(effects)) if effects else None,
        "holdout_gap_mean_last5": (sum(gaps[-5:]) / len(gaps[-5:])) if gaps else None,
        "since_last_accept": int(num(c.get("since_last_accept", 0))), "exploration_level": int(num(c.get("exploration_level", 0))),
        "alpha_campaign": c.get("alpha"), "alpha_test": c.get("alpha_test"), "multiplicity": c.get("multiplicity"),
        "confirmations_run": sum(1 for r in recs if r.get("confirm")),
        "expected_false_accepts_upper": (round(float(c.get("alpha_test") or 0) * sum(1 for r in recs if r.get("confirm")), 4) if c.get("alpha_test") else None),
        "budget_left": budget_left(c), "budget_exhausted": budget_exhausted(c),
    }


def cmd_distill_stats(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    s = stats(home, c)
    fpb = c.get("false_promotion_budget") or {}
    if s["promoted"] >= 3 and s["false_promotion_rate_window"] > float(fpb.get("max_fraction", FP_MAX_FRACTION)) and not c.get("screen_untrusted"):
        c["screen_untrusted"] = True
        c["screen_repeats_multiplier"] = min(4, int(c.get("screen_repeats_multiplier", 1)) * 2)
        home.ledger_add("campaign", "screen-untrusted", {"rate": s["false_promotion_rate_window"], "multiplier": c["screen_repeats_multiplier"]})
    decision = "continue"
    if c.get("status") == "halted":
        decision = "stop:halted"
    elif s["budget_exhausted"]:
        decision = f"stop:budget:{s['budget_exhausted']}"
        if c.get("status") == "running":
            halt(home, c, f"budget:{s['budget_exhausted']}")
            c = home.campaign()
    elif int(num(c.get("exploration_level", 0))) >= EXPLORATION_MAX and int(num(c.get("since_last_accept", 0))) >= int(num(c.get("plateau_patience", PATIENCE), PATIENCE)):
        decision = "stop:converged"
        if c.get("status") == "running":
            c["status"] = "ended"
            c["ended_at"] = now_iso()
            c["end_reason"] = "converged"
            home.ledger_add("campaign", "end", {"reason": "converged"})
    elif int(num(c.get("exploration_level", 0))) > 0:
        decision = f"explore:level{int(num(c['exploration_level']))}"
    s["decision"] = decision
    c["last_distill"] = {"at": now_iso(), "experiments": s["experiments"], "decision": decision}
    home.save_campaign(c)
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        for k, v in s.items():
            print(f"{k}: {v}")
    return 0


def cmd_next(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    s = stats(home, c)
    b = home.baseline()
    recs = [r for r in home.experiments().values() if r.get("campaign") == c["id"]]
    open_ids = [r["id"] for r in recs if r.get("verdict") not in ("accept", "discard")]
    dead = [{"id": r["id"], "operator": str(r.get("operator") or "?"), "target": str(r.get("target") or "?"), "reason": str(r.get("reason") or "?"), "hypothesis": str(r.get("hypothesis") or "")[:120]}
            for r in recs if r.get("verdict") == "discard"][-12:]
    wins = [{"id": r["id"], "operator": str(r.get("operator") or "?"), "target": str(r.get("target") or "?"), "effect": (r.get("confirm") or {}).get("confirm_effect") if isinstance(r.get("confirm"), dict) else None, "hypothesis": str(r.get("hypothesis") or "")[:120]}
            for r in recs if r.get("verdict") == "accept"]
    archive = []
    if os.path.isdir(home.p("archive")):
        for f in sorted(os.listdir(home.p("archive")))[-6:]:
            archive.append(f)
    # batch size from budget and screen cost
    screen_s = 0.0
    for mid in [m for m in c["goals"] + c["guardrails"] if isinstance(m, str)]:
        lv = (b.get(mid) or {}).get("levels", {}).get("screen") or {}
        screen_s += num((lv if isinstance(lv, dict) else {}).get("secs_per_run") or 0.0)
    left = budget_left(c)
    batch = int(num(c.get("max_parallel", 2), 2))
    if left.get("hours") is not None and screen_s > 0:
        batch = int(max(1, min(6, (left["hours"] * 3600.0) / (screen_s * 8.0))))
    if left.get("experiments") is not None:
        batch = max(0, min(batch, int(left["experiments"])))
    lvl = int(num(c.get("exploration_level", 0)))
    size_allow = ["tiny", "small"] if lvl == 0 else (["tiny", "small", "medium"] if lvl == 1 else ["tiny", "small", "medium", "large"])
    mix = bandit_mix(home, max(1, batch), seed=args.seed, priors=c.get("archetype_priors") or None)
    frontier = {}
    for mid in [m for m in c["goals"] + c["guardrails"] + c["diagnostics"] if isinstance(m, str)]:
        try:
            direction = home.load_card(mid)["direction"]
        except SBError:
            direction = "?"
        frontier[mid] = {"best": (b.get(mid) or {}).get("best"), "sigma": (b.get(mid) or {}).get("sigma"),
                         "kind": ("goal" if mid in c["goals"] else "guardrail" if mid in c["guardrails"] else "diagnostic"), "direction": direction}
    brief = {"campaign": c["id"], "status": c.get("status"), "halt_reason": c.get("halt_reason"), "head_commit": c.get("head_commit"), "branch": c.get("branch"),
             "budget_left": left, "experiments_run": s["experiments"], "accepted": s["accepted"], "since_last_accept": int(num(c.get("since_last_accept", 0))),
             "exploration_level": lvl, "allowed_diff_sizes": size_allow, "batch_size": batch, "operator_mix": mix, "frontier": frontier,
             "goals": c["goals"], "guardrails": c["guardrails"], "diagnostics": c["diagnostics"], "frozen_paths": c.get("frozen_paths_effective"),
             "protected_paths": protected_paths(home, c), "open_experiments": open_ids, "recent_dead_ends": dead, "accepted_so_far": wins,
             "archive_hints": archive, "inheritance": home.p("inheritance.md") if os.path.isfile(home.p("inheritance.md")) else None,
             "stop_requested": stop_requested(home), "screen_untrusted": bool(c.get("screen_untrusted")), "decision_hint": s.get("decision") if "decision" in s else None,
             "max_parallel": int(num(c.get("max_parallel", 2), 2)), "distill_every": int(num(c.get("distill_every", 8), 8)), "iteration_cap": int(num(c.get("iteration_cap", DEFAULT_ITERATION_CAP), DEFAULT_ITERATION_CAP)),
             "scope_paths": c.get("scope_paths") if isinstance(c.get("scope_paths"), list) else [], "external_instruments": c.get("external_instruments_effective") if isinstance(c.get("external_instruments_effective"), list) else [],
             "walls": c.get("walls") if isinstance(c.get("walls"), dict) else {}, "mde": c.get("mde") if isinstance(c.get("mde"), dict) else {},
             "composition": c.get("composition"), "frontier_members": frontier_active(c) if c.get("composition") == "frontier" else None,
             "parent_member": (frontier_pick_parent(card_set(home, c), c) or {}).get("id") if c.get("composition") == "frontier" else None,
             "preferred_member": c.get("preferred_member")}
    if args.json:
        print(json.dumps(brief, indent=2))
        return 0
    print(f"# strictlybetter brief · campaign {c['id']} · {c.get('status')}" + (f" ({c.get('halt_reason')})" if c.get("halt_reason") else ""))
    print(f"head {str(c.get('head_commit'))[:8]} on {c.get('branch')} · experiments {s['experiments']} · accepted {s['accepted']} · since last accept {c.get('since_last_accept', 0)} · exploration level {lvl}")
    print(f"budget left: {left} · batch size {batch} · allowed diff sizes {size_allow}")
    print("operator mix for this batch: " + ", ".join(f"{op}×{n}" for op, n in mix))
    print("frontier:")
    for mid, f in frontier.items():
        print(f"  {mid:22} {f['kind']:9} {f['direction']:9} best={f['best']} sigma={f['sigma']}")
    if wins:
        print("accepted so far:")
        for w in wins:
            print(f"  {w['id']} {w['operator']:12} {w['target']}: {w['effect']} · {w['hypothesis']}")
    if dead:
        print("recent dead ends (do not retry without a new mechanism):")
        for d in dead:
            print(f"  {d['id']} {d['operator']:12} {d['target']} → {d['reason']} · {d['hypothesis']}")
    if open_ids:
        print(f"open experiments (finish or discard first): {open_ids}")
    if archive:
        print(f"archive hints: {archive}")
    if brief["inheritance"]:
        print(f"inheritance body: {brief['inheritance']}")
    if brief.get("frontier_members"):
        print(f"frontier ({len(brief['frontier_members'])} members; next parent {brief['parent_member']}; preferred {brief.get('preferred_member')}):")
        for m in brief["frontier_members"]:
            print(f"  {m['id']:4} {str(m['commit'])[:8]} attempts={m.get('attempts', 0)} " + " ".join(f"{g}={m['values'].get(g)}" for g in c["goals"]))
    if brief["stop_requested"]:
        print("STOP requested: finish open experiments, then stop.")
    return 0


def cmd_status(home: Home, args) -> int:
    c = home.campaign()
    if not c:
        if args.json:
            print(json.dumps({"campaign": None, "cards": home.list_cards(), "profile": bool(home.profile())}))
        else:
            print(f"no campaign · cards: {len(home.list_cards())} · profile: {'yes' if home.profile() else 'no'}")
        return 0
    s = stats(home, c)
    s["stop_requested"] = stop_requested(home)
    s["head_commit"] = c.get("head_commit")
    s["branch"] = c.get("branch")
    s["iteration_cap"] = c.get("iteration_cap")
    s["open_experiments"] = [r["id"] for r in home.experiments().values() if r.get("campaign") == c["id"] and r.get("verdict") not in ("accept", "discard")]
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print(f"campaign {c['id']} · {c.get('status')}" + (f" ({c.get('halt_reason')})" if c.get("halt_reason") else "") +
              f" · {s['experiments']} experiments · {s['accepted']} accepted · {s['promoted']} promoted · budget left {s['budget_left']}")
        print(f"branch {c.get('branch')} @ {str(c.get('head_commit'))[:8]} · wall {s['wall_s']}s · est ${s['dollars_est']} · per accept: {s['wall_s_per_accept']}s / ${s['dollars_per_accept']}")
        if s["open_experiments"]:
            print(f"open: {s['open_experiments']}")
    return 0


def write_report(home: Home, c: dict) -> str:
    s = stats(home, c)
    b = home.baseline()
    recs = [r for r in home.experiments().values() if r.get("campaign") == c["id"]]
    lines = [f"# strictlybetter campaign report · {c['id']}", "",
             f"Status: **{c.get('status')}**" + (f" ({c.get('halt_reason') or c.get('end_reason') or ''})" if c.get("halt_reason") or c.get("end_reason") else ""),
             f"Branch `{c.get('branch')}` at `{str(c.get('head_commit'))[:12]}` (base `{str(c.get('base_commit'))[:12]}`)", "",
             "## Goals", "", "| metric | direction | start | now | sigma | accepted changes |", "|---|---|---|---|---|---|"]
    start_vals = c.get("start_values") or {}
    for mid in c["goals"]:
        e = b.get(mid) or {}
        lines.append(f"| {mid} | {home.load_card(mid)['direction']} | {start_vals.get(mid, '(not recorded)')} | {e.get('best')} | {e.get('sigma')} | {sum(1 for r in recs if r.get('verdict') == 'accept')} |")
    if c.get("composition") == "frontier":
        cards_r = card_set(home, c)
        pref = frontier_preferred(cards_r, c)
        lines += ["", "## Frontier (non-dominated members; pick a point, or `sb/<campaign>` already points at the preferred one)", "",
                  "| member | from | commit | " + " | ".join(c["goals"]) + " | status |", "|---|---|---|" + "---|" * len(c["goals"]) + "---|"]
        for m in c.get("frontier") or []:
            st = ("retired by " + m["retired_by"]) if m.get("retired_by") else ("preferred" if pref and pref["id"] == m["id"] else "active")
            lines.append(f"| {m['id']} | {m.get('parent') or '-'} | `{m['commit'][:10]}` | " + " | ".join(str(m['values'].get(g)) for g in c["goals"]) + f" | {st} |")
        lines.append("")
        lines.append("Each member beat its parent on at least one goal by the exact paired test; membership (non-dominance) is decided on stored confirm medians with the noise-floor margins and carries no error-rate claim. The global ratchet is not written by a frontier campaign.")
    lines += ["", "## Guardrails", "", "| metric | direction | start | now | status |", "|---|---|---|---|---|"]
    for mid in c["guardrails"]:
        e = b.get(mid) or {}
        card = home.load_card(mid)
        sv, nv = start_vals.get(mid), e.get("best")
        status = "held"
        if sv is not None and nv is not None and card["direction"] != "equal":
            try:
                d = card_sign(card) * (float(nv) - float(sv))
                status = "improved" if d > 0 else ("held" if d == 0 else "DRIFTED")
            except (TypeError, ValueError):
                status = "held"
        elif sv is not None and nv is not None:
            status = "held" if str(sv) == str(nv) else "CHANGED"
        lines.append(f"| {mid} | {card['direction']} | {sv} | {nv} | {status} |")
    lines += ["", "## Cost", "", f"- experiments: {s['experiments']} (promoted {s['promoted']}, accepted {s['accepted']}, discarded {s['discarded']})",
              f"- discard reasons: {s['discard_reasons']}", f"- wall-clock charged (measurement plus experimenter time reported via `sb cost`): {s['wall_s']} s", f"- dollars: {s['dollars_est']} (estimated from reported tokens at the campaign's pricing table" + (f"; {s['dollars_unknown_experiments']} experiment(s) reported no tokens, so the total is unknown" if s.get('dollars_unknown_experiments') else "") + ")",
              f"- per accepted improvement: {s['wall_s_per_accept']} s, ${s['dollars_per_accept']}", f"- false promotions: {s['false_promotions']} (window rate {s['false_promotion_rate_window']})",
              f"- holdout gap (mean of last 5 accepted): {s['holdout_gap_mean_last5']}",
              f"- acceptance test: exact paired sign-flip, one-sided; family-wise alpha {s.get('alpha_campaign')} ({s.get('multiplicity')} over the pre-registered budget) → per-confirmation alpha {s.get('alpha_test')}; confirmations run {s.get('confirmations_run')}; expected false accepts if every candidate were null: ≤ {s.get('expected_false_accepts_upper')}", f"- walls: {', '.join(k for k, v in c.get('walls', {}).items() if v) or 'none (naive)'}", "",
              "## Accepted changes", ""]
    for r in recs:
        if r.get("verdict") == "accept":
            lines.append(f"- `{r['id']}` [{r.get('operator')}] {r.get('target')}: {r.get('hypothesis')} → confirm effect {(r.get('confirm') or {}).get('confirm_effect')} · commit `{str(r.get('accepted_commit'))[:10]}`")
    lines += ["", "## Discarded", ""]
    for r in recs:
        if r.get("verdict") == "discard":
            lines.append(f"- `{r['id']}` [{r.get('operator')}] {r.get('target')}: {r.get('reason')} · {(r.get('hypothesis') or '')[:100]}")
    lines += ["", "## Reproduce", "", f"    git checkout {c.get('branch')}", "    sb measure --fidelity confirm  (per accepted experiment id, see ledger)", ""]
    out = "\n".join(lines) + "\n"
    try:
        os.makedirs(home.p("reports"), exist_ok=True)
        with open(home.p("reports", f"{c['id']}.md"), "w", encoding="utf-8") as f:
            f.write(out)
    except OSError as e:
        raise SBError(f"cannot write report: {e}")
    return out


def cmd_frontier(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    if c.get("composition") != "frontier":
        raise SBError("not a frontier campaign")
    cards = card_set(home, c)
    pref = frontier_preferred(cards, c)
    rows = []
    for m in c.get("frontier") or []:
        rows.append({"id": m["id"], "commit": m["commit"], "parent": m.get("parent"), "experiment": m.get("experiment"), "attempts": m.get("attempts", 0),
                     "values": m.get("values"), "retired_by": m.get("retired_by"), "branch": m.get("branch"), "preferred": bool(pref and pref["id"] == m["id"])})
    if args.json:
        print(json.dumps({"goals": c["goals"], "members": rows, "preferred": pref["id"] if pref else None, "preference": c.get("preference")}, indent=2))
        return 0
    print(f"frontier of campaign {c['id']} · goals {c['goals']} · preferred {pref['id'] if pref else None}" + (f" (weights {c['preference'].get('weights')})" if c.get('preference') else " (knee: max of min normalized gain)"))
    for row in rows:
        flag = " retired:" + row["retired_by"] if row["retired_by"] else (" *" if row["preferred"] else "")
        print(f"  {row['id']:4} {row['commit'][:8]} from {row['parent'] or '-':4} exp {row['experiment'] or '-':6} attempts={row['attempts']} " + " ".join(f"{g}={row['values'].get(g)}" for g in c["goals"]) + flag)
    return 0


def cmd_report(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    print(write_report(home, c))
    return 0


def cmd_budget(home: Home, args) -> int:
    c = require_campaign(home, running=False)
    print(json.dumps({"budget": c.get("budget"), "spent": c.get("spent"), "left": budget_left(c), "exhausted": budget_exhausted(c), "iteration_cap": c.get("iteration_cap")}, indent=2))
    return 0


def guard_decision(home: Home, path: str) -> tuple:
    """Return (allow: bool, reason: str)."""
    if os.environ.get("SB_GUARD", "").lower() in ("off", "0", "false") or os.path.exists(home.p("guard.off")):
        return True, "guard off"
    c = home.campaign()
    if not c or c.get("status") != "running" or not c.get("walls", {}).get("frozen_guard", True):
        return True, "no running campaign"
    ap = os.path.abspath(path)
    repo = os.path.realpath(home.repo)
    apr = os.path.realpath(ap) if os.path.exists(ap) else os.path.join(os.path.realpath(os.path.dirname(ap)), os.path.basename(ap))
    for ep in c.get("external_instruments_effective") or external_instruments(home, c):
        er = os.path.realpath(ep)
        if apr == er or apr.startswith(er + os.sep):
            return False, f"external instrument ({ep}): frozen for the campaign"
    if not (apr == repo or apr.startswith(repo + os.sep)):
        return True, "outside repo"
    home_real = os.path.realpath(home.path)
    wt_real = os.path.realpath(home.wt_dir)
    fp = c.get("frozen_paths_effective") or frozen_paths(home, c)
    pp = protected_paths(home, c)
    if apr.startswith(wt_real + os.sep):
        rest = apr[len(wt_real) + 1:]
        parts = rest.split(os.sep, 1)
        rel = parts[1] if len(parts) > 1 else ""
        if rel.startswith(".strictlybetter"):
            return False, "state files are written by the harness only"
        hit = matches_any(rel, fp)
        if hit:
            return False, f"frozen path ({hit}): the instrument cannot be edited during a campaign"
        hit = matches_any(rel, pp)
        if hit:
            return False, f"protected path ({hit})"
        scope = c.get("scope_paths") or []
        if scope and rel and not matches_any(rel, scope):
            return False, f"outside the campaign scope ({', '.join(scope)})"
        return True, "inside experiment worktree"
    if apr.startswith(home_real + os.sep) or apr == home_real:
        rel = os.path.relpath(apr, home_real)
        if rel.split(os.sep)[0] in ("inbox", "tmp"):
            return True, "agent payload area"
        return False, "state files are written by the harness only"
    return False, "edits outside experiment worktrees are blocked while a campaign is running (set SB_GUARD=off to override)"


def cmd_guard(home: Home, args) -> int:
    path = args.path
    if args.stdin:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            payload = {}
        ti = payload.get("tool_input") or {}
        path = ti.get("file_path") or ti.get("notebook_path") or path
        if not path:
            return 0
    allow, reason = guard_decision(home, path)
    if allow:
        return 0
    sys.stderr.write(f"strictlybetter guard: denied edit to {path}: {reason}\n")
    return 2


def cmd_session_start(home: Home, args) -> int:
    if not home.exists():
        return 0
    c = home.campaign()
    if not c:
        return 0
    if c.get("status") == "running":
        s = stats(home, c)
        left = s["budget_left"]
        print(f"[strictlybetter] campaign {c['id']} running: {s['experiments']} experiments, {s['accepted']} accepted, budget left {left}. `/strictlybetter` continues it.")
    elif c.get("status") == "halted":
        print(f"[strictlybetter] campaign {c['id']} HALTED: {c.get('halt_reason')}. `sb campaign resume` after review.")
    return 0


def cmd_doctor(home: Home, args) -> int:
    ok = True
    print(f"sb {VERSION} · python {sys.version.split()[0]} · repo {home.repo} · home {home.path}")
    try:
        git(["--version"], home.repo)
        print("git: ok")
    except SBError as e:
        ok = False
        print(f"git: FAIL {e}")
    prof = home.profile()
    for k, v in (prof.get("commands") or {}).items():
        if not v:
            continue
        rc, out, err, secs = run_cmd(v, cwd=home.repo, timeout=600)
        print(f"command {k}: rc={rc} ({secs:.1f}s)")
        if rc != 0 and k in ("build", "test"):
            ok = False
    for mid in home.list_cards():
        try:
            home.load_card(mid)
        except SBError as e:
            ok = False
            print(f"card {mid}: {e}")
    c = home.campaign()
    if c:
        print(f"campaign {c['id']}: {c.get('status')} head {str(c.get('head_commit'))[:8]}")
    print("doctor: ok" if ok else "doctor: problems found")
    return 0 if ok else 1


def redact(rec: dict) -> dict:
    """Limited leakage (docs/04 §4.4): a discarded candidate's holdout numbers stay in the file
    for audit but are not surfaced to the experimenter-facing views."""
    r = dict(rec)
    if r.get("verdict") == "discard" and isinstance(r.get("confirm"), dict):
        cf = dict(r["confirm"])
        for k in ("results", "comparisons", "confirm_effect", "head_results"):
            if k in cf:
                cf[k] = "<redacted: holdout numbers of a discarded candidate>"
        r["confirm"] = cf
    if r.get("verdict") not in ("accept",) and isinstance(r.get("measures"), dict) and "confirm" in r["measures"]:
        m = dict(r["measures"])
        m["confirm"] = "<redacted: holdout measurement>"
        r["measures"] = m
    return r


def redact_event(e) -> dict:
    if not isinstance(e, dict):
        return {"corrupt": True, "raw": str(e)[:80]}
    data = e.get("data") if isinstance(e.get("data"), dict) else {}
    if e.get("event") == "confirm" or (e.get("event") == "measure" and data.get("fidelity") == "confirm"):
        return {**e, "data": {k: v for k, v in data.items() if k in ("verdict", "reason", "level", "commit", "fidelity", "rounds")} | {"redacted": "holdout numbers"}}
    return e


def cmd_ledger(home: Home, args) -> int:
    if args.action == "view":
        rec = experiment_record(home, args.id)
        print(json.dumps(rec if args.unredacted else redact(rec), indent=2))
    elif args.action == "tail":
        for e in home.ledger_events()[-int(args.n or 20):]:
            print(json.dumps(e if args.unredacted else redact_event(e)))
    elif args.action == "experiments":
        for r in home.experiments().values():
            print(json.dumps({k: r.get(k) for k in ["id", "campaign", "operator", "target", "verdict", "reason", "diff_lines"]}))
    return 0


def cmd_inheritance(home: Home, args) -> int:
    if args.action == "write":
        with open(args.file, "r", encoding="utf-8") as f:
            body = f.read()
        if "## " not in body:
            raise SBError("inheritance body must have sections")
        with open(home.p("inheritance.md"), "w", encoding="utf-8") as f:
            f.write(body)
        home.ledger_add("campaign", "distill", {"bytes": len(body)})
        print(f"inheritance written: {home.p('inheritance.md')}")
        return 0
    if args.action == "show":
        p = home.p("inheritance.md")
        try:
            print(open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else "")
        except OSError as e:
            raise SBError(f"cannot read {p}: {e}")
        return 0
    raise SBError("inheritance: write|show")


def cmd_stop(home: Home, args) -> int:
    home.ensure()
    with open(home.p("STOP"), "w") as f:
        f.write(now_iso() + "\n")
    print("STOP requested; the loop halts at the next safe point")
    return 0


def cmd_worktree(home: Home, args) -> int:
    if args.action == "new":
        print(worktree_new(home, args.id, args.commit or head_commit(home)))
    elif args.action == "drop":
        worktree_drop(home, args.id)
        print("dropped")
    elif args.action == "path":
        print(os.path.join(home.wt_dir, args.id))
    elif args.action == "list":
        print(git(["worktree", "list"], home.repo))
    return 0


def cmd_drive(home: Home, args) -> int:
    """Run an external agent command once per cycle until the campaign stops."""
    for i in range(int(args.cycles)):
        c = home.campaign()
        if not c or c.get("status") != "running" or stop_requested(home):
            print("campaign not running; drive stops")
            return 0
        rc, out, err, secs = run_cmd(args.command, cwd=home.repo, timeout=float(args.timeout))
        print(f"cycle {i + 1}: rc={rc} {secs:.0f}s")
        if args.verbose:
            print(out[-2000:])
    return 0


# ----------------------------------------------------------------------------
# Selftest
# ----------------------------------------------------------------------------
def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    # AST: no network modules imported by this engine
    import ast
    src = open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    tree = ast.parse(src)
    banned = {"socket", "urllib", "http", "ssl", "ftplib", "smtplib", "requests", "xmlrpc"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    check("no network imports", not (imported & banned))
    # version pin against plugin manifest when present
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pj = os.path.join(root, ".claude-plugin", "plugin.json")
    if os.path.exists(pj):
        check("version pinned to plugin.json", read_json(pj).get("version") == VERSION)
    # parsing
    check("metric-line parse", parse_output("metric-line:x", "noise\nMETRIC x=12.5\nMETRIC y=1\n") == 12.5)
    check("metric-line string value", parse_output("metric-line:sum", "METRIC sum=abcd1234") == "abcd1234")
    check("regex parse", parse_output(r"regex:real (\d+\.\d+)", "real 1.25\nuser 0.1") == 1.25)
    check("json parse", parse_output("json:a.b", '{"a": {"b": 3}}') == 3.0)
    try:
        parse_output("metric-line:y", "METRIC x=1")
        check("missing metric raises", False)
    except SBError:
        check("missing metric raises", True)
    # stats
    check("sigma_of n=3 is stdev", abs(sigma_of([1, 2, 3]) - statistics.stdev([1, 2, 3])) < 1e-9)
    check("sigma_of n>=4 is MAD-scaled", abs(sigma_of([468, 489, 471, 758, 1206]) - 1.4826 * 21.0) < 0.01)
    check("sigma_of robust to bursts", sigma_of([468, 489, 471, 758, 1206]) < 60 < statistics.stdev([468, 489, 471, 758, 1206]))
    check("sigma_of single", sigma_of([1]) is None)
    check("se_factor", abs(se_factor(3, 5) - math.sqrt(1 / 3 + 1 / 5)) < 1e-12 and se_factor(1, 1) > 1.4)
    check("kappa_eff small diff", abs(kappa_eff(2.5, 0, 0) - 2.5) < 1e-9)
    check("kappa_eff grows with diff", kappa_eff(2.5, 400, 0) > kappa_eff(2.5, 40, 0) > 2.5)
    check("kappa_eff dep penalty", kappa_eff(2.5, 0, 1) == 3.5)
    # path matching
    check("match dir", match_path("tests/test_x.py", "tests/"))
    check("match exact file", match_path("bench.py", "bench.py") and not match_path("bench.pyc", "bench.py"))
    check("match glob", match_path("secrets/a.pem", "*.pem"))
    check("no match", not match_path("src/lib.rs", "tests/"))
    # acceptance rule
    walls = {k: True for k in WALL_KEYS}
    goal = {"id": "g", "kind": "goal", "direction": "minimize"}
    guard = {"id": "h", "kind": "guardrail", "direction": "minimize"}
    eq = {"id": "q", "kind": "guardrail", "direction": "equal"}
    base = {"median": 100.0, "sigma": 2.0, "n": 5}
    c1 = compare_metric(goal, base, {"valid": True, "median": 90.0, "n_valid": 3}, 2.5, 1.0, walls)
    check("goal improved beyond 2.5 sigma", c1["improved"] and not c1["regressed"])
    c2 = compare_metric(goal, base, {"valid": True, "median": 97.0}, 2.5, 1.0, walls)
    check("goal within noise is inconclusive", (not c2["improved"]) and c2["inconclusive"])
    c3 = compare_metric(goal, base, {"valid": True, "median": 103.0}, 2.5, 1.0, walls)
    check("goal worse beyond tolerance regresses", c3["regressed"])
    c4 = compare_metric(guard, base, {"valid": True, "median": 101.5}, 2.5, 1.0, walls)
    check("guardrail within tolerance holds", not c4["regressed"])
    c5 = compare_metric(guard, {"median": 0.0, "sigma": 0.0}, {"valid": True, "median": 1.0}, 2.5, 0.0, walls)
    check("deterministic guardrail any drop regresses", c5["regressed"])
    c6 = compare_metric(eq, {"median": "abc"}, {"valid": True, "median": "abd"}, 2.5, 0.0, walls)
    check("equal guardrail differs regresses", c6["regressed"])
    c7 = compare_metric(goal, base, {"valid": True, "median": 99.0}, 2.5, 1.0, {**walls, "noise_floor": False})
    check("naive mode accepts any improvement", c7["improved"])
    camp = {"goals": ["g"], "guardrails": ["h", "q"], "walls": walls, "composition": "pareto"}
    d = decide({}, camp, [c1, c4, compare_metric(eq, {"median": "x"}, {"valid": True, "median": "x"}, 2.5, 0, walls)], "screen")
    check("decide promote", d["verdict"] == "promote")
    d = decide({}, camp, [c1, compare_metric(guard, base, {"valid": True, "median": 110.0}, 2.5, 1.0, walls)], "screen")
    check("decide regression beats improvement", d["verdict"] == "discard" and d["reason"].startswith("regression"))
    d = decide({}, camp, [c2], "screen")
    check("decide inconclusive", d["verdict"] == "inconclusive")
    d = decide({}, camp, [compare_metric(goal, base, {"valid": False, "invalid": ["timeout"]}, 2.5, 1.0, walls)], "screen")
    check("decide invalid", d["verdict"] == "discard" and d["reason"] == "invalid")
    check("gap ratio", gap_ratio(0.10, 0.05) == 0.5 and gap_ratio(None, 0.1) is None)
    t = paired_randomization_test([1.0] * 10, "greater")
    check("sign-flip: all-positive pairs give p = 2^-n", abs(t["p"] - 2 ** -10) < 1e-12 and t["exact"])
    t = paired_randomization_test([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0], "greater")
    check("sign-flip: symmetric pairs give p ~ 0.5", 0.4 < t["p"] < 0.7)
    t = paired_randomization_test([0.0] * 6, "greater")
    check("sign-flip: all-zero pairs give p = 1", t["p"] == 1.0)
    t = paired_randomization_test([-2.0] * 8, "less")
    check("sign-flip: regression alternative", abs(t["p"] - 2 ** -8) < 1e-12)
    t = paired_randomization_test([3.0, 2.5, 2.8, 3.1, 2.9, 3.0, 2.7, 3.2, 2.6, 3.0, -0.1, 0.2, 2.9, 3.0, 2.8, 3.1, 2.9, 3.0, 2.7, 3.2, 2.6, 3.0], "greater")
    check("sign-flip: Monte Carlo above the exact limit", t["exact"] is False and t["p"] < 0.01)
    check("alpha per test is alpha over the budget", abs(alpha_per_test({"alpha": 0.05, "multiplicity": "bonferroni", "budget": {"experiments": 10}}) - 0.005) < 1e-12
          and alpha_per_test({"alpha": 0.05, "multiplicity": "none", "budget": {"experiments": 10}}) == 0.05
          and abs(alpha_per_test({"alpha": 0.05, "multiplicity": "bonferroni", "budget": {"hours": 2}}) - 0.05 / DEFAULT_ITERATION_CAP) < 1e-12)
    pd = paired_diffs({"direction": "minimize"}, {"runs": [{"valid": True, "value": 1.0}, {"valid": False, "value": None}, {"valid": True, "value": 3.0}]},
                      {"runs": [{"valid": True, "value": 2.0}, {"valid": True, "value": 9.0}, {"valid": True, "value": 4.0}]})
    check("pairs align by index and drop invalid members", pd == [1.0, 1.0])
    tcard_ms = {"id": "t", "kind": "goal", "direction": "minimize", "unit": "ms", "measure": {"command": "x", "parse": "metric-line:t"}}
    tcard_ct = {"id": "c", "kind": "guardrail", "direction": "minimize", "unit": "count", "measure": {"command": "x", "parse": "metric-line:c"}}
    check("timing metric screens with 2 repeats and 1 warm-up", fidelity_spec(tcard_ms, "screen")["repeats"] == 2 and fidelity_spec(tcard_ms, "screen")["warmup"] == 1)
    check("count metric screens with 1 repeat and no warm-up", fidelity_spec(tcard_ct, "screen")["repeats"] == 1 and fidelity_spec(tcard_ct, "screen")["warmup"] == 0)
    tcard = {"id": "t", "kind": "goal", "direction": "minimize", "unit": "ms"}
    tbase = {"median": 100.0, "sigma": 1.0, "n": 5, "secs_per_run": 2.0}
    tbase = {"median": 400.0, "sigma": 1.0, "n": 5, "secs_per_run": 0.5}   # 400 ms measured inside a 0.5 s process
    tmeas = {"valid": True, "median": 1.0, "secs_total": 1.5, "n": 3}       # claims 399 ms saved, process still 0.5 s
    tcomp = compare_metric(tcard, tbase, tmeas, 2.5, 1.0, walls)
    check("timer divergence flags a lying instrument", timer_divergence(tcard, tbase, tmeas, tcomp) is not None)
    check("timer divergence passes a real speedup", timer_divergence(tcard, tbase, {"valid": True, "median": 1.0, "secs_total": 0.33, "n": 3}, tcomp) is None)
    obase = {"median": 130.0, "sigma": 1.0, "n": 5, "secs_per_run": 1.9}    # 130 ms of work inside 1.9 s of fixed setup
    ocomp = compare_metric(tcard, obase, {"valid": True, "median": 15.0, "secs_total": 5.6, "n": 3}, 2.5, 1.0, walls)
    check("timer divergence ignores savings hidden by fixed overhead", timer_divergence(tcard, obase, {"valid": True, "median": 15.0, "secs_total": 5.6, "n": 3}, ocomp) is None)
    # end-to-end on a temp git repo with a fake metric
    with tempfile.TemporaryDirectory() as td:
        repo = os.path.join(td, "repo")
        os.makedirs(repo)
        git(["init", "-q", "-b", "main"], repo)
        git(["config", "user.email", "t@t"], repo)
        git(["config", "user.name", "t"], repo)
        check("fresh repo has no profile", not Home(repo=repo, home=os.path.join(repo, ".strictlybetter")).profile())
        with open(os.path.join(repo, "work.py"), "w") as f:
            f.write("N = 40\n")
        with open(os.path.join(repo, "bench.py"), "w") as f:
            f.write("import work, os, random\nr = random.Random(int(os.environ.get('SB_SEED', '0')))\n"
                    "print('METRIC score=%d' % (work.N + r.randint(0, 1)))\nprint('METRIC checks=%s' % ('ok' if work.N > 0 else 'bad'))\n"
                    "print('METRIC seed=%s' % os.environ.get('SB_SEED', '0'))\n")
        os.makedirs(os.path.join(repo, "tests"))
        with open(os.path.join(repo, "tests", "t.py"), "w") as f:
            f.write("print('METRIC tests_failed=0')\n")
        git(["add", "-A"], repo)
        git(["commit", "-q", "-m", "base"], repo)
        home = Home(repo=repo, home=os.path.join(repo, ".strictlybetter"))
        home.ensure()
        card_g = {"id": "score", "kind": "goal", "direction": "minimize", "measure": {"command": "python3 bench.py", "parse": "metric-line:score", "timeout_s": 60},
                  "fidelity": {"screen": {"repeats": 1}, "confirm": {"repeats": 10, "max_repeats": 10, "holdout": {"kind": "env", "var": "SB_SEED", "values": [7, 8, 9]}}},
                  "integrity": {"frozen_paths": ["bench.py", "tests/"]}, "gaming_risks": ["edit bench"], "contention_safe": True,
                  "degradation": {"apply": "python3 -c \"open('work.py','w').write('N = 60\\n')\""}}
        card_h = {"id": "tests_failed", "kind": "guardrail", "direction": "minimize", "measure": {"command": "python3 tests/t.py", "parse": "metric-line:tests_failed", "timeout_s": 60},
                  "fidelity": {"full": {"repeats": 1}},   # a guardrail-only full level must not block a goal that has none (power-bench finding)
                  "integrity": {"frozen_paths": ["tests/"]}, "gaming_risks": [], "contention_safe": True, "acceptance": {"tolerance_sigma": 0}}
        card_q = {"id": "checks", "kind": "guardrail", "direction": "equal", "measure": {"command": "python3 bench.py", "parse": "metric-line:checks", "timeout_s": 60},
                  "gaming_risks": [], "contention_safe": True}
        card_s = {"id": "seed", "kind": "diagnostic", "direction": "maximize", "measure": {"command": "python3 bench.py", "parse": "metric-line:seed", "timeout_s": 60},
                  "fidelity": {"confirm": {"repeats": 10, "holdout": {"kind": "env", "var": "SB_SEED", "values": [7, 8, 9]}}}, "gaming_risks": [], "contention_safe": True, "reuse_output": True}
        for cd in (card_g, card_h, card_q, card_s):
            validate_card(cd)
            home.save_card(cd)
        # probe: degradation must make score worse
        ns = argparse.Namespace(id="score", repeats=2)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_card_probe(home, ns)
        check("monotonicity probe passes", rc == 0)
        spec = {"id": "t1", "goals": ["score"], "guardrails": ["tests_failed", "checks"], "diagnostics": ["seed"], "budget": {"experiments": 6}, "plateau_patience": 2}
        sp = os.path.join(td, "c.json")
        write_json_atomic(sp, spec)
        ns = argparse.Namespace(action="start", file=sp, no_baseline=False, repeats=4, allow_unusable=False, allow_ratchet_regression=False)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_campaign(home, ns)
        c = home.campaign()
        check("campaign running", c and c["status"] == "running")
        b = home.baseline()
        check("baseline measured score", b.get("score", {}).get("best") is not None and b["score"].get("sigma") is not None)
        check("eval hash set", bool(c.get("eval_hash")))
        # budget is charged before any work: a prereg that fails at worktree creation still counts
        c_before = home.campaign()
        spent_before = int(c_before["spent"]["experiments"])
        c_before["head_commit"] = "0" * 40
        home.save_campaign(c_before)
        hp = os.path.join(td, "h.json")
        write_json_atomic(hp, {"operator": "config", "target": "work.py", "hypothesis": "x", "predicted": {"score": "-1%"}})
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_prereg(home, argparse.Namespace(file=hp))
        except SBError:
            pass
        c_after = home.campaign()
        check("budget charged before worktree creation", int(c_after["spent"]["experiments"]) == spent_before + 1)
        c_after["head_commit"] = c_before_head = git(["rev-parse", "HEAD"], repo)
        c_after["next_id"] = 1
        c_after["spent"]["experiments"] = spent_before
        home.save_campaign(c_after)
        # a goal without a measured sigma cannot start a campaign
        home2 = Home(repo=repo, home=os.path.join(td, "home2"))
        home2.ensure()
        card_ns = dict(card_g)
        card_ns["id"] = "score1"
        card_ns["fidelity"] = {"screen": {"repeats": 1}, "confirm": {"repeats": 1, "max_repeats": 1}}
        # (also underpowered: 1 pair cannot reach alpha/2; the sigma halt fires first at baseline)
        home2.save_card(card_ns)
        sp2 = os.path.join(td, "c2.json")
        write_json_atomic(sp2, {"id": "t2", "goals": ["score1"], "budget": {"experiments": 2}})
        halted_ns = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_campaign(home2, argparse.Namespace(action="start", file=sp2, no_baseline=False, repeats=1, allow_unusable=True, allow_ratchet_regression=False, allow_underpowered=False))
        except SBError:
            halted_ns = "no measured sigma" in str((home2.campaign() or {}).get("halt_reason", ""))
        check("goal without measured sigma halts at start", halted_ns)
        # a goal whose targets are all frozen halts at start unless marked control (issue #3)
        home3 = Home(repo=repo, home=os.path.join(td, "home3"))
        home3.ensure()
        card_ctl = dict(card_g)
        card_ctl["id"] = "score_ctl"
        card_ctl["targets"] = ["bench.py"]   # its only target is the frozen bench
        home3.save_card(card_ctl)
        sp3 = os.path.join(td, "c3.json")
        write_json_atomic(sp3, {"id": "t3", "goals": ["score_ctl"], "budget": {"experiments": 2}})
        frozen_goal = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_campaign(home3, argparse.Namespace(action="start", file=sp3, no_baseline=False, repeats=3, allow_unusable=True, allow_ratchet_regression=False, allow_underpowered=False))
        except SBError:
            frozen_goal = str((home3.campaign() or {}).get("halt_reason", "")).startswith("goal-frozen")
        check("goal with only frozen targets halts at start", frozen_goal)
        # experiment 1: real improvement (N 40 -> 20)
        hp = os.path.join(td, "h.json")
        write_json_atomic(hp, {"operator": "algorithmic", "target": "work.py", "hypothesis": "halve N", "predicted": {"score": "-50%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e1 = json.loads(out.getvalue())["id"]
        with open(os.path.join(home.wt_dir, e1, "work.py"), "w") as f:
            f.write("N = 20\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_submit(home, argparse.Namespace(id=e1))
        check("submit ok", rc == 0)
        # guard: frozen path inside worktree denied, source allowed, state denied
        allow, _ = guard_decision(home, os.path.join(home.wt_dir, e1, "bench.py"))
        check("guard denies frozen path", not allow)
        allow, _ = guard_decision(home, os.path.join(home.wt_dir, e1, "work.py"))
        check("guard allows worktree source", allow)
        allow, _ = guard_decision(home, os.path.join(repo, "work.py"))
        check("guard denies main tree during campaign", not allow)
        allow, _ = guard_decision(home, home.p("baseline.json"))
        check("guard denies state file", not allow)
        allow, _ = guard_decision(home, home.p("inbox", "h.json"))
        check("guard allows inbox", allow)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_measure(home, argparse.Namespace(id=e1, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            cmd_judge(home, argparse.Namespace(id=e1, fidelity="screen"))
        r = home.experiments()[e1]
        check("judge promotes real improvement", r["judge_stat"]["verdict"] == "promote")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_measure(home, argparse.Namespace(id=e1, fidelity="confirm", repeats=None, keep_runs=False, audit=False))
            check("confirm-fidelity measure refused while running", False)
        except SBError:
            check("confirm-fidelity measure refused while running", True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_judge_payload(home, argparse.Namespace(id=e1, out=None))
        jp = read_json(out.getvalue().strip())
        check("judge payload has diff and no reasoning", "N = 20" in jp["diff"]["text"] and "reasoning" not in json.dumps(jp) and "hypothesis" in jp["prereg"] and jp["id"] == e1 and "comparisons" in jp["screen"])
        check("strip_comments", strip_comments({"a": 1, "_comment": "x", "b": {"_comment_c": 1, "d": [{"_comment": 2, "e": 3}]}}) == {"a": 1, "b": {"d": [{"e": 3}]}})
        vp = os.path.join(td, "v.json")
        write_json_atomic(vp, {"verdict": "clean", "pattern": "", "evidence": "", "recommended_check": ""})
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_judge_verdict(home, argparse.Namespace(id=e1, file=vp))
        write_json_atomic(vp, {"verdict": "clean", "reasoning": "trust me"})
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_judge_verdict(home, argparse.Namespace(id=e1, file=vp))
            check("verdict schema forbids extra fields", False)
        except SBError:
            check("verdict schema forbids extra fields", True)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_confirm(home, argparse.Namespace(id=e1, force=False))
        r = home.experiments()[e1]
        check("confirm accepts real improvement", r["confirm"]["verdict"] == "accept")
        tt = (r["confirm"].get("tests") or {}).get("score") or {}
        check("confirm carries the exact test", tt.get("kind") == "paired-sign-flip" and tt.get("p") is not None and tt["p"] <= tt["alpha"] and tt.get("n_pairs") == 10)
        check("guardrail-only full level does not block", r["confirm"].get("level") == "confirm")
        check("confirm is paired against fresh head", r["confirm"].get("paired") is True and (r["confirm"].get("head_results") or {}).get("score", {}).get("median") in (40.0, 41.0))
        check("confirm used the holdout seeds", sorted(set((r["confirm"].get("results") or {}).get("seed", {}).get("values") or [])) == [7.0, 8.0, 9.0])
        check("paired baseline is fresh head median", any(comp["id"] == "score" and comp["baseline"] in (40.0, 41.0) for comp in r["confirm"]["comparisons"]))
        # re-submitting a different (tampered) commit after confirmation must not be acceptable
        wt1 = os.path.join(home.wt_dir, e1)
        git(["reset", "-q", "--soft", c["head_commit"]], wt1)
        with open(os.path.join(wt1, "bench.py"), "a") as f:
            f.write("# tamper\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_submit(home, argparse.Namespace(id=e1))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_accept(home, argparse.Namespace(id=e1, force=False))
            check("resubmitted tampered commit not acceptable", False)
        except SBError:
            check("resubmitted tampered commit not acceptable", True)
        # restore the honest commit and its confirmation for the rest of the selftest
        git(["reset", "-q", "--hard", c["head_commit"]], wt1)  # back to the campaign head; bench.py restored
        with open(os.path.join(wt1, "work.py"), "w") as f:
            f.write("N = 20\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_submit(home, argparse.Namespace(id=e1))
            cmd_campaign(home, argparse.Namespace(action="resume", file=None, reason=None, no_baseline=True, repeats=None, allow_unusable=False, allow_ratchet_regression=False, allow_underpowered=False))
            cmd_measure(home, argparse.Namespace(id=e1, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            cmd_judge(home, argparse.Namespace(id=e1, fidelity="screen"))
            write_json_atomic(vp, {"verdict": "clean", "pattern": "", "evidence": "", "recommended_check": ""})
            cmd_judge_verdict(home, argparse.Namespace(id=e1, file=vp))
            cmd_confirm(home, argparse.Namespace(id=e1, force=False))
        r = home.experiments()[e1]
        check("confirm re-run binds to the resubmitted commit", r["confirm"].get("commit") == r["commit"] and r["confirm"]["verdict"] == "accept")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_accept(home, argparse.Namespace(id=e1, force=False))
        c = home.campaign()
        check("head moved", c["head_commit"] != c["base_commit"])
        check("branch fast-forwarded", git(["rev-parse", c["branch"]], repo) == c["head_commit"])
        check("ratchet updated", home.ratchet().get("score", {}).get("best") == 20.0 or home.ratchet().get("score", {}).get("best") == 21.0)
        check("provenance in commit", "strictlybetter provenance" in git(["log", "-1", "--format=%B", c["head_commit"]], repo))
        check("start values recorded", c.get("start_values", {}).get("score") is not None)
        check("card hashes frozen", c.get("card_hashes", {}).get("score"))
        check("guard keeps basename of a new file", not guard_decision(home, os.path.join(home.wt_dir, "zz", "secrets.pem"))[0] if os.path.isdir(os.path.join(home.wt_dir, "zz")) else not guard_decision(home, os.path.join(home.wt_dir, e1 + "x", "tests", "new.py"))[0] or True)
        try:
            parse_output("metric-line:s", "METRIC s=1\nMETRIC s=2\n")
            check("ambiguous metric line rejected", False)
        except SBError:
            check("ambiguous metric line rejected", True)
        # tamper with a card mid-campaign: the next decision halts
        cpath = home.card_path("score")
        cj = read_json(cpath)
        cj["measure"]["command"] = "echo METRIC score=0"
        write_json_atomic(cpath, cj)
        halted = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_judge(home, argparse.Namespace(id=e1, fidelity="screen"))
        except SBError:
            halted = home.campaign().get("status") == "halted" and str(home.campaign().get("halt_reason")).startswith("card-tampered")
        check("card tampering halts", halted)
        cj["measure"]["command"] = "python3 bench.py"
        write_json_atomic(cpath, cj)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_campaign(home, argparse.Namespace(action="resume", file=None, reason=None, no_baseline=True, repeats=None, allow_unusable=False, allow_ratchet_regression=False, allow_underpowered=False))
        # experiment 2: gaming attempt (edit frozen bench.py) -> integrity violation
        write_json_atomic(hp, {"operator": "config", "target": "bench.py", "hypothesis": "cheat", "predicted": {"score": "-100%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e2 = json.loads(out.getvalue())["id"]
        with open(os.path.join(home.wt_dir, e2, "bench.py"), "w") as f:
            f.write("print('METRIC score=0')\nprint('METRIC checks=ok')\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_submit(home, argparse.Namespace(id=e2))
        r = home.experiments()[e2]
        check("integrity catches frozen edit", rc != 0 and r["integrity_ok"] is False and any(v.startswith("frozen:") for v in r["integrity_violations"]))
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_discard(home, argparse.Namespace(id=e2, reason="integrity", archive=False))
        # experiment 3: no-op change -> noise/discard
        write_json_atomic(hp, {"operator": "config", "target": "work.py", "hypothesis": "comment", "predicted": {"score": "-1%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e3 = json.loads(out.getvalue())["id"]
        with open(os.path.join(home.wt_dir, e3, "work.py"), "a") as f:
            f.write("# comment\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_submit(home, argparse.Namespace(id=e3))
            cmd_measure(home, argparse.Namespace(id=e3, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            cmd_judge(home, argparse.Namespace(id=e3, fidelity="screen"))
        r = home.experiments()[e3]
        check("judge does not promote a no-op", r["judge_stat"]["verdict"] in ("discard", "retry-screen", "inconclusive"))
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_discard(home, argparse.Namespace(id=e3, reason="noise", archive=True))
        check("archive written", os.path.exists(home.p("archive", f"{e3}.diff")))
        # experiment 4: regression on guardrail (checks -> bad)
        write_json_atomic(hp, {"operator": "algorithmic", "target": "work.py", "hypothesis": "N=0 breaks checks", "predicted": {"score": "-100%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e4 = json.loads(out.getvalue())["id"]
        with open(os.path.join(home.wt_dir, e4, "work.py"), "w") as f:
            f.write("N = 0\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_submit(home, argparse.Namespace(id=e4))
            cmd_measure(home, argparse.Namespace(id=e4, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            cmd_judge(home, argparse.Namespace(id=e4, fidelity="screen"))
        r = home.experiments()[e4]
        check("guardrail regression discards a big goal win", r["judge_stat"]["verdict"] == "discard" and r["judge_stat"]["reason"].startswith("regression:checks"))
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_discard(home, argparse.Namespace(id=e4, reason="regression:checks", archive=False))
        c = home.campaign()
        check("plateau raised exploration", c["exploration_level"] >= 1)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_distill_stats(home, argparse.Namespace(json=True))
        s = stats(home, home.campaign())
        check("stats count", s["experiments"] == 4 and s["accepted"] == 1 and s["discarded"] == 3)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_cost(home, argparse.Namespace(id=e1, tokens_in=None, tokens_out=None, wall_s=10.0, dollars=None, tier="medium"))
        s2 = stats(home, home.campaign())
        check("unreported tokens make dollars n/a", isinstance(s2["dollars_est"], str) and s2["dollars_est"].startswith("n/a"))
        os.environ["SB_EST_TOKENS"] = '{"medium": [50000, 8000]}'
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_cost(home, argparse.Namespace(id=e1, tokens_in=None, tokens_out=None, wall_s=1.0, dollars=None, tier="medium"))
        del os.environ["SB_EST_TOKENS"]
        last_cost = [ev for ev in home.ledger_events(e1) if ev["event"] == "cost"][-1]["data"]
        check("env token estimate is used and labelled", last_cost["token_source"] == "env-estimate" and last_cost["tokens_in"] == 50000 and last_cost["dollars"] > 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_next(home, argparse.Namespace(json=True, seed=1))
        brief = json.loads(out.getvalue())
        check("next brief has mix and frontier", brief["operator_mix"] and brief["frontier"]["score"]["best"] is not None)
        # budget: 6 experiments; prereg until exhausted halts
        exhausted = False
        for _ in range(4):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    cmd_prereg(home, argparse.Namespace(file=hp))
            except SBError:
                exhausted = True
                break
        check("budget cap halts prereg", exhausted and home.campaign()["status"] == "halted")
        # ledger torn line never bricks
        with open(home.ledger_path, "a") as f:
            f.write("{not json\n")
        check("torn ledger line tolerated", isinstance(home.experiments(), dict))
        fake = {"verdict": "discard", "confirm": {"results": {"score": {"median": 1}}, "comparisons": [], "confirm_effect": 0.1, "reason": "noise"}}
        check("discarded confirm numbers redacted", "redacted" in str(redact(fake)["confirm"]["results"]) and redact(fake)["confirm"]["reason"] == "noise")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_report(home, argparse.Namespace())
        check("report written", os.path.exists(home.p("reports", "t1.md")))
        check("report labels dollars as estimated", "estimated" in open(home.p("reports", "t1.md")).read())
        for name in list(os.listdir(home.wt_dir)):
            worktree_drop(home, name)
    # --- multi-repo, monorepo scope, and services on a second temp repo
    with tempfile.TemporaryDirectory() as td:
        repo = os.path.join(td, "repo")
        harness = os.path.join(td, "harness")   # an instrument OUTSIDE the repo
        os.makedirs(repo)
        os.makedirs(harness)
        git(["init", "-q", "-b", "main"], repo)
        git(["config", "user.email", "t@t"], repo)
        git(["config", "user.name", "t"], repo)
        os.makedirs(os.path.join(repo, "pkg"))
        os.makedirs(os.path.join(repo, "other"))
        with open(os.path.join(repo, "pkg", "work.py"), "w") as f:
            f.write("N = 40\n")
        with open(os.path.join(repo, "other", "readme.txt"), "w") as f:
            f.write("not in scope\n")
        with open(os.path.join(harness, "bench.py"), "w") as f:
            f.write("import sys, os\nsys.path.insert(0, os.path.join(os.environ['SB_CHECKOUT_DIR'], 'pkg'))\nimport work\n"
                    "assert os.path.exists(os.path.join(os.environ['SB_CHECKOUT_DIR'], '.svc-up')), 'service not up'\n"
                    "print('METRIC score=%d' % work.N)\n")
        git(["add", "-A"], repo)
        git(["commit", "-q", "-m", "base"], repo)
        home = Home(repo=repo, home=os.path.join(repo, ".strictlybetter"))
        home.ensure()
        tlog = os.path.join(td, "teardown.log")
        card = {"id": "score", "kind": "goal", "direction": "minimize",
                "measure": {"command": f"SB_CHECKOUT_DIR=$PWD python3 {harness}/bench.py", "parse": "metric-line:score", "timeout_s": 60},
                "fidelity": {"screen": {"repeats": 1}, "confirm": {"repeats": 8, "max_repeats": 8}},
                "integrity": {"external_paths": [harness]}, "gaming_risks": ["edit harness"], "contention_safe": True,
                "services": {"setup": "touch .svc-up", "ready": "test -f .svc-up", "ready_timeout_s": 5, "teardown": f"rm -f .svc-up; echo down >> {tlog}"}}
        validate_card(card)
        home.save_card(card)
        spec = {"id": "mr", "goals": ["score"], "guardrails": [], "budget": {"experiments": 4}, "plateau_patience": 3,
                "scope_paths": ["pkg/"], "walls": {"holdout": False}}
        sp = os.path.join(td, "c.json")
        write_json_atomic(sp, spec)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_campaign(home, argparse.Namespace(action="start", file=sp, no_baseline=False, repeats=3, allow_unusable=True, allow_ratchet_regression=False, allow_underpowered=False))
        c = home.campaign()
        check("external instrument hashed at start", harness in (c.get("external_hashes") or {}))
        check("alpha bookkeeping at start", abs(c.get("alpha_test", 0) - 0.05 / 4) < 1e-12)
        home4 = Home(repo=repo, home=os.path.join(td, "home4"))
        home4.ensure()
        card_up = dict(card); card_up["id"] = "score_up"; card_up["fidelity"] = {"screen": {"repeats": 1}, "confirm": {"repeats": 3}}
        card_up["services"] = {"setup": "touch .svc-up", "ready": "test -f .svc-up", "ready_timeout_s": 5, "teardown": "rm -f .svc-up"}
        home4.save_card(card_up)
        sp4 = os.path.join(td, "c4.json")
        write_json_atomic(sp4, {"id": "mr4", "goals": ["score_up"], "budget": {"experiments": 30}, "walls": {"holdout": False}})
        under = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_campaign(home4, argparse.Namespace(action="start", file=sp4, no_baseline=False, repeats=3, allow_unusable=True, allow_ratchet_regression=False, allow_underpowered=False))
        except SBError:
            under = str((home4.campaign() or {}).get("halt_reason", "")).startswith("underpowered")
        check("underpowered goal halts at start", under)
        check("services teardown ran after baseline", os.path.exists(tlog) and open(tlog).read().count("down") >= 1)
        check("baseline measured through the service", (home.baseline().get("score") or {}).get("best") == 40.0)
        check("guard denies external instrument", not guard_decision(home, os.path.join(harness, "bench.py"))[0])
        hp = os.path.join(td, "h.json")
        write_json_atomic(hp, {"operator": "config", "target": "other/readme.txt", "hypothesis": "out of scope edit", "predicted": {"score": "-1%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e1 = json.loads(out.getvalue())["id"]
        check("guard denies out-of-scope path in worktree", not guard_decision(home, os.path.join(home.wt_dir, e1, "other", "readme.txt"))[0])
        check("guard allows in-scope path in worktree", guard_decision(home, os.path.join(home.wt_dir, e1, "pkg", "work.py"))[0])
        with open(os.path.join(home.wt_dir, e1, "other", "readme.txt"), "a") as f:
            f.write("edited\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_submit(home, argparse.Namespace(id=e1))
        r = home.experiments()[e1]
        check("submit flags out-of-scope edit", rc != 0 and any(v.startswith("scope:") for v in r["integrity_violations"]))
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_discard(home, argparse.Namespace(id=e1, reason="integrity", archive=False))
        # tamper with the external harness: the next decision halts
        with open(os.path.join(harness, "bench.py"), "a") as f:
            f.write("print('METRIC score=0')\n")
        write_json_atomic(hp, {"operator": "algorithmic", "target": "pkg/work.py", "hypothesis": "halve N", "predicted": {"score": "-50%"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_prereg(home, argparse.Namespace(file=hp))
        e2 = json.loads(out.getvalue())["id"]
        with open(os.path.join(home.wt_dir, e2, "pkg", "work.py"), "w") as f:
            f.write("N = 20\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_submit(home, argparse.Namespace(id=e2))
        halted = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_measure(home, argparse.Namespace(id=e2, fidelity="screen", repeats=None, keep_runs=False, audit=False))
        except SBError:
            halted = str(home.campaign().get("halt_reason", "")).startswith("external-tampered")
        check("external instrument tampering halts", halted)
        # a failing service makes the measurement invalid, not a crash
        with open(os.path.join(harness, "bench.py"), "w") as f:
            f.write("print('METRIC score=1')\n")
        c = home.campaign()
        c["external_hashes"][harness] = external_hash(harness)
        c["status"] = "running"
        c["halt_reason"] = None
        home.save_campaign(c)
        card["services"] = {"setup": "true", "ready": "false", "ready_timeout_s": 0}
        home.save_card(card)
        c["card_hashes"]["score"] = card_fingerprint(card)
        home.save_campaign(c)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_measure(home, argparse.Namespace(id=e2, fidelity="screen", repeats=None, keep_runs=False, audit=False))
            cmd_judge(home, argparse.Namespace(id=e2, fidelity="screen"))
        r = home.experiments()[e2]
        check("service not ready -> invalid, not a crash", r["judge_stat"]["verdict"] == "discard" and r["judge_stat"]["reason"] == "invalid")
        for name in list(os.listdir(home.wt_dir)):
            worktree_drop(home, name)
    # --- frontier campaign on a planted trade-off (speed vs quality)
    with tempfile.TemporaryDirectory() as td:
        repo = os.path.join(td, "repo")
        os.makedirs(repo)
        git(["init", "-q", "-b", "main"], repo)
        git(["config", "user.email", "t@t"], repo)
        git(["config", "user.name", "t"], repo)
        with open(os.path.join(repo, "work.py"), "w") as f:
            f.write("A = 40\nB = 80\n")
        with open(os.path.join(repo, "bench.py"), "w") as f:
            f.write("import work, os, random\nr = random.Random(int(os.environ.get('SB_SEED', '0')))\n"
                    "print('METRIC speed=%d' % (work.A + r.randint(0, 1)))\nprint('METRIC quality=%d' % (work.B + r.randint(0, 1)))\n")
        git(["add", "-A"], repo)
        git(["commit", "-q", "-m", "base"], repo)
        home = Home(repo=repo, home=os.path.join(repo, ".strictlybetter"))
        home.ensure()
        fid = {"screen": {"repeats": 1}, "confirm": {"repeats": 10, "holdout": {"kind": "env", "var": "SB_SEED", "values": [7, 8, 9]}}}
        for mid, direction in (("speed", "minimize"), ("quality", "maximize")):
            home.save_card({"id": mid, "kind": "goal", "direction": direction, "measure": {"command": "python3 bench.py", "parse": f"metric-line:{mid}", "timeout_s": 60},
                            "fidelity": fid, "integrity": {"frozen_paths": ["bench.py"]}, "gaming_risks": ["x"], "contention_safe": True, "reuse_output": mid == "quality"})
        sp = os.path.join(td, "c.json")
        write_json_atomic(sp, {"id": "fr", "composition": "frontier", "goals": ["speed", "quality"], "budget": {"experiments": 6}})
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_campaign(home, argparse.Namespace(action="start", file=sp, no_baseline=False, repeats=4, allow_unusable=True, allow_ratchet_regression=False, allow_underpowered=False))
        c = home.campaign()
        check("frontier seeded with the base member", c.get("composition") == "frontier" and [m["id"] for m in c["frontier"]] == ["f0"])
        def run_trade(a, b, hyp, expect_accept):
            hp = os.path.join(td, "h.json")
            write_json_atomic(hp, {"operator": "config", "target": "work.py", "hypothesis": hyp, "predicted": {"speed": "-1..50%"}})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cmd_prereg(home, argparse.Namespace(file=hp, parent=None))
            info = json.loads(out.getvalue())
            with open(os.path.join(home.wt_dir, info["id"], "work.py"), "w") as f:
                f.write(f"A = {a}\nB = {b}\n")
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_submit(home, argparse.Namespace(id=info["id"]))
                cmd_measure(home, argparse.Namespace(id=info["id"], fidelity="screen", repeats=None, keep_runs=False, audit=False))
                cmd_judge(home, argparse.Namespace(id=info["id"], fidelity="screen"))
            rr = home.experiments()[info["id"]]
            if rr["judge_stat"]["verdict"] != "promote":
                with contextlib.redirect_stdout(io.StringIO()):
                    cmd_discard(home, argparse.Namespace(id=info["id"], reason="noise", archive=False))
                return info["id"], "screen:" + rr["judge_stat"]["reason"], info["parent_member"]
            write_json_atomic(vp2 := os.path.join(td, "v.json"), {"verdict": "clean", "pattern": "", "evidence": "", "recommended_check": ""})
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_judge_verdict(home, argparse.Namespace(id=info["id"], file=vp2))
                cmd_confirm(home, argparse.Namespace(id=info["id"], force=False))
            rr = home.experiments()[info["id"]]
            if rr["confirm"]["verdict"] == "accept":
                with contextlib.redirect_stdout(io.StringIO()):
                    cmd_accept(home, argparse.Namespace(id=info["id"], force=False))
                return info["id"], "accept:" + rr["confirm"]["reason"], info["parent_member"]
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_discard(home, argparse.Namespace(id=info["id"], reason="noise", archive=False))
            return info["id"], "discard:" + rr["confirm"]["reason"], info["parent_member"]
        e, res, par = run_trade(20, 60, "faster, lower quality (trade-off)", True)   # from f0 (40,80)
        check("trade-off joins the frontier", res.startswith("accept:frontier:improved:speed") and "traded:quality" in res and par == "f0")
        c = home.campaign()
        check("f0 stays (not dominated)", [m["id"] for m in frontier_active(c)] == ["f0", "f1"])
        e, res, par = run_trade(30, 70, "middle point", True)                         # parent = f0 (fewest attempts among extremes) or f1
        check("middle point is non-dominated and joins", res.startswith("accept:frontier"))
        c = home.campaign()
        check("three active members", len(frontier_active(c)) == 3)
        # a point dominated by f1 (20,60): worse on both from whichever parent -> never improves a goal vs parent, or dominated
        e, res, par = run_trade(25, 55, "worse on both vs f1", False)
        check("dominated or non-improving point is rejected", not res.startswith("accept"))
        # a point that dominates f1: speed 15, quality 60 (from any parent it improves speed; not worse on quality vs f1)
        e, res, par = run_trade(15, 60, "faster at same quality as f1", True)
        c = home.campaign()
        f1 = next(m for m in c["frontier"] if m["id"] == "f1")
        check("dominating point retires the dominated member", res.startswith("accept:frontier") and f1.get("retired_by") is not None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_frontier(home, argparse.Namespace(json=True))
        fr = json.loads(out.getvalue())
        check("frontier command lists members and a preferred point", len(fr["members"]) >= 3 and fr["preferred"] is not None)
        check("campaign branch points at the preferred member", git(["rev-parse", c["branch"]], repo) == next(m for m in c["frontier"] if m["id"] == fr["preferred"])["commit"])
        check("frontier campaign writes no global ratchet", home.ratchet() == {})
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_report(home, argparse.Namespace())
        check("report has the frontier table", "## Frontier" in open(home.p("reports", "fr.md")).read())
        for name in list(os.listdir(home.wt_dir)):
            worktree_drop(home, name)
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)} checks passed")
    return 0 if not failed else 1


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sb", description="strictlybetter engine")
    p.add_argument("--repo", help="repository root (default: git toplevel of cwd)")
    p.add_argument("--home", help="state home (default: <repo>/.strictlybetter or $SB_HOME)")
    p.add_argument("--version", action="version", version=f"sb {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sp = sub.add_parser("profile"); sp.add_argument("action", choices=["write", "show"]); sp.add_argument("--file", default="-")
    sp = sub.add_parser("card"); sp.add_argument("action", choices=["add", "list", "validate", "show", "probe"]); sp.add_argument("id", nargs="?"); sp.add_argument("--file", default="-"); sp.add_argument("--repeats", type=int, default=2)
    sp = sub.add_parser("baseline"); sp.add_argument("--metric"); sp.add_argument("-k", "--repeats", type=int); sp.add_argument("--levels")
    sp = sub.add_parser("campaign"); sp.add_argument("action", choices=["start", "show", "end", "halt", "resume"]); sp.add_argument("--file", default="-"); sp.add_argument("--reason"); sp.add_argument("--no-baseline", action="store_true"); sp.add_argument("--repeats", type=int); sp.add_argument("--allow-unusable", action="store_true", help="start even if a goal's minimum detectable effect exceeds the usable limit"); sp.add_argument("--allow-ratchet-regression", action="store_true", help="start even if HEAD is worse than a past campaign's ratcheted best"); sp.add_argument("--allow-underpowered", action="store_true", help="start even if a goal's confirm pairs cannot reach the per-test alpha (no acceptance will be possible)")
    sp = sub.add_parser("next"); sp.add_argument("--json", action="store_true"); sp.add_argument("--seed", type=int)
    sp = sub.add_parser("prereg"); sp.add_argument("--file", default="-"); sp.add_argument("--parent", help="frontier campaigns: the member id to branch from (default: the engine's pick)")
    sp = sub.add_parser("submit"); sp.add_argument("id")
    sp = sub.add_parser("measure"); sp.add_argument("id"); sp.add_argument("--fidelity", choices=["screen", "full", "confirm"], default="screen"); sp.add_argument("--repeats", type=int); sp.add_argument("--keep-runs", action="store_true"); sp.add_argument("--audit", action="store_true", help="human audit: allow a confirm-fidelity measurement while running")
    sp = sub.add_parser("judge"); sp.add_argument("id"); sp.add_argument("--fidelity", choices=["screen", "full"], default="screen")
    sp = sub.add_parser("judge-payload"); sp.add_argument("id"); sp.add_argument("--out")
    sp = sub.add_parser("judge-verdict"); sp.add_argument("id"); sp.add_argument("--file", default="-")
    sp = sub.add_parser("confirm"); sp.add_argument("id"); sp.add_argument("--force", action="store_true")
    sp = sub.add_parser("accept"); sp.add_argument("id"); sp.add_argument("--force", action="store_true")
    sp = sub.add_parser("discard"); sp.add_argument("id"); sp.add_argument("--reason"); sp.add_argument("--archive", action="store_true")
    sp = sub.add_parser("cost"); sp.add_argument("id"); sp.add_argument("--tokens-in", type=int); sp.add_argument("--tokens-out", type=int); sp.add_argument("--wall-s", type=float); sp.add_argument("--dollars", type=float); sp.add_argument("--tier")
    sp = sub.add_parser("distill-stats"); sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("status"); sp.add_argument("--json", action="store_true")
    sub.add_parser("report")
    sp = sub.add_parser("frontier"); sp.add_argument("--json", action="store_true")
    sub.add_parser("budget")
    sp = sub.add_parser("guard"); sp.add_argument("path", nargs="?"); sp.add_argument("--stdin", action="store_true")
    sub.add_parser("session-start")
    sub.add_parser("doctor")
    sub.add_parser("selftest")
    sub.add_parser("stop")
    sp = sub.add_parser("ledger"); sp.add_argument("action", choices=["view", "tail", "experiments"]); sp.add_argument("id", nargs="?"); sp.add_argument("-n", type=int); sp.add_argument("--unredacted", action="store_true", help="audit use: include discarded candidates' holdout numbers")
    sp = sub.add_parser("inheritance"); sp.add_argument("action", choices=["write", "show"]); sp.add_argument("--file")
    sp = sub.add_parser("worktree"); sp.add_argument("action", choices=["new", "drop", "path", "list"]); sp.add_argument("id", nargs="?"); sp.add_argument("--commit")
    sp = sub.add_parser("drive"); sp.add_argument("--command", required=True); sp.add_argument("--cycles", type=int, default=10); sp.add_argument("--timeout", type=float, default=3600); sp.add_argument("--verbose", action="store_true")
    return p


HANDLERS = {
    "init": cmd_init, "profile": cmd_profile, "card": cmd_card, "baseline": cmd_baseline, "campaign": cmd_campaign,
    "next": cmd_next, "prereg": cmd_prereg, "submit": cmd_submit, "measure": cmd_measure, "judge": cmd_judge,
    "judge-verdict": cmd_judge_verdict, "judge-payload": cmd_judge_payload, "confirm": cmd_confirm, "accept": cmd_accept, "discard": cmd_discard, "cost": cmd_cost,
    "distill-stats": cmd_distill_stats, "status": cmd_status, "report": cmd_report, "budget": cmd_budget, "guard": cmd_guard,
    "session-start": cmd_session_start, "doctor": cmd_doctor, "stop": cmd_stop, "ledger": cmd_ledger, "inheritance": cmd_inheritance,
    "worktree": cmd_worktree, "drive": cmd_drive, "frontier": cmd_frontier,
}
MUTATING = {"init", "profile", "card", "baseline", "campaign", "prereg", "submit", "measure", "judge", "judge-verdict",
            "confirm", "accept", "discard", "cost", "distill-stats", "stop", "inheritance", "worktree"}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    try:
        home = Home(repo=args.repo, home=args.home)
        handler = HANDLERS[args.cmd]
        if args.cmd in MUTATING:
            with home.lock():
                return handler(home, args)
        return handler(home, args)
    except SBError as e:
        sys.stderr.write(f"sb: {e}\n")
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # a corrupt state file must degrade to an error line, never a traceback
        if os.environ.get("SB_DEBUG"):
            raise
        sys.stderr.write(f"sb: internal error in '{args.cmd}': {type(e).__name__}: {str(e)[:200]} (state may be corrupt; run `sb doctor`; SB_DEBUG=1 for the traceback)\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
