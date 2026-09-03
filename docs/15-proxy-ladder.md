# 15 · The proxy ladder: iterating when the real instrument takes hours

Status: Implemented in 1.3.0 (2026-09-03). `docs/14` §14.12 has the formulas and `docs/13` §13.9 the guarantee statement. This document is the rationale and the field reference, written from the code in `scripts/sb.py` (`audit_spec`, `run_audit`, `update_trust`, `proxies_claim`, the audit hooks in `cmd_accept` and `cmd_discard`, and the end audit in `cmd_campaign`).

## 15.1 The problem

The loop's acceptance rule needs about ten interleaved pairs at confirmation, plus warm-ups: twenty-two runs of the instrument per promoted candidate. On a benchmark that takes two seconds that is under a minute. On an instrument that takes four hours (a full scan, a training run, a simulation sweep) it is eighty hours per candidate, and the loop is not a loop.

The binding metric for a research loop is iterations per hour. Everything the docs call cost levers (`05-cost-and-speed.md`) assumed the instrument was cheap enough that screening at a smaller size and confirming at full size was the whole ladder. For a four-hour instrument the ladder needs more rungs, and the rung the guarantee attaches to has to move.

## 15.2 The shape: a ladder of validated proxies with an audited top

```
tier 0   component proxy    one pipeline stage replayed from recorded intermediates      seconds to minutes
tier 1   slice proxy        the whole pipeline on a frozen small slice of inputs           minutes
tier 2   the real instrument                                                              hours
```

The loop screens and confirms on the proxies with the exact test, and **audits** on tier 2 on a pre-registered cadence. The real metric's ratchet moves only when an audit returns `confirmed` or `direction`. Everything below the audit is the proxy's word, and the engine measures how good that word is.

This is the ladder perf CI and ML engineering already use (unit → integration → end-to-end; micro-benchmarks → macro; the L0 to L3 ladder in `redswarm-decoded/docs/20`, where "L1 is never quotable as a metric" and "L3 is the only promoter"). The contribution here is making the ladder a first-class object the engine enforces, with the proxy's trust earned from data rather than asserted.

## 15.3 Proxy cards

A metric card may declare that it stands in for another:

```json
{
  "id": "detect_stage_ms",
  "kind": "goal",
  "direction": "minimize",
  "unit": "ms",
  "proxy_for": "full_scan_seconds",
  "trust": "provisional",
  "covers": ["hand/detect/"],
  "targets": ["hand/detect/"],
  "measure": { "command": "python3 bench/replay.py --stage detect --fixture bench/recorded/run-2026-09-03", "parse": "metric-line:detect_stage_ms" },
  "fidelity": { "screen": { "repeats": 2 }, "confirm": { "repeats": 10, "holdout": { "kind": "arg", "values": ["slice-a", "slice-b", "slice-c"] } } },
  "integrity": { "frozen_paths": ["bench/replay.py", "bench/recorded/"] },
  "degradation": { "apply": "python3 - <<'EOF'\np='hand/detect/run.py';s=open(p).read();assert 'def detect(' in s;open(p,'w').write(s.replace('def detect(', 'import time\\ndef detect(',1).replace('    results = []', '    time.sleep(0.05)\\n    results = []',1))\nEOF" },
  "gaming_risks": ["replay fixture could be edited (frozen)", "stage could detect the replay harness and skip work", "recorded intermediates could go stale against the real pipeline"]
}
```

- `proxy_for` names the real metric's card. The real card keeps its own `measure` (the four-hour command) and gains `audit` (§15.5). `sb campaign start` refuses a proxy whose `proxy_for` is not in the campaign's `audits` list.
- `trust` is engine-owned. A proxy listed in a campaign without it is set to `provisional` at `campaign start`. It moves only through audits (§15.5). It is excluded from the card fingerprint, so the engine's own change to it is not read as tampering; `sb card add` accepts the four values `provisional`, `validated`, `suspect`, `demoted` and nothing else.
- `covers` is the scope: repo-relative path patterns (`dir/` prefix, glob, or exact path) the proxy is valid for. A proxy without `covers` is valid for every target. §15.4 says how pre-registration uses it. `targets` keeps its ordinary meaning (the code whose change moves the metric).
- A proxy's screen and confirm levels are ordinary: the exact test, the power gate, warm-ups, holdouts, all apply to the proxy metric.
- A proxy is listed as a **goal**. A guardrail may carry `proxy_for` too (the same wiring check applies), but the engine records fidelity and trust only for goals, because the proxy's claim is read from the confirm comparison of the goals. The real metric is listed once, under the campaign's `audits`, never under goals or guardrails.

