# 02 · Metrics: cards, sets, and the ratchet

A metric is a command that emits a number plus everything the loop needs to trust that number. This document defines the metric card, the metric set, the acceptance rule, and the global ratchet.

## 2.1 The metric card

Every metric is a JSON file under `.strictlybetter/metrics/<id>.json`, written with `sb card add --file` and schema-checked on every load. Nothing about a metric lives only in an agent's head.

```json
{
  "id": "bench_throughput",
  "title": "Criterion throughput, parse_large fixture",
  "kind": "goal",
  "direction": "maximize",
  "unit": "MiB/s",

  "measure": {
    "command": "cargo bench --bench parse -- --output-format bencher parse_large",
    "parse": "regex:parse_large.*?(\\d+(?:\\.\\d+)?) MiB/s",
    "cwd": ".",
    "timeout_s": 600,
    "env": {"CARGO_INCREMENTAL": "0"},
    "expected_duration_s": [60, 200],
    "allow_nonzero_exit": false
  },

  "fidelity": {
    "screen":  {"command": "cargo bench --bench parse -- --warm-up-time 1 --measurement-time 2 parse_large",
                "expected_duration_s": [10, 60]},
    "full":    {"repeats": 1},
    "confirm": {"repeats": 3, "max_repeats": 6,
                "holdout": {"kind": "env", "var": "SB_SEED", "values": [1913, 8241, 6607]}}
  },

  "degradation": {"apply": "sh .sb/degrade-lexer.sh", "expected": "worse"},

  "acceptance": {"kappa": 2.5, "tolerance_sigma": 1.0},
  "integrity": {"frozen_paths": ["benches/", "tests/fixtures/"]},
  "gaming_risks": [
    "fixture could be shrunk or cached between runs",
    "bench could be narrowed to a faster subset"
  ],
  "contention_safe": false,
  "reuse_output": false,
  "hygiene": false,

  "noise": {"sigma": 1.84, "samples": 5, "method": "stdev-of-repeats",
            "measured_at": "3f9a2c1d…", "environment_fingerprint": "darwin-23.6.0-arm64-8cores-py3.12"},
  "probe": {"monotonic": true, "detail": "412.0 -> 388.5 (sigma 1.84)",
            "at": "2026-09-03T10:41:00Z", "commit": "3f9a2c1d…"}
}
```

Field notes:

