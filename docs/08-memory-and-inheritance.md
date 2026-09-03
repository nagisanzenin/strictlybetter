# 08 · Memory and inheritance

The loop's memory has two layers with different readers. The **ledger** is for machines and audits. The **inheritance body** is for whoever starts the loop tomorrow, agent or human, with an empty context window.

## 8.1 The ledger

`ledger.jsonl` is append-only and event-sourced: one line per event, never rewritten, one JSON object per line:

```json
{"ts": "2026-09-03T11:04:12Z", "id": "e0042", "event": "prereg", "data": {"...": "..."}}
```

Per-experiment events (`id` is the experiment id) and what their `data` carries:

| event | data | written by |
|---|---|---|
| `prereg` | `campaign, operator, target, hypothesis, predicted, expected_diff_size, mechanism, prereg_hash, worktree, base_commit, exploration_level` | `sb prereg`, before any diff exists |
| `submit` | `commit, diff_hash, diff_lines, new_deps, files, integrity_ok, integrity_violations` | `sb submit` |
| `measure` | `fidelity, results{metric: {median, sigma, n, n_valid, values, invalid, secs_total}}, wall_s` | `sb measure`; `sb confirm` for the full pass |
| `retry` | `level` | `sb judge` when it returns `retry-screen` |
| `judge` | `level, verdict, reason, improved, regressed, invalid, score, anomaly, kappa_eff, comparisons[]` | `sb judge` (the statistical verdict) |
| `verdict` | `verdict, pattern, evidence, recommended_check, judge` | `sb judge-verdict` (the blind judge, whose input `sb judge-payload` composed in `inbox/`) |
| `confirm` | `verdict (accept\|discard), reason, level, rounds, anomaly_extra_repeats, screen_effect, confirm_effect, comparisons[], results{}, kappa_eff` | `sb confirm` |
| `accept` | `reason, accepted_commit, branch` | `sb accept` |
| `discard` | `reason, archived, archive_key` | `sb discard` |
| `cost` | `tokens_in, tokens_out, wall_s, dollars, tier, estimated` | `sb cost` |

Campaign-level events carry `id: "campaign"`: `start` (goals, guardrails, walls, commit, eval hash), `baseline`, `halt` (reason), `resume`, `end` (reason), `explore` (new exploration level), `holdout-rotate`, `screen-untrusted`, `distill` (inheritance body written).

`sb ledger view <id>` folds one experiment's events into a single record with the fields `id`, `events[]`, `campaign`, `operator`, `target`, `hypothesis`, `predicted`, `expected_diff_size`, `mechanism`, `prereg_hash`, `worktree`, `base_commit`, `ts_start`, `commit`, `diff_hash`, `diff_lines`, `new_deps`, `files`, `integrity_ok`, `integrity_violations`, `measures{screen|full|confirm}`, `judge_stat`, `judge`, `confirm`, `verdict` (`accept` | `discard`), `reason`, `ts_end`, `accepted_commit`, `archived`, `cost{tokens_in, tokens_out, wall_s, dollars, tier}`, `retries`. `sb ledger tail -n N` prints raw events; `sb ledger experiments` prints one summary line per experiment.

**Limited leakage** (`04-anti-overfitting.md` §4.4) is implemented as redaction in the human-facing view, not as a hidden field: for a discarded experiment, `sb ledger view` replaces the confirm record's `results`, `comparisons`, and `confirm_effect` with a redaction marker; `--unredacted` is the audit path. The file itself keeps everything.

Properties:

- Written by the harness only. Agents submit; the harness records. A torn line is skipped on read and never bricks the file.
- Every accepted commit's message contains a provenance block built from its record, so `git log` on the campaign branch is a readable experiment history even without the file.
- The ledger is the replay buffer: the bandit, the plateau detector, the cost report, `sb next`, and the distiller all read from it and nothing else.
- The engine never commits the state home; whether `ledger.jsonl` is committed on the campaign branch is the project's choice (`10-implementation-plan.md` §10.9). Projects with many campaigns can archive old ledgers; the global ratchet in `ratchet.json` carries forward what matters.

## 8.2 The inheritance body

`inheritance.md` is rewritten (not appended) by the distiller at every DISTILL, through `sb inheritance write --file` (the engine requires `## ` sections and logs a `distill` event; `sb inheritance show` prints it, and `sb next` points at it). It is modeled on an operations manual for cold-start use, not on an incident log. Fixed sections:

1. **How to run the loop here.** Verified commands, machine requirements, how long a screen and a confirm take, what to do if a metric is quarantined.
2. **Current frontier.** The best confirmed value of every ratcheted metric, with sigma, and the commit that set it.
3. **What works here.** Operator classes and targets with confirmed effect sizes. "Allocation changes in `parse/` returned +4..12% four times. Config changes never exceeded noise."
4. **Dead ends.** Hypotheses tried and discarded, grouped, with the reason, so they are not retried. Includes the diff hash so an agent can look at what was attempted.
5. **Noise realities.** Which metrics are noisy on this machine, measured sigmas, what quarantine decisions were made, and whether repeats were increased.
6. **Open hypotheses.** Things the loop thinks are promising but has not tried, with why (usually cost or exploration level).
7. **Gotchas.** Environment facts that cost time: a bench that needs a warm cache, a test that needs a service, a flag that silently changes measurement.
8. **Mechanisms (science projects).** The accumulated explanations from pre-registrations that were confirmed.

The distiller writes for a reader with no context. Every claim points to ledger ids. The document should let a new agent produce a good first hypothesis batch within one read.

## 8.3 What is inherited across projects

Some knowledge is not project-specific:

- Archetype priors for the bandit (which operator classes tend to pay off for `rust-crate`).
- Noise floor expectations per metric type (how many repeats criterion needs on a laptop).
- Gaming patterns the judge has seen, as a growing checklist.

These live in the plugin itself as static, versioned files: `archetypes/*.json` carries the operator priors and noise sources, `templates/judge-checklist.md` the gaming patterns. Not in v1.0: a global learned store or a distill step that updates it; the per-project `bandit.json` is the only learned prior, and cross-project knowledge changes only through a plugin release. The default is conservative: project memory is rich, global memory is slow-moving.

## 8.4 Memory as regularization

The inheritance body is a prior. It should make the next campaign's first batch better than random, and it should stop the loop from re-running its own failures. It should not become a straitjacket: at exploration level 2 the experimenter is explicitly allowed to revisit dead ends with a new mechanism, because the code has changed since they were recorded.

The ledger is the ground truth. When the inheritance body and the ledger disagree, the ledger wins and the distiller is re-run.

## 8.5 Handing off to humans

At campaign end the loop produces one branch, one ledger, one inheritance body, and a short campaign report (`reports/<campaign id>.md`, written by `sb report` and by `sb campaign end`):

- goals and their movement (best value now, sigma, number of accepted changes; the start value is in the ledger's `baseline` event)
- guardrails and their values
- cost: experiments by outcome and discard reason, measurement wall-clock, estimated dollars, cost per accepted improvement, false promotions, holdout gap, which walls were on
- the list of accepted commits with one line each, and the discards with their reasons
- the reproduction commands
- what the distiller recommends next: this is in the inheritance body's open-hypotheses section, not in the engine's report

The report is the pull request description. A reviewer who reads only it should know what changed, how much it helped, how sure the loop is, and what it cost.
