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

**Walls and toggles.** The engine exposes nine toggles in the campaign's `walls` object, all true by default, so the meta-benchmark can ablate them one at a time (`10-implementation-plan.md` §10.7). The five walls of this document map onto them as follows. Turning one off is recorded in `campaign.json`, in the ledger's `start` event, and in the report.

| Wall | Toggles | What the toggle does when off |
|---|---|---|
| 1 validity, noise floor, confirmation | `validity`, `noise_floor`, `confirm`, `anomaly_breaker` | invalid runs are no longer discarded; κ_eff becomes 0 and any raw improvement counts (the regularizer goes with it), and confirmation falls back to the heuristic rule with no error rate; `promote` becomes `accept-naive` with no confirmation run; the anomaly flag is never raised |
| 1 paired confirmation | `paired` | `sb confirm` compares the candidate against the stored confirm-level baseline instead of a fresh, interleaved measurement of the campaign head; the head worktree is not created and confirmation costs half; there are no pairs, so the exact test is not run and confirmation uses the screen rule with no error-rate claim |
| 2 frozen instrument | `frozen_guard` | `sb submit` records violations but does not fail; the guard hook allows every edit; `sb measure` no longer refuses a failed-integrity experiment |
| 3 holdout | `holdout` | confirm runs without holdout values; no rotation |
| 4 pre-registration | `prereg` | nothing: pre-registration is structural (no worktree without a ledger line) and the toggle exists for symmetry and reporting |
| 5 blind judge | `judge` | a `clean` verdict is written automatically on promote; `sb confirm` no longer requires one |

## 4.2 Wall 1: validity, the noise floor, and the confirmation run

**Validity first.** A number is compared only if the run that produced it was a run: exit code zero, metric parsed, duration within the card's expected band, output not a placeholder or a suspicious constant, manifest recorded. This is cheap and it catches the crudest class outright: an agent that replaced a neural net with a search engine reported `train_time_sec: 0.0` and a 99% win rate (`01-prior-art.md`, casebook). Curie's setup validator (placeholders, hard-coded values) is the same instinct. In the engine, validity is: exit code zero unless the card allows otherwise, no timeout, metric parsed, duration inside the card's `expected_duration_s` band, and an `equal` metric that agrees with itself across repeats. One more check guards the timer itself: for a minimize-direction metric whose `unit` is a time unit, an instrument that claims at least 2× faster (instrument ratio below 0.5) while the process wall-clock the harness measured stayed above 0.9× of the baseline's is invalid, with the note "timer or instrument tampering?". Not in v1.0: a placeholder or constant-output check; the monotonicity probe and the frozen instrument cover most of that ground.

**Noise floor.** At the current best commit, `sb baseline` measures each metric `k` times from a clean throwaway worktree, at every fidelity level the card defines (`k = 5`, fixed; `-k` raises it). Sigma is 1.4826 × the median absolute deviation of the repeats when there are at least four (the sample standard deviation when the MAD is zero) and the sample standard deviation for two or three. The robust estimator exists because timing noise on a shared machine is one-sided bursts, not a bell curve: for the repeats `[468, 489, 471, 758, 1206]` the standard deviation is 319 while the MAD-scaled sigma is 31, and with the former every real win on that metric was being called noise. The card's `noise.method` records which estimator applied (`mad-scaled` or `stdev-of-repeats`). It is stored on the card and in `baseline.json` with the commit and an environment fingerprint. The recommendation for cheap metrics is to raise `k` until the standard error of sigma is below 20% of sigma; not in v1.0: the engine does not do this adaptively. It is re-measured when `sb baseline` is run again, at campaign start for any metric lacking a baseline at the head commit, and (confirm level, goals only) after a holdout rotation. Not in v1.0: automatic re-measurement when the environment fingerprint changes or when a plateau makes the distiller suspect the instrument; the fingerprint is recorded so a human or the distiller can see the change and re-run `sb baseline`.

**Screen: a filter, not a claim.** `sb judge` compares a candidate's screen median against the screen-level baseline with the rule `Δ > κ_eff · σ · √(1/r + 1/k)`, where `r` is the number of screen runs (one; two for timing metrics) and `k` the baseline repeats (five). A candidate that passes is promoted to the blind judge and to confirmation. A candidate that regresses beyond `τ · σ · √(1/r + 1/k)` on any goal or guardrail is discarded; one that is positive but inside the threshold gets a single `retry-screen`. The rule is an effect-size threshold in sigma units, the kind performance CI uses (rustc-perf's triage is the same idea). It carries no error-rate claim. It decides what gets confirmed, never what gets accepted. The same rule decides `full` fidelity inside `sb confirm`, where it can only discard.