- **Required** fields are `id` (`[A-Za-z0-9_.-]`, at most 64 characters), `kind`, `direction`, and `measure` with `command` and `parse`. Everything else is optional and defaults as described below.
- **kind** decides how the acceptance rule treats the metric. A goal must improve; a guardrail must hold; a diagnostic is recorded (at `confirm`, and at `full` when measured on request) but never decides anything.
- **direction** is `maximize`, `minimize`, or `equal`. An `equal` metric is a guardrail that must match the baseline exactly (a checksum, an API surface, a row count). Its value may be a string. At confirm it is summarized per holdout value, so a checksum may legitimately differ per seed; it is invalid only when the same holdout value disagrees with itself across repeats.
- **measure** is the base command. `cwd` defaults to `.`, `timeout_s` to 600 (a timeout is an invalid run, never a slow win). `env` is the pinned environment; the harness adds `SB_FIDELITY`, `SB_METRIC`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=0` unless the card sets it. `expected_duration_s` is a validity band `[lo, hi]` on the command's wall-clock; a run outside it is invalid. Only a two-number list counts; a placeholder string is ignored by the engine and is the metrologist's to resolve. `allow_nonzero_exit` lets a command that reports through its output exit non-zero.
- **parse** takes one of three forms. `metric-line:NAME` reads the last `METRIC NAME=value` line in stdout, then stderr; this is the convention of the autoresearch ecosystem (pi-autoresearch, codex-autoresearch), so an existing bench script can be a card without modification. `regex:PATTERN` takes the last match, using the first capture group if there is one. `json:a.b.0` walks a dotted path into the stdout JSON (the whole output, or the last line that parses). Non-numeric values are kept as strings and are only meaningful for `equal`.
- **fidelity** is an object keyed `screen`, `full`, `confirm`. Each level overrides only what differs from `measure`: `command`, `parse`, `cwd`, `timeout_s`, `env` (merged over the base), `expected_duration_s`, `allow_nonzero_exit`, `repeats`, `max_repeats`, `holdout`, `skip`. Defaults: `repeats` is 1 at screen and full and 3 at confirm; `max_repeats` equals `repeats`. `skip: true` at screen and full makes a confirm-only metric (a held-out test split). Experiments run at `screen`; `sb confirm` runs `full` when the card defines it, then `confirm`, from a clean checkout. See `05-cost-and-speed.md` for the ladder.
- **holdout** is read at `confirm` only. `{"kind": "env", "var": "SB_SEED", "values": [...]}` sets the variable per repeat (`var` defaults to `SB_SEED`); `{"kind": "arg", "values": [...]}` substitutes `{holdout}` in the command; `{"kind": "dir", "name": "...", "dest": "..."}` copies `.strictlybetter/holdout/<name>/` into the clean checkout before measuring. Repeats cycle through the values. The experimenter's worktree never contains them.
- **noise** is measured, not declared. `sb baseline` writes it from the confirm-level repeats: `sigma`, `samples`, `method` (`stdev-of-repeats`), `measured_at` (the commit), `environment_fingerprint`. `sb card add` carries the old `noise` and `probe` forward when a re-added card omits them. A goal or guardrail without a measured sigma halts `sb campaign start`.
- **probe** is written by `sb card probe`: whether the degradation moved the metric the wrong way, the before and after values, and the commit.
- **acceptance** overrides the campaign defaults `kappa` (2.5) and `tolerance_sigma` (1.0) for this card. A `tolerance_sigma` of 0 means any regression fails.
- **integrity.frozen_paths** freezes the instrument. The union of every campaign card's frozen paths plus the campaign's own `frozen_paths` is hashed at campaign start into `campaign.json` (`eval_hash`, `frozen_paths_effective`); the hash lives there, not on the card. A diff touching a frozen path, or one that changes the hash, fails `sb submit`; two consecutive failures halt the campaign for human review. Instrument changes are legitimate only in an instrument campaign (see `07-universality.md`).
- **gaming_risks** are written by the metrologist agent at card creation and handed to the blind judge. They are the checklist the judge reads the diff against. `sb card validate` flags a card without them.
- **degradation** is a recipe for a known-bad change. `sb card probe <id>` runs `apply` as a shell command in a throwaway worktree and requires the metric to get worse by more than sigma (for `equal`, to differ). A metric that cannot detect a deliberate regression is not an instrument (engram's release protocol calls this the monotonicity test; the discriminability check in `skillforge-autoresearch` is the same idea). `expected` is documentation; the engine only checks "worse".
- **contention_safe** marks counts and sizes that may be measured while other worktrees run. Anything timed is measured under a lock.
- **reuse_output** lets a card that re-parses another card's identical command (a checksum next to a timing) reuse the most recent run in-process instead of paying twice.
- **hygiene** marks a guardrail that every campaign includes whether or not the user listed it. Archetype packs name their hygiene cards (tests, lint) in `hygiene_guardrails`; the metrologist sets the flag when adding them.
- **Not read by the engine**: `title`, and any `cost` block. Cost is measured, not declared: `sb baseline` records `secs_per_run` per fidelity level in `baseline.json`.

## 2.2 Metric properties the loop cares about

| Property | Why it matters | How it is obtained |
|---|---|---|
| Cost (seconds, dollars) | Decides fidelity ladder and batch sizes | Measured during baseline (`secs_per_run` per fidelity level in `baseline.json`) |
| Noise (sigma) | Decides acceptance threshold | Measured: k repeats at the same commit |
| Sensitivity | A metric that does not move under plausible changes is useless as a goal | Monotonicity probe (`sb card probe`); wider sensitivity probes are the metrologist's experiments, not an engine command |
| Direction | Sign of improvement | Declared |
| Gameability | Which cheap tricks would inflate it | Declared by metrologist, checked by judge |
| Determinism | Whether repeats agree; flaky metrics are quarantined | Measured: a metric with no valid confirm-level baseline is `quarantined` in `baseline.json`; an `equal` metric whose repeats disagree is invalid |
| Coverage | How much of the project the metric actually sees | Declared, revisited at distill |

Instrument quality is summarized as `sensitivity / (sigma × cost)`. It is the goal metric of an instrument campaign and the tie-breaker when the loop chooses which of several candidate goals to work on first. Not in v1.0: the engine does not compute this ratio; the metrologist compares candidates from the baseline's sigma and `secs_per_run`.

## 2.3 Metric sets and campaigns

A campaign is a named, versioned metric set with a budget. `sb campaign start --file campaign.json` reads a spec like this:

```json
{
  "id": "2026-09-03-parse-perf",
  "goals": ["bench_throughput"],
  "guardrails": ["tests_pass", "clippy_warnings", "public_api_surface", "binary_size"],
  "diagnostics": ["build_seconds", "unsafe_blocks"],
  "composition": "pareto",
  "oec_weights": {},
  "budget": {"dollars": 40, "hours": 8, "experiments": 60},
  "plateau_patience": 8,
  "protected_paths": ["benches/", "tests/", ".github/", "Cargo.lock"],
  "frozen_paths": [],
  "branch": "sb/2026-09-03-parse-perf",
  "walls": {"validity": true, "noise_floor": true, "confirm": true, "holdout": true,
            "frozen_guard": true, "judge": true, "prereg": true, "anomaly_breaker": true},
  "iteration_cap": 200,
  "max_parallel": 2,
  "distill_every": 8,
  "false_promotion_budget": {"window": 10, "max_fraction": 0.4},
  "archetype_priors": {"algorithmic": [3, 4], "allocation": [2, 4]},
  "notes": ""
}
```

Every field except `goals` has a default: `budget` is `{"experiments": 40}`, `branch` is `sb/<id>`, `plateau_patience` is 8, `max_parallel` is 2, `distill_every` is 8, `iteration_cap` is 200, and every wall is true. The engine writes the result to `.strictlybetter/campaign.json` together with the fields it owns: `status` (`running` | `halted` | `ended`), `halt_reason`, `base_commit`, `head_commit`, `eval_hash`, `frozen_paths_effective`, `spent`, `exploration_level`, `since_last_accept`, `accepted_ids`, `consecutive_integrity`, `consecutive_gamed`, `screen_repeats_multiplier`, `screen_untrusted`, `holdout_override`, `next_id`. Only the harness writes this file.

Rules:

- A campaign has at least one goal and always includes the **hygiene guardrails** (every card flagged `hygiene`: build, tests, lint), whether or not the user listed them. It also inherits the global ratchet (§2.5) as guardrails.
- The metric set is frozen once the campaign starts. `sb card add` refuses to change a goal or guardrail card while a campaign is running. Changing the set means ending the campaign and starting another. This is pre-registration at the campaign level.
- **composition: pareto** means a change is accepted only if it improves at least one goal beyond its noise floor and does not regress any other goal or guardrail beyond tolerance. This is the default.
- **composition: oec** allows a single Overall Evaluation Criterion with declared weights, for the case where the user has decided a trade-off in advance (for example, one point of accuracy is worth ten percent latency). The score is the weighted sum of each goal's delta in sigma units and must exceed κ_eff; guardrails still hold. Weights (`oec_weights`) are part of the frozen set.

## 2.4 The acceptance rule

Let `A` be the current best state, `A'` the candidate, `m_x(·)` the measurement of metric `x`, `s_x ∈ {+1, −1}` its direction, `σ_x` its measured noise. The candidate is **strictly better** when all of the following hold on the *confirmation* measurement:

1. Improvement: there exists a goal `g` with `s_g · (m_g(A') − m_g(A)) > κ_g · σ_g`.
2. No regression: for every other goal and every guardrail `h`, `s_h · (m_h(A') − m_h(A)) ≥ −τ_h · σ_h`.
3. Integrity: no frozen path touched, eval hash unchanged, no protected path touched, holdout inputs unchanged.
4. Judgment: the blind judge finds no gaming pattern (see `04-anti-overfitting.md`).
5. Confirmation independence: the numbers in (1) and (2) come from the harness's confirmation run, not from the screening run the experimenter observed.

Defaults: `κ = 2.5`, `τ = 1.0`, overridable per card in `acceptance`. In the engine: a goal *improves* when `Δ > κ_eff · σ`, *regresses* when `Δ < −τ · σ`, and is *inconclusive* when `0 < Δ ≤ κ_eff · σ`; a sigma of zero makes any move decisive. Larger diffs raise κ: `κ_eff = κ · (1 + 0.3 · ln(1 + diff_lines / 50)) + 1.0 · σ` per touched dependency manifest (the complexity regularizer in `04-anti-overfitting.md`).

This is the Ladder mechanism of Blum and Hardt (2015) applied to a repository: report a new best only when it beats the previous best by more than a step size, otherwise keep the old value. The Ladder is the theoretical reason a threshold-ratchet resists adaptive overfitting; the noise floor gives the step size a physical meaning.

