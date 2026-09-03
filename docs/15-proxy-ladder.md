# 15 · The proxy ladder: iterating when the real instrument takes hours

Status: design for review (2026-09-03). Nothing in this document is implemented. Where it names a field or a command, that is the proposed name. When it is built, `docs/14` gets the formulas and `docs/13` gets the guarantee statement; this document then becomes the rationale.

## 15.1 The problem

The loop's acceptance rule needs about ten interleaved pairs at confirmation, plus warm-ups: twenty-two runs of the instrument per promoted candidate. On a benchmark that takes two seconds that is under a minute. On an instrument that takes four hours (a full scan, a training run, a simulation sweep) it is eighty hours per candidate, and the loop is not a loop.

The binding metric for a research loop is iterations per hour. Everything the docs call cost levers (`05-cost-and-speed.md`) assumed the instrument was cheap enough that screening at a smaller size and confirming at full size was the whole ladder. For a four-hour instrument the ladder needs more rungs, and the rung the guarantee attaches to has to move.

## 15.2 The shape: a ladder of validated proxies with an audited top

```
tier 0   component proxy    one pipeline stage replayed from recorded intermediates      seconds to minutes
tier 1   slice proxy        the whole pipeline on a frozen small slice of inputs           minutes
tier 2   the real instrument                                                              hours
```

The loop screens on tier 0, confirms on tier 1 with the exact test, and **audits** on tier 2 on a pre-registered cadence. The real metric's ratchet moves only when an audit confirms it. Everything below the audit is the proxy's word, and the engine measures how good that word is.

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
  "measure": { "command": "python3 bench/replay.py --stage detect --fixture bench/recorded/run-2026-09-03", "parse": "metric-line:detect_stage_ms" },
  "fidelity": { "screen": { "repeats": 2 }, "confirm": { "repeats": 10, "holdout": { "kind": "arg", "values": ["slice-a", "slice-b", "slice-c"] } } },
  "integrity": { "frozen_paths": ["bench/replay.py", "bench/recorded/"] },
  "targets": ["hand/detect/"],
  "gaming_risks": ["replay fixture could be edited (frozen)", "stage could detect the replay harness and skip work", "recorded intermediates could go stale against the real pipeline"]
}
```

- `proxy_for` names the real metric's card. The real card keeps its own `measure` (the four-hour command) and gains `audit` (below).
- `trust` is `provisional` at creation. It becomes `validated` only through audits (§15.5). A proxy never becomes trusted by declaration.
- A proxy's screen and confirm levels are ordinary: the exact test, the power gate, warm-ups, holdouts, all apply to the proxy metric.
- A proxy is a goal or a guardrail like any card. The campaign's goals list names the proxies it optimizes; the real metric is listed once, as the audited target.

## 15.4 Building the proxies: record and replay

The metrologist's job grows one step. For a slow instrument it must produce tiers 0 and 1, and the rule for both is the same: **the proxy runs the project's own code on frozen inputs recorded from one real run.**

1. **One full, profiled run** at campaign start (the orienteer already runs each command once; this run also records per-stage wall-clock and, where the pipeline allows, the intermediate artifacts between stages: the crawl output, the context bundle, the fuzz corpus, the detector inputs).
2. **Attribution.** From the profile: which stage owns the time (or the error) the goal measures. This is the ablation step MLE-STAR uses; here it is a profile, not an ablation, because one run of the real thing is all the budget allows.
3. **Component proxies** for the stages that matter: a replay harness that feeds the recorded input of stage N into stage N alone and reports the stage's metric. Frozen: the harness and the recording.
4. **A slice proxy**: the whole pipeline on a frozen small subset of inputs (one target instead of twenty; one epoch instead of fifty; one parameter setting instead of the sweep), with three holdout slices the experimenter never sees.
5. **Degradation recipes** for each proxy, as for any card: a known slowdown or a known error must move the proxy the wrong way.

What record-and-replay cannot do: a change that alters what an upstream stage produces (a crawler that finds different pages) is invisible to a downstream replay proxy that consumes the old recording. The metrologist records this as a `gaming_risk` and a `scope` note on the card: the proxy is valid for hypotheses whose `targets` lie in its stage. The engine enforces it: a hypothesis whose target is outside every screening proxy's stage is refused at pre-registration unless the campaign allows `slice-only` screening for it.

## 15.5 Trust is earned: the audit rule

The real metric's card declares its audit:

```json
{ "id": "full_scan_seconds", "kind": "audit", "direction": "minimize", "unit": "s",
  "measure": { "command": "make scan-full", "parse": "metric-line:full_scan_seconds", "timeout_s": 21600 },
  "audit": { "every_accepts": 3, "discard_sample_rate": 0.1, "pairs": 3, "alpha": 0.05 } }