## 15.4 Building the proxies: record and replay

The metrologist's job grows one step. For a slow instrument it must produce tiers 0 and 1, and the rule for both is the same: **the proxy runs the project's own code on frozen inputs recorded from one real run.**

1. **One full, profiled run.** The orienteer already runs each command once; this run also records per-stage wall-clock and, where the pipeline allows, the intermediate artifacts between stages: the crawl output, the context bundle, the fuzz corpus, the detector inputs. The engine does not require this run. It does baseline the real card at `campaign start` like any other card in the campaign, so the real instrument runs at start whether or not a recording exists: `k` repeats (`--repeats`, default 5) at every level the card measures, which is `screen` and `confirm` (and `full` when defined), plus one unmeasured warm-up per level for a time-unit card. On a four-hour instrument that is forty hours before the first experiment. Bound it on the card: `"fidelity": {"screen": {"skip": true}, ...}` so only `confirm` is measured, `"warmup": 0` in `measure`, and a small `--repeats`. Or baseline the proxies by hand (`sb baseline --metric <id>`) and start with `--no-baseline`; the audit card then has no baseline, which the engine allows (audits measure both sides fresh) and which only zeroes the ladder-efficiency comparison in the report.
2. **Attribution.** From the profile: which stage owns the time (or the error) the goal measures. This is the ablation step MLE-STAR uses; here it is a profile, not an ablation, because one run of the real thing is all the budget allows.
3. **Component proxies** for the stages that matter: a replay harness that feeds the recorded input of stage N into stage N alone and reports the stage's metric. Frozen: the harness and the recording. `covers` names the stage's paths.
4. **A slice proxy**: the whole pipeline on a frozen small subset of inputs (one target instead of twenty; one epoch instead of fifty; one parameter setting instead of the sweep), with three holdout slices the experimenter never sees. No `covers`: it is valid for every target.
5. **Degradation recipes** for each proxy, as for any card: a known slowdown or a known error must move the proxy the wrong way. The metrics skill probes every goal and demotes a failure to diagnostic before gate 1; the engine itself does not gate `campaign start` on the probe.

What record-and-replay cannot do: a change that alters what an upstream stage produces (a crawler that finds different pages) is invisible to a downstream replay proxy that consumes the old recording. The metrologist records this as a `gaming_risk` and limits the card with `covers`. The engine enforces it at pre-registration, in a campaign with `audits`: the hypothesis `target` (the part before the first `:`) must match the `covers` of at least one goal that has `proxy_for` and is not `demoted`, or some such goal must have no `covers`. Otherwise `sb prereg` refuses with `no confirming proxy covers target`. A goal without `proxy_for` does not count. A hypothesis may not `predict` the real metric; predictions name goals, guardrails, and diagnostics only.

## 15.5 Trust is earned: the audit rule

The real metric's card keeps `kind: goal` (the engine accepts only `goal`, `guardrail`, `diagnostic`) and declares its audit:

```json
{ "id": "full_scan_seconds", "kind": "goal", "direction": "minimize", "unit": "s",
  "measure": { "command": "make scan-full", "parse": "metric-line:full_scan_seconds", "timeout_s": 21600 },
  "fidelity": { "confirm": { "holdout": { "kind": "env", "var": "SB_SEED", "values": [11, 12, 13] } } },
  "audit": { "every_accepts": 3, "discard_sample_rate": 0.1, "pairs": 3, "alpha": 0.05 } }
```

The campaign spec lists it under `audits`. `sb campaign start` refuses an audit card without an `audit` object, and refuses one that is also a goal or guardrail. Every key of `audit` has a default from the constants block: `every_accepts` 3, `discard_sample_rate` 0.10, `pairs` 3, `alpha` 0.05. An audit measures the real card at its `confirm` fidelity (command, timeout, holdout) with `pairs` interleaved pairs, so the card's confirm holdout applies to audits. A time-unit card also gets one unmeasured warm-up run per side per audit unless the card sets `"warmup": 0`; with the default 3 pairs that is eight runs of the real instrument per audit, six with warm-ups off.

