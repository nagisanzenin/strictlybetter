---
id: config
title: Config
expected_diff_size: tiny
tier: low
default_prior: [2, 4]
---

# config

A knob, flag, constant, or hyperparameter changes value. Nothing structural moves. The diff is usually one to five lines and the whole hypothesis is "this number is wrong for this workload".

## When to use

- A diagnostic says a resource is mis-sized: thread pool smaller than cores, batch too small for the device, buffer too small for the typical payload.
- A build or runtime profile has a documented faster setting the project does not use (`opt-level`, `lto`, `codegen-units`, `PYTHONOPTIMIZE`, `NODE_OPTIONS`).
- ML: learning rate, warmup, batch size, sequence length, optimizer betas. This is where most of the first autoresearch wins came from and where seed noise is worst.
- The inheritance body says config never beat noise here: do not use it, the bandit will stop asking for it.
- Never use it to change what the instrument measures (repeats, warm-up, fixture size, tolerance). Those are frozen and a config diff that touches them is `integrity`.

## How to pre-register

The hypothesis names the exact key and both values (`codegen-units: 16 -> 1`), the workload property that makes the new value better, and a predicted effect on one goal. A good prediction is a bounded range with a mechanism the harness could falsify: "+3..8% bench_ns because the hot loop inlines across the two crates only at codegen-units=1". A prediction of "faster" is not a hypothesis. Config changes must also predict what they cost: `binary_bytes: +0..5%`, `build_release_s: +10..30%`. If a guardrail is expected to move the wrong way, say so; the tolerance decides.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | `[profile.release]` in Cargo.toml, `RUSTFLAGS` in `.cargo/config.toml` (protected; must be proposed, not edited), allocator choice behind a feature |
| python-package | env pins in the package, `sys.setrecursionlimit`, lazy-import flags, GC thresholds |
| node-frontend | bundler target and minify options, `sideEffects`, chunk size limits |
| service-api | worker count, keep-alive, pool sizes, GC flags, request body limits |
| cli-tool | opt-level, strip, panic strategy, buffered stdout |
| ml-training | lr, warmup steps, batch size, grad accumulation, dtype, compile flag |
| ml-inference | threads, batch size, dtype, KV-cache size |
| science-sim | tolerance and max iterations of the solver (goal-side only; guardrails read the reference), preconditioner choice, time step |
| data-pipeline | chunk size, thread count, compression level |
| docs-site | plugin toggles, strict mode (guardrail, do not touch), minification |

## Gaming risks the judge should look for

- The knob is on the instrument, not the artifact: bench iteration count, warm-up time, criterion `measurement-time`, pytest `-k`, Lighthouse run count. Any of these is `integrity`, not a win.
- Environment tampering disguised as config: `PYTHONHASHSEED`, `OMP_NUM_THREADS`, `RAYON_NUM_THREADS`, GC flags set inside the code under test so the measurement process inherits them. The card's `env` is the only legitimate place for these.
- `panic = "abort"` or `overflow-checks = false` presented as size wins. They change semantics; the tests guardrail may not cover the difference.
- ML: a learning-rate change that wins on seed 0 and loses on the holdout seeds. Expect the confirm gap to be large for this operator; the holdout is the wall that catches it.
- A tolerance loosened on the solver so it "converges" faster. The reference-case and conservation guardrails must hold; if they do, the tolerance was too tight, which is a real finding.

## Example hypotheses

```json
{"id": "e0007", "operator": "config", "target": "Cargo.toml",
 "hypothesis": "Setting codegen-units = 1 in [profile.release] lets LLVM inline the tokenizer into the parser hot loop.",
 "mechanism": "cross-crate inlining only happens within one codegen unit; the flamegraph shows 31% of time in call overhead between lex and parse",
 "predicted": {"bench_ns": "-4..-10%", "build_release_s": "+15..40%", "binary_bytes": "-2..0%"},
 "expected_diff_size": "tiny", "est_cost_s": 200}
```

```json
{"id": "e0019", "operator": "config", "target": "train.py",
 "hypothesis": "Raising warmup from 100 to 400 steps stops the loss spike at step 150 that the current run never fully recovers from.",
 "mechanism": "the loss curve in the last accepted state shows a 0.3 nat spike at step 150 coinciding with peak lr; a longer warmup keeps the Adam second moment estimate from being dominated by the first noisy gradients",
 "predicted": {"val_bpb": "-0.01..-0.03", "tokens_per_s": "0"},
 "expected_diff_size": "tiny", "est_cost_s": 330}
```

```json
{"id": "e0033", "operator": "config", "target": "src/server.rs",
 "hypothesis": "The tokio worker count is hard-coded to 2; setting it to available_parallelism() halves p95 at the fixed load.",
 "mechanism": "the load test runs 16 connections against 2 workers; the request handler is CPU-bound for about 1.5 ms, so queueing dominates the tail",
 "predicted": {"p95_s": "-30..-50%", "rss_kb": "+5..15%", "error_rate": "0"},
 "expected_diff_size": "tiny", "est_cost_s": 120}
```
