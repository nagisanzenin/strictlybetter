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
- **Validity before comparison** (`measure_once`): exit code, parse, timeout, duration inside
  `expected_duration_s`, a non-deterministic value on an `equal` metric. An invalid run is
  `discard: invalid`, never a candidate. Every run records a manifest.
- **Baseline** (`sb baseline`): k=5 repeats per fidelity level from a clean throwaway worktree;
  median, sigma, commit, and environment fingerprint written to `baseline.json` and back onto the
  card's `noise`. A goal or guardrail with no valid baseline or no measured sigma halts
  `campaign start`.
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
- **Selftest**: 54 checks, including the AST no-network guard, the version pin to
  `.claude-plugin/plugin.json`, parser and acceptance-rule fixtures, guard decisions, and a scripted
  four-experiment campaign on an in-memory git repo (real improvement accepted with provenance;
  frozen-path edit refused at submit; no-op discarded as noise and archived; guardrail regression
  discarded despite a large goal win; budget cap halts; torn ledger tolerated; report written).
  `tests/test_engine.py`: 25 stdlib `unittest` cases.

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

- Archetype packs `archetypes/*.json` (rust-crate, python-package, node-frontend, service-api,
  cli-tool): match rules, command hints, protected and frozen-path hints, default cards, operator
  priors, noise sources, hygiene guardrails.
- Operator library `operators/*.md`, one per class: when to use, tier, expected diff size.
- Templates for the profile, the campaign spec, the inheritance body, and card skeletons.
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
- Hooks: SessionStart → `sb session-start`; PreToolUse on edits → `sb guard --stdin` (exit 2
  denies); PreCompact re-pins the campaign id, frozen paths, and the harness-computes rule; Stop
  driver re-invokes one cycle while the campaign is running, under budget, and below the
  iteration cap.
- `.claude-plugin/plugin.json` and `marketplace.json`.

**Ports**

- L0 (manual skills + engine) always works; further platforms follow the omniplugin ladder with
  one `INSTALL-<PLATFORM>.md` each and an honest Verified live / Not verified row in
  `RELEASE_PROTOCOL.md` §7.6.

**Bench** (`docs/10` §10.7)

- `bench/`: the fixtures plus public targets; conditions walled vs naive (same engine, walls off);
  `--mode gaming` runs the casebook tricks against the walls and reports tricks caught and walls
  load-bearing; results under `bench/results/`, written by the engine, never hand-edited.

### Known limitations at 1.0.0

- `WALL_KEYS` declares `prereg`, and no code path reads it. Pre-registration is enforced by
  construction (`prereg` precedes the worktree), not by the toggle; the toggle is inert.
- The docs describe a drift check at re-baseline, a disk and memory halt, a per-phase cost
  split, judge overhead, a yield curve, and `sb distill --global`. None is in the engine yet.
- Limited leakage is not enforced: the confirm results of discarded candidates are written to
  the ledger in full and `sb ledger view` prints them. The brief (`sb next`) surfaces accepted
  effects only, as designed.
- The version-pin selftest is skipped when `.claude-plugin/plugin.json` is absent (§4 of the
  release protocol demands the line be printed).
- Wall-clock spend in `cmd_measure` is added after the `try/finally`, so a measurement that
  raises loses its wall-clock from the budget; `cmd_confirm` charges inside `finally`.
- Cost accounting is an estimate unless the platform's real usage is passed in; the label says so.
