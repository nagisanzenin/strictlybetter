#!/usr/bin/env python3
"""Benchmark for slowlib. Frozen instrument.

Environment:
    SB_SEED           int, default 0     seed for the input generator
    SB_BENCH_SIZE     int, default 3000  problem size n
    SB_BENCH_REPEATS  int, default 5     timed repeats per function; median kept

Prints, one per line:
    METRIC <fn>_ms=<median ms, 3 decimals>   for each of the five functions
    METRIC bench_ms=<sum of the five medians, 3 decimals>
    METRIC bench_checksum=<16 hex chars>     sha256 of the canonical outputs

The checksum covers every function's output on the generated inputs, so an
implementation that is faster because it is wrong changes the checksum.
Dict outputs are canonicalised to sorted item lists before hashing, so a
correct implementation with a different insertion order still matches.
"""

import hashlib
import os
import random
import statistics
import string
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slowlib.core import (  # noqa: E402
    common_prefix_len,
    dedupe_preserve_order,
    pairs_with_sum,
    top_k,
    word_freq,
)


def env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def make_inputs(rng, n):
    """Deterministic inputs for size n from a seeded random.Random."""
    letters = string.ascii_lowercase

    # dedupe: n ints drawn from n values, so roughly 63% are distinct.
    dedupe_items = [rng.randrange(n + 1) for _ in range(n)]

    # word_freq: 2n pseudo-words drawn from a vocabulary of n // 2.
    vocab = ["".join(rng.choices(letters, k=rng.randint(3, 8))) for _ in range(max(1, n // 2))]
    text = " ".join(rng.choice(vocab) for _ in range(2 * n))

    # pairs_with_sum: n ints in [-2n, 2n] with a target near zero.
    nums = [rng.randint(-2 * n, 2 * n) for _ in range(n)]
    target = rng.randint(-(n // 4), n // 4)

    # top_k: n ints, k = 10.
    topk_items = [rng.randrange(10 * n + 1) for _ in range(n)]
    k = 10

    # common_prefix_len: n strings sharing a 24-char prefix.
    prefix = "".join(rng.choices(letters, k=24))
    strings = [prefix + "".join(rng.choices(letters, k=rng.randint(0, 12))) for _ in range(n)]

    return {
        "dedupe_preserve_order": (dedupe_items,),
        "word_freq": (text,),
        "pairs_with_sum": (nums, target),
        "top_k": (topk_items, k),
        "common_prefix_len": (strings,),
    }


FUNCTIONS = {
    "dedupe_preserve_order": dedupe_preserve_order,
    "word_freq": word_freq,
    "pairs_with_sum": pairs_with_sum,
    "top_k": top_k,
    "common_prefix_len": common_prefix_len,
}


def canonical(value):
    if isinstance(value, dict):
        return sorted(value.items())
    if isinstance(value, (list, tuple)):
        return [tuple(x) if isinstance(x, (list, tuple)) else x for x in value]
    return value


def main():
    seed = env_int("SB_SEED", 0)
    size = env_int("SB_BENCH_SIZE", 3000)
    repeats = max(1, env_int("SB_BENCH_REPEATS", 5))

    rng = random.Random(seed)
    inputs = make_inputs(rng, size)

    medians = {}
    outputs = []
    for name, fn in FUNCTIONS.items():
        args = inputs[name]
        times = []
        out = None
        for _ in range(repeats):
            t0 = time.perf_counter()
            out = fn(*args)
            times.append((time.perf_counter() - t0) * 1000.0)
        medians[name] = statistics.median(times)
        outputs.append(canonical(out))

    digest = hashlib.sha256(repr(outputs).encode("utf-8")).hexdigest()[:16]

    for name, ms in medians.items():
        print(f"METRIC {name}_ms={ms:.3f}")
    print(f"METRIC bench_ms={sum(medians.values()):.3f}")
    print(f"METRIC bench_checksum={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
