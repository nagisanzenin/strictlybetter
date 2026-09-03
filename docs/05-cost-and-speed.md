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

1. All `N` candidates measured at `screen` (cheap: subset of tests, short bench, short training run) with `sb measure --fidelity screen`.
2. Candidates beyond `κσ_screen` are promoted by `sb judge`. Sigma is measured per fidelity level (`baseline.json` keeps `screen`, `full`, and `confirm` entries); screen is noisier and the threshold accounts for it.
3. `sb confirm` runs `full` for every card that defines it and discards a candidate that regresses, is invalid, or shows no positive movement there; whatever survives goes on to `confirm` (repeats, holdout, clean checkout) in the same command.

Typical ratios for a Rust bench: screen 25 s, full 120 s, confirm 3 × 120 s. If one candidate in six promotes, the batch costs about 6 × 25 + 120 + 360 = 630 s instead of 6 × 480 = 2880 s at confirm-grade for all. Hyperband's insight is that the promotion rate can be tuned to the budget. Not in v1.0: a promotion-fraction setting; the promotion rate is whatever `κσ_screen` yields, and the false-promotion budget (§5.8) is the feedback on it.

**Early kill** applies inside a single long measurement: for metrics with intermediate values (training loss at checkpoints, tests in a suite), the harness stops a run whose intermediate is worse than the baseline's intermediate by more than a margin (default 3σ of the intermediate). This is the largest single saving for ML archetypes. Not in v1.0: the engine runs every measurement to completion or to its `timeout_s`; a card's screen command can implement its own early exit.

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

- Each experiment lives in its own git worktree (`.strictlybetter/wt/<id>/`, created by `sb prereg` with `git worktree add --detach`). Worktree creation is seconds; a fresh clone is not. Not in v1.0: a shared build cache set up by the engine; a card's `env` can point `CARGO_TARGET_DIR` or a venv at a shared location, and the project's own caches apply.
- Implementation runs in parallel across worktrees, bounded by the campaign's `max_parallel` (default 2); `sb next` uses it as the batch size floor.
- **Measurement is serialized** for timing-sensitive metrics. Parallel measurement inflates sigma and the loop would then need more repeats; serial measurement is cheaper overall. Metrics whose card says `contention_safe: true` (test pass counts, lint counts, sizes) may run in parallel.
- A dedicated measurement host is a configuration option: the harness can run `confirm` over SSH on a quiet machine while the developer laptop does implementation. Not in v1.0 (`10-implementation-plan.md` §10.9); a card's command may itself shell out over SSH.

## 5.6 Lever 5: caching and amortization

- Build artifacts are cached per worktree and shared where the toolchain allows (the project's own caches; the engine adds none).
- Measurement results cached by `(metric id, commit hash, fidelity, environment fingerprint)`, so re-measuring a commit the harness has already measured is free. Not in v1.0: the only cache is in-process, for cards flagged `reuse_output` that re-parse another card's identical command.
- Baseline sigma is reused until a re-baseline: `sb baseline` by hand, or the confirm-level re-baseline after a holdout rotation.
- Diagnostics (profiles, coverage, slow-test lists) are collected once per accepted state, not per hypothesis. This is the experimenter's or orchestrator's job; the engine collects none.
- Test impact analysis where the ecosystem supports it (`pytest-testmon`, `cargo nextest` filtering, `jest --changedSince`) narrows the screen suite to tests affected by the diff; the full suite runs at `full`. In v1.0 this is expressed per card: a narrower `fidelity.screen.command` and the full command at `full`.

## 5.7 Lever 6: batch shape

Cheap screening favors many small hypotheses; expensive screening favors few, well-grounded ones. The harness sets batch size from the measured screen cost and the remaining budget:

```
batch = max_parallel                                              # default 2
if budget.hours is set and screen_s > 0:
    batch = clamp( hours_left × 3600 / (screen_s × 8), 1, 6 )
batch = min( batch, experiments_left )
```

where `screen_s` is the sum of the goals' and guardrails' screen-level `secs_per_run` from `baseline.json`. `sb next` prints the batch size and the operator mix; the experimenter is told both. It does not decide how much to spend.

## 5.8 The meta-metric

`sb status`, `sb distill-stats --json`, and the campaign report (`sb report`) all print the same `stats()` block, per campaign:

- `experiments`, `promoted` (judge said promote), `accepted`, `discarded`, and `discard_reasons` by prefix
- `wall_s` (measurement wall-clock charged by `sb measure` and `sb confirm`, plus whatever `sb cost` reported) and `dollars_est` (from reported tokens and the campaign's `pricing`)
- **cost per accepted improvement**: `wall_s_per_accept`, `dollars_per_accept`
- `false_promotions` and `false_promotion_rate_window`: promoted at screen but discarded at full or confirm, over the last 10 promotions, which is the screen fidelity's quality
- `confirmed_effects` and `mean_confirmed_effect`: the relative confirmed improvement on the primary goal per accepted change
- `holdout_gap_mean_last5`: screen improvement minus confirm improvement, as a ratio, over the last five accepted changes (`04-anti-overfitting.md` §4.4)
- `by_operator` attempts and accepts, `since_last_accept`, `exploration_level`, `budget_left`, `budget_exhausted`, `screen_untrusted`; `distill-stats` adds the `decision`

Not in v1.0: a per-phase cost split (hypothesis, implementation, measurement, judgment), the yield curve (accepted improvements against experiments over time), and judge overhead as a fraction of spend. The ledger's `cost` events carry `tier`, so a reader can compute these from the file.

**False-promotion budget.** A campaign setting (`false_promotion_budget`, default 40% of promotions over a window of 10). When at least three candidates have been promoted and the window rate exceeds it, `sb distill-stats` marks the campaign `screen_untrusted`, doubles the screen repeats (the multiplier is capped at 4), and writes a `screen-untrusted` event to the ledger; the report and `sb next` say so. Not in v1.0: re-measuring screen sigma or demoting screen to full automatically. This is what keeps multi-fidelity cheap without letting it become a source of noise-selected winners.

These numbers are in the campaign report and the inheritance body. A campaign whose cost per accepted improvement rises steeply is saturating; the distiller says so and the loop escalates or stops rather than grinding.

## 5.9 What is not optimized

- The noise floor is never lowered to save money. If a metric needs 7 repeats to be trustworthy on this machine, it gets 7 or it is quarantined. The minimum-detectable-effect gate is the same rule at campaign start: a goal whose smallest detectable improvement exceeds 50% on this host halts the start (`04-anti-overfitting.md` §4.2).
- Confirmation is never skipped. A candidate the loop cannot afford to confirm is not accepted; it is archived with `budget` and the report says so.
- The judge is never skipped for promoted candidates. Its cost is small relative to a false acceptance.

The engine's wall toggles (`04-anti-overfitting.md` §4.1) can switch each of these off. They exist for the meta-benchmark's naive condition; a campaign that turns one off has it recorded in `campaign.json`, in the ledger, and in the report.
