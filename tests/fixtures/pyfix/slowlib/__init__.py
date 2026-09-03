"""slowlib: five small pure functions, three of them deliberately slow.

This package is a benchmark fixture for the strictlybetter research loop.
See ``slowlib.core`` for the functions and ``bench.py`` / ``run_tests.py``
at the repository root for the frozen instruments.
"""

from slowlib.core import (
    common_prefix_len,
    dedupe_preserve_order,
    pairs_with_sum,
    top_k,
    word_freq,
)

__all__ = [
    "common_prefix_len",
    "dedupe_preserve_order",
    "pairs_with_sum",
    "top_k",
    "word_freq",
]
