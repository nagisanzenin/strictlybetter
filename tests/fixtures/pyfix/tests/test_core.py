"""Correctness tests for slowlib.core.

Every function gets explicit edge-case tests plus a seeded randomized
cross-check against a deliberately naive reference implementation. The
reference implementations live here, not in slowlib, so that an agent
optimising slowlib cannot change what "correct" means.
"""

import collections
import itertools
import random
import string
import unittest

from slowlib.core import (
    common_prefix_len,
    dedupe_preserve_order,
    pairs_with_sum,
    top_k,
    word_freq,
)

# --------------------------------------------------------------------------
# Reference implementations (naive on purpose)
# --------------------------------------------------------------------------


def ref_dedupe(items):
    return list(dict.fromkeys(items))


def ref_word_freq(text):
    return dict(collections.Counter(text.split()))


def ref_pairs(nums, target):
    found = set()
    for i, j in itertools.combinations(range(len(nums)), 2):
        if nums[i] + nums[j] == target:
            a, b = sorted((nums[i], nums[j]))
            found.add((a, b))
    return sorted(found)


def ref_top_k(items, k):
    return sorted(items, reverse=True)[: max(k, 0)]


def ref_prefix(strings):
    if not strings:
        return 0
    n = 0
    for chars in zip(*strings):
        if len(set(chars)) != 1:
            break
        n += 1
    return n


# --------------------------------------------------------------------------
# dedupe_preserve_order
# --------------------------------------------------------------------------


