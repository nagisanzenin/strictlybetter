# 13 · Statistical guarantees: what the acceptance test proves

This is the formal statement behind `04-anti-overfitting.md` §4.2. It claims exactly what the engine does and no more.

## 13.1 Definitions

- **Pair.** One run of the candidate and one run of the campaign head, measured back to back in ABBA order with the same holdout value on both sides. `r` pairs are pre-registered on the card (`fidelity.confirm.repeats`, default 10).
- **Paired improvement.** `d_i = s · (m(candidate_i) − m(head_i))`, with `s = +1` for maximize and `−1` for minimize, so positive is better.
- **H0.** The candidate is not better: for every pair, the two runs are exchangeable, so `d_i` and `−d_i` are equally likely.
- **Statistic.** `T = mean(d_1, …, d_r)`.
- **p.** The fraction of the `2^r` sign assignments `(±d_1, …, ±d_r)` whose mean is at least the observed `T`. Above 20 pairs the engine draws 20,000 seeded assignments and reports `(count + 1) / (20,001)`, marked `exact: false`.
- **α_test.** `α / K`, with `α` the campaign's `alpha` (default 0.05) and `K` its `budget.experiments` (default 40), under `multiplicity: bonferroni`. `α_look = α_test`, or `0.59 · α_test` per look for a two-stage card.
- **Accept.** For some goal, `p ≤ α_look` and `median(d) ≥ min_effect_rel · |head median|`, and no guardrail or goal blocks.

## 13.2 Exactness

**Statement.** If, under H0, the two members of every pair are exchangeable and pairs are independent, then for every `α` in (0, 1), `P(p ≤ α | H0) ≤ α`. The test is exact: the level holds for any noise distribution, for any `r`, with no variance estimate.

**Why.** Under H0 the `2^r` sign assignments of the observed `|d_i|` are equally likely, so the observed `T` is a uniform draw from the set of assignment means. The fraction at or above it is then a valid p-value by construction. This is Fisher's randomization argument (Fisher 1935, ch. III) made general by Pitman (1937); Ernst (2004) is the modern statement, with the Monte Carlo case.

**Attainable p.** The smallest p is `2^-r`, reached only when every `d_i` is positive. `sb campaign start` refuses a goal whose `r` cannot reach `α_look` (`underpowered:` halt) because such a goal could never accept anything. The lattice of attainable p-values also makes the test conservative: the true size is at most `α_look`, usually below it.

## 13.3 The family-wise bound

**Statement.** Fix `K` at campaign start and run every confirmation at `α_test = α / K`. In a campaign whose candidates are all null, the probability of at least one false accept is at most `K · α_test = α`, whatever the dependence between experiments (Bonferroni's inequality). `stats()` reports `alpha_campaign`, `alpha_test`, `multiplicity`, `confirmations_run`, and `expected_false_accepts_upper = alpha_test × confirmations_run`, the expected number of false accepts if every confirmed candidate were null.

**The two-stage design.** A card with `stages: [r1, r2]` tests all pairs so far at each look at `0.59 · α_test`, and stops after look 1 for futility when the mean improvement is not positive or `p ≥ 0.5`. The constant 0.59 is Pocock's two-look nominal level at overall α 0.05 (0.0294 / 0.05; Pocock 1977, Table 1). At the much smaller `α_test` the exact two-look constant is nearer 0.53 to 0.56 (at overall 0.01 Pocock's table gives 0.0056), and the sign-flip statistic is discrete rather than normal. A two-stage card can therefore exceed `α_test` by roughly a tenth, offset in part by the test's conservatism and the futility stop. The bound of this section is exact for single-stage cards and approximate for two-stage cards.

## 13.4 What breaks the guarantee

- **Changing `K` mid-campaign.** `α_test` is recomputed from `budget.experiments` at every confirmation. Editing the budget after the first confirmation changes the level of tests already run. A budget without an `experiments` count has no `K`; `α_test` then equals `α` and no family-wise claim holds.
- **More than one confirmation per experiment.** The budget counts experiments, and an experiment that is resubmitted after a discarded confirmation can be confirmed again. Every `sb confirm` is one test; the bound assumes at most `K` of them.
- **Adding pairs after seeing p.** `r` is fixed before the data. A second look is valid only when it was pre-registered as `stages` and spends its share of `α_test`.
- **Non-interleaved measurement.** Exchangeability within a pair is delivered by the ABBA order under the same load. Measuring all candidate runs and then all head runs breaks it. With the `paired` wall off, or when the head's fresh runs are invalid, the engine falls back to the screen heuristic and claims nothing.
- **Misaligned pairs.** Pairs are formed by position among the valid runs on each side. An invalid run on one side only shifts the pairing of the later runs, and the holdout values no longer match within those pairs.
- **Holdout leakage.** A candidate tuned to the confirm holdout is not null on it. The redaction of discarded candidates' confirm numbers and the rotation after 10 acceptances limit leakage; they do not bound it.

## 13.5 The walls that carry no error rate

| Wall | What it is | Its claim |
|---|---|---|
| Screen filter | `Δ > κ_eff · σ · √(1/r + 1/k)` on one or two runs against a 5-repeat baseline | Decides what gets confirmed. None. |
| Blind judge | An LLM reading the diff against a checklist | Catches named gaming patterns. None. |
| Anomaly breaker and false-promotion budget | Monitors on the campaign's trend of effects and promotions | Raise repeats or distrust the screen. None. |

Sigma (1.4826 × MAD of five repeats) enters only the screen filter, the minimum-detectable-effect gate, and the guardrail tolerance `τσ`. The confirmation test never uses it.

## 13.6 What the benchmark measures and what it cannot

