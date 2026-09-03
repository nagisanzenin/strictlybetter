---
id: allocation
title: Allocation
expected_diff_size: small
tier: medium
default_prior: [2, 4]
---

# allocation

Remove copies and allocations on a hot path: reuse a buffer, borrow instead of clone, reserve capacity, avoid an intermediate collection, return a view instead of a copy. The algorithm is unchanged. Effects are modest and reliable in systems languages and near zero in most interpreted code.

## When to use

- A heap profiler or allocation counter (`dhat`, `heaptrack`, `tracemalloc`, `--track-allocations`) shows a hot loop allocating per iteration.
- The code clones to satisfy the borrow checker or copies a slice to pass it on; `Vec` growth in a loop without `with_capacity`; `String` built by repeated `+`.
- Python or JS: intermediate lists built only to be iterated once, repeated `list(...)` on the same iterable, a per-call regex compile. Expect small wins.
- ML and inference: tensors materialized when a view would do, `.cpu()` or `.numpy()` round trips inside a loop, dataloader collate copying.
- Not for: changing the data structure's shape (`algorithmic`), memoization across calls (`caching`).

## How to pre-register

Name the allocation site (file, function, the line that allocates), the count per unit of work if the profiler gave one ("3 allocations per token, 2.1M per bench iteration"), and the replacement. Predict the goal movement as a range and predict `peak_mem_mb` or `rss_kb` if there is a memory guardrail: buffer reuse often raises steady-state memory slightly. A good prediction for a Rust hot loop is "-5..-15% bench_ns"; a prediction above 30% for this operator should raise the judge's attention.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | `.clone()`, `.to_string()`, `.collect()` in loops, `Vec::new()` inside functions called per item, `format!` in hot paths, `Box<dyn>` where generics would do |
| python-package | list-building comprehensions consumed once, `str` concatenation, `copy.deepcopy` |
| node-frontend | object spread in render loops, array copies, closure allocation in hot event handlers |
| service-api | per-request buffer allocation, JSON encoders built per call, connection objects |
| cli-tool | per-line `String` allocation in readers, output built in memory then written |
| ml-training | tensor copies in the collate function, `.item()` inside the step, CPU-GPU transfers |
| ml-inference | KV-cache reallocation, output tensor allocation per token |
| science-sim | temporary arrays in the inner stencil, `numpy` intermediates that could be in-place |
| data-pipeline | DataFrame copies, `.apply` creating per-row objects, string columns not categorical |

## Gaming risks the judge should look for

- The "reused buffer" is a static or global that leaks state between calls and happens to hold the bench's previous result. Recommended check: run the bench twice with different inputs in one process.
- A copy removed by returning a reference to internal state that the caller mutates; tests may not cover aliasing. Look for lifetime or `unsafe` changes in Rust, and for returned mutable containers in Python.
- `unsafe` introduced to avoid a bounds check or a copy; the `unsafe_count` diagnostic moves and the judge should say `suspicious` with recommended check "miri or a fuzz run on the changed function".
- Memory guardrail traded silently: a bigger reusable arena that never shrinks. Check `rss_kb`/`peak_mem_mb` moved and whether the hypothesis predicted it.
- In interpreted languages, a native helper introduced under the name of "avoiding allocation".

## Example hypotheses

```json
{"id": "e0044", "operator": "allocation", "target": "src/parse/token.rs",
 "hypothesis": "Token::text is a String cloned from the input for every token; storing a byte range into the source slice removes one allocation per token.",
 "mechanism": "dhat shows 2.1M allocations per bench iteration, 94% from Token::new; the tokens do not outlive the input in any caller",
 "predicted": {"bench_ns": "-6..-14%", "tests_failed": "0", "unsafe_count": "0"},
 "expected_diff_size": "small", "est_cost_s": 120}
```

```json
{"id": "e0052", "operator": "allocation", "target": "train.py",
 "hypothesis": "The step loop calls loss.item() every iteration, forcing a device sync; logging every 50 steps and accumulating on device raises tokens/s.",
 "mechanism": "the profiler shows 12% of step time waiting on cudaStreamSynchronize called from .item(); the value is only used for logging",
 "predicted": {"tokens_per_s": "+8..14%", "val_bpb": "-0.005..-0.015", "peak_mem_mb": "0"},
 "expected_diff_size": "small", "est_cost_s": 330}
```
