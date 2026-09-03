"""noisylib: one pure function whose running time is a dial (``WORK_UNITS``).

A calibrated noise-floor fixture for the strictlybetter research loop. See
``noisylib.core`` and the frozen instruments ``bench.py`` / ``run_tests.py``
at the repository root.
"""

from noisylib.core import WORK_UNITS, work

__all__ = ["WORK_UNITS", "work"]