`bench/run_bench.py` runs the real engine on one laptop against the `pyfix` fixture with planted effects: scripted wins, no-ops, and gaming tricks. Every accepted commit is re-validated on fresh seeds with the pristine instrument and an external process timer, using the same sign-flip test on 6 interleaved pairs at one-sided 0.05, plus output and test checks. Each cell has a small `n`, so rates come with Wilson intervals, not point claims. It measures whether the walls catch the planted tricks on that machine under that load. It says nothing yet about real repositories, real agents' hypotheses, or other hosts.

## References

- Fisher, R. A. (1935). *The Design of Experiments*. Oliver and Boyd, Edinburgh. Verified 2026-09-03.
- Pitman, E. J. G. (1937). Significance tests which may be applied to samples from any populations. *Supplement to the Journal of the Royal Statistical Society*, 4(1), 119–130. https://doi.org/10.2307/2984124. Verified 2026-09-03 (DOI, volume, pages).
- Ernst, M. D. (2004). Permutation methods: a basis for exact inference. *Statistical Science*, 19(4), 676–685. https://doi.org/10.1214/088342304000000396. Verified 2026-09-03.
- Pocock, S. J. (1977). Group sequential methods in the design and analysis of clinical trials. *Biometrika*, 64(2), 191–199. https://doi.org/10.1093/biomet/64.2.191. Verified 2026-09-03.
- Deb, K., Pratap, A., Agarwal, S., and Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. *IEEE Transactions on Evolutionary Computation*, 6(2), 182–197. https://doi.org/10.1109/4235.996017. DOI resolution verified 2026-09-03 (IEEE document 996017); page details not re-checked. Cited for the crowding-distance heuristic of §13.7 only.
- Bonferroni's inequality: `P(∪ A_i) ≤ Σ P(A_i)`; the union bound, no citation needed.


## 13.6 What the external-adversary gate showed (2026-09-03)

Eight attack diffs written blind by a separate agent (given only the fixture, the frozen list, and the goal) ran through the engine with all walls on (`bench/results/20260903-170034-adversary-pyfix.md`). None was accepted. Three instrument-tampering attacks (timer monkeypatch, stdout rewrite, stdlib shadowing) were discarded by the validity wall at screen. Five attacks that leave the instrument honest and cheat inside the code under test (checksum forgery via environment tampering, repeat-keyed memoization, environment-sniffing lookup table, lazy result proxies, a background worker thread) passed the statistical screen with about 100% claimed improvement and were stopped only by the blind judge, which named the mechanism in every case.

The lesson that changes the guarantees: for deferred or memoised work, the paired confirmation on held-out seeds is not a defense, because the instrument runs its repeats in-process and hashes the result once, so the fake speedup reproduces under any seed. The exact test controls the false-accept rate for **honest noise**; it says nothing about a candidate that has changed what the instrument measures. That class is the judge's, and the judge is an LLM with no error-rate claim. The two are complementary, not redundant, and the earlier statement that the other walls catch everything without the judge was wrong: it held for the six scripted tricks, not for these eight.

## 13.7 Frontier campaigns: which parts of the rule carry an error rate

A campaign with `composition: frontier` (`02-metrics.md` §2.3, `06-search.md` §6.9) keeps an archive of non-dominated commits instead of one line of strictly better ones. Its acceptance rule has two parts, and only one of them is a test.

**The tested part.** Every member other than `f0` was confirmed against its parent member with the test of §13.2: `r` interleaved (candidate, parent) pairs, the exact sign-flip p at `α_look` on at least one goal, the practical floor held, and no guardrail regressing at 0.10 or beyond `τσ`. The bound of §13.3 applies as written: with `K` confirmations at `α_test = α / K`, the probability that some member was accepted on a null improvement over its parent is at most `α`, under the assumptions of §13.2 and with the breakers of §13.4. Two remarks. The bound counts confirmations, and a frontier confirmation tests every goal; a candidate that is null on all `G` goals is accepted with probability up to `G · α_look`, the same looseness a pareto campaign with several goals has. And the claim is relative to the parent only: a member three steps from the base has three tested links behind it, not a tested claim against `f0`.

**The untested part.** Whether a candidate is dominated, and which members it retires, is decided by `dominates()` on stored confirm medians: the candidate's medians from its own confirmation, each member's medians from theirs, measured at different times against different parents and never re-measured. The margins `τσ` (not worse) and `κσ` (better) use the stored confirm-level sigma. This is the screen heuristic of §13.5 applied between members. It carries no error rate. A member retired by `f<k>` was not shown worse than `f<k>` by any test, and a member kept as non-dominated was not shown different from its neighbours. The archive is a map drawn from confirmation medians, not a set of pairwise claims. Pruning by NSGA-II crowding distance (Deb et al. 2002) is a coverage heuristic and claims nothing.

**The preferred point.** `sb/<campaign>` points at the member chosen by `frontier_preferred()`: under `preference.weights`, the largest `Σ_g w_g · s_g · (m_g(member) − m_g(f0)) / |m_g(f0)|`; without weights, the member maximizing the minimum of those normalized gains, the knee. Both are decision aids for the human at gate 2, computed from the same stored medians. Neither is a claim: the preferred member has not been tested against any other member, only against its parent. Without weights the base scores zero on every goal, so `f0` stays preferred until some member improves every goal over it; that is the rule working as written, not evidence that no trade is worth taking.

**No ratchet.** A frontier campaign writes neither `ratchet.json` nor `baseline.json`. Nothing it accepts becomes a floor for a later campaign, and the campaign claims nothing about the project's global frontier of `02-metrics.md` §2.5. What it delivers is the archive, the branches, and the report's Frontier table, with the exact test behind each link recorded in the ledger's `confirm` events.