## 2.5 The ratchet and the global ratchet

`baseline.json` holds, per metric, the best confirmed value, its commit, and its sigma:

```json
{
  "bench_throughput": {
    "levels": {
      "screen":  {"median": 401.2, "sigma": 3.1, "n": 5, "values": [...], "secs_per_run": 24.8, "invalid": []},
      "confirm": {"median": 412.0, "sigma": 1.84, "n": 5, "values": [...], "secs_per_run": 121.3, "invalid": []}
    },
    "best": 412.0, "sigma": 1.84, "commit": "3f9a2c1d…",
    "env_fingerprint": "darwin-23.6.0-arm64-8cores-py3.12",
    "measured_at": "2026-09-03T10:41:00Z", "quarantined": false
  }
}
```

`sb baseline` writes it (one entry per fidelity level the card defines, `best` and `sigma` taken from the confirm level, `quarantined` when no valid confirm-level median exists). `sb accept` updates it: the confirm-level median (and sigma, when the confirmation had at least two valid repeats) and the screen-level median move to the accepted commit's numbers. Nothing else writes it.

The **global ratchet** lives in `ratchet.json`: one entry per metric that has ever been a goal in any campaign on this project, holding `best`, `sigma`, `commit`, `campaign`, and `direction`, written by `sb accept`. `sb campaign start` adds every ratcheted metric that has a card as a guardrail (at its best confirmed value, with its tolerance) unless its entry carries `"demoted": true`. Consequences:

- A perf campaign after an accuracy campaign cannot trade accuracy for speed without a human explicitly demoting the accuracy metric from the ratchet. Demotion is a logged, human-only act: there is no engine command for it, the `demoted` flag is set by hand in `ratchet.json`.
- The project's Pareto frontier can only move outward over time. This is what "points towards being better" means operationally.
- The ratchet is what lets metric sets vary freely without the loop cannibalizing its own past work.

## 2.6 Discovering metrics

The metrologist agent produces candidate cards from, in order of trust:

1. **Existing instruments**: CI workflows, `Makefile`/`justfile`/`package.json` scripts, `cargo bench`, `pytest-benchmark`, Lighthouse configs, existing eval scripts, notebooks that print a headline number.
2. **Archetype defaults**: the per-archetype card templates in `07-universality.md` (for a Rust crate: tests, clippy, build time, binary size, criterion benches, unsafe count).
3. **Stated goals**: README claims ("fast", "zero-copy", "97.2% on the benchmark"), open issues labelled performance/bug, a paper's headline table.
4. **Probes**: cheap experiments that change something plausible and see which candidate metrics respond. A metric with no sensitivity is demoted to diagnostic. In v1.0 these are the metrologist's own experiments; the engine has no sensitivity-probe command.
5. **Monotonicity selftest**: `sb card probe <id>` applies the card's `degradation` recipe in a throwaway worktree (two screen-fidelity runs each side by default, `--repeats` to raise); the metric must move in the wrong direction by more than its sigma. The result is stored on the card as `probe`. `sb card validate <id>` fails a goal or guardrail whose probe failed, which has no measured noise, or which lists no `gaming_risks`.

The output of discovery is a proposal, not a decision. The user picks the campaign's goals and guardrails at the first human gate (`09-governance.md`). Cards for metrics not chosen are kept as diagnostics so the ledger still records them.

## 2.7 Things that are not metrics

- LLM-judged scores without a frozen rubric and a fixed judge model. Allowed only as diagnostics until proven stable across repeats.
- Anything the experimenter agent can change the definition of.
- Anything measured on the experimenter's own machine state (uncommitted files, caches). The harness measures from a clean worktree checkout.
