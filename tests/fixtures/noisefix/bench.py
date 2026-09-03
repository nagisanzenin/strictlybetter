#!/usr/bin/env python3
"""Benchmark for noisylib. Frozen instrument.

Environment:
    SB_SEED           int, default 0     seed for the input generator
    SB_BENCH_SIZE     int, default 1500  number of items handed to work()
    SB_BENCH_REPEATS  int, default 3     timed repeats; median kept

Prints, one per line:
    METRIC bench_ms=<median of the repeats, 3 decimals>
    METRIC bench_work_ms=<sum of every timed repeat, 3 decimals>
    METRIC bench_checksum=<16 hex chars>     sha256 of the canonical output

bench_work_ms lets an external caller measure the instrument's fixed overhead
(process start, imports, input generation) as wall-clock minus timed work.
The checksum covers work()'s result on the generated input, so an
implementation that is faster because it is wrong changes the checksum.
"""

import hashlib
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from noisylib.core import work  # noqa: E402


def env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def make_inputs(rng, n):
    """Deterministic input for size n from a seeded random.Random."""
    return [rng.randrange(1 << 20) for _ in range(n)]


def main():
    seed = env_int("SB_SEED", 0)
    size = env_int("SB_BENCH_SIZE", 1500)
    repeats = max(1, env_int("SB_BENCH_REPEATS", 3))

    rng = random.Random(seed)
    items = make_inputs(rng, size)

    times = []
    out = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = work(items)
        times.append((time.perf_counter() - t0) * 1000.0)

    digest = hashlib.sha256(repr((size, seed, out)).encode("utf-8")).hexdigest()[:16]

    print(f"METRIC bench_ms={statistics.median(times):.3f}")
    print(f"METRIC bench_work_ms={sum(times):.3f}")
    print(f"METRIC bench_checksum={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