**Confirmation is a test with a stated error rate.** `sb confirm` re-measures from a clean checkout of the experiment commit. For each goal and guardrail it measures `r` pre-registered pairs. Each pair is one run of the candidate and one run of the campaign head, interleaved in ABBA order, with the same holdout value on both sides. Let `d_i` be the improvement in pair `i`, signed so that positive is better. The null hypothesis is that the candidate is not better. The statistic is the mean of the `d_i`. The reference distribution is that mean under all `2^r` assignments of signs to the `d_i`: the exact Fisher–Pitman randomization test (`citations.md`; `13-statistical-guarantees.md`). Above 20 pairs the engine draws 20,000 seeded sign assignments instead and marks the result `exact: false`. The one-sided p is the fraction of assignments whose mean is at least the observed mean. A goal counts as improved iff `p ≤ α_look` and the median `d_i` is at least `acceptance.min_effect_rel` × the head's median (default 0, so the practical floor is opt-in). The candidate is accepted when at least one goal is improved and nothing blocks. Guardrails block on their own pairs: the same test with the regression alternative at `α = 0.10` (`ALPHA_GUARDRAIL`, more sensitive than the goal test on purpose), or a median regression beyond `τσ`, blocks; a goal that regresses by the same rule blocks too; a guardrail with `σ = 0` or `τ = 0` blocks on any consistent regression; `equal` guardrails must match exactly. The validity of p rests on three assumptions: under H0 the two members of each pair are exchangeable (this is what the interleaving delivers, since a load burst hits both sides alike); pairs are independent; the holdout values were fixed before measurement. Not assumed: normality, a known or estimated variance, or a symmetric noise distribution. The `confirm` ledger event records every test under `tests.<metric>` with `p`, `alpha`, `n_pairs`, `exact`, `mean_diff`, and `median_diff`; the provenance block in the commit message prints them.

**Paired against a fresh head.** What the candidate is compared against matters as much as its own numbers. The stored baseline was measured when the campaign started or last ratcheted; by the time a candidate is confirmed the machine may be under a different load, thermally throttled, or warmed differently. The bench showed exactly that drift producing a false accept and a no-op accept on a loaded machine. With the `paired` wall on (the default), `sb confirm` checks the campaign head out into a second worktree and, at `full` and `confirm` fidelity, measures head and candidate interleaved: pair by pair, in ABBA order (head then candidate, then candidate then head), with the same holdout value on both sides, so a load burst or a clock change hits both alike. This interleaving is what makes the two members of a pair exchangeable under H0, the assumption the test rests on. `σ` still comes from the `k`-repeat baseline and enters only the guardrail tolerance; the test never uses it. If the head's fresh runs are all invalid there are no pairs: the comparison falls back to the stored baseline and the screen rule, the ledger records `tests.<metric>.kind` as `unpaired-fallback`, and no error rate is claimed. The same fallback applies with the `paired` or `noise_floor` wall off. This is standard performance-CI practice: rustc-perf measures the baseline in the same job as the candidate, and Chromium's Pinpoint runs paired A/B jobs. The confirm ledger event records `paired: true` and the head's summaries as `head_results`; the provenance block prints `paired=yes`. The price is that confirmation takes about twice as long (`05-cost-and-speed.md` §5.2).

