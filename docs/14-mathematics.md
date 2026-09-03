# 14 · The mathematics, in one place

Every quantity the engine computes, as a formula, with the constant it uses and the function in `scripts/sb.py` that computes it. Where a rule carries an error-rate claim it says so; where it is a heuristic it says so. `docs/13` states the guarantees; this document states the arithmetic.

Notation. A metric card has direction `s ∈ {+1, −1}` (+1 maximize, −1 minimize) or `equal`. A measurement is a run's parsed value `v`. "Better" always means `s·v` larger. Constants are fixed before data (`sb.py` constants block).

## 14.1 Baseline and noise floor (`cmd_baseline`, `sigma_of`)

For each card and fidelity level, `k` repeats at the campaign head from a clean worktree (`k = BASELINE_REPEATS = 5`; `-k` raises it). With values `v₁…v_k`:

```
median  m = median(v)
sigma   σ = 1.4826 · median(|vᵢ − m|)      if k ≥ 4      (MAD_MIN_N = 4, MAD_SCALE = 1.4826)
        σ = sample stdev(v)                if k ∈ {2, 3}
        σ = undefined                      if k < 2  → the card cannot be a goal or guardrail
```

Timing metrics (unit in ms/s/us/ns/min) get one unmeasured warm-up run per level and at least two recorded screen runs (`fidelity_spec`). `σ` carries no distributional claim; it is a robust scale estimate used by the screen filter, the guardrail tolerance, and the detectability gate.

## 14.2 Screen filter (`compare_metric`, `decide`): a filter, no error rate

Candidate screen median `m'` from `r` runs versus the stored screen baseline `m` from `k` runs:

```
Δ         = s · (m' − m)
se        = √(1/r + 1/k)                                          (se_factor)
κ_eff     = κ · (1 + λ · ln(1 + L / 50)) + 1.0 · D                (kappa_eff)
            κ = 2.5, λ = 0.3, L = diff lines, D = dependency manifests touched
promote   ⇔ Δ > κ_eff · σ · se                  (goal)
regressed ⇔ Δ < −τ · σ · se                     (goal or guardrail; τ = TOLERANCE_SIGMA = 1.0 by default; τ = 0 makes any drop a regression)
equal     ⇔ canonical strings match exactly     (equal-direction metrics; per holdout value)
```

A screen verdict of `inconclusive` (0 < Δ ≤ threshold) is retried once, then discarded. In frontier campaigns goal regressions do not discard at screen. Validity precedes all of this (§14.8).

## 14.3 Minimum detectable effect gate (`campaign_start`): a sanity gate, no error rate

For each goal with confirm repeats `r` and baseline `(m, σ, k)`:

```
MDE = κ · σ · √(1/r + 1/k) / |m|          refuse the campaign if MDE > MAX_MDE = 0.5
```

## 14.4 Confirmation: the exact test (`paired_randomization_test`, `confirm_decision`)

`r` pre-registered pairs, each pair = one candidate run and one head run measured interleaved (ABBA order across pairs) with the same holdout value. Pairs align by index; a pair with an invalid member is dropped (`paired_diffs`).

```
dᵢ  = s · (cᵢ − hᵢ)                       improvement in pair i, i = 1…r
T   = (1/r) Σ dᵢ                          statistic: mean paired improvement
H₀: the candidate is not better; under H₀ the sign of each dᵢ is exchangeable.
Reference distribution: all 2^r sign assignments ε ∈ {−1,+1}^r, T_ε = (1/r) Σ εᵢ dᵢ.
p  = #{ε : T_ε ≥ T} / 2^r                 one-sided, exact, for r ≤ PERM_EXACT_MAX_PAIRS = 20
p  = (#{Monte Carlo draws with T_ε ≥ T} + 1) / (N + 1),  N = PERM_MC_SAMPLES = 20000, fixed seed, for r > 20
min attainable p = 2^−r
```

Alpha accounting:

```
α_campaign = α = 0.05 (campaign `alpha`)
α_test     = α / K        K = pre-registered experiment budget (`budget.experiments`, else `iteration_cap` = 200)   [multiplicity: bonferroni]
           = α            [multiplicity: none]
α_look     = α_test / 2   for a two-stage card (`stages: [r₁, r₂]`, TWO_LOOK_SPLIT = 0.5); α_test for a single stage
α_goal     = α_look / G   G = number of non-equal goals tested in this confirmation (pareto and frontier); α_look for OEC
```

Decision per goal: `improved ⇔ p ≤ α_goal and median(d) ≥ min_effect_rel · |head median|` (`acceptance.min_effect_rel`, default 0). A confirmation is refused when the campaign's confirmations already number `K` (`alpha-budget-exhausted`). Campaign start refuses a goal whose `r` cannot reach `α_goal`: `2^−r > α_goal` (`underpowered`; the message prints `r_min = ⌈−log₂ α_goal⌉`).

Family-wise claim (docs/13 §13.3): with `K` fixed before data and every confirmation at `α_test` split across its goals, `P(at least one false accept in a campaign of null candidates) ≤ α`.

## 14.5 Guardrails at confirmation

