# 05 · Cost and iteration speed

"Super optimized in cost and iteration speed" is a measurable claim. The loop's own efficiency metric is **cost per accepted improvement**: dollars and wall-clock spent per change that survived confirmation. Everything in this document exists to push that number down without weakening the walls in `04-anti-overfitting.md`.

## 5.1 Where the money goes

A typical experiment spends on four things:

| Phase | Spend | Lever |
|---|---|---|
| Hypothesis generation | LLM tokens, high tier | Batch hypotheses; ground them in harness-collected diagnostics so fewer are wasted |
| Implementation | LLM tokens, tier by operator | Model tiering; small diffs; operator templates |
| Measurement | wall-clock, sometimes dollars (GPU, cloud) | Multi-fidelity; caching; parallel worktrees; early kill |
| Judgment and confirmation | LLM tokens (judge) + repeats of measurement | Only promoted candidates are judged and confirmed |

The design principle: **spend LLM tokens on judgment, spend compute on measurement, and never spend confirmation-grade measurement on a candidate that has not earned it.**

## 5.2 Lever 1: multi-fidelity measurement

Every metric card declares a fidelity ladder (`02-metrics.md`). The loop runs it as successive halving over a hypothesis batch:

1. All `N` candidates measured at `screen` (cheap: subset of tests, short bench, short training run).
2. Candidates beyond `κσ_screen` promote to `full`. Sigma is measured per fidelity level; screen is noisier and the threshold accounts for it.
3. Candidates beyond `κσ_full` promote to `confirm` (repeats, holdout, clean checkout).

Typical ratios for a Rust bench: screen 25 s, full 120 s, confirm 3 × 120 s. If one candidate in six promotes, the batch costs about 6 × 25 + 120 + 360 = 630 s instead of 6 × 480 = 2880 s at confirm-grade for all. Hyperband's insight is that the promotion rate can be tuned to the budget; the loop exposes the promotion fraction as a campaign setting.

**Early kill** applies inside a single long measurement: for metrics with intermediate values (training loss at checkpoints, tests in a suite), the harness stops a run whose intermediate is worse than the baseline's intermediate by more than a margin (default 3σ of the intermediate). This is the largest single saving for ML archetypes.

## 5.3 Lever 2: bandit allocation over operator classes

`06-search.md` §6.2 defines the bandit. Its cost role: it directs hypothesis batches toward operator classes with high confirmed effect per dollar *in this repo*. A repo where config changes never beat noise stops receiving config hypotheses after a few rounds. Cold start uses archetype priors so the first batch is not uniform.

## 5.4 Lever 3: model tiering

Not every step needs the strongest model. The loop follows the effortmining calibration: pin reasoning effort per task class, and route mechanical work to cheap tiers.

| Task | Tier | Why |
|---|---|---|
| Orient, hypothesize, distill | high | Judgment, synthesis, multi-file reasoning |
| Implement `config`, `docs`, `test-add` | low/medium | Template-shaped edits |
| Implement `algorithmic`, `allocation`, `concurrency`, `model` | medium/high | Real coding; correctness matters |
| Judge | medium, blind | Checklist-driven; must not be persuadable |
| Parse output, format ledger, run commands | none (harness) | Deterministic |

On Claude Code this is implemented with tier-pinned worker agents, the same mechanism effortmining uses, because there is no per-spawn effort parameter. Other platforms map to their model selection.

## 5.5 Lever 4: isolation and parallelism

- Each experiment lives in its own git worktree with a shared build cache (`target/` via `CARGO_TARGET_DIR`, `node_modules` via hard links, Python venvs reused). Worktree creation is seconds; a fresh clone is not.
- Implementation runs in parallel across worktrees, bounded by `max_parallel` (default: cores / 2).
- **Measurement is serialized** for timing-sensitive metrics. Parallel measurement inflates sigma and the loop would then need more repeats; serial measurement is cheaper overall. Metrics whose card says `contention_safe: true` (test pass counts, lint counts, sizes) may run in parallel.
- A dedicated measurement host is a configuration option: the harness can run `confirm` over SSH on a quiet machine while the developer laptop does implementation.

## 5.6 Lever 5: caching and amortization

- Build artifacts are cached per worktree and shared where the toolchain allows.
- Measurement results are cached by `(metric id, commit hash, fidelity, environment fingerprint)`. Re-measuring a commit the harness has already measured is free.
- Baseline sigma is reused until a re-baseline trigger (environment change, rotation, drift suspicion).
- Diagnostics (profiles, coverage, slow-test lists) are collected once per accepted state, not per hypothesis.
- Test impact analysis where the ecosystem supports it (`pytest-testmon`, `cargo nextest` filtering, `jest --changedSince`) narrows the screen suite to tests affected by the diff; the full suite runs at `full`.

## 5.7 Lever 6: batch shape

Cheap screening favors many small hypotheses; expensive screening favors few, well-grounded ones. The harness sets batch size from the measured screen cost and the remaining budget:

```
batch = clamp( budget_remaining_s / (screen_s × expected_rounds_remaining), 2, 12 )
```

The experimenter is told the batch size and the operator mix. It does not decide how much to spend.

## 5.8 The meta-metric

`sb status` reports, per campaign and cumulatively:

- experiments run, promoted, confirmed, accepted
- dollars and wall-clock, split by phase
- **cost per accepted improvement** (dollars, minutes)
- yield curve: accepted improvements vs experiments, which shows saturation before the plateau detector fires
- false-promotion rate: promoted at screen but discarded at full/confirm, which is the screen fidelity's quality
- judge overhead: fraction of spend on judgment
- holdout gap trend: screen improvement minus confirm improvement over accepted changes (`04-anti-overfitting.md` §4.4)

**False-promotion budget.** A campaign setting (default: 40% of promotions over any window of 10). Exceeding it means the screen fidelity is lying on this machine; the harness re-measures screen sigma, raises screen repeats, or demotes screen to full for the rest of the campaign, and the report says which. This is what keeps multi-fidelity cheap without letting it become a source of noise-selected winners.

These numbers are in the campaign report and the inheritance body. A campaign whose cost per accepted improvement rises steeply is saturating; the distiller says so and the loop escalates or stops rather than grinding.

## 5.9 What is not optimized

- The noise floor is never lowered to save money. If a metric needs 7 repeats to be trustworthy on this machine, it gets 7 or it is quarantined.
- Confirmation is never skipped. A candidate the loop cannot afford to confirm is not accepted; it is archived with `budget` and the report says so.
- The judge is never skipped for promoted candidates. Its cost is small relative to a false acceptance.
