# 11 · Machine learning principles, mapped

The loop is not a neural network, but the discipline that keeps ML experiments honest transfers almost one-to-one. This table is the cheat sheet; each row points to the doc that defines the mechanism.

| ML principle | In strictlybetter | Doc |
|---|---|---|
| Train / validation / test split | Screen fidelity (experimenter sees) / full fidelity / confirm with holdout (harness only) | 02, 04 |
| Overfitting to the validation set under adaptive selection | The Ladder: accept only if improvement exceeds a step size; reusable-holdout style leakage budget on confirm | 04 |
| Noise-aware evaluation, multiple seeds | Measured sigma from k repeats at the same commit; acceptance threshold κσ | 02, 04 |
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
| Multiple comparisons | Confirmation run as a per-candidate correction; halt on repeated `gamed` verdicts as a drift detector | 04 |
| Change-point detection over time | Periodic re-baseline; drift check on the ledger's time series | 04, 05 |
| Meta-learning across tasks | Archetype priors for the bandit, updated slowly from many projects | 08 |
| Cost-aware optimization | Cost per accepted improvement as the loop's own metric | 05 |

Two principles deliberately do not transfer:

- **Gradient descent.** There is no differentiable path through a repository. All search here is zeroth-order; the hypotheses are the gradient estimator and they are as good as the diagnostics that ground them.
- **Large batch sizes.** Measurement contention destroys the noise floor. Parallelism is bounded by the measurement host, not by the number of ideas.
