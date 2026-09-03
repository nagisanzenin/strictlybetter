# Benchmark fixtures for the strictlybetter harness

Three small projects the harness tests run against, plus `make_fixture.py`, which copies one of them into a throwaway git repository. Nothing here has a third-party dependency; the toolchain is Python 3 (unittest only) and cargo (no crates).

| Fixture | What it is | Instruments | Meant to exercise |
|---|---|---|---|
| `pyfix/` | Python package `slowlib`: five pure functions, three deliberately slow | `run_tests.py`, `bench.py` | brownfield loop: find the algorithmic fix, keep the tests green, keep the checksum |
| `rustfix/` | Rust crate `slowcrate`: four pure functions, two deliberately slow | `checks.sh`, `src/bin/bench.rs`, `tests/` | same, with cargo test and clippy as guardrails |
| `greenfield/` | `textstats.py`, one module, no tests, no bench | none | instrument-first mode (`docs/07-universality.md` §7.3) |

## The METRIC protocol

Every instrument prints lines of the form `METRIC name=value` on stdout, one metric per line, and always exits 0 so the harness can read the numbers even when the underlying suite is red. Everything else the instrument says goes to stderr. Cards reference a line with `parse: "metric-line:<name>"`.

Benchmarks read three environment variables: `SB_SEED` (input generator seed, default 0), `SB_BENCH_SIZE` (problem size), and `SB_BENCH_REPEATS` (timed repeats per function, median kept). They print one `METRIC <fn>_ms` line per function, `METRIC bench_ms` as the sum of the medians, and `METRIC bench_checksum`, a hash of every function's output on the generated inputs. A change that is faster because it is wrong changes the checksum. The checksum depends on the seed and size, so it is only comparable between runs with the same env.

Measured on this machine (Apple laptop, Python 3.14, cargo 1.97, release build):

| Fixture | Command | Wall time | `bench_ms` | Slow-function share |
|---|---|---|---|---|
| pyfix | `python3 bench.py` (size 3000, 5 repeats) | ~1.1 s | ~210 ms | 99.9% |
| pyfix | screen env (size 1200, 3 repeats) | ~0.12 s | ~34 ms | |
| rustfix | `cargo run --release --bin bench -q` (size 30000, 5 repeats) | ~0.9 s | ~140 ms | 99.6% |
| rustfix | screen env (size 12000, 3 repeats) | ~0.26 s | ~28 ms | |

Run-to-run noise of `bench_ms` at the default size was a few milliseconds on both fixtures.

## Deliberately slow functions

pyfix (`slowlib/core.py`):

- `dedupe_preserve_order`: `if x not in result` on a growing list, O(n²). Fix: a `seen` set.
- `word_freq`: `words.count(w)` once per distinct word, O(n·u). Fix: a dict or `Counter` in one pass.
- `pairs_with_sum`: every pair of positions, O(n²). Fix: one pass with a set of seen values.
- `top_k` (`heapq.nlargest`) and `common_prefix_len` (compare only the min and max string) are already near-optimal.

rustfix (`src/lib.rs`):

- `dedupe`: `Vec::contains` on the growing result, O(n²). Fix: a `HashSet`.
- `count_words`: linear scan of the result plus a full rescan of the words per distinct word. Fix: a `HashMap`.
- `top_k` (`select_nth_unstable`) and `common_prefix_len` (single pass over chars) are already near-optimal.

## Metric cards

`<fixture>/fixture-cards/*.json` are metric cards in the shape the harness tests load (see `docs/02-metrics.md` for the YAML original). Exact top-level keys: `id, title, kind, direction, unit, measure, fidelity, acceptance, integrity, degradation, gaming_risks, contention_safe, noise`.

| Fixture | Card | Kind | Direction | Command | Notes |
|---|---|---|---|---|---|
| pyfix | `bench_ms` | goal | minimize | `python3 bench.py` | screen shrinks size to 1200; confirm uses holdout seeds 1913, 8241, 6607 |
| pyfix | `tests_failed` | guardrail | minimize, tolerance 0 | `python3 run_tests.py` | deterministic, contention-safe |
| pyfix | `bench_checksum` | guardrail | equal | `python3 bench.py` | same env/fidelity as `bench_ms`; compare against a baseline measured with the same env |
| pyfix | `loc` | diagnostic | minimize | inline `python3 -c` | never decides anything |
| rustfix | `bench_ms` | goal | minimize | `cargo run --release --bin bench -q` | screen size 12000; same holdout seeds |
| rustfix | `tests_failed` | guardrail | minimize, tolerance 0 | `bash checks.sh` | a build failure reports 1, not 0 |
| rustfix | `clippy_warnings` | guardrail | minimize, tolerance 0 | `bash checks.sh` | counts `warning:` lines minus the summary; compile errors count too |
| rustfix | `bench_checksum` | guardrail | equal | `cargo run --release --bin bench -q` | FNV-1a 64 of the outputs |

Frozen paths: pyfix `bench.py`, `run_tests.py`, `tests/`; rustfix `src/bin/bench.rs`, `tests/`, `checks.sh`. The unit tests inside `rustfix/src/lib.rs` are deliberately not frozen; `tests/integration.rs` carries the randomized cross-checks.

Every card's `degradation.apply` is a shell recipe (a `python3 - <<'EOF'` patch with an asserted anchor, so a stale anchor fails loudly instead of silently doing nothing). Applied to a fresh copy, each one moves its metric the wrong way: a `sleep` in `dedupe` for `bench_ms`, dropping an element for `tests_failed`, changing an output for `bench_checksum`, an unneeded `return` for `clippy_warnings`. `noise` is `null` in every card; the harness measures it.

## `make_fixture.py`

```
python3 tests/fixtures/make_fixture.py <pyfix|rustfix|greenfield> <dest_dir> [--force]
```

Copies the fixture (without `fixture-cards/`, `target/`, `__pycache__/`), runs `git init -q -b main`, sets a local `user.name`/`user.email`, commits `fixture baseline`, and prints two lines: the absolute destination path, then the commit hash. It refuses to touch an existing destination unless `--force` is passed.
