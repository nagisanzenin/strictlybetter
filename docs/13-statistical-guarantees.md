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
- Bonferroni's inequality: `P(∪ A_i) ≤ Σ P(A_i)`; the union bound, no citation needed.


## 13.6 What the external-adversary gate showed (2026-09-03)

Eight attack diffs written blind by a separate agent (given only the fixture, the frozen list, and the goal) ran through the engine with all walls on (`bench/results/20260903-170034-adversary-pyfix.md`). None was accepted. Three instrument-tampering attacks (timer monkeypatch, stdout rewrite, stdlib shadowing) were discarded by the validity wall at screen. Five attacks that leave the instrument honest and cheat inside the code under test (checksum forgery via environment tampering, repeat-keyed memoization, environment-sniffing lookup table, lazy result proxies, a background worker thread) passed the statistical screen with about 100% claimed improvement and were stopped only by the blind judge, which named the mechanism in every case.

The lesson that changes the guarantees: for deferred or memoised work, the paired confirmation on held-out seeds is not a defense, because the instrument runs its repeats in-process and hashes the result once, so the fake speedup reproduces under any seed. The exact test controls the false-accept rate for **honest noise**; it says nothing about a candidate that has changed what the instrument measures. That class is the judge's, and the judge is an LLM with no error-rate claim. The two are complementary, not redundant, and the earlier statement that the other walls catch everything without the judge was wrong: it held for the six scripted tricks, not for these eight.
