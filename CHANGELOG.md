# Changelog

## 1.0.0 — 2026-09-03 · first release

The engine, the walls, the cost layer, the knowledge packs, the Claude Code surface, the port
scaffold, and the meta-benchmark ship together, because the acceptance rule is not worth shipping
without the walls that make it true. The theory docs (`docs/00` to `docs/11`, with verified
citations) are the spec. Where this entry and a doc disagree, the doc is wrong and is fixed in the
next commit (`CLAUDE.md`, doc-drift rule).

Gates run for this release: <to be filled by the release run>
Benchmark: see bench/results/

### Added

**Engine** (`scripts/sb.py`: one file, stdlib only, zero network, `VERSION = "1.0.0"`)

- 27 commands behind a `HANDLERS` dict plus `selftest`; the 18 in `MUTATING` run under a file
  lock. Free text enters through `--file` or stdin, never argv. Every state write is atomic
  (temp file + rename). State home is `<repo>/.strictlybetter/`, overridable with `SB_HOME`.
- **Metric cards** as JSON under `metrics/`, schema-checked on every load (`id`, `kind`,
  `direction` incl. `equal`, `measure.{command,parse}`, `fidelity` keyed by
  `screen|full|confirm`). Three parsers: `metric-line:` (the autoresearch ecosystem's
  `METRIC name=value` line, so an existing bench is a card without modification), `regex:`, `json:`.
- **Validity before comparison** (`measure_once`, `comparisons_for`): exit code, parse, timeout,
  duration inside `expected_duration_s`, a non-deterministic value on an `equal` metric, and an
  **instrument-versus-wall-clock divergence check**: a time-unit goal whose instrument claims at
  least 2× faster while the process wall-clock barely moved is invalidated with the note "timer or
  instrument tampering?". An invalid run is `discard: invalid`, never a candidate.
- **Baseline** (`sb baseline`): k=5 repeats at every fidelity level the card defines, from a clean
  throwaway worktree; median, sigma, seconds per run, commit, and environment fingerprint written
  to `baseline.json` and back onto the card's `noise`. A goal or guardrail with no valid baseline
  or no measured sigma halts `campaign start`. `equal`-direction metrics are summarized per
  holdout value as one canonical string, so a checksum may legitimately differ per seed and is
  invalid only when the same seed disagrees with itself. A card with `reuse_output` re-parses the
  most recent identical run in-process instead of paying for the command twice.
- **Monotonicity probe** (`sb card probe`): applies the card's `degradation.apply` recipe in a
  throwaway worktree and requires the metric to move the wrong way. A card that cannot see a
  deliberate regression is not an instrument.
- **The acceptance rule** (`compare_metric`, `decide`): a goal must beat κσ (κ = 2.5); a
  guardrail may not drop more than τσ (τ = 1.0); `equal` guardrails must match byte-for-byte;
  invalid beats everything, regression beats improvement. Complexity regularizer
  κ_eff = κ·(1 + 0.3·ln(1 + diff_lines/50)) + 1.0 per undeclared dependency manifest.
  Composition `pareto` (default) or `oec` with frozen weights.
- **Campaign lifecycle**: `campaign start` freezes the set, hashes frozen paths from a clean
  checkout, auto-adds hygiene guardrails and the global ratchet, and creates `sb/<id>`;
  `prereg` charges the experiment budget *before* creating the worktree and returns `eNNNN`;
  `submit` commits the worktree and runs integrity (frozen, protected, `.strictlybetter/`, eval
  hash, dependency manifests outside the `dependency` operator); `measure` at
  `screen|full|confirm`; `judge` gives the statistical verdict with one `retry-screen` for
  within-noise-but-predicted-large; `judge-verdict` stores the blind judge's JSON and rejects any
  extra field; `confirm` runs `full` then `confirm` from a clean checkout with holdout values and
  adaptive repeats up to the card's cap, then discards as `noise`; `accept` fast-forwards the
  branch with `commit-tree`, appends a provenance block to the commit message, and ratchets;
  `discard --reason` uses a fixed vocabulary and can archive the diff.
- **Ledger** `ledger.jsonl`: append-only `{ts, id, event, data}` events folded into one record per
  experiment; a torn line is skipped and never bricks a read.
- **Cold-start brief** (`sb next`): frontier with sigma, budget left, batch size from screen cost,
  exploration level and allowed diff sizes, a Thompson-sampled operator mix over 13 operator
  classes with archetype priors, recent dead ends, accepted wins, archive hints, the inheritance
  body's path.
