---
id: data
title: Data
expected_diff_size: medium
tier: medium
default_prior: [2, 5]
---

# data

Change what goes into the model or the pipeline: filtering, deduplication, augmentation, sampling weights, tokenization, ordering, curation rules. The code that consumes the data is unchanged. In ML this operator competes with `model` for the largest honest gains and is also the easiest place to leak the evaluation set into training.

## When to use

- ML training: a data-quality diagnostic (duplicate rate, length distribution, label noise estimate) suggests headroom; a curriculum or mixture change has a mechanism.
- Data pipelines: a filter or a curation rule is the artifact being improved and the downstream eval is the goal (docs/07 §7.5).
- Science: input preprocessing (mesh generation, initial conditions sampling) when the reference solution does not depend on it.
- Not for: changing the eval set, the val split, the holdout, or the reference (frozen; any such diff is `integrity`).

## How to pre-register

Name the transformation, the fraction of data it touches ("removes 3.2% of documents as near-duplicates at Jaccard 0.8"), and the mechanism linking it to the goal. Predict the goal and predict the dataset-size guardrail (`train_examples`, `dataset_rows`) and the class balance if there is one. State explicitly that the change does not read, touch, or derive from any eval, val, or holdout path. A data hypothesis without a stated fraction and mechanism is the seed-noise trap; the noise floor will discard most of them and the bandit will learn that.

## Typical targets

| Archetype | Targets |
|---|---|
| ml-training | dedup, quality filters, mixture weights, sequence packing, curriculum order, tokenizer vocabulary (only if the eval's bpb denominator is bytes, not tokens) |
| ml-inference | calibration set for quantization, prompt templates for an eval (frozen eval inputs; templates are artifact) |
| data-pipeline | filter predicates, normalization rules, join strategy for enrichment sources |
| science-sim | initial condition sampling, mesh generation parameters (the resolution guardrail must hold) |
| python-package / service-api | seed data and fixtures used by the artifact at runtime (not the test fixtures) |

## Gaming risks the judge should look for

- Eval leakage: a filter that keeps documents similar to the val set, a dedup that runs against val, a mixture that upweights the val domain. The `test_bpb`/`holdout_accuracy` confirm-only cards are the wall; the judge should flag any code path that opens an eval, val, or holdout file outside the frozen evaluator.
- Fewer examples reported as a win: dropping hard examples raises accuracy on a fixed eval only if the eval was also touched, but drops training examples in a way that helps a fixed-budget run by seeing easy data more often. Check the size guardrail and ask whether the holdout moved as much as val.
- Augmentation that produces exact copies of eval inputs (crop-and-resize on an image eval set that overlaps with training).
- Class balance changed to match the eval distribution.
- A pipeline filter that drops the rows the golden comparison would flag.

## Example hypotheses

```json
{"id": "e0066", "operator": "data", "target": "data/filter.py",
 "hypothesis": "Near-duplicate documents (MinHash Jaccard > 0.8) make up about 4% of the training set; removing them gives the fixed budget more distinct tokens and lowers val bpb.",
 "mechanism": "duplicate-rate diagnostic on 10k sampled documents found 4.1% near-duplicates, clustered in two crawl sources; the val set was constructed from a third source so the filter cannot touch it",
 "predicted": {"val_bpb": "-0.005..-0.015", "train_examples": "-3..-5%", "tokens_per_s": "0", "test_bpb": "-0.005..-0.015"},
 "expected_diff_size": "medium", "est_cost_s": 400}
```

```json
{"id": "e0079", "operator": "data", "target": "pipeline/normalize.py",
 "hypothesis": "Normalizing phone numbers to E.164 before the dedup step merges the 1,840 records that currently survive as distinct; downstream match rate rises.",
 "mechanism": "the match-rate diagnostic shows 1,840 pairs differing only in phone formatting; the golden output for the fixture was produced with the same rule so golden_diff_lines stays 0",
 "predicted": {"match_rate": "+1.5..2.5", "golden_diff_lines": "0", "row_count": "0", "runtime_s": "+1..4%"},
 "expected_diff_size": "small", "est_cost_s": 200}
```