The engine runs the real instrument in three situations, each pre-registered:

1. **Accept audit.** At the first accept of the campaign, and then whenever the accepts counted since the last accept audit reach `every_accepts` (with several audit cards, the smallest value). With the default 3 the audits fall at accepts 1, 4, 7, and so on. The current head is measured against the last audited commit, interleaved, `pairs` pairs (the largest value across audit cards), one-sided sign-flip at the card's `alpha`. With 3 pairs the smallest p is 0.125, so the default is a direction check, not a significance test; five pairs or more can reach `confirmed` at 0.05. The audit blocks: `sb accept` returns only after it, and prints one JSON line with the verdicts before its own line. The real metric's ratchet moves only here and at the end audit.
2. **Discard audit.** A pre-registered fraction of proxy discards (`discard_sample_rate`, the largest across audit cards) is re-measured on the real instrument: one pair of the experiment's commit against the experiment's base commit. The sample is deterministic: the first eight hex digits of `sha256("<campaign id>:<experiment id>")` divided by `0xFFFFFFFF` must be below the rate. Only discards with reason `noise` or `regression`, a submitted commit, and integrity passed are eligible, and only while the campaign runs. This is how the proxy's misses are estimated, not just its false promotions. One pair is a sign check: a positive difference is `direction` and counts as a miss, a negative one is `worse`, an exact tie is `no-change`. There is no noise floor on it.
3. **Campaign-end audit.** `sb campaign end` measures the final head versus the base commit, `pairs` pairs, when the head has moved. This is the number the report leads with for the real metric. It updates no proxy's fidelity (no experiment claimed it).

Verdicts, per audit card: `confirmed` (p at or below `alpha` and the median improvement positive), `direction` (every pair improved but p did not reach `alpha`), `worse` (every pair regressed), `no-change` (mixed signs, or no movement), `invalid` (no valid pair). The ratchet and `baseline.json` for the real metric move on `confirmed` or `direction`, only at accept and end audits, and only forward: `best` becomes the audited head median and the entry carries `audited: true` and the verdict.

From the accept and discard audits the engine keeps a **proxy fidelity record** per proxy goal, in `campaign.json` under `proxy_fidelity`:

```
audits             audited changes with a proxy claim (better | not-better, from the confirm comparison's `improved`)
agree              claims the real verdict agreed with: better ↔ confirmed | direction; not-better ↔ worse | no-change
false_promotions   proxy said better, audit said worse or no-change
misses             proxy said not better, audit said confirmed or direction
history            the last 20 outcomes, 1 agree / 0 disagree (an `invalid` audit is a 0, neither a false promotion nor a miss)
exchange_rates     real median improvement / proxy confirm delta, on agreeing `better` claims; the report shows the median
```

Trust transitions are mechanical and pre-declared (constants `TRUST_*`):

```
provisional → validated   audits ≥ 4, agree / audits ≥ 0.75, false_promotions ≤ 1
validated   → suspect     2 or more disagreements in the last 4 audits; or the last audit disagreed, the record holds a false promotion, and audits > 4
suspect     → demoted     the next disagreement
suspect     → validated   the last 4 audits all agreed
```

Every transition writes a `trust` event to the ledger and refreshes the card's fingerprint in `campaign.json`. A demoted proxy no longer counts at pre-registration: a target only it covers can no longer be pre-registered. It is still measured at screen and confirm like any goal, and its confirm verdict still enters the acceptance rule for experiments already open. The campaign halts (`proxy-demoted:<id>:no-confirming-proxy-left`) only when no goal with a trust other than `demoted` remains.

The thresholds are heuristics; `docs/13` §13.9 says what they do and do not give.

## 15.6 Where the guarantee attaches

Honestly:

- The exact test, the α budget, and the family-wise bound (`docs/13` §13.2, §13.3) apply to **the proxy metric**. "Accepted" means the candidate beat its parent on the proxy with the stated error rate.
- The real metric has **audited movement**, not a per-candidate guarantee. Between audits the branch carries proxy-only wins. The audit's own test is exact but low-powered by design (three pairs), so it is a direction check unless the card buys more pairs. The audit's `alpha` is the card's, not split by the campaign's multiplicity rule.
- The report shows two tables for every audited campaign: every audit (kind, commit, against, per-metric `against → head (verdict, p=…)`, pairs, wall seconds) and every proxy's fidelity (trust, audits, agree, false promotions, misses, exchange rate). A campaign whose proxy moved and whose audit did not is reported as such; nothing is averaged across the two.
- The ratchet and the global ratchet record only audited real values. A later campaign inherits the real metric's audited floor, never a proxy value. The proxy goals ratchet as ordinary goals do.