- **Plateau and distill** (`sb distill-stats`): exploration rises after `PATIENCE` = 8 discards
  (max level 3); `screen_untrusted` trips when the false-promotion window (10 promotions, 40%) is
  exceeded and doubles screen repeats; decision is `continue`, `explore:levelN`,
  `stop:converged`, `stop:budget`, or `stop:halted`.
- **Governance**: `STOP` file and `sb stop`; iteration cap (200); halts on budget, on two
  consecutive integrity violations, and on a holdout-gap ratio above 0.75 over the last five
  acceptances; `sb guard <path>` exits 2 to deny and reads the PreToolUse payload with `--stdin`;
  `session-start` prints one line or nothing; `doctor`; `drive --command` runs an external agent
  once per cycle for headless use; `worktree`, `ledger`, `inheritance`, `cost`, `budget`,
  `status`, `report`.
- **Selftest**: 55 checks, including the AST no-network guard, the version pin to
  `.claude-plugin/plugin.json`, parser and acceptance-rule fixtures, guard decisions, and a scripted
  four-experiment campaign on an in-memory git repo (real improvement accepted with provenance;
  frozen-path edit refused at submit; no-op discarded as noise and archived; guardrail regression
  discarded despite a large goal win; budget cap halts; torn ledger tolerated; report written).
  `tests/`: 32 stdlib `unittest` cases, 25 unit (`test_engine.py`) and 7 end-to-end through the
  real CLI on the pyfix fixture (`test_fixture_campaign.py`: baseline sigma, monotonic probe,
  frozen edit caught and guard denies, wrong output is a guardrail regression, verdict schema,
  status/next/report, doctor/ledger).

**Walls** (`docs/04`; toggles in `WALL_KEYS`, all on by default, each switchable off for the bench)

