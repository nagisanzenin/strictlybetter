# 04 · Anti-overfitting: five walls and a ratchet

Overfitting in a code research loop means optimizing the instrument instead of the property. The failure comes in four flavors (Manheim and Garrabrant's taxonomy of Goodhart's law) and each needs a different defense. This document defines the defenses and why each is necessary.

## 4.1 Four ways a metric lies

| Goodhart variant | What it looks like in a repo loop | Defense |
|---|---|---|
| **Regressional**: selecting on a noisy proxy selects for noise | Of 40 experiments at ±3% noise, two will look like +5% by luck; the loop merges them and the "gain" evaporates | Noise floor + confirmation (Wall 1) |
| **Extremal**: the proxy stops tracking the goal at extremes | 100% coverage by deleting code; zero lint by disabling rules; fast benchmark by making it do less | Guardrails, frozen instrument, complexity regularizer (Walls 2, 5) |
| **Causal**: the change moves the proxy without moving the cause | Caching the exact benchmark inputs; tuning to the development seeds; pre-computing the eval set | Holdout (Wall 3) |
| **Adversarial**: the optimizer targets the measurement itself | Editing the test, skipping the slow case, special-casing inputs, patching the timer | Frozen instrument, blind judge (Walls 2, 5) |

An LLM experimenter is not malicious, but it is an optimizer under pressure, and documented cases (see `citations.md` §7) show coding agents editing tests, special-casing evaluators, and rewriting harnesses when that is the shortest path to a passing number. The design assumes this will happen and makes it non-fatal.

## 4.2 Wall 1: the noise floor and the confirmation run

**Noise floor.** At the current best commit, the harness measures each metric `k` times (default 5; raised until the standard error of sigma is below 20% of sigma, capped by cost). Sigma is stored on the card with the commit and an environment fingerprint. It is re-measured whenever the environment fingerprint changes, at every re-baseline, and whenever a plateau makes the distiller suspect the instrument.

