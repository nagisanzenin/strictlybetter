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
| `confirm` | `verdict (accept\|discard), reason, level, rounds, anomaly_extra_repeats, screen_effect, confirm_effect, paired, comparisons[], results{}, head_results{}, kappa_eff` (`head_results` holds the campaign head's fresh summaries when `paired` is true) | `sb confirm` |
| `accept` | `reason, accepted_commit, branch` | `sb accept` |
| `discard` | `reason, archived, archive_key` | `sb discard` |
| `cost` | `tokens_in, tokens_out, wall_s, dollars, tier, estimated` | `sb cost` |
| `audit` | `kind (accept\|discard), commit, against, pairs, experiment, at, wall_s, metrics{real id: {verdict, p, n_pairs, median_improvement, head_median, against_median, alpha, unit}}, proxies{proxy id: {said (better\|not-better), agree}}` (proxy ladder, docs/15; `verdict` is `confirmed\|direction\|no-change\|worse\|invalid`) | `sb accept` (at the first accept and then every `every_accepts`), `sb discard` (a sampled discard, one pair vs the experiment's base) |

## Campaign-level events (`id: "campaign"`)

`start`, `baseline`, `halt`, `resume`, `end`, `explore` (exploration level raised),
`screen-untrusted` (false-promotion budget exceeded; screen repeats doubled),
`holdout-rotate`, `distill`, and for a proxy ladder (docs/15):

| event | data | written by |
|---|---|---|
| `audit` | as the per-experiment `audit` event with `kind: end`, `experiment: null`, `against` the base commit, and no `proxies` | `sb campaign end` (when the head moved) |
| `trust` | `proxy, from, to, fidelity{audits, agree, false_promotions, misses, exchange_rates}` | the audit that moved a proxy's `trust` (`provisional → validated`, `validated → suspect`, `suspect → demoted`, `suspect → validated`) |

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
An experiment's `audit` event appears in its `events[]` and nowhere else in the merged record;
`campaign.json` `audit_history` holds every audit record in order.

## Discard reasons (fixed vocabulary)

`noise`, `regression:<metric>`, `integrity`, `gamed`, `build-failed`, `timeout`, `budget`,
`invalid`, `harness-error`, `manual[:detail]`. `sb discard --reason` accepts any string whose
prefix before the first `:` is in this list.

## Integrity violations (`submit.integrity_violations`, fixed vocabulary)

`frozen:<file>`, `protected:<file>`, `state:<file>`, `scope:<file>` (a changed file outside the
campaign's `scope_paths`, when they are set), `eval-hash-changed`, `deps:<manifest,…>` (a
dependency manifest touched outside the `dependency` operator). Any of them fails the submit;
two failing submits in a row halt the campaign.

## Halt reasons (`campaign` event `halt`; `campaign.json` `halt_reason`)

`integrity:<violations>`, `external-tampered:<path>` (an external instrument's content hash
differs from the one taken at `campaign start`; checked before every decision),
`card-tampered:<id>`, `card-missing:<id>`, `gamed-twice`, `holdout-gap:<ratio>`,
`budget:<dimension>`, `instrument-unusable:<metric>:mde=<value>`, `ratchet-regression:<metric>`,
`proxy-demoted:<proxy>:no-confirming-proxy-left` (a proxy was demoted and no goal with another
trust remains), `manual` (or the `--reason` given to `sb campaign halt`).

## Reading it

```bash
$SB ledger view e0007          # one merged record (a discarded candidate's confirm numbers are redacted; --unredacted for audits)
$SB ledger tail -n 30          # the last 30 raw events
$SB ledger experiments         # one line per experiment: id, operator, target, verdict, reason, diff_lines
```

Never edit the file. Never write a summary of it from memory; run the command and quote it.