Numeric guardrail with paired regressions `gᵢ = −dᵢ` (regression positive):

```
p_reg = one-sided sign-flip p for "regression"     (alternative = "less" on dᵢ)
blocks ⇔ (p_reg ≤ ALPHA_GUARDRAIL = 0.10 and median(d) < 0)  or  (τ·σ > 0 and −median(d) > τ·σ)
          or (τ = 0 and every dᵢ ≤ 0 and some dᵢ < 0)
```

Equal-direction guardrails must match exactly per holdout value. A goal that regresses significantly is treated as a guardrail failure in pareto campaigns and as a trade in frontier campaigns (§14.7). No non-inferiority proof is claimed; the rule is an alarm plus a margin.

## 14.6 OEC composition (`confirm_decision`)

With weights `w_g` (`oec_weights`, default 1) and head median `m_g` per goal:

```
uᵢ = Σ_g w_g · dᵢ,g / |m_g|          composite relative improvement per pair
```

One sign-flip test on `u` at `α_look`. The guardrail rule of §14.5 still applies to every goal and guardrail.

## 14.7 Frontier composition (`dominates`, `crowding_distances`, `frontier_pick_parent`, `frontier_preferred`)

Members `M` with stored confirm medians `v_M(g)`; candidate `C` with confirm medians `v_C(g)`; `σ_g` the goal's stored sigma.

```
A dominates B ⇔ ∀g: s_g·v_A(g) ≥ s_g·v_B(g) − τ·σ_g   and   ∃g: s_g·v_A(g) > s_g·v_B(g) + κ·σ_g     (heuristic margins, no error rate)
accept C     ⇔ C improved ≥ 1 goal vs its parent (§14.4, exact) and no guardrail blocks and no active member dominates C
retire M     ⇔ C dominates M
```

Crowding distance (Deb et al. 2002), goals normalized by their active range; extremes get ∞; pruning removes the smallest until the archive size ≤ `frontier_max = 8`:

```
cd(M) = Σ_g ( s_g·v_{next}(g) − s_g·v_{prev}(g) ) / ( max_g − min_g )      over members sorted by goal g
```

Parent for the next experiment: fewest attempts, ties to largest `cd`. Preferred point, with `pos(M, g) = (s_g·v_M(g) − min_g) / (max_g − min_g) ∈ [0, 1]` over active members:

```
weights given:  argmax_M Σ_g w_g · pos(M, g)
no weights:     argmax_M ( min_g pos(M, g), Σ_g pos(M, g) )        the knee: most balanced, then best overall
```

## 14.8 Validity (`measure_once`, `timer_divergence`): a filter, no error rate

A run is invalid if: non-zero exit (unless allowed), timeout, metric not parsed, more than one `METRIC name=` line for the metric, duration outside `expected_duration_s`, or an equal-direction metric disagreeing with itself across repeats. For a time-unit goal that screens as improved:

```
saved_instr = (m − m') · unit_seconds          wall_base = mean process seconds per baseline run
saved_wall  = wall_base − wall_new
invalid ⇔ saved_instr ≥ 0.10 · wall_base  and  saved_wall < 0.25 · saved_instr      (WALL_DIVERGENCE_MIN_SHARE, WALL_DIVERGENCE_MIN_FRACTION)
```

## 14.9 Monitors (no error rate)

```
false-promotion rate  = promoted-then-discarded / promoted, over the last FP_WINDOW = 10 promotions; > FP_MAX_FRACTION = 0.4 doubles screen repeats (≤ 4×)
holdout gap           = (effect_screen − effect_confirm) / effect_screen per accept; mean over the last 5 > GAP_HALT_RATIO = 0.75 (with ≥ GAP_MIN_N = 3) halts
anomaly               = screen effect > ANOMALY_MULT = 3 × mean confirmed effect, after ≥ patience/2 discards → confirm at max_repeats
holdout rotation      every HOLDOUT_ROTATE_AFTER = 10 accepts (env/arg holdouts): fresh seeds, confirm level re-baselined
bandit                Thompson sampling on Beta(α_op, β_op) per operator class, α/β incremented by accept/discard from archetype priors
plateau               patience = 8 discards raises exploration level (max 3); level 3 at patience ⇒ converged
```

## 14.10 What the benchmark computes (`bench/run_bench.py`, `bench/run_adversary.py`)

External re-validation of an accepted commit: 6 interleaved rounds of (parent, commit, commit, parent) process wall-clock with the pristine instrument on fresh seeds; paired deltas per round; genuine ⇔ sign-flip p ≤ 0.05 (one-sided) and outputs match the parent on every fresh seed and pristine tests pass. Power study: per cell `n` seeds; acceptance rate with the Wilson 95% interval

```
p̂ = a/n,  z = 1.96:   centre = (p̂ + z²/2n) / (1 + z²/n),   half-width = z·√(p̂(1−p̂)/n + z²/4n²) / (1 + z²/n)
```

## 14.11 What is not computed

No confidence interval on effect sizes (medians and p-values only); no sequential always-valid p (stages are fixed in advance instead); no correction across campaigns; no test on diagnostics; no error rate for the screen, the judge, the anomaly breaker, or non-dominance.
