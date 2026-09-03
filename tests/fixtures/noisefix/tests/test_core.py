"""Correctness tests for noisylib.core.

``work`` is checked against a one-pass reference that lives here, not in
noisylib, so an agent optimising noisylib cannot change what "correct" means.
The reference is a single fold; ``work`` must agree with it whatever
``WORK_UNITS`` is, which also pins ``WORK_UNITS >= 1`` (zero passes never
fold and return 0 for every input).
"""

import random
import unittest

from noisylib import core
from noisylib.core import work


def ref_work(items):
    acc = 0
    for x in items:
        acc = (acc * 31 + x) & 0xFFFFFFFF
    return acc


class TestWork(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(work([]), 0)

    def test_single(self):
        self.assertEqual(work([7]), 7)

    def test_docstring_example(self):
        self.assertEqual(work([1, 2, 3]), 1026)

    def test_wraps_at_32_bits(self):
        items = [0xFFFFFFFF] * 40
        self.assertEqual(work(items), ref_work(items))
        self.assertLess(work(items), 1 << 32)

    def test_order_matters(self):
        self.assertNotEqual(work([1, 2]), work([2, 1]))

    def test_accepts_any_iterable_of_ints(self):
        self.assertEqual(work(range(10)), ref_work(list(range(10))))
        self.assertEqual(work((5, 6)), ref_work([5, 6]))

    def test_does_not_mutate_input(self):
        data = [3, 1, 2]
        work(data)
        self.assertEqual(data, [3, 1, 2])

    def test_work_units_is_a_positive_int(self):
        self.assertIsInstance(core.WORK_UNITS, int)
        self.assertGreaterEqual(core.WORK_UNITS, 1)

    def test_randomized_against_reference(self):
        rng = random.Random(1234)
        for _ in range(60):
            n = rng.randint(0, 40)
            items = [rng.randrange(1 << 20) for _ in range(n)]
            self.assertEqual(work(items), ref_work(items), items)


if __name__ == "__main__":
    unittest.main()
