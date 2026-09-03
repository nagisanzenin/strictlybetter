---
id: caching
title: Caching
expected_diff_size: small
tier: medium
default_prior: [2, 4]
---

# caching

Memoize, precompute, or recompute incrementally. The work is the same the first time and cheaper afterwards. This operator has the highest ratio of gamed to honest wins in the casebook, because a cache keyed on what only the benchmark supplies is the simplest way to make a measurement lie.

## When to use

- A profile shows the same pure computation repeated with the same inputs (a regex compiled per call, a config parsed per request, a shape computed per batch, a schema validated per row).
- A build or pipeline redoes work whose inputs did not change (incremental recompute, content-addressed intermediate outputs).
- A service recomputes a response that is identical across many requests within a window, and staleness is acceptable and documented.
- Not for: reusing a buffer (`allocation`), a different algorithm (`algorithmic`).

## How to pre-register

Name what is cached, the key, the invalidation rule, and the expected hit rate on the real workload with evidence ("the load test has 2,000 distinct keys over 40k requests, so hit rate about 95%"). State the memory cost and predict the memory guardrail. State explicitly that the key is derived from the input, not from the caller or the environment. A cache without an invalidation rule is a bug, not a hypothesis. The predicted effect should be consistent with the hit rate: a 30% hit rate cannot yield an 80% speedup.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | `once_cell`/`LazyLock` for compiled regexes and tables, memoized parse results keyed by content hash |
| python-package | `functools.lru_cache` on pure functions, module-level compiled regexes, cached properties |
| node-frontend | memoized selectors, `useMemo` on expensive derivations, build-time precompute of static data |
| service-api | response cache with TTL, prepared statements, connection reuse, ETag |
| cli-tool | cached parsed config, cached completion trees |
| ml-training | tokenized dataset cached to disk, precomputed positional tables |
| ml-inference | KV cache, prefix cache, compiled graph cache |
| science-sim | assembled operators reused across time steps when the mesh is static, factorization reuse |
| data-pipeline | incremental recompute keyed by input file hash, materialized intermediates |
| docs-site | search index and syntax-highlight cache |

## Gaming risks the judge should look for

- The key includes something only the benchmark supplies: the fixture's file name, its exact byte length, the bench's seed, the load generator's URL. Recommended check: run confirm on a fresh fixture (the holdout does this; the judge should still name it).
- The cache is warm on the second bench iteration because the bench calls the function with the same input every iteration, so the measured speedup is the hit path only. The card's `gaming_risks` usually say this; the fix is a bench that varies input, which is an instrument campaign, not an acceptance.
- Cache populated at import or build time from a file that happens to contain the eval inputs (precomputing the eval set).
- No invalidation: a cache keyed by path but not by content, so a changed input returns a stale result. Tests with a single fixture will not see it.
- A cache placed in the frozen instrument path (a bench helper) rather than in the artifact.
- Unbounded growth: no eviction, memory guardrail predicted flat. Suspicious if `rss_kb` did not move on a service under load.

## Example hypotheses

```json
{"id": "e0061", "operator": "caching", "target": "src/schema/validate.py",
 "hypothesis": "compile_schema is called once per row with the same schema dict; caching the compiled validator by the schema's id() and a content hash makes validation amortized.",
 "mechanism": "profile: 44% of pipeline time in jsonschema compile; there are 3 distinct schemas in the fixture and in production, so the cache holds 3 entries",
 "predicted": {"runtime_s": "-30..-45%", "peak_mem_mb": "+0..2%", "golden_diff_lines": "0"},
 "expected_diff_size": "small", "est_cost_s": 200}
```

```json
{"id": "e0088", "operator": "caching", "target": "server/handlers/catalog.py",
 "hypothesis": "GET /catalog/{id} rebuilds the response from four queries; a 30 s TTL cache keyed on id and the catalog's updated_at version cuts p95 at the fixed load.",
 "mechanism": "the load has 2,000 distinct ids over 40k requests; four queries at 0.8 ms each dominate the 4.1 ms median; invalidation is by the version column the writer already bumps",
 "predicted": {"p95_s": "-40..-60%", "rss_kb": "+2..6%", "error_rate": "0", "tests_failed": "0"},
 "expected_diff_size": "small", "est_cost_s": 300}
```