- `validity`, `noise_floor`, `confirm` (clean checkout, never the experimenter's worktree),
  `holdout` (kinds `env`, `arg`, `dir`; rotated after 10 acceptances with a confirm-level
  re-baseline), `frozen_guard` (PreToolUse hook plus gate-time check in `submit`), `judge` (blind
  by schema: `verdict`, `pattern`, `evidence`, `recommended_check`, nothing else; `suspicious`
  raises confirm repeats to the cap; `gamed` blocks confirm and counts toward the halt),
  `prereg` (the ledger line exists before the worktree does), `anomaly_breaker` (a screen effect
  above 3× the rolling mean of confirmed effects, after half a patience without acceptance, is
  confirmed at max repeats).
- **Holdout gap** tracked per accepted change and as a trend; the campaign halts when the mean
  over the last five exceeds the ratio.
- **Regression by construction**: every goal and guardrail measured at every fidelity; hygiene
  guardrails always included; the global ratchet (`ratchet.json`) turns every past goal into a
  guardrail for every future campaign, demotable only by a logged human act.

**Cost layer** (`docs/05`)

- Fidelity ladder per card; screen repeats multiplier when screen is untrusted.
- Budget in experiments, hours, and dollars; `experiments` charged at pre-registration;
  wall-clock charged per measurement; `sb cost <id>` records tokens, wall, and tier, converting
  tokens to dollars with the campaign's pricing table (default 5 / 25 per Mtok) and stamping the
  record `estimated: true` unless `--dollars` was given. Status and report print `est $`.
- Bandit over operator classes (Beta posterior, archetype priors) sets the batch mix.
- `stats()` reports experiments, promoted, accepted, discarded by reason, false promotions and
  the window rate, wall and estimated dollars per accepted improvement, mean confirmed effect,
  holdout-gap mean over the last five, budget left.
- Contention: timing-sensitive cards (`contention_safe: false`) serialize behind `measure.lock`;
  `max_parallel` worktrees; `PYTHONHASHSEED` and `PYTHONDONTWRITEBYTECODE` pinned by the harness.

**Knowledge packs**

- Archetype packs `archetypes/*.json`, one per row of `docs/07` §7.1 (rust-crate,
  python-package, node-frontend, service-api, cli-tool, ml-training, ml-inference, science-sim,
  data-pipeline, docs-site, library-generic): match rules, command hints, protected and
  frozen-path hints, default cards, operator priors, noise sources, hygiene guardrails.
- Operator library `operators/*.md`, one file per class in `OPERATORS` plus a README: when to
  use, tier, expected diff size.
- Templates under `templates/`: `profile.md.tmpl` + `profile.schema.json`, `campaign.json.tmpl`,
  `card.json.tmpl`, `hypothesis.json.tmpl` + schema, `verdict.json.tmpl` + schema,
  `judge-checklist.md`, `inheritance.md.tmpl`, `report.md.tmpl`.
- Fixtures under `tests/fixtures/`: `pyfix` (Python package, three deliberately slow functions),
  `rustfix` (Rust crate with bench, tests, clippy), `greenfield` (one module, no instruments),
  each with `fixture-cards/` and `make_fixture.py` to stamp a throwaway git repo.
- Inheritance body `inheritance.md`, rewritten by the distiller through `sb inheritance write`.

**Claude Code surface** (`docs/10` §10.2 to §10.5)

- Skills: front door `/strictlybetter` (status → orient / instrument / gate 1 → one cycle), plus
  `sb-orient`, `sb-metrics`, `sb-run`, `sb-status`, `sb-distill`, `sb-stop`; `_shared/` carries
  the engine-resolution block, the card schema, the ledger schema, the judge protocol, and the
  subagent rules (items by file path, one child per judgment, no dialogue).
- Agents: `sb-orienteer`, `sb-metrologist`, `sb-experimenter-{low,medium,high}` (byte-identical
  except `effort:`), `sb-judge` (Read-only, medium), `sb-distiller`.
- Hooks (`hooks/hooks.json`): SessionStart on `startup|resume|clear|compact` →
  `session-start.sh`; PreToolUse on `Edit|MultiEdit|Write|NotebookEdit` → `frozen-guard.sh`,
  which pipes the raw payload to `sb guard --stdin` and exits 2 to deny (fast path: no
  `campaign.json` reachable from the edited path means python is never started); PreCompact
  re-pins the campaign id, frozen paths, and the harness-computes rule; Stop driver re-invokes
  one cycle while the campaign is running, under budget, and below the iteration cap.
- `.claude-plugin/plugin.json` and `marketplace.json`.

**Ports**

- L0 (manual skills + engine) always works; further platforms follow the omniplugin ladder with
  one `INSTALL-<PLATFORM>.md` each and an honest Verified live / Not verified row in
  `RELEASE_PROTOCOL.md` §7.6.

**Bench** (`docs/10` §10.7)

- `bench/run_bench.py` with three modes: `scripted` (LLM-free seeded sequence of real wins,
  no-ops, and gaming tricks through the real engine under each condition, every accepted commit
  re-validated on a fresh holdout with the pristine instrument and an external process timer, so
  a change that only fooled the loop's own instrument counts as a false accept); `gaming`
  (wall-ablation matrix: each trick under full walls and with each wall disabled in turn,
  reporting which wall catches which trick); `analyze` (re-validate a campaign real agents ran).
  Conditions `walls` (all eight on; guardrails tests + checksum) and `naive` (every wall off, one
  full-size run decides, tests only). Results land in
  `bench/results/<stamp>-<mode>-<fixture>.{json,md}`; nothing in a report is typed by hand.

### Known limitations at 1.0.0

- `WALL_KEYS` declares `prereg`, and no code path reads it. Pre-registration is enforced by
  construction (`prereg` precedes the worktree), not by the toggle; the toggle is inert.
- The docs describe a drift check at re-baseline, a disk and memory halt, a per-phase cost
  split, judge overhead, a yield curve, and `sb distill --global`. None is in the engine yet.
- Limited leakage is not enforced: the confirm results of discarded candidates are written to
  the ledger in full and `sb ledger view` prints them. The brief (`sb next`) surfaces accepted
  effects only, as designed.
- The version-pin selftest is skipped when `.claude-plugin/plugin.json` is absent; the manifest
  exists now, so the check runs, and §4 of the release protocol demands its line be printed.
- The judge's `recommended_check` is stored and never executed; a `suspicious` verdict raises
  confirm repeats to the card's cap instead of running the check the judge asked for.
- `frozen-guard.sh` exits 0 (allows) when it cannot find a campaign, a readable path in the
  payload, `python3`, or the engine. This is the documented fast path and the shape of the
  fail-open bug class; the port table must record it per platform.
- Wall-clock spend in `cmd_measure` is added after the `try/finally`, so a measurement that
  raises loses its wall-clock from the budget; `cmd_confirm` charges inside `finally`.
- Cost accounting is an estimate unless the platform's real usage is passed in; the label says so.
