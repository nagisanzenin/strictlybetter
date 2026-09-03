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

Two properties are attached to every class in `operators/*.md`: an **expected diff size** (what `sb next` allows per exploration level; the complexity regularizer itself uses the submitted diff's actual line count) and a **model tier** for implementation (`05-cost-and-speed.md`). The engine's `OPERATORS` list is exactly these thirteen ids; `sb prereg` rejects any other.

## 6.2 Choosing moves: a bandit with priors

Each operator class keeps, per repo, in `bandit.json`: `alpha`, `beta`, `attempts`, `accepts`, `effect_sum` (confirmed relative effects), `cost_s`. `sb accept` and `sb discard` update it. Selection in `sb next` is Thompson sampling on the Beta(`alpha`, `beta`) posterior over acceptance probability, one draw per class, then a weighted draw of the batch. Not in v1.0: weighting by mean effect per dollar; effect and cost are recorded for the distiller but do not enter the draw. Cold start uses archetype priors (for a Rust crate: `allocation` and `algorithmic` start warm; `docs` starts cold unless a docs metric is a goal): the campaign spec's `archetype_priors`, copied from the archetype pack's `operator_priors`, or the engine's defaults.

The bandit chooses the *mix* of a hypothesis batch, not individual hypotheses. The experimenter agent still writes the hypotheses; the bandit tells it "four algorithmic, one caching, one config this round". This keeps the LLM in charge of content and the harness in charge of allocation.

Hypothesis quality inputs, in priority order:

1. **Diagnostics from the current best state**: profiler output, flame graphs, slowest tests, coverage gaps, failing cases, compiler warnings, largest functions. Collected once per accepted state so hypotheses are grounded in evidence, not guesswork. In v1.0 the experimenter or orchestrator collects them; the engine's `sb next` brief carries the frontier, dead ends, wins, and archive hints, not diagnostics.
2. **Ablation probes** (MLE-STAR style): cheap experiments that disable or stub a component to measure how much of the metric it accounts for. Run at most a few per campaign; they tell the loop where the leverage is. In v1.0 these are ordinary pre-registered experiments the experimenter chooses to run.
3. **The inheritance body**: what worked, what is a dead end.
4. **The archive**: partial or near-miss diffs that could be recombined.

## 6.3 Step size and the complexity regularizer

Smaller diffs are cheaper to judge, less likely to hide gaming, and less likely to break guardrails. The loop prefers them and makes larger ones earn their keep:

```
kappa_effective = kappa × (1 + λ · ln(1 + diff_lines / 50)) + 1.0 × new_deps     λ = 0.3
```

A one-line diff must beat 2.5σ; a 40-line diff about 2.9σ; a 400-line diff about 4.2σ. Each touched dependency manifest adds one sigma (and only the `dependency` operator may touch one). The regularizer is the loop's version of a prior toward simple explanations and is what stops "rewrite everything" hypotheses from being accepted on a lucky run.

Step size is scheduled inversely to progress: after an acceptance, expected diff size resets to small; during a plateau it is allowed to grow (`§6.4`). This is a learning-rate schedule with the sign flipped: when the landscape is flat locally, take bigger steps.

## 6.4 Plateaus and exploration levels

A plateau is `patience` consecutive experiments without an acceptance (default 8). Each plateau raises the exploration level:

| Level | What changes |
|---|---|
| 0 (default) | small diffs, bandit exploitation, top-3 diagnostics targeted |
| 1 | medium diffs allowed; bandit temperature raised; ablation probes run to relocate leverage |
| 2 | `refactor-enabling` operator unlocked on a **side branch** (stepping stones, §6.5); hypotheses may target components ablation showed matter but the loop has not touched |
| 3 | campaign-level decision: switch metric set or stop (`03-loop.md` §DISTILL) |

Any acceptance resets to level 0. Exploration levels are logged (an `explore` event in the ledger) so the inheritance body can say "this metric saturated at level 2 after 31 experiments".

In v1.0 the engine implements the levels as follows. `sb discard` raises the level after `plateau_patience` discards since the last acceptance (up to 3) and resets the counter; `sb next` widens the allowed diff sizes (level 0: tiny, small; level 1: adds medium; level 2 and above: adds large) and prints the level; `sb judge` arms the anomaly breaker once half a patience has passed without an acceptance; `sb distill-stats` returns `explore:levelN` while the level is above 0 and `stop:converged` after a further `patience` discards at level 3. Not in v1.0: a raised bandit temperature at level 1, engine-run ablation probes, and the side branch at level 2 (§6.5); `refactor-enabling` is always a legal operator, and at level 2 the experimenter is expected to use it for stepping stones that still pass the acceptance rule on the campaign branch. The bandit draw is the same at every level.

## 6.5 Stepping stones: annealing on a side branch, never on main

Design; not in v1.0. The engine has one branch per campaign and no side-branch budget or merge-back; what follows is the intended mechanism for a later version.

Hill climbing with a strict-improvement rule cannot cross a valley: a refactor that makes nothing faster but makes the next optimization possible is always discarded. Simulated annealing solves this by sometimes accepting worse moves, but accepting worse on the campaign branch would violate the ratchet.

Resolution: at exploration level 2 the loop may open a **side branch** rooted at the campaign head. On the side branch, `refactor-enabling` moves are accepted if guardrails hold even when no goal improves. The side branch has its own small budget (default 15% of campaign) and a hard length (default 3 stepping stones). The side branch is merged back only if its final state is strictly better than the campaign head on the confirmation run. Otherwise it is archived whole.

This keeps the invariant: the campaign branch only ever fast-forwards to strictly better states. Valleys are crossed off to the side and only the far bank is kept.

## 6.6 Quality-diversity archive

Evolutionary program search (AlphaEvolve, ShinkaEvolve) keeps an archive of diverse solutions rather than a single best, because recombination of near-misses is where many of their wins come from. The loop keeps a light version:

- Discards marked interesting (`sb discard --archive`) are stored as `archive/<id>.diff`; the ledger's `discard` event records `archive_key` as `operator|target`.
- At most one entry per key is kept (the best by screen effect), which is MAP-Elites with a two-dimensional behaviour space. Not in v1.0: the engine keeps one file per archived experiment and does not dedupe by key; the distiller prunes.
- The experimenter receives archive hints when hypothesizing: `sb next` lists the six most recent archive files. Not in v1.0: selection by relevance to the target.

The archive is local and never committed (the state home's `.gitignore` excludes it); the ledger references entries by experiment id.

## 6.7 Stopping

The loop stops, in order of precedence:

1. `STOP` file present (`sb stop`; no new pre-registrations), two consecutive integrity violations, two consecutive `gamed` verdicts, a holdout-gap ratio above 0.75, or `sb campaign halt`: **halted**, needs a human (`sb campaign resume`). Not in v1.0: the three-consecutive-harness-errors halt; the constant is reserved and the counter is never incremented.
2. Budget exhausted in any dimension (dollars, hours, experiments) or the iteration cap (200) reached: **budget**; `sb prereg` and `sb distill-stats` halt the campaign with `budget:<dimension>`.
3. Exploration level 3 reached and a further `patience` experiments without acceptance: **converged**; `sb distill-stats` ends the campaign.

"Headroom" for an inactive metric set is estimated from its last campaign's plateau level and the time since; a set that saturated long ago and whose code has since changed is considered to have headroom again. Not in v1.0: the engine does not estimate headroom or switch sets; the distiller and the human decide what the next campaign optimizes.

## 6.8 What the loop does not do

- It does not run many parallel campaigns on the same metric set; contention on measurement destroys the noise floor.
- It does not chase a goal below its noise floor by increasing repeats without bound; if `κσ` cannot be beaten in a plateau, the instrument is the problem, and the distiller says so. The minimum-detectable-effect gate at `campaign start` applies the same rule before the first experiment (`04-anti-overfitting.md` §4.2).
- It does not accept an experimenter's claim that a change "should" help. Only confirmation numbers move the baseline.

## 6.9 Frontier campaigns: when goals trade off

`composition: pareto` (`02-metrics.md` §2.3) discards any candidate that regresses a goal. With two goals that compete, a faster scan that finds less, a smaller model that is less accurate, the loop accepts the few changes that improve one goal for free and then stalls, because every remaining move is a trade. There are three ways to handle a trade-off. The choice is made at gate 1.

| Option | Spec | What the campaign returns | Choose it when |
|---|---|---|---|
| Guardrail with tolerance | one goal; the other metric a guardrail with `acceptance.tolerance_sigma` | one line of strictly better commits, the guardrail held within `τσ` | one goal matters and the other must merely not slip |
| OEC | `composition: oec`, `oec_weights`; the traded metric also a guardrail with a floor | one line of commits screened by the weighted score, each confirmed on a single goal | the exchange rate is known in advance (one point of recall is worth ten seconds) |
| Frontier | `composition: frontier`; optional `preference.weights`, `frontier_max` | a mapped set of non-dominated commits, one branch each, and a preferred point | the exchange rate is unknown, or the person who will decide it is not the one running the loop |

**The rule.** The campaign keeps an archive of non-dominated commits, the members, each on its own branch `sb/<campaign>-f<k>`; `f0` is the base. Each experiment branches from a member the engine picks: fewest attempts, ties to the largest NSGA-II crowding distance, so the extremes are explored first and the frontier is pushed outward before it is filled in. `sb prereg --parent f2` overrides the pick. At screen a guardrail regression discards; a goal regression does not. At confirm the exact paired test runs against the parent member: the candidate must improve at least one goal at `α_look` and break no guardrail, and it may regress the others. Then it is compared with every active member on stored confirm medians: a member that is not worse on any goal beyond `τσ` and better on at least one beyond `κσ` dominates it (`discard dominated:<member>`); otherwise it joins as `f<k>`, retires the members it dominates, and the archive is pruned to `frontier_max` (default 8) by crowding distance, extremes last. `sb/<campaign>` follows the preferred member: the largest weighted sum of normalized gains over the base under `preference.weights`, else the knee, the member whose smallest gain over the base is largest. No ratchet is written. The frontier is the deliverable; a human picks a point at gate 2, or the preference does.

**Two things the rule does not do.** It does not test non-dominance (a margin rule on stored medians, `docs/14` §14.7), and it does not decide the trade for you: without weights `sb/<campaign>` points at the knee, the most balanced active member across the frontier's own extremes, as a suggestion; with `preference.weights` at the weighted best; picking the point is gate 2.

**What carries an error rate.** "Improved a goal versus its parent" is the exact test of `13-statistical-guarantees.md` §13.2 at the campaign's per-test alpha. Non-dominance is a margin rule on medians and claims nothing (§13.7).

**Example: recall against scan time.** A vulnerability scanner has two goals, `recall` on a fixture of planted findings (maximize) and `scan_seconds` (minimize), with `tests_pass` and `false_positives` as guardrails. Nobody knows in advance whether a two-point recall loss is worth halving the scan. The spec:

```json
{"id": "2026-09-03-scan-frontier", "composition": "frontier", "goals": ["recall", "scan_seconds"],
 "guardrails": ["tests_pass", "false_positives"], "frontier_max": 8, "budget": {"experiments": 40}}
```

The first experiments branch from `f0`. A change that halves `scan_seconds` and drops `recall` by two points is accepted as `f1` (`frontier:improved:scan_seconds:traded:recall`); `f0` stays, since neither dominates the other. A later change from `f1` that recovers a point of recall beyond the noise margin at the same scan time joins as `f2` and retires `f1`. A change that is slower than its parent and finds no more is discarded at confirm (`noise`); one that beats its parent but is beaten on both goals by some member is `discard dominated:<member>`. At the end `sb frontier` lists the members with their confirm medians, the report's Frontier table shows who retired whom, and `sb/2026-09-03-scan-frontier` points at `f0` unless a member improved both goals or the spec declared `"preference": {"weights": {"recall": 3, "scan_seconds": 1}}`. The product owner reads the table and merges the branch of the point they want.

**Cost.** Per experiment the same as `pareto`: one screen, one judge, one paired confirmation. The archive adds one branch per member and nothing else; members are never re-measured.
