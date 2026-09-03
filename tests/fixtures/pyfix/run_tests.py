#!/usr/bin/env python3
"""Run the unittest suite and report METRIC lines. Frozen instrument.

Prints exactly:
    METRIC tests_passed=<n>
    METRIC tests_failed=<n>     (failures + errors)

and always exits 0 so the harness can read the numbers even when the suite
is red. The human-readable runner output goes to stderr.
"""

import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=ROOT)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    passed = result.testsRun - failed - len(result.skipped)
    sys.stderr.write(stream.getvalue())
    sys.stderr.flush()
    print(f"METRIC tests_passed={passed}")
    print(f"METRIC tests_failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
