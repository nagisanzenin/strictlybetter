---
id: refactor-enabling
title: Refactor-enabling
expected_diff_size: large
tier: high
default_prior: [1, 6]
---

# refactor-enabling

A structural change with no metric effect that makes a later move possible: splitting a function so its hot half can be specialized, introducing a trait or interface so a faster backend can be swapped in, moving state so it can be cached, decoupling a module so it can be parallelized. Under the strict-improvement rule this operator can never be accepted on the campaign branch. It is unlocked only at **exploration level 2** on a **side branch** (docs/06 §6.5), where guardrails must hold and no goal must improve; the side branch merges only if its final state beats the campaign head on confirmation.

## When to use

- The loop has plateaued at level 2 and the ablation probes show leverage in a component the loop cannot reach with a small diff.
- Several discarded experiments in the archive share a target and a reason like "would need the parser to expose byte offsets" or "cannot parallelize while the writer holds the lock".
- A hypothesis of another class was written and then marked `BLOCKED` by the experimenter with a structural reason.
- Never as the first move in a campaign, never on the campaign branch, never without a named follow-up hypothesis.

## How to pre-register

The hypothesis names the follow-up it enables (as a draft hypothesis in the same JSON shape, embedded under `enables`), the structural change, and the invariant that stays fixed (public API count, tests, golden output). Predict every goal as `0` and every guardrail as `0`; a refactor that predicts a goal movement is a different operator. State the stepping-stone budget it consumes. The distiller records the pair; a stepping stone whose follow-up never ran is a dead end to be noted.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | extracting a trait for the hot path, splitting a monolithic module, making a struct generic over the allocator or hasher |
| python-package | separating pure computation from I/O so it can be cached or vectorized, introducing a class boundary for a C-extension later |
| node-frontend | lifting state, splitting a bundle entry, extracting a component so it can be lazy-loaded |
| service-api | separating the handler from the storage call so the storage can be batched or cached |
| cli-tool | separating parsing from execution so startup can skip execution setup |
| ml-training | isolating the data path from the model so the loader can be parallelized; config objects replacing globals |
| ml-inference | separating pre/post-processing from the model call so they can be batched |
| science-sim | assembling operators once and applying them per step (enables `caching`); separating the stencil from the boundary logic (enables `concurrency`) |
| data-pipeline | making transforms pure per partition (enables `concurrency`), separating schema from logic |

## Gaming risks the judge should look for

- A "no-effect" refactor that quietly moves a goal: it is accepted on the side branch only if guardrails hold, so a hidden improvement here is a way to bank a change without confirmation on holdout. The side-branch merge confirmation is the wall; the judge should still note any goal movement beyond noise.
- Public API changes hidden inside the restructure (`public_api_items` or `api_surface_lines` must be equal).
- Tests weakened "because the structure changed" (frozen; but a large diff is where a skipped test hides).
- The refactor is the whole rewrite: a 2,000-line diff that replaces the component. The regularizer raises κ, but on a side branch there is no κ to raise; the hard length and budget of the side branch are the limits and the report must show them.
- A follow-up that never materializes: three stepping stones and no goal movement is an archived branch, not knowledge.

## Example hypotheses

```json
{"id": "e0140", "operator": "refactor-enabling", "target": "src/parse/mod.rs",
 "hypothesis": "Split Parser::parse into lex_all and build_tree so the lexer can be specialized per input encoding in a follow-up.",
 "mechanism": "e0102 and e0119 were both discarded because the encoding check sits inside the token loop; with lexing separated, a UTF-8 fast path becomes a 40-line algorithmic change",
 "predicted": {"bench_ns": "0", "tests_failed": "0", "public_api_items": "0", "binary_bytes": "0..+1%"},
 "expected_diff_size": "large", "est_cost_s": 900,
 "enables": {"operator": "algorithmic", "target": "src/parse/lex.rs", "hypothesis": "ASCII fast path in lex_all", "predicted": {"bench_ns": "-15..-30%"}}}
```

```json
{"id": "e0155", "operator": "refactor-enabling", "target": "solver/assemble.py",
 "hypothesis": "Move operator assembly out of the time-step loop into a setup phase keyed on the mesh so it can be cached across steps.",
 "mechanism": "the profile shows 61% of step time in assemble(); the mesh is static in every case in cases/, but assemble() takes the current state as an argument by habit, so caching is impossible without this split",
 "predicted": {"wall_to_convergence_s": "0", "ref_error": "0", "conservation_violation": "0", "resolution_cells": "0"},
 "expected_diff_size": "medium", "est_cost_s": 600,
 "enables": {"operator": "caching", "target": "solver/assemble.py", "hypothesis": "cache assembled operators per mesh hash", "predicted": {"wall_to_convergence_s": "-40..-55%"}}}
```
