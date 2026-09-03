# Operator library

A hypothesis belongs to exactly one operator class (docs/06 §6.1). Classes are the arms of the bandit, the unit of inheritance, and the key of the archive. Each file in this directory has frontmatter the harness reads (`id`, `title`, `expected_diff_size`, `tier`, `default_prior`) and a body the experimenter reads: when to use it, how to pre-register it, typical targets per archetype, gaming risks the judge should look for, and example hypotheses in the ledger's JSON shape.

`tier` is the experimenter agent tier from docs/05 §5.4 (`sb-experimenter-low|medium|high`). `default_prior` is the Beta prior `[alpha, beta]` on acceptance probability used at cold start when the archetype pack does not override it; archetype packs carry their own `operator_priors` and win. `expected_diff_size` sets the batch's diff budget; the complexity regularizer uses the actual diff line count, not this field.

| Operator | Typical diff | Expected size | Tier | Default prior | Notes |
|---|---|---|---|---|---|
| [`config`](config.md) | knob, flag, constant, hyperparameter | tiny | low | [2, 4] | never a knob on the instrument |
| [`algorithmic`](algorithmic.md) | replace an algorithm or data structure in one function | small | high | [3, 4] | largest honest wins; judge reads for "does less" |
| [`allocation`](allocation.md) | remove copies and allocations, reuse buffers | small | medium | [2, 4] | reliable in systems languages, near zero in interpreted code |
| [`caching`](caching.md) | memoize, precompute, incremental recompute | small | medium | [2, 4] | highest gamed-to-honest ratio; key must come from the input |
| [`concurrency`](concurrency.md) | parallelize, batch, pipeline | medium | high | [1, 5] | host-dependent; determinism guardrails apply |
| [`dependency`](dependency.md) | upgrade or replace a library | small | medium | [1, 6] | fixed regularizer penalty per new dependency; needs an editable lockfile |
| [`test-add`](test-add.md) | add a test that captures a bug or a missing case | small | medium | [2, 3] | instrument campaigns only, or when tests are not frozen |
| [`bugfix`](bugfix.md) | fix the root cause of a failing or flaky test | small | high | [2, 3] | correctness goals |
| [`refactor-enabling`](refactor-enabling.md) | structural change with no metric effect that unlocks a later move | large | high | [1, 6] | exploration level 2, side branch only; must name what it enables |
| [`data`](data.md) | data pipeline, filtering, augmentation, curation | medium | medium | [2, 5] | ML and science; eval leakage is the risk |
| [`model`](model.md) | architecture or objective change | medium | high | [1, 6] | ML only; "does it still learn" is the judge's question |
| [`numerics`](numerics.md) | precision, solver, tolerance, stability | small | high | [1, 5] | science and inference; silent wrong answers |
| [`docs`](docs.md) | documentation coverage and correctness | small | low | [1, 6] | docs goals only |

## Adding an operator

The metrologist or the distiller may propose a new class when a repo's wins do not fit these (docs/06 §6.1). A new file needs the same frontmatter, at least two example hypotheses, and a gaming-risk section; the id must be added to the `operator` enum in `templates/hypothesis.schema.json` or the harness will reject hypotheses that use it.
