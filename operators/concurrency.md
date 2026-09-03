---
id: concurrency
title: Concurrency
expected_diff_size: medium
tier: high
default_prior: [1, 5]
---

# concurrency

Parallelize, batch, or pipeline work that is independent: I/O fan-out, embarrassingly parallel loops, overlapping compute with transfer. Larger diffs, subtler bugs, and effects that depend on the measurement host's cores. Cold prior because it fails guardrails more often than it wins.

## When to use

- A profile shows the process idle or single-core while the machine has cores to spare, and the work units are independent (per-file, per-request, per-chunk).
- I/O waits dominate: sequential HTTP calls, sequential file reads, a database queried once per item.
- A pipeline has stages that could overlap (read while transforming, transform while writing).
- ML: dataloader workers, prefetch, overlapping host-to-device copies with compute.
- Not for: raising a thread-count knob (`config`), and not on a metric whose card says the measurement is serialized to one core.

## How to pre-register

Name the loop or the call site, the unit of parallelism, the expected degree (bounded by cores or by I/O concurrency), and the synchronization point. Predict the goal movement with an Amdahl argument: "the parallel section is 70% of runtime; at 4 workers the ceiling is -52%; predicting -30..-45%". Predict the memory guardrail (parallelism usually raises it) and state that output ordering is preserved or that the golden comparison is order-independent. If nondeterminism is introduced anywhere near a measured number, say so; the determinism guardrail will read it.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | `rayon` on independent iterators, `std::thread::scope` for chunks, async I/O fan-out |
| python-package | `concurrent.futures` for I/O, `multiprocessing` for CPU-bound pure functions |
| node-frontend | `Promise.all` on independent fetches, web workers for heavy computation off the main thread |
| service-api | async handlers, connection pools, batching backend calls |
| cli-tool | parallel file processing, streaming output while reading |
| ml-training | dataloader `num_workers`, `pin_memory`, prefetch, gradient accumulation to enable larger batch |
| ml-inference | request batching, pipelined decode |
| science-sim | OpenMP or `numba.prange` on stencils, domain decomposition |
| data-pipeline | partitioned reads, parallel transforms per partition, async writes |

## Gaming risks the judge should look for

- The measurement host's core count is the win: a change that is 4x on an 8-core laptop and 1x on the CI runner. Not gaming, but the environment fingerprint should be in the ledger and the report should say it.
- Threads left running after the timed region so the next repeat starts warm or contended; a thread pool that is not joined; a background task that finishes the work after the metric line prints.
- Output order changes that the golden comparison tolerates but downstream consumers do not; check `golden_diff_lines` is sort-based and whether the project's users depend on order.
- Nondeterminism introduced in a reduction (floating-point sums in parallel) that widens variance in the favorable direction. The `seed_gap` and `determinism_gap` guardrails exist for this; recommend re-running confirm with `OMP_NUM_THREADS=1` as the check.
- Shared mutable state guarded by nothing; tests are single-threaded and pass. Recommended check: run the test suite under a race detector (`RUSTFLAGS=-Zsanitizer=thread`, `go test -race`, `pytest -p xdist`).
- A latency win that is really a throughput loss under the fixed load: check `error_rate` and `rss_kb` moved.

## Example hypotheses

```json
{"id": "e0093", "operator": "concurrency", "target": "pipeline/load.py",
 "hypothesis": "Input partitions are read sequentially; a ThreadPoolExecutor with 4 workers over partitions overlaps I/O and parsing.",
 "mechanism": "iostat during the run shows 20% disk utilization and the profile shows 55% of wall time in read_partition; the partitions are independent and the merge step already sorts",
 "predicted": {"runtime_s": "-25..-40%", "peak_mem_mb": "+30..80%", "golden_diff_lines": "0", "row_count": "0"},
 "expected_diff_size": "medium", "est_cost_s": 400}
```

```json
{"id": "e0104", "operator": "concurrency", "target": "train.py",
 "hypothesis": "The dataloader runs in the main process; num_workers=4 with pin_memory and prefetch_factor=4 removes the input stall visible between steps.",
 "mechanism": "the step trace shows 18 ms of the 60 ms step waiting on the next batch; the tokenized dataset is memory-mapped so workers add no copy",
 "predicted": {"tokens_per_s": "+15..25%", "val_bpb": "-0.01..-0.02", "peak_mem_mb": "+5..10%", "determinism_gap": "0"},
 "expected_diff_size": "small", "est_cost_s": 330}
```