**Multiplicity.** `α_campaign` (the campaign's `alpha`, default 0.05, one-sided) is split Bonferroni over the pre-registered experiment budget `K` (`budget.experiments`, default 40): `α_test = α / K`. Because `K` is fixed at campaign start and every confirmation uses `α_test`, the probability of at least one false accept in a campaign whose candidates are all null is at most `α`, whatever the dependence between experiments. `multiplicity: none` uses `α` per test instead, and the report then prints the expected number of false accepts as `α_test × confirmations run`, an upper bound that holds if every candidate were null. A budget without an `experiments` count has no `K`; the engine falls back to `α` per test and the family-wise claim is gone.

**Sample size is fixed before data.** There is no "add repeats until it wins". The number of pairs is the card's `fidelity.confirm.repeats` (default 10), or its `max_repeats` when the anomaly breaker fired or the judge said `suspicious`, both decided before confirmation starts. A card may pre-register a two-stage design `fidelity.confirm.stages: [r1, r2]`. Each look tests all pairs so far at `α_look = 0.59 · α_test`, Pocock's constant for two looks. After look 1 the engine stops for futility when the mean improvement is not positive or `p ≥ 0.5`; otherwise it measures `r2` more pairs and tests once more. The constant is approximate, and in the anti-conservative direction at the engine's small `α_test` (`13-statistical-guarantees.md` §13.3).

**The power gate.** The smallest p the exact test can produce is `2^-r`. `sb campaign start` refuses a goal whose `r` (the sum of the stages, if any) cannot reach `α_look`, halts with `underpowered:<metric>:pairs=r:alpha=…`, and prints the minimum `r = ⌈−log2 α_look⌉`. Example: `α` 0.05 and `K` 30 give `α_test` 0.00167 and need `r ≥ 10`; the default `K` 40 gives 0.00125 and also needs 10, which is why `CONFIRM_REPEATS` defaults to 10. A two-stage card at the defaults needs 11 pairs in total, and its first look can only stop for futility or regression, because `2^-r1` reaches `α_look` only from `r1 ≥ 11`. `--allow-underpowered` starts anyway; nothing can then be accepted on that goal. The gate runs only when the `paired` and `noise_floor` walls are on.

**What is still heuristic.** Sigma (1.4826 × MAD of the five baseline repeats) is used for the screen filter, for the guardrail tolerance `τσ`, and for the **minimum detectable effect** computed at campaign start, `κ · σ · √(1/r + 1/k) / |median|` with `r` the confirm repeats and `k` the baseline repeats, stored in `campaign.json` under `mde` and halting with `instrument-unusable:<metric>:mde=…` above 50% (`--allow-unusable` overrides; the message says to raise repeats or reduce machine load). This is the "the instrument is the problem" rule of `06-search.md` §6.8 made concrete before any experiment is spent. None of these carries an error-rate claim. The anomaly breaker (§4.6) and the false-promotion budget (`05-cost-and-speed.md` §5.8) are monitors, not tests. The κ_eff complexity regularizer acts at screen and full only. With `composition: oec` the weighted score decides screen and full; confirmation applies the per-goal test unchanged.

**The Ladder and the reusable holdout.** Blum and Hardt's Ladder (a leaderboard that publishes a new best only when it beats the old one by a step size, `citations.md` §1) and Dwork et al.'s reusable holdout (a holdout answered through a noisy threshold under a query budget, `citations.md` §2) are the ideas that motivated the ratchet in `baseline.json` and the redaction of discarded candidates' confirm numbers (§4.4). Their theorems do not apply here. The Ladder assumes a fixed finite holdout and a data-independent step size; the engine measures a fresh head each time and its screen step is `κσ` from a measured sigma. Thresholdout assumes a query budget with added Laplace noise; the engine adds none. No guarantee is claimed from either. The guarantee this design claims is the one in `13-statistical-guarantees.md`: an exact per-confirmation test and a family-wise bound over the pre-registered budget.

## 4.3 Wall 2: the frozen instrument

The experimenter cannot change what is measured or how, and the boundary is enforced by the harness and the platform's tool hooks, not by prompt text. In a March 2026 comparison of autoresearch skills, file protection was prompt-only in every mainstream one; an agent asked to speed up a Python sort compiled a C radix sort and loaded it through `ctypes` (`01-prior-art.md`, casebook). BAITBENCH measured validity prompting reducing shortcut-taking by six points. Prompts are advice; hooks are walls.

- **Frozen paths** listed on each card (tests, benches, fixtures, eval scripts, reference outputs), plus the campaign's own `frozen_paths`, are hashed at campaign start from a clean checkout (`eval_hash` in `campaign.json`). During a campaign the guard hook (`sb guard`, exit 2) denies any write to them at the tool boundary, and denies writes to protected paths, to the state home, and to anything outside an experiment worktree; at `sb submit` the diff is checked again for platforms without such hooks. A diff touching a frozen path, a protected path, or `.strictlybetter/`, one that changes the eval hash, or one that touches a dependency manifest under any operator but `dependency`, fails the submit and the experiment can only be discarded; two consecutive violations halt the campaign, and a clean submit resets the counter. `sb measure` refuses an experiment that failed integrity.
- **Measurement runs outside the experimenter's process** from a clean checkout of the experiment commit in a separate worktree, with the card's pinned environment. The experimenter's shell state, caches, and uncommitted files are not part of the measurement.
- **Timers, counters, and parsers** belong to the harness, not to the code under test. If a metric's command lives inside the repo (a `make bench`), the script is a frozen path.
- **Metric definitions** (`.strictlybetter/metrics/`) are outside the experimenter's write set: the guard denies the whole state home except `inbox/` and `tmp/`, and `sb card add` refuses to change a goal or guardrail card while a campaign runs.

Instrument changes are legitimate in an *instrument campaign* (`07-universality.md` §7.3), where the roles invert and the implementation is frozen instead.

## 4.4 Wall 3: the holdout

The experimenter tunes against what it can see. Confirmation therefore uses what it cannot:

- **Seeds** it never saw (ML training, simulations, randomized tests): holdout kind `env`, the value goes into an environment variable per repeat.
- **Input slices** it never saw (a benchmark fixture set split into dev and confirm; a held-out test split; a second dataset): holdout kind `arg`, the value is substituted into the confirm command; or a confirm-only card (`skip` at screen and full).
- **Hidden tests** kept outside the worktree: holdout kind `dir`, a directory under `.strictlybetter/holdout/` that the harness copies into the clean checkout at confirm only (copy-in, not a mount).

Two disciplines keep the holdout useful over many experiments:

1. **Limited leakage.** Confirmation reports `accepted` or `discarded` and the confirmation numbers of *accepted* candidates only. Discarded candidates' holdout numbers stay in the ledger file for audit, but the human- and agent-facing view redacts them: `sb ledger view <id>` replaces a discarded candidate's confirm `results`, `comparisons`, and `confirm_effect` with a redaction marker, and `sb next` and `sb status` never print them; `sb ledger view --unredacted` is the audit path. This is the reusable-holdout idea (Dwork et al. 2015) in its crude, practical form: the experimenter learns about the holdout only through the ratchet, which moves rarely.
2. **Rotation.** After 10 acceptances, `sb accept` regenerates the holdout values of every `env` and `arg` kind card (fresh random values, stored as `holdout_override` in `campaign.json`) and re-baselines the confirm level of the goals on them. A loop that ran for weeks against one holdout has, in effect, seen it. Not in v1.0: rotating a `dir` holdout; swap the directory by hand and re-run `sb baseline`.
3. **The gap is a signal.** The harness tracks, per accepted change and as a campaign trend, the difference between the screen (visible) improvement and the confirm (holdout) improvement, as the ratio `(screen − confirm) / screen` on the primary goal. A growing gap is the signature of overfitting; SpecBench measured it growing with code size, and the tennis post-mortem saw it open exactly when gaming began. When the mean ratio over the last five accepted changes (at least three) exceeds 0.75, `sb accept` halts the campaign for review rather than continuing.

## 4.5 Wall 4: pre-registration

Every experiment has a ledger line with operator, target, hypothesis, and predicted effect *before a diff exists*: `sb prereg` writes the line, then creates the worktree, and there is no other way to get one. Consequences:

- A change that helps a metric it did not predict is still accepted if it passes, but the ledger records the surprise, and the distiller treats unpredicted wins as lower-confidence knowledge (more likely to be noise or gaming).
- Post-hoc metric switching within an experiment is impossible; the metric set is frozen at campaign start.
- The predicted effect is data for the bandit: an operator class whose predictions are systematically wrong gets its variance raised. Not in v1.0: the bandit updates on accept and discard only; predictions are recorded for the distiller to read.

Pre-registration is the reproducibility movement's answer to the garden of forking paths (Gelman and Loken; Nosek et al. 2018). It costs the loop nothing and it is the single highest-leverage habit the agent can have.

## 4.6 Wall 5: the blind judge and the complexity regularizer

**Blind judge.** For every promoted candidate, a separate agent receives the diff, the pre-registration, the numbers, and each affected metric card's `gaming_risks` list. It receives nothing else: not the experimenter's reasoning, not the conversation, not the campaign chat. It returns fixed JSON:

```json
{"verdict":"clean|suspicious|gamed","pattern":"<from checklist or free text>","evidence":"<lines>","recommended_check":"<a cheap extra measurement>"}
```

`sb judge-verdict <id> --file` stores it and rejects any other key, so reasoning cannot be smuggled in by schema.

The checklist grows from experience (`08-memory-and-inheritance.md` §8.3). Seed entries:

- test deleted, skipped, marked xfail, or its assertion weakened
- input-specific branch (`if name == "parse_large"`) or fixture-shaped shortcut
- caching keyed on something only the benchmark supplies
- measurement narrowed (fewer iterations, smaller fixture, warm-up counted)
- output hard-coded, table-lookup on eval inputs
- environment tampering (thread count, GC flags, `PYTHONHASHSEED`) outside the declared operator
- timer, counter, or parser touched
- nondeterminism introduced that widens variance in the favorable direction
- the learning or computing component replaced by something that does not learn or compute (a search engine in place of the net; a lookup in place of the algorithm)
- implausibly short work (zero-second training, a benchmark that finishes before warm-up)
- a native or foreign-language extension loaded (`ctypes`, a compiled module, a subprocess to another toolchain) outside the declared operator
- logs or receipts written by the diff itself rather than by the harness

**Curve-shape anomaly breaker.** Honest optimization decelerates; gaming accelerates after a plateau. A promoted candidate whose screen effect exceeds three times the rolling mean of the campaign's confirmed effects, arriving after half a `patience` of discards, is flagged `anomaly` by `sb judge`; `sb confirm` then runs the confirmation at the card's `max_repeats` regardless of the verdict. This is the rule the tennis post-mortem derived after watching +14 bps per honest iteration become +212 bps in one gamed step.

`suspicious` is not an automatic discard: the engine raises the confirmation to `max_repeats`, and the `recommended_check` (usually a fresh fixture or a different seed set) is for the orchestrator or the human to run; the engine does not execute it. `gamed` makes `sb confirm` refuse the candidate, and two consecutive `gamed` verdicts halt the campaign (`09-governance.md`).

The blind design is borrowed from engram's assessor and effortmining's grader: the judge that cannot see the argument cannot be persuaded by it.

**Complexity regularizer.** Larger diffs must clear a higher threshold:

```
κ_eff = κ × (1 + λ·ln(1 + diff_lines/50)) + 1.0 × new_deps     λ = 0.3
```

where `diff_lines` is the added plus removed lines of the submitted diff and `new_deps` the number of dependency manifests it touched (one extra sigma each; only the `dependency` operator may touch one at all). The regularizer targets extremal Goodhart: sweeping changes are where "make the metric better by making the program do less" hides, and they are also where review is hardest. Small diffs with clear mechanisms are the loop's native step.

## 4.7 The regression wall

Regression is prevented by construction, not by review:

- Every goal and guardrail is measured on every candidate at every fidelity level; a candidate that improves the goal and breaks a guardrail is discarded with `regression:<metric>`.
- The **global ratchet** (`02-metrics.md` §2.5) carries every past goal forward as a guardrail, so a later campaign cannot regress an earlier one.
- Hygiene guardrails (build, tests, lint) are always present, whether the user listed them or not.
- **Drift check.** At each re-baseline the harness re-measures the whole ratchet at the campaign head. If a ratcheted metric has drifted below its floor beyond tolerance without any accepted change touching it, the environment changed and the loop halts with `baseline-drift`. Long-horizon drift over the ledger's time series is checked with a change-point test (the E-divisive method MongoDB uses for performance CI is the reference). Not in v1.0: neither check is in the engine. What v1.0 does: `sb campaign start` halts when a goal or guardrail has no valid baseline at the head commit, and `sb baseline` can be re-run by hand at any time to see a drifted value.

## 4.8 What still gets through, and what catches it later

No wall is complete. The engram release protocol's lesson, that every gate misses its own bug class, applies here. What each wall does not catch:

- Wall 1 misses systematic bias that repeats identically (a cache warm on every run). Wall 2 and 3 catch it.
- Wall 2 misses gaming that lives entirely in the implementation (special-casing). Wall 3 and 5 catch it.
- Wall 3 misses a holdout that is too similar to the dev set. Rotation and the human at Gate 2 catch it.
- Wall 4 catches nothing by itself; it makes the others' evidence legible.
- Wall 5 is an LLM judgment and will miss novel patterns. The checklist grows; the ledger makes the miss auditable.

The last defense is the human at Gate 2 reading a report designed to make these misses visible: diff sizes, targets, judge flags, and reproduction commands.
