# 02 · Metrics: cards, sets, and the ratchet

A metric is a command that emits a number plus everything the loop needs to trust that number. This document defines the metric card, the metric set, the acceptance rule, and the global ratchet.

## 2.1 The metric card

Every metric is a YAML file under `.strictlybetter/metrics/`. Nothing about a metric lives only in an agent's head.

```yaml
id: bench_throughput
title: Criterion throughput, parse_large fixture
kind: goal            # goal | guardrail | diagnostic
direction: maximize   # maximize | minimize
unit: MiB/s

measure:
  command: "cargo bench --bench parse -- --output-format bencher parse_large"
  parse: 'regex:parse_large.*?(\d+(?:\.\d+)?) MiB/s'   # also json:<path> or metric-line:<name>
  cwd: .
  timeout_s: 600
  env: { CARGO_INCREMENTAL: "0" }
  expected_duration_s: [60, 200]   # validity band; a 0-second "win" is invalid, not a win

degradation:                     # recipe for the monotonicity selftest (§2.6)
  patch: "insert std::thread::sleep(1ms) in parse_large's inner loop"
  expected: worse

fidelity:                       # cheapest first; screen is what experiments see
  - name: screen
    command: "cargo bench --bench parse -- --warm-up-time 1 --measurement-time 2 parse_large"
    seconds: 25
  - name: full
    seconds: 120
  - name: confirm                # run by the harness, never by the experimenter
    repeats: 3
    holdout: { kind: seeds, values: [1913, 8241, 6607] }

cost:
  seconds: 120
  dollars: 0

noise:                          # filled by `sb baseline`, never by hand
  sigma: 1.84
  samples: 5
  method: median-of-repeats
  measured_at: 3f9a2c1
  environment_fingerprint: "darwin-23.6-arm64-8cores"

acceptance:
  kappa: 2.5                    # improvement must exceed kappa * sigma
  tolerance_sigma: 1.0          # as a guardrail: may not drop more than this

integrity:
  frozen_paths: ["benches/", "tests/fixtures/"]
  eval_hash: "sha256:…"         # of frozen_paths at campaign start
gaming_risks:
  - "fixture could be shrunk or cached between runs"
  - "bench could be narrowed to a faster subset"
```

Field notes:

