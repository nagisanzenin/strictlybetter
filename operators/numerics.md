---
id: numerics
title: Numerics
expected_diff_size: small
tier: high
default_prior: [1, 5]
---

# numerics

Precision, solver, tolerance, stability: fp32 to bf16, a fused kernel, a different linear solver, a looser or tighter tolerance, a stabilized formula (log-sum-exp, Kahan summation, pivoting). Small diffs whose effects are large and whose failure modes are silent: the number is wrong and nothing crashes. Warm prior in `science-sim` and `ml-inference`, cold elsewhere.

## When to use

- Science: a profile shows the linear solve or the residual evaluation dominating; the problem class has a better-suited solver or a preconditioner; the tolerance is tighter than the reference comparison needs.
- Inference: a precision or kernel change with a known accuracy cost that the floor can absorb.
- Training: mixed precision, a fused optimizer, `torch.compile`, a stable loss formulation where NaNs appear in diagnostics.
- Any archetype where a float comparison, an accumulation order, or an overflow is the diagnosed cause of a wrong result (`bugfix` if there is a failing test, `numerics` if the metric is error against a reference).
- Not for: parallelizing the solve (`concurrency`), changing the discretization (`algorithmic`).

## How to pre-register

Name the operation, the current and proposed precision or method, and the mechanism that bounds the error change ("the residual is dominated by the O(h²) discretization error at 1e-4; a solver tolerance of 1e-6 instead of 1e-10 changes the answer by less than 1e-7"). Predict the goal and predict `ref_error`, `conservation_violation`, `eval_accuracy` or the equivalent guardrail to stay inside its tolerance, with a number. Predict the holdout cases to behave the same; a numerics change that is stable on the dev case only is the usual failure. If the change introduces nondeterminism (atomics, reduced-precision reductions), say so and predict `seed_gap`/`determinism_gap`.

## Typical targets

| Archetype | Targets |
|---|---|
| science-sim | solver choice (direct vs iterative), preconditioner, tolerance, time-step control, stabilized summation, mixed precision in the residual |
| ml-inference | bf16/fp16/int8 quantization, fused attention kernels, KV-cache precision, sampling numerics |
| ml-training | autocast, fused optimizer, gradient clipping formula, loss scaling, z-loss for stability |
| data-pipeline | float32 vs float64 columns, rounding rules (guardrail: golden diff), decimal for money |
| rust-crate / python-package | fast-math style flags, integer vs float paths, `f32` accumulators in reductions |
| service-api | rarely; serialization precision of floats in responses |

## Gaming risks the judge should look for

- Tolerance loosened until the goal is met: "converged" faster because the stopping criterion changed. Guardrails on `ref_error`, `ref_case_failed` and `conservation_violation` must hold; if the card's tolerance is wide, recommend a check with the reference tolerance tightened by 10x.
- Precision reduced where the test's tolerance is looser than the users' need; the eval passes at 1e-3 while the product is specified at 1e-6.
- Error computed in the new precision (the comparison itself cast to fp16), which hides the loss. The evaluator is frozen; check the diff does not change the dtype of what is handed to it.
- Nondeterminism introduced and the best of several screen runs reported; `seed_gap` is the wall, and the judge should flag reductions with atomics or reordered sums.
- A stability fix that clips or clamps values so a diverging run reports a finite, good-looking number (NaN replaced by zero loss).
- Denormal or overflow behaviour changed by a compiler flag (`-ffast-math`, `-Ofast`) declared as a numerics change but affecting every function in the crate.

## Example hypotheses

```json
{"id": "e0109", "operator": "numerics", "target": "solver/step.py",
 "hypothesis": "The inner CG solve runs to 1e-12 while the outer scheme's truncation error is about 1e-6; a tolerance of 1e-8 halves iterations without moving the reference error.",
 "mechanism": "the error-vs-reference curve is flat below solver tolerance 1e-7 on the two dev cases; the residual history shows 60% of CG iterations spent between 1e-8 and 1e-12",
 "predicted": {"wall_to_convergence_s": "-30..-45%", "iters_to_tol": "-40..-55%", "ref_error": "0..+1e-8", "conservation_violation": "0..+1e-10", "ref_case_failed": "0"},
 "expected_diff_size": "tiny", "est_cost_s": 600}
```

```json
{"id": "e0117", "operator": "numerics", "target": "infer/model.py",
 "hypothesis": "Running the attention blocks in bf16 with fp32 accumulation for the softmax halves p50 latency; the eval accuracy floor has 0.8 points of headroom and published bf16 results for this architecture lose under 0.2.",
 "mechanism": "the profile shows 74% of latency in fp32 matmuls; the softmax accumulation in fp32 avoids the overflow that caused the earlier fp16 attempt (e0071) to fail the accuracy floor",
 "predicted": {"latency_p50_ms": "-40..-55%", "eval_accuracy": "-0.1..-0.3 points", "holdout_accuracy": "-0.1..-0.3 points", "peak_mem_mb": "-30..-45%"},
 "expected_diff_size": "small", "est_cost_s": 500}
```