```

The engine runs the real instrument in three situations, each pre-registered:

1. **Accept audit.** After every `every_accepts` accepted changes (default 3), the current head is measured against the last audited commit, interleaved, `pairs` pairs (default 3, one-sided sign-flip at the audit `alpha`; with 3 pairs the smallest p is 0.125, so the default is a direction check, not a significance test; the card can raise `pairs` when hours allow). The ratchet on the real metric moves only here.
2. **Discard audit.** A pre-registered fraction of proxy discards (`discard_sample_rate`, default 10%) is measured on the real instrument, one run against the last audited commit, so the proxy's misses are estimated, not just its false promotions. Without this the proxy's fidelity would be known only on one side.
3. **Campaign-end audit.** The final head versus the base, `pairs` pairs. This is the number the report leads with for the real metric.

From these the engine keeps a **proxy fidelity record** per proxy card:

```
direction agreement   fraction of audited changes where sign(proxy Δ) = sign(real Δ)
false promotions      proxy said better, audit said not
misses                proxy said not better, discard audit said better
magnitude ratio       median of real Δ / proxy Δ over agreeing audits (the exchange rate)
```

Trust transitions are mechanical and pre-declared:

```
provisional → validated   after ≥ 4 audited changes with direction agreement ≥ 0.75 and no more than 1 false promotion
validated  → suspect       when the last 4 audits include ≥ 2 disagreements, or any false promotion after validation
suspect    → demoted       on the next disagreement; a demoted proxy can screen but cannot confirm, and the campaign halts if no confirming proxy remains
```

The thresholds are constants in the fixed-before-data block. They are heuristic; the section on guarantees says what they do and do not give.

## 15.6 Where the guarantee attaches

Honestly:

- The exact test, the α budget, and the family-wise bound (`docs/13` §13.2, §13.3) apply to **the proxy metric**. "Accepted" means the candidate beat its parent on the proxy with the stated error rate.
- The real metric has **audited movement**, not a per-candidate guarantee. Between audits the branch carries proxy-only wins. The audit's own test is exact but low-powered by design (three pairs), so it is a direction check unless the card buys more pairs.
- The report shows two columns for every audited metric: proxy movement (with the guarantee) and audited real movement (with its p-value and pair count). A campaign whose proxy moved and whose audit did not is reported as such; nothing is averaged across the two.
- The ratchet and the global ratchet record only audited real values. A later campaign inherits the real metric's audited floor, never a proxy value.

This is the same split `docs/13` §13.8 makes for frontier campaigns: the tested part and the untested part, named.

## 15.7 Iterations per hour becomes a reported metric

`stats()` gains, per fidelity tier: runs, wall-clock, and the fraction of candidates that stopped at that tier; and overall `iterations_per_hour` (experiments per hour of measurement wall-clock) and `accepts_per_hour`. The campaign report leads its cost section with these. The distiller's inheritance body records which proxy paid off (which stage's proxy produced accepted changes that later audited true) so the next campaign starts from that.

A ladder efficiency line makes the trade visible: how many hours of the real instrument the campaign spent (audits only) against how many it would have spent confirming every promoted candidate on it.

## 15.8 A RedSwarm-shaped example

Real instrument: a full scan of the benchmark target set, about four hours, goal `recall` (higher) with guardrail `false_positive_rate` and `scan_seconds`. Ladder:

- tier 0: `detect_replay_recall` on recorded fuzz outputs for the target set (about 90 seconds); `context_replay_ms` for the context stage.
- tier 1: `slice_recall` on three frozen single-target slices (about 6 minutes), holdout slices never seen by the experimenter.
- tier 2: `recall` (audit every 3 accepts, 3 pairs overnight; discard sample 10%; campaign-end audit).

A detector hypothesis is pre-registered with `targets: ["hand/detect/"]`, screened on `detect_replay_recall` in 90 seconds, confirmed on `slice_recall` with the exact test in about two hours (ten pairs, both sides, six minutes each), and the third such accept triggers a four-hour audit overnight. The campaign runs about eight candidates per working day instead of one every three days, and the report says which of them the real instrument has confirmed.

## 15.9 What this does not solve

- A proxy is only as good as its recording. Recordings go stale as the pipeline changes; the engine can only detect it through audits, so `every_accepts` should be small early in a campaign.
- Cross-stage effects are invisible to component proxies by construction. The slice proxy sees them; the audit proves them.
- Three audit pairs cannot detect small real effects. Users with an eight-hour night get two pairs. The report will say "direction only".
- None of this reduces the real instrument's cost; it reduces how often it is paid.

## 15.10 Decisions to take before building

1. Default `every_accepts` (3) and `discard_sample_rate` (0.1): both are a trade between trust and hours.
2. Whether a demoted proxy halts the campaign or only stops confirming.
3. Whether the audit runs inside the loop (blocking) or is scheduled (the campaign continues on the proxy and the audit result arrives later, retroactively marking accepts). Blocking is simpler and honest; scheduled is faster and needs a "provisionally accepted" state in the ledger and the report.
4. Whether to require a recorded full run at campaign start or allow the metrologist to build proxies from an existing recording.
