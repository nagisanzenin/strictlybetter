---
id: dependency
title: Dependency
expected_diff_size: small
tier: medium
default_prior: [1, 6]
---

# dependency

Upgrade, replace, or remove a library. The diff is small and the risk is unknown: a new version can change behaviour the tests do not cover, and a replacement can be faster because it does less. The complexity regularizer adds a fixed penalty per new dependency, so this operator must clear a higher bar than its diff size suggests.

## When to use

- A profile shows time inside a dependency that has a known faster alternative for the same interface (`orjson` for `json`, `polars` for `pandas` on the hot transform, `regex` for `re`, `ahash` for the default hasher).
- A dependency is pinned far behind a release with documented performance work.
- A heavy dependency is imported for one small function (import time, bundle size, binary size goals).
- The campaign explicitly includes `dependency` and the lockfile is therefore editable. If the lockfile is protected in this campaign, this operator is unavailable; the bandit should not be asked for it.

## How to pre-register

Name the dependency, the version pair or the replacement, the call sites affected, and the evidence for the effect (the library's own benchmark, a profile of the current version). Predict the goal, predict `binary_bytes`/`bundle_gzip_bytes`/`import_ms` if present, and predict `new_deps: 1` so the regularizer is applied openly. State the semantic differences you know about (unicode handling, float formatting, error types) and which tests cover them. If none do, say the hypothesis is `suspicious` on its own terms and propose the extra check.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | hasher, allocator (`mimalloc`, `jemalloc`), serde backend, regex engine, `parking_lot` |
| python-package | `orjson`, `regex`, `numpy` version, `pydantic` v1 to v2, removing a heavy import |
| node-frontend | `lodash` to per-function imports, `moment` to `date-fns` or `Temporal`, lighter UI libraries, `sharp` for images |
| service-api | HTTP framework or server version, JSON codec, database driver (async vs sync) |
| cli-tool | argument parser, terminal libraries, regex engine |
| ml-training | framework version with fused kernels, `flash-attn`, a faster tokenizer |
| ml-inference | runtime (`onnxruntime` vs `torch`), quantization library |
| science-sim | BLAS backend, sparse solver library, FFT library |
| data-pipeline | `pandas` to `polars`/`duckdb`, `pyarrow` version, compression codecs |
| docs-site | generator version, search plugin |

## Gaming risks the judge should look for

- The replacement does less: a JSON library that drops NaN handling, a regex engine without lookbehind, a date library without time zones. Tests that only exercise the fixture's shape pass. Recommended check: run the suite on a fuzzed or holdout input; grep the diff for removed error handling that the old library needed.
- A native extension introduced under the name of an upgrade (the `ctypes` sort case wearing a dependency's clothes). Legitimate only if the pre-registration named it.
- The lockfile changed but the manifest did not, or vice versa; a transitive upgrade smuggled in with a direct one. `new_deps` in the ledger should match the manifest diff.
- Network at build time: a dependency fetched from a git URL or a fork the project does not control.
- The dependency's version pin loosened (`>=`) so future measurements drift; the environment fingerprint should catch it later but the judge should flag it now.

## Example hypotheses

```json
{"id": "e0027", "operator": "dependency", "target": "Cargo.toml",
 "hypothesis": "Switching the HashMap hasher from SipHash to ahash for the symbol table cuts parse time; the table is keyed by short strings and is not exposed to untrusted input.",
 "mechanism": "perf shows 22% of parse in SipHash::write; ahash's own bench and prior ledger entries on similar crates show 2..4x on short keys; the symbol table is internal so HashDoS resistance is not required",
 "predicted": {"bench_ns": "-10..-18%", "binary_bytes": "+0..1%", "build_release_s": "+2..5%", "tests_failed": "0"},
 "expected_diff_size": "small", "est_cost_s": 240}
```

```json
{"id": "e0115", "operator": "dependency", "target": "package.json",
 "hypothesis": "Replacing moment with date-fns for the three formatting calls in src/format.ts removes 68 kB gzipped from the bundle.",
 "mechanism": "the bundle analyzer attributes 71 kB gzipped to moment and its locales; the three calls use format and parseISO only; date-fns is tree-shakeable so only those functions ship",
 "predicted": {"bundle_gzip_bytes": "-60..-72 kB", "lighthouse_perf": "+0.01..0.04", "tests_failed": "0", "tsc_errors": "0"},
 "expected_diff_size": "small", "est_cost_s": 300}
```
