# Ledger (shared contract)

`.strictlybetter/ledger.jsonl` is append-only and event-sourced. One JSON object per line:

```json
{"ts": "2026-09-03T11:04:12Z", "id": "e0001", "event": "prereg", "data": {…}}
```

Written by the engine only. Agents submit; the engine records. A torn line is skipped on
read and never bricks the file. The ledger is the replay buffer: the bandit, the plateau
detector, the cost report, `sb next`, and the distiller read from it and nothing else. When
the inheritance body and the ledger disagree, the ledger wins.

## Events, per experiment id (`e0001`, `e0002`, …)

| event | data | written by |
|---|---|---|
| `prereg` | `campaign, operator, target, hypothesis, predicted, expected_diff_size, mechanism, prereg_hash, worktree, base_commit, exploration_level` | `sb prereg` (before any diff exists) |
| `submit` | `commit, diff_hash, diff_lines, new_deps, files, integrity_ok, integrity_violations` | `sb submit` |
| `measure` | `fidelity, results{metric: {median, sigma, n, n_valid, values, invalid, secs_total}}, wall_s` | `sb measure`, `sb confirm` (full) |
| `retry` | `level` | `sb judge` when it returns `retry-screen` |
| `judge` | `level, verdict, reason, improved, regressed, invalid, score, anomaly, kappa_eff, comparisons[]` | `sb judge` (the statistical verdict) |
| `verdict` | `verdict, pattern, evidence, recommended_check, judge` | `sb judge-verdict` (the blind judge) |
| `confirm` | `verdict (accept\|discard), reason, level, rounds, anomaly_extra_repeats, screen_effect, confirm_effect, comparisons[], results{}, kappa_eff` | `sb confirm` |
| `accept` | `reason, accepted_commit, branch` | `sb accept` |
| `discard` | `reason, archived, archive_key` | `sb discard` |
| `cost` | `tokens_in, tokens_out, wall_s, dollars, tier, estimated` | `sb cost` |

## Campaign-level events (`id: "campaign"`)

`start`, `baseline`, `halt`, `resume`, `end`, `explore` (exploration level raised),
`screen-untrusted` (false-promotion budget exceeded; screen repeats doubled),
`holdout-rotate`, `distill`.

## The merged experiment record

`$SB ledger view <id>` folds an experiment's events into one record (`Home.experiments()`):

```
id, events[],
campaign, operator, target, hypothesis, predicted, expected_diff_size, mechanism, prereg_hash, worktree, ts_start,
commit, diff_hash, diff_lines, new_deps, files, integrity_ok, integrity_violations,
measures: {screen: {metric: summary}, full: {…}, confirm: {…}},
judge_stat: {the judge event, with comparisons[]},
judge:      {the blind verdict},
confirm:    {the confirm event},
verdict: accept | discard, reason, ts_end, accepted_commit, archived,
cost: {tokens_in, tokens_out, wall_s, dollars, tier},
retries
```

A `comparisons[]` entry, per goal and guardrail:
`{id, kind, direction, valid, value, baseline, sigma, delta, delta_sigma, rel, improved, regressed, inconclusive, threshold, note}`.
`delta` is already signed so that positive means better; `threshold` is `kappa_eff × sigma`;
`rel` is `delta / |baseline|`.

Not carried into the merged record (read the `prereg` event or the worktree instead):
`base_commit`. The parent of the experiment's commit is the base: `git -C <worktree> rev-parse HEAD^`.

## Discard reasons (fixed vocabulary)

`noise`, `regression:<metric>`, `integrity`, `gamed`, `build-failed`, `timeout`, `budget`,
`invalid`, `harness-error`, `manual[:detail]`. `sb discard --reason` accepts any string whose
prefix before the first `:` is in this list.

## Reading it

```bash
$SB ledger view e0007          # one merged record (a discarded candidate's confirm numbers are redacted; --unredacted for audits)
$SB ledger tail -n 30          # the last 30 raw events
$SB ledger experiments         # one line per experiment: id, operator, target, verdict, reason, diff_lines
```

Never edit the file. Never write a summary of it from memory; run the command and quote it.