**Threshold.** A goal must move by more than `κσ` (κ = 2.5 default). This is deliberately not a p-value from a two-sample test; with 3 to 5 repeats per side those tests are unreliable, and an effect-size threshold in sigma units is what practitioners actually use in performance CI (the Rust compiler's perf triage uses a significance threshold in the same spirit).

**Confirmation.** The screening number that promoted a candidate is discarded for the purpose of acceptance. The harness re-measures at `full` and `confirm` fidelity from a clean checkout, with holdout inputs, `r` repeats (default 3). Acceptance uses the confirmation median. This is the winner's-curse correction: the number that selected the winner is biased upward by selection, the fresh number is not.

**Why this is the Ladder.** Blum and Hardt (2015) showed that a leaderboard which only publishes a new score when it beats the previous best by more than a step size resists adaptive overfitting: the number of "false improvements" an adaptive submitter can extract is bounded, and the bound depends on the step size, not on the number of submissions. Our step size is `κσ`. The ratchet in `baseline.json` is a Ladder over the project's metrics.

## 4.3 Wall 2: the frozen instrument

The experimenter cannot change what is measured or how:

- **Frozen paths** listed on each card (tests, benches, fixtures, eval scripts, reference outputs) are hashed at campaign start. Any diff touching them is rejected before measurement, and the campaign halts.
- **Measurement runs outside the experimenter's process** from a clean checkout of the experiment commit in a separate worktree, with the card's pinned environment. The experimenter's shell state, caches, and uncommitted files are not part of the measurement.
- **Timers, counters, and parsers** belong to the harness, not to the code under test. If a metric's command lives inside the repo (a `make bench`), the script is a frozen path.
- **Metric definitions** (`.strictlybetter/metrics/`) are outside the experimenter's write set.

Instrument changes are legitimate in an *instrument campaign* (`07-universality.md` §7.3), where the roles invert and the implementation is frozen instead.

## 4.4 Wall 3: the holdout

The experimenter tunes against what it can see. Confirmation therefore uses what it cannot:

- **Seeds** it never saw (ML training, simulations, randomized tests).
- **Input slices** it never saw (a benchmark fixture set split into dev and confirm; a held-out test split; a second dataset).
- **Hidden tests** kept outside the worktree and mounted only by the harness at confirm.

Two disciplines keep the holdout useful over many experiments:

1. **Limited leakage.** Confirmation reports `accepted` or `discarded` and the confirmation numbers of *accepted* candidates only. Discarded candidates' holdout numbers are written to the ledger under a field the experimenter is instructed not to read and the harness does not surface in status. This is the reusable-holdout idea (Dwork et al. 2015) in its crude, practical form: the experimenter learns about the holdout only through the ratchet, which moves rarely.
2. **Rotation.** After `n` acceptances (default 10), the harness regenerates holdout seeds or rotates the slice, and re-baselines. A loop that ran for weeks against one holdout has, in effect, seen it.

## 4.5 Wall 4: pre-registration

Every experiment has a ledger line with operator, target, hypothesis, and predicted effect *before a diff exists*. Consequences:

- A change that helps a metric it did not predict is still accepted if it passes, but the ledger records the surprise, and the distiller treats unpredicted wins as lower-confidence knowledge (more likely to be noise or gaming).
- Post-hoc metric switching within an experiment is impossible; the metric set is frozen at campaign start.
- The predicted effect is data for the bandit: an operator class whose predictions are systematically wrong gets its variance raised.

Pre-registration is the reproducibility movement's answer to the garden of forking paths (Gelman and Loken; Nosek et al. 2018). It costs the loop nothing and it is the single highest-leverage habit the agent can have.

## 4.6 Wall 5: the blind judge and the complexity regularizer

**Blind judge.** For every promoted candidate, a separate agent receives the diff, the pre-registration, the numbers, and each affected metric card's `gaming_risks` list. It receives nothing else: not the experimenter's reasoning, not the conversation, not the campaign chat. It returns fixed JSON:

```json
{"verdict":"clean|suspicious|gamed","pattern":"<from checklist or free text>","evidence":"<lines>","recommended_check":"<a cheap extra measurement>"}
```

The checklist grows from experience (`08-memory-and-inheritance.md` §8.3). Seed entries:

- test deleted, skipped, marked xfail, or its assertion weakened
- input-specific branch (`if name == "parse_large"`) or fixture-shaped shortcut
- caching keyed on something only the benchmark supplies
- measurement narrowed (fewer iterations, smaller fixture, warm-up counted)
- output hard-coded, table-lookup on eval inputs
- environment tampering (thread count, GC flags, `PYTHONHASHSEED`) outside the declared operator
- timer, counter, or parser touched
- nondeterminism introduced that widens variance in the favorable direction

`suspicious` triggers the recommended check (usually a fresh fixture or a different seed set) rather than an automatic discard. `gamed` discards and counts toward the halt condition in `09-governance.md`.

The blind design is borrowed from engram's assessor and effortmining's grader: the judge that cannot see the argument cannot be persuaded by it.

**Complexity regularizer.** Larger diffs must clear a higher threshold:

```
κ_eff = κ × (1 + λ·log(1 + diff_lines/50))     λ = 0.3
```

plus a fixed penalty per new dependency. The regularizer targets extremal Goodhart: sweeping changes are where "make the metric better by making the program do less" hides, and they are also where review is hardest. Small diffs with clear mechanisms are the loop's native step.

## 4.7 The regression wall

Regression is prevented by construction, not by review:

- Every goal and guardrail is measured on every candidate at every fidelity level; a candidate that improves the goal and breaks a guardrail is discarded with `regression:<metric>`.
- The **global ratchet** (`02-metrics.md` §2.5) carries every past goal forward as a guardrail, so a later campaign cannot regress an earlier one.
- Hygiene guardrails (build, tests, lint) are always present, whether the user listed them or not.
- **Drift check.** At each re-baseline the harness re-measures the whole ratchet at the campaign head. If a ratcheted metric has drifted below its floor beyond tolerance without any accepted change touching it, the environment changed and the loop halts with `baseline-drift`. Long-horizon drift over the ledger's time series is checked with a change-point test (the E-divisive method MongoDB uses for performance CI is the reference).

## 4.8 What still gets through, and what catches it later

No wall is complete. The engram release protocol's lesson, that every gate misses its own bug class, applies here. What each wall does not catch:

- Wall 1 misses systematic bias that repeats identically (a cache warm on every run). Wall 2 and 3 catch it.
- Wall 2 misses gaming that lives entirely in the implementation (special-casing). Wall 3 and 5 catch it.
- Wall 3 misses a holdout that is too similar to the dev set. Rotation and the human at Gate 2 catch it.
- Wall 4 catches nothing by itself; it makes the others' evidence legible.
- Wall 5 is an LLM judgment and will miss novel patterns. The checklist grows; the ledger makes the miss auditable.

The last defense is the human at Gate 2 reading a report designed to make these misses visible: diff sizes, targets, judge flags, and reproduction commands.