- **kind** decides how the acceptance rule treats the metric. A goal must improve; a guardrail must hold; a diagnostic is recorded and plotted but never decides anything.
- **fidelity** encodes the multi-fidelity ladder from `05-cost-and-speed.md`. Experiments run at `screen`; promising ones are re-measured at `full`; `confirm` is executed by the harness from a clean worktree with holdout inputs. The experimenter agent never sees the confirm command's holdout values.
- **noise.sigma** is measured, not declared. A card without a measured sigma cannot be used as a goal. The harness refuses.
- **integrity** freezes the instrument. If any experiment's diff touches a frozen path, or the hash of frozen paths changes, the experiment is rejected before measurement and the campaign halts for human review. Instrument changes are legitimate only in an instrument campaign (see `07-universality.md`).
- **gaming_risks** are written by the metrologist agent at card creation and handed to the blind judge. They are the checklist the judge reads the diff against.
- **parse: metric-line** accepts the `METRIC name=value` stdout convention used by the autoresearch ecosystem (pi-autoresearch, codex-autoresearch), so an existing bench script can be a card without modification.
- **degradation** is a recipe for a known-bad change. The harness applies it in a throwaway worktree and requires the metric to get worse. A metric that cannot detect a deliberate regression is not an instrument (engram's release protocol calls this the monotonicity test; the discriminability check in `skillforge-autoresearch` is the same idea).

## 2.2 Metric properties the loop cares about

| Property | Why it matters | How it is obtained |
|---|---|---|
| Cost (seconds, dollars) | Decides fidelity ladder and batch sizes | Measured during baseline |
| Noise (sigma) | Decides acceptance threshold | Measured: k repeats at the same commit |
| Sensitivity | A metric that does not move under plausible changes is useless as a goal | Probe experiments during instrumenting |
| Direction | Sign of improvement | Declared |
| Gameability | Which cheap tricks would inflate it | Declared by metrologist, checked by judge |
| Determinism | Whether repeats agree; flaky metrics are quarantined | Measured |
| Coverage | How much of the project the metric actually sees | Declared, revisited at distill |

Instrument quality is summarized as `sensitivity / (sigma × cost)`. It is the goal metric of an instrument campaign and the tie-breaker when the loop chooses which of several candidate goals to work on first.

## 2.3 Metric sets and campaigns

A campaign is a named, versioned metric set with a budget:

```yaml
# .strictlybetter/campaign.yaml
id: 2026-09-03-parse-perf
goals: [bench_throughput]
guardrails: [tests_pass, clippy_warnings, public_api_surface, binary_size]
diagnostics: [build_seconds, unsafe_blocks]
composition: pareto          # pareto | oec
budget: { dollars: 40, hours: 8, experiments: 60 }
plateau_patience: 8
protected_paths: [benches/, tests/, .github/, Cargo.lock]
branch: sb/2026-09-03-parse-perf
status: running
```

Rules:

- A campaign has at least one goal and always includes the **hygiene guardrails** for its archetype (build succeeds, tests pass, no new lint errors), whether or not the user listed them.
- The metric set is frozen once the campaign starts. Changing it means ending the campaign and starting another. This is pre-registration at the campaign level.
- **composition: pareto** means a change is accepted only if it improves at least one goal beyond its noise floor and does not regress any other goal or guardrail beyond tolerance. This is the default.
- **composition: oec** allows a single Overall Evaluation Criterion with declared weights, for the case where the user has decided a trade-off in advance (for example, one point of accuracy is worth ten percent latency). Weights are part of the frozen set.

## 2.4 The acceptance rule

Let `A` be the current best state, `A'` the candidate, `m_x(·)` the measurement of metric `x`, `s_x ∈ {+1, −1}` its direction, `σ_x` its measured noise. The candidate is **strictly better** when all of the following hold on the *confirmation* measurement:

1. Improvement: there exists a goal `g` with `s_g · (m_g(A') − m_g(A)) > κ_g · σ_g`.
2. No regression: for every other goal and every guardrail `h`, `s_h · (m_h(A') − m_h(A)) ≥ −τ_h · σ_h`.
3. Integrity: no frozen path touched, eval hash unchanged, no protected path touched, holdout inputs unchanged.
4. Judgment: the blind judge finds no gaming pattern (see `04-anti-overfitting.md`).
5. Confirmation independence: the numbers in (1) and (2) come from the harness's confirmation run, not from the screening run the experimenter observed.

Defaults: `κ = 2.5`, `τ = 1.0`. Larger diffs raise κ (the complexity regularizer in `04-anti-overfitting.md`).

This is the Ladder mechanism of Blum and Hardt (2015) applied to a repository: report a new best only when it beats the previous best by more than a step size, otherwise keep the old value. The Ladder is the theoretical reason a threshold-ratchet resists adaptive overfitting; the noise floor gives the step size a physical meaning.

## 2.5 The ratchet and the global ratchet

`baseline.json` holds, per metric, the best confirmed value, its commit, and its sigma. Acceptance updates it. Nothing else does.

The **global ratchet** is the set of every metric that has ever been a goal in any campaign on this project, retained as a guardrail at its best confirmed value (with its tolerance). A new campaign can pick any goals it likes, but it inherits the global ratchet as guardrails automatically. Consequences:

- A perf campaign after an accuracy campaign cannot trade accuracy for speed without a human explicitly demoting the accuracy metric from the ratchet. Demotion is a logged, human-only act.
- The project's Pareto frontier can only move outward over time. This is what "points towards being better" means operationally.
- The ratchet is what lets metric sets vary freely without the loop cannibalizing its own past work.

## 2.6 Discovering metrics

The metrologist agent produces candidate cards from, in order of trust:

1. **Existing instruments**: CI workflows, `Makefile`/`justfile`/`package.json` scripts, `cargo bench`, `pytest-benchmark`, Lighthouse configs, existing eval scripts, notebooks that print a headline number.
2. **Archetype defaults**: the per-archetype card templates in `07-universality.md` (for a Rust crate: tests, clippy, build time, binary size, criterion benches, unsafe count).
3. **Stated goals**: README claims ("fast", "zero-copy", "97.2% on the benchmark"), open issues labelled performance/bug, a paper's headline table.
4. **Probes**: cheap experiments that change something plausible and see which candidate metrics respond. A metric with no sensitivity is demoted to diagnostic.
5. **Monotonicity selftest**: the card's `degradation` recipe is applied in a throwaway worktree; the metric must move in the wrong direction by more than its sigma. A card that fails cannot be a goal or a guardrail.

The output of discovery is a proposal, not a decision. The user picks the campaign's goals and guardrails at the first human gate (`09-governance.md`). Cards for metrics not chosen are kept as diagnostics so the ledger still records them.

## 2.7 Things that are not metrics

- LLM-judged scores without a frozen rubric and a fixed judge model. Allowed only as diagnostics until proven stable across repeats.
- Anything the experimenter agent can change the definition of.
- Anything measured on the experimenter's own machine state (uncommitted files, caches). The harness measures from a clean worktree checkout.
