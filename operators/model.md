---
id: model
title: Model
expected_diff_size: medium
tier: high
default_prior: [1, 6]
---

# model

Change the architecture or the objective: a layer, an attention variant, a normalization, a loss term, an initialization, a regularizer. ML archetypes only. The autoresearch lineage found most of its late wins here, and the casebook found most of its gaming here too (a search engine in place of the net). Cold prior everywhere except `ml-training`, where the archetype pack warms it.

## When to use

- ML training with a fixed budget and a diagnostic that points at capacity or optimization (loss plateaus early, gradient norms spike, attention entropy collapses).
- A published change with a mechanism that applies to this model's size and data (RMSNorm for LayerNorm, rotary embeddings, SwiGLU, QK-norm, muP-style init).
- Inference: a structurally cheaper equivalent (grouped-query attention, a distilled head) when the accuracy floor has headroom.
- Not for: hyperparameters (`config`), precision changes (`numerics`), data changes (`data`).

## How to pre-register

Name the component, the replacement, and the mechanism at this scale ("the 12-layer model at 300 s of training is optimization-bound; RMSNorm removes the mean subtraction and the variance estimate is stable at batch 64"). Predict `val_bpb` as a range, predict `tokens_per_s` and `peak_mem_mb` (architecture changes usually move both), and predict the held-out `test_bpb` to move by the same amount as val. A model hypothesis that predicts a val gain and does not mention test is incomplete. Parameter count is a good extra prediction: state it so the judge can check the change did not simply make the model bigger inside the same wall-clock.

## Typical targets

| Archetype | Targets |
|---|---|
| ml-training | normalization, activation, positional encoding, attention variant, init scheme, loss (z-loss, label smoothing), weight tying, depth/width at fixed budget |
| ml-inference | head pruning, layer dropping with a distillation step, speculative decoding draft model |
| science-sim | not applicable; surrogate models inside a simulation are `numerics` or `algorithmic` |

## Gaming risks the judge should look for

- The learning component replaced by something that does not learn: a retrieval index, an n-gram cache, a lookup over val text, a heuristic engine (the Gomoku case). Signs: `train_loss` does not move while `val_bpb` improves; `tokens_per_s` jumps; the diff opens a data file at eval time; a forward pass called once and discarded.
- Implausibly short work: a training run finishing early because the "model" has nothing to train. The validity band on duration and the `determinism_gap` card are the wall.
- Eval-time behaviour differing from train-time behaviour in a way that reads the labels or the full sequence (a "teacher-forced" eval that peeks at the next token).
- A bigger model inside the same budget that wins on val by capacity and loses on the holdout; the confirm gap is the signal.
- Objective changed so the reported val loss is no longer comparable (a different reduction, a different denominator, dropping the hardest tokens from the loss). The evaluator is frozen, but a model that returns a different logit shape can change what the evaluator computes; recommend checking the eval token count is unchanged.

## Example hypotheses

```json
{"id": "e0087", "operator": "model", "target": "model.py",
 "hypothesis": "Replacing LayerNorm with RMSNorm in all 12 blocks removes the mean computation and lets the 300 s budget fit about 6% more steps at the same loss per step.",
 "mechanism": "the step profile shows 9% of forward+backward in LayerNorm kernels; RMSNorm at this depth is known to match LayerNorm per step; the gain is throughput, not per-step quality",
 "predicted": {"val_bpb": "-0.004..-0.010", "test_bpb": "-0.004..-0.010", "tokens_per_s": "+5..8%", "peak_mem_mb": "-1..0%", "determinism_gap": "0"},
 "expected_diff_size": "small", "est_cost_s": 330}
```

```json
{"id": "e0098", "operator": "model", "target": "model.py",
 "hypothesis": "Tying the input embedding and the output projection frees 25% of parameters for two extra layers at the same parameter budget, which the fixed-time run can afford because the embedding matmul is cheap.",
 "mechanism": "the 50k-vocab embedding is 12.8M of the 51M parameters; tied weights are standard at this scale; two more layers cost about 4% throughput which the last accepted state's step time can absorb",
 "predicted": {"val_bpb": "-0.01..-0.02", "test_bpb": "-0.01..-0.02", "tokens_per_s": "-3..-6%", "peak_mem_mb": "+2..5%"},
 "expected_diff_size": "medium", "est_cost_s": 330}
```
