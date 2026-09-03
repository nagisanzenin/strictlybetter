---
id: algorithmic
title: Algorithmic
expected_diff_size: small
tier: high
default_prior: [3, 4]
---

# algorithmic

Replace an algorithm or a data structure inside one function or one module. The interface stays; the complexity or the constant factor changes. This is the operator with the largest honest effect sizes and the one the judge reads most carefully, because "do less work" and "do the wrong work" look alike in a diff.

## When to use

- A profile or flamegraph puts one function at the top and its body has a visible better choice: linear scan where a map would do, repeated sorting, string building by concatenation, regex in a loop, O(n²) dedup.
- The diagnostics show a data structure used against its grain (a `Vec` searched by key, a `dict` iterated for the min, a list used as a queue).
- A hot loop re-derives something invariant across iterations (recomputing a length, re-scanning whitespace, re-parsing a format string).
- Science: a solver, integrator, or linear algebra routine with a known better method for the problem class (a preconditioner, a sparse factorization, a higher-order scheme).
- Not for: parallelism (`concurrency`), memoization (`caching`), or removing allocations without changing the algorithm (`allocation`). Pick the narrower operator; the bandit learns per class.

## How to pre-register

Name the function, the current algorithm and the replacement, and the input property that makes the replacement win ("keys are dense integers", "the input is mostly sorted", "n is typically 10⁵"). Predict the effect as a range on the goal and state what will not change: output must be identical, so predict `tests_failed: 0` and, where a golden output exists, `golden_diff_lines: 0`. For science projects the mechanism must explain why the error does not move ("the new quadrature is exact to the same order; the residual is dominated by the time step"). A good prediction for this operator is often large: "+20..60% bench" is plausible; "+2%" is usually noise and should be another operator.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | lexers and parsers, `HashMap` vs `BTreeMap` vs `Vec` of pairs, string handling, sorting and dedup |
| python-package | pure-Python inner loops, list comprehensions that should be set operations, `str` joins, regex compiled once |
| node-frontend | array `.find` inside loops, JSON reshaping, virtual DOM keys, diffing |
| service-api | query shape (N+1), serialization, routing tables, middleware order |
| cli-tool | argument parsing on every call, glob matching, output formatting |
| ml-training | data loading and tokenization, attention variants, sampler logic |
| ml-inference | decoding loop, beam search, top-k selection, batching logic |
| science-sim | solver choice, preconditioner, quadrature, neighbour search, FFT vs direct |
| data-pipeline | joins (hash vs sort), group-by, window functions, dedup |
| docs-site | search index build, link resolution |

## Gaming risks the judge should look for

- An input-specific branch: `if len(x) == 4096`, `if name == "parse_large"`, a fast path keyed on the fixture's shape. The holdout is meant to catch this; the judge should catch it first.
- The algorithm does less: a dedup that keeps the first match instead of all, a sort that stops early, a parser that skips a construct the fixture lacks. Read the tests guardrail together with the diff; if the tests do not cover the dropped case the change is `suspicious` with recommended check "run on a fixture that contains the dropped construct".
- A lookup replacing computation: a precomputed table for exactly the inputs the bench uses; a hash of the input mapped to a stored result (the SpecBench 2,900-line hash-table case).
- Native escape: a `ctypes` load, a compiled extension, a subprocess to another language. Only legitimate under `dependency` and only if declared.
- Numerics changed silently: a faster method with lower precision passing tests that have loose tolerances. For science-sim the conservation guardrail is the check; for others recommend a bit-exact diff of the output on a fresh input.

## Example hypotheses

```json
{"id": "e0042", "operator": "algorithmic", "target": "src/parse/lexer.rs",
 "hypothesis": "The lexer re-scans whitespace on every token; a single skip loop that advances a byte index should raise throughput.",
 "mechanism": "perf shows 38% of lexer time in is_whitespace called per char from three call sites; one forward scan per token removes two of them",
 "predicted": {"bench_ns": "-8..-20%", "tests_failed": "0", "binary_bytes": "0"},
 "expected_diff_size": "small", "est_cost_s": 90}
```

```json
{"id": "e0058", "operator": "algorithmic", "target": "pipeline/dedup.py",
 "hypothesis": "dedup_rows compares each row to all previous rows; hashing a tuple of the key columns into a set makes it linear.",
 "mechanism": "the fixture has 200k rows and the profile shows 71% of runtime in dedup_rows; the key columns are already normalized strings so tuple hashing is exact",
 "predicted": {"runtime_s": "-40..-65%", "golden_diff_lines": "0", "row_count": "0", "peak_mem_mb": "+5..20%"},
 "expected_diff_size": "small", "est_cost_s": 240}
```

```json
{"id": "e0071", "operator": "algorithmic", "target": "solver/linear.py",
 "hypothesis": "Replacing the Jacobi preconditioner with incomplete Cholesky cuts iterations to tolerance on the diffusion cases by about half.",
 "mechanism": "the system is SPD and the condition number grows with mesh refinement; IC(0) is the standard choice and the reference solution does not change because the converged residual is the same",
 "predicted": {"iters_to_tol": "-40..-60%", "wall_to_convergence_s": "-25..-50%", "ref_error": "0", "conservation_violation": "0"},
 "expected_diff_size": "small", "est_cost_s": 600}
```