class TestDedupePreserveOrder(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(dedupe_preserve_order([]), [])

    def test_all_same(self):
        self.assertEqual(dedupe_preserve_order([7, 7, 7, 7]), [7])

    def test_already_unique(self):
        self.assertEqual(dedupe_preserve_order([3, 2, 1]), [3, 2, 1])

    def test_keeps_first_occurrence_order(self):
        self.assertEqual(dedupe_preserve_order([3, 1, 3, 2, 1, 4, 2]), [3, 1, 2, 4])

    def test_mixed_hashables(self):
        data = ["a", 1, None, "a", (1, 2), 1, None, (1, 2), 1.5]
        self.assertEqual(dedupe_preserve_order(data), ["a", 1, None, (1, 2), 1.5])

    def test_accepts_any_iterable(self):
        self.assertEqual(dedupe_preserve_order(iter("abracadabra")), ["a", "b", "r", "c", "d"])

    def test_returns_new_list_and_does_not_mutate(self):
        data = [1, 1, 2]
        out = dedupe_preserve_order(data)
        self.assertIsNot(out, data)
        self.assertEqual(data, [1, 1, 2])
        self.assertIsInstance(out, list)

    def test_randomized_against_reference(self):
        rng = random.Random(1234)
        for _ in range(300):
            n = rng.randint(0, 60)
            data = [rng.randint(0, 15) for _ in range(n)]
            self.assertEqual(dedupe_preserve_order(data), ref_dedupe(data), data)


# --------------------------------------------------------------------------
# word_freq
# --------------------------------------------------------------------------


class TestWordFreq(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(word_freq(""), {})

    def test_whitespace_only(self):
        self.assertEqual(word_freq("   \n\t  "), {})

    def test_basic_counts(self):
        self.assertEqual(word_freq("a b a"), {"a": 2, "b": 1})

    def test_mixed_whitespace(self):
        self.assertEqual(word_freq("x\ty\nx  y\r\nz"), {"x": 2, "y": 2, "z": 1})

    def test_case_sensitive_and_punctuation_kept(self):
        self.assertEqual(word_freq("Dog dog dog. Dog"), {"Dog": 2, "dog": 1, "dog.": 1})

    def test_first_occurrence_key_order(self):
        self.assertEqual(list(word_freq("c b a b c c")), ["c", "b", "a"])

    def test_counts_sum_to_word_total(self):
        text = "the quick brown the lazy the dog quick"
        self.assertEqual(sum(word_freq(text).values()), len(text.split()))

    def test_randomized_against_reference(self):
        rng = random.Random(99)
        vocab = ["".join(rng.choices(string.ascii_lowercase, k=rng.randint(1, 4))) for _ in range(12)]
        for _ in range(300):
            n = rng.randint(0, 40)
            sep = rng.choice([" ", "  ", "\n", "\t"])
            text = sep.join(rng.choice(vocab) for _ in range(n))
            self.assertEqual(word_freq(text), ref_word_freq(text), text)


# --------------------------------------------------------------------------
# pairs_with_sum
# --------------------------------------------------------------------------


class TestPairsWithSum(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(pairs_with_sum([], 5), [])

    def test_single_element_has_no_pair(self):
        self.assertEqual(pairs_with_sum([3], 6), [])

    def test_equal_halves_need_two_positions(self):
        self.assertEqual(pairs_with_sum([3, 3], 6), [(3, 3)])
        self.assertEqual(pairs_with_sum([3, 3, 3], 6), [(3, 3)])

    def test_no_pairs(self):
        self.assertEqual(pairs_with_sum([1, 2, 3], 100), [])

    def test_docstring_example(self):
        self.assertEqual(pairs_with_sum([1, 4, 2, 3, 3, 5], 6), [(1, 5), (2, 4), (3, 3)])

    def test_pairs_are_normalised_and_distinct(self):
        # 5+1 and 1+5 are the same value pair, listed once as (1, 5).
        self.assertEqual(pairs_with_sum([5, 1, 5, 1, 1], 6), [(1, 5)])

    def test_negative_numbers_and_zero_target(self):
        self.assertEqual(pairs_with_sum([-2, 2, 0, 0, 3, -3], 0), [(-3, 3), (-2, 2), (0, 0)])

    def test_output_is_sorted_tuples(self):
        out = pairs_with_sum([9, 1, 8, 2, 7, 3, 6, 4, 5, 5], 10)
        self.assertEqual(out, sorted(out))
        self.assertTrue(all(isinstance(p, tuple) and len(p) == 2 for p in out))
        self.assertEqual(out, [(1, 9), (2, 8), (3, 7), (4, 6), (5, 5)])

    def test_does_not_mutate_input(self):
        data = [4, 2, 6, 2]
        pairs_with_sum(data, 8)
        self.assertEqual(data, [4, 2, 6, 2])

    def test_randomized_against_reference(self):
        rng = random.Random(2024)
        for _ in range(300):
            n = rng.randint(0, 25)
            nums = [rng.randint(-8, 8) for _ in range(n)]
            target = rng.randint(-10, 10)
            self.assertEqual(pairs_with_sum(nums, target), ref_pairs(nums, target), (nums, target))


# --------------------------------------------------------------------------
# top_k
# --------------------------------------------------------------------------


class TestTopK(unittest.TestCase):
    def test_empty_items(self):
        self.assertEqual(top_k([], 3), [])

    def test_k_zero_and_negative(self):
        self.assertEqual(top_k([1, 2, 3], 0), [])
        self.assertEqual(top_k([1, 2, 3], -2), [])

    def test_k_larger_than_input(self):
        self.assertEqual(top_k([2, 9, 4], 10), [9, 4, 2])

    def test_basic(self):
        self.assertEqual(top_k([5, 1, 9, 3, 7], 2), [9, 7])

    def test_duplicates_are_kept(self):
        self.assertEqual(top_k([5, 5, 1, 5], 2), [5, 5])
        self.assertEqual(top_k([5, 5, 1, 5], 4), [5, 5, 5, 1])

    def test_works_on_strings(self):
        self.assertEqual(top_k(["pear", "apple", "zoo", "fig"], 2), ["zoo", "pear"])

    def test_does_not_mutate_input(self):
        data = [3, 1, 2]
        top_k(data, 2)
        self.assertEqual(data, [3, 1, 2])

    def test_randomized_against_reference(self):
        rng = random.Random(7)
        for _ in range(300):
            n = rng.randint(0, 50)
            items = [rng.randint(-100, 100) for _ in range(n)]
            k = rng.randint(-2, n + 3)
            self.assertEqual(top_k(items, k), ref_top_k(items, k), (items, k))


# --------------------------------------------------------------------------
# common_prefix_len
# --------------------------------------------------------------------------


class TestCommonPrefixLen(unittest.TestCase):
    def test_empty_sequence(self):
        self.assertEqual(common_prefix_len([]), 0)

    def test_single_string(self):
        self.assertEqual(common_prefix_len(["hello"]), 5)
        self.assertEqual(common_prefix_len([""]), 0)

    def test_identical_strings(self):
        self.assertEqual(common_prefix_len(["abc", "abc", "abc"]), 3)

    def test_docstring_example(self):
        self.assertEqual(common_prefix_len(["interview", "internet", "interval"]), 5)

    def test_no_common_prefix(self):
        self.assertEqual(common_prefix_len(["abc", "xbc"]), 0)

    def test_one_empty_string_kills_prefix(self):
        self.assertEqual(common_prefix_len(["abc", "", "abd"]), 0)

    def test_prefix_is_a_whole_string(self):
        self.assertEqual(common_prefix_len(["ab", "abc", "abcd"]), 2)

    def test_unicode_code_points(self):
        self.assertEqual(common_prefix_len(["naïveté", "naïve", "naïf"]), 3)

    def test_accepts_tuples(self):
        self.assertEqual(common_prefix_len(("flow", "flower", "flown")), 4)

    def test_randomized_against_reference(self):
        rng = random.Random(55)
        for _ in range(300):
            n = rng.randint(0, 8)
            base = "".join(rng.choices("ab", k=rng.randint(0, 6)))
            strings = [base + "".join(rng.choices("abc", k=rng.randint(0, 5))) for _ in range(n)]
            self.assertEqual(common_prefix_len(strings), ref_prefix(strings), strings)


if __name__ == "__main__":
    unittest.main()