This is the same split `docs/13` §13.8 makes for frontier campaigns: the tested part and the untested part, named.

## 15.7 Iterations per hour becomes a reported metric

`stats()` reports `iterations_per_hour` (experiments per hour of charged wall-clock) and `accepts_per_hour`, plus `audit_wall_s`, `audits_run`, and `proxy_fidelity` (without `history`). The charged wall-clock includes measurement, audits, and whatever `sb cost` reported, so audit hours count against a `budget.hours`. The campaign report prints iterations per hour in its cost section. Not implemented: a per-tier breakdown of runs, wall-clock, and the fraction of candidates that stopped at each tier. The distiller's inheritance body records which proxy paid off (which stage's proxy produced accepted changes that later audited true) so the next campaign starts from that.

A ladder efficiency line makes the trade visible: the real-instrument seconds the campaign spent on audits against the seconds it would have spent confirming every promoted candidate on it (the real card's confirm `secs_per_run` from `baseline.json`, times two sides, times ten pairs, times the promoted count).

## 15.8 A RedSwarm-shaped example

Real instrument: a full scan of the benchmark target set, about four hours, goal `recall` (higher) with guardrail `false_positive_rate` and `scan_seconds`. Ladder:

- tier 0: `detect_replay_recall` on recorded fuzz outputs for the target set (about 90 seconds), `covers: ["hand/detect/"]`; `context_replay_ms` for the context stage, `covers: ["hand/context/"]`.
- tier 1: `slice_recall` on three frozen single-target slices (about 6 minutes), holdout slices never seen by the experimenter, no `covers`.
- tier 2: `recall` under `audits` (audit at the first accept and then every 3, 3 pairs overnight; discard sample 10%; campaign-end audit).

A detector hypothesis is pre-registered with `target: "hand/detect/"`, screened on `detect_replay_recall` in 90 seconds, confirmed on `slice_recall` and `detect_replay_recall` with the exact test in about two hours (ten pairs, both sides, six minutes each), and the first accept triggers a four-hour audit, the fourth the next. The campaign runs about eight candidates per working day instead of one every three days, and the report says which of them the real instrument has confirmed.

## 15.9 What this does not solve

- A proxy is only as good as its recording. Recordings go stale as the pipeline changes; the engine can only detect it through audits, so `every_accepts` should be small early in a campaign.
- Cross-stage effects are invisible to component proxies by construction. The slice proxy sees them; the audit proves them.
- Three audit pairs cannot detect small real effects. Users with an eight-hour night get two pairs. The report says `direction`, never `confirmed`, below five pairs.
- A one-pair discard audit has no noise floor. On a noisy instrument it will register misses that are noise, and the fidelity record will be pessimistic on that side.
- None of this reduces the real instrument's cost; it reduces how often it is paid.

## 15.10 Decisions taken

1. **Cadence and rates.** The real instrument audits at the first accept and then every `every_accepts` accepts (default 3). `discard_sample_rate` defaults to 0.10. `pairs` defaults to 3, a direction check unless the card raises it.
2. **A demoted proxy keeps screening and stops confirming; the campaign halts only when no confirming proxy is left.** As built, "stops confirming" is enforced at pre-registration: a demoted proxy no longer covers any target, so no new experiment can rest on it. It is still measured at confirm for experiments already open. The halt fires when every goal is a demoted proxy.
3. **Audits block.** There is no scheduled audit and no provisional accept state in the ledger. `sb accept` runs the audit and returns after it.
4. **No recorded full run is required at start.** The metrologist may build proxies from an existing recording. The engine still baselines the real card at `campaign start` (unless `--no-baseline`), and that is the only run of the real instrument before the first audit.
5. **Every proxy must pass its degradation probe and the real card must declare `audit`.** The second is an engine check at `campaign start`. The first is the metrics skill's rule (probe every goal, demote failures); the engine does not read `probe` at start.
