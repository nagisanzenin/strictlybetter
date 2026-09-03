# 06 · Search: operators, bandits, plateaus, and stepping stones

The loop is gradient-free search over program space. This document defines what a move is, how moves are chosen, how the loop avoids getting stuck, and when it stops.

## 6.1 Operators: the vocabulary of moves

A hypothesis belongs to exactly one **operator class**. Classes are the arms of the bandit and the unit of inheritance ("allocation changes pay off here; dependency upgrades never do"). The library ships with a default set; the metrologist and distiller can propose new ones.

| Operator | Typical diff | Typical cost | Typical targets |
|---|---|---|---|
| `config` | knob, flag, constant, hyperparameter | tiny | build flags, LR, batch size, thread counts |
| `algorithmic` | replace an algorithm or data structure in one function | small | hot loops, parsers, queries |
| `allocation` | remove copies/allocations, reuse buffers | small | Rust/C++/Go hot paths |
| `caching` | memoize, precompute, incremental recompute | small–medium | repeated work |
| `concurrency` | parallelize, batch, pipeline | medium | I/O and embarrassingly parallel loops |
| `dependency` | upgrade/replace a library | small diff, unknown risk | anything |
| `test-add` | add a test that captures a bug or a missing case | small | guardrail coverage |
| `bugfix` | fix a failing or flaky test's root cause | small | correctness goals |
| `refactor-enabling` | structural change with no metric effect that unlocks later moves | medium–large | stepping stones only |
| `data` | change data pipeline, filtering, augmentation | medium | ML and science |
| `model` | architecture or objective change | medium–large | ML |
| `numerics` | precision, solver, tolerance, stability | small | science and simulation |
| `docs` | documentation coverage | small | docs goals only |

Two properties are attached to every class: an **expected diff size** (which sets the complexity regularizer's κ) and a **model tier** for implementation (`05-cost-and-speed.md`).

## 6.2 Choosing moves: a bandit with priors

Each operator class keeps, per repo, in `bandit.json`: attempts, acceptances, mean confirmed effect size, mean cost. Selection is Thompson sampling on a Beta posterior over acceptance probability, weighted by mean effect per dollar. Cold start uses archetype priors (for a Rust crate: `allocation` and `algorithmic` start warm; `docs` starts cold unless a docs metric is a goal).

The bandit chooses the *mix* of a hypothesis batch, not individual hypotheses. The experimenter agent still writes the hypotheses; the bandit tells it "four algorithmic, one caching, one config this round". This keeps the LLM in charge of content and the harness in charge of allocation.

Hypothesis quality inputs, in priority order:

1. **Diagnostics from the current best state**: profiler output, flame graphs, slowest tests, coverage gaps, failing cases, compiler warnings, largest functions. The harness collects these once per accepted state so hypotheses are grounded in evidence, not guesswork.
2. **Ablation probes** (MLE-STAR style): cheap experiments that disable or stub a component to measure how much of the metric it accounts for. Run at most a few per campaign; they tell the loop where the leverage is.
3. **The inheritance body**: what worked, what is a dead end.
4. **The archive**: partial or near-miss diffs that could be recombined.

## 6.3 Step size and the complexity regularizer

Smaller diffs are cheaper to judge, less likely to hide gaming, and less likely to break guardrails. The loop prefers them and makes larger ones earn their keep:

```
kappa_effective = kappa × (1 + λ · log(1 + diff_lines / 50))     λ = 0.3 default
```

A 40-line diff must beat 2.5σ; a 400-line diff must beat about 3.4σ. New dependencies add a fixed penalty. The regularizer is the loop's version of a prior toward simple explanations and is what stops "rewrite everything" hypotheses from being accepted on a lucky run.

Step size is scheduled inversely to progress: after an acceptance, expected diff size resets to small; during a plateau it is allowed to grow (`§6.4`). This is a learning-rate schedule with the sign flipped: when the landscape is flat locally, take bigger steps.

## 6.4 Plateaus and exploration levels

A plateau is `patience` consecutive experiments without an acceptance (default 8). Each plateau raises the exploration level:

| Level | What changes |
|---|---|
| 0 (default) | small diffs, bandit exploitation, top-3 diagnostics targeted |
| 1 | medium diffs allowed; bandit temperature raised; ablation probes run to relocate leverage |
| 2 | `refactor-enabling` operator unlocked on a **side branch** (stepping stones, §6.5); hypotheses may target components ablation showed matter but the loop has not touched |
| 3 | campaign-level decision: switch metric set or stop (`03-loop.md` §DISTILL) |

Any acceptance resets to level 0. Exploration levels are logged so the inheritance body can say "this metric saturated at level 2 after 31 experiments".

## 6.5 Stepping stones: annealing on a side branch, never on main

Hill climbing with a strict-improvement rule cannot cross a valley: a refactor that makes nothing faster but makes the next optimization possible is always discarded. Simulated annealing solves this by sometimes accepting worse moves, but accepting worse on the campaign branch would violate the ratchet.

Resolution: at exploration level 2 the loop may open a **side branch** rooted at the campaign head. On the side branch, `refactor-enabling` moves are accepted if guardrails hold even when no goal improves. The side branch has its own small budget (default 15% of campaign) and a hard length (default 3 stepping stones). The side branch is merged back only if its final state is strictly better than the campaign head on the confirmation run. Otherwise it is archived whole.

This keeps the invariant: the campaign branch only ever fast-forwards to strictly better states. Valleys are crossed off to the side and only the far bank is kept.

## 6.6 Quality-diversity archive

Evolutionary program search (AlphaEvolve, ShinkaEvolve) keeps an archive of diverse solutions rather than a single best, because recombination of near-misses is where many of their wins come from. The loop keeps a light version:

- Discards marked interesting are stored in `archive/` keyed by `(operator, target file, effect signature)`.
- At most one entry per key is kept (the best by screen effect), which is MAP-Elites with a two-dimensional behaviour space.
- The experimenter receives up to three archive entries relevant to its target when hypothesizing.

The archive is local and never committed; the ledger references entries by hash.

## 6.7 Stopping

The loop stops, in order of precedence:

1. `STOP` file present, integrity violation, or three consecutive harness errors: **halted**, needs a human.
2. Budget exhausted in any dimension (dollars, hours, experiments): **budget**.
3. Exploration level 3 reached and no other metric set has headroom: **converged**.

"Headroom" for an inactive metric set is estimated from its last campaign's plateau level and the time since; a set that saturated long ago and whose code has since changed is considered to have headroom again.

## 6.8 What the loop does not do

- It does not run many parallel campaigns on the same metric set; contention on measurement destroys the noise floor.
- It does not chase a goal below its noise floor by increasing repeats without bound; if `κσ` cannot be beaten in a plateau, the instrument is the problem, and the distiller says so.
- It does not accept an experimenter's claim that a change "should" help. Only confirmation numbers move the baseline.
