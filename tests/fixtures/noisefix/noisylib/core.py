"""noisylib.core: one pure function whose cost is a dial.

``work(items)`` folds ``items`` into a 32-bit checksum and repeats that fold
``WORK_UNITS`` times. Every pass computes the same value, so the result depends
only on ``items`` while the running time is proportional to ``WORK_UNITS``.
That makes the module a calibrated noise-floor fixture for the strictlybetter
research-loop harness: an edit that multiplies ``WORK_UNITS`` by ``1 - p`` is a
genuine speedup of exactly ``p`` on the timed work, with byte-identical output,
which is what a power study needs (``bench/run_bench.py --mode power``).

``WORK_UNITS`` must stay at least 1: with zero passes the fold never runs and
``tests/`` fails.

Public functions:
    work(items) -> int      32-bit checksum of ``items``
"""

WORK_UNITS = 1000


def work(items):
    """Return the 32-bit polynomial checksum of ``items`` (ints), computed WORK_UNITS times.

    >>> work([1, 2, 3])
    1026
    """
    acc = 0
    for _ in range(WORK_UNITS):
        acc = 0
        for x in items:
            acc = (acc * 31 + x) & 0xFFFFFFFF
    return acc
