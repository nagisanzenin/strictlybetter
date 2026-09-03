# 11 · Machine learning principles, mapped

The loop is not a neural network, but the discipline that keeps ML experiments honest transfers almost one-to-one. This table is the cheat sheet; each row points to the doc that defines the mechanism.

| ML principle | In strictlybetter | Doc |
|---|---|---|
| Train / validation / test split | Screen fidelity (experimenter sees) / full fidelity / confirm with holdout (harness only) | 02, 04 |
| Overfitting to the validation set under adaptive selection | Acceptance by an exact paired sign-flip test at confirm on pre-registered interleaved pairs; discarded candidates' confirm numbers redacted from the experimenter | 04, 13 |
| Noise-aware evaluation, multiple seeds | Measured sigma from k repeats at the same commit; screen threshold κσ; at confirm the same holdout seed on both sides of every pair | 02, 04 |
| Winner's curse | Confirmation on an independent measurement, never on the screening number that selected the winner | 04 |
| Early stopping with patience | Plateau detection: `patience` experiments without acceptance escalates exploration or stops | 06 |
| Early termination of bad runs (Hyperband) | Multi-fidelity ladder; kill runs that are worse than baseline's checkpoint by a margin | 05 |
| Learning-rate schedule | Allowed diff size resets small after an acceptance, grows on plateau | 06 |
| Regularization / Occam prior | Complexity regularizer: κ grows with diff size; new dependencies penalized | 06 |
| Exploration vs exploitation | Thompson sampling over operator classes; exploration levels on plateau | 06 |
| Replay buffer | Append-only ledger | 08 |
| Experience distillation | Inheritance body rewritten at every DISTILL | 08 |
| Ensembles / population methods | Parallel worktrees; quality-diversity archive; recombination of near-misses | 05, 06 |
| Ablation study | Ablation probes to locate leverage before hypothesizing | 06 |
| Curriculum | Cheap, low-noise metrics first; instrument campaign for greenfield | 07 |
| Simulated annealing | Stepping stones on a side branch, never on the campaign branch | 06 |
| Reward hacking / specification gaming | Frozen instrument, holdout, blind judge, gaming-risk checklist per metric | 04 |
| Pre-registration (from experimental science) | Ledger line with predicted effect before any diff exists | 03, 04 |
| Multiple comparisons | Bonferroni over the pre-registered experiment budget: per-test alpha is `alpha / K`, so the family-wise false-accept probability per campaign is at most alpha; halt on repeated `gamed` verdicts as a drift detector | 04, 13 |
| Optional stopping (peeking) | Sample size fixed before the data; an optional pre-registered two-stage design with Pocock alpha spending and a futility stop | 04, 13 |
| Change-point detection over time | Periodic re-baseline; drift check on the ledger's time series | 04, 05 |
| Meta-learning across tasks | Archetype priors for the bandit, updated slowly from many projects | 08 |
| Cost-aware optimization | Cost per accepted improvement as the loop's own metric | 05 |

Two principles deliberately do not transfer:

- **Gradient descent.** There is no differentiable path through a repository. All search here is zeroth-order; the hypotheses are the gradient estimator and they are as good as the diagnostics that ground them.
- **Large batch sizes.** Measurement contention destroys the noise floor. Parallelism is bounded by the measurement host, not by the number of ideas.

Rows whose mechanism is design rather than shipped code in v1.0: early termination of bad runs (no early kill), simulated annealing (no side branch), change-point detection (no drift check; re-baseline is by hand), meta-learning across tasks (archetype priors are static files, updated only by a plugin release), and ablation study (the experimenter's own experiments, not an engine command). See the "not in v1.0" notes in the linked docs.
