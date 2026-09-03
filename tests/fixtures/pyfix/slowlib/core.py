"""slowlib.core: five small pure functions.

Three of these are written in a slow but correct way and have a well-known
faster algorithm; two are already close to optimal. The module is a fixture
for the strictlybetter research-loop harness, which asks an agent to make
``bench.py`` faster without breaking ``tests/``.

Public functions:
    dedupe_preserve_order(items)   -> list
    word_freq(text)                -> dict
    pairs_with_sum(nums, target)   -> list of (a, b) tuples
    top_k(items, k)                -> list
    common_prefix_len(strings)     -> int
"""

import heapq


def dedupe_preserve_order(items):
    """Return the distinct elements of ``items`` in first-occurrence order.

    ``items`` may be any iterable of hashable values. The input is never
    modified; a new list is always returned.

    >>> dedupe_preserve_order([3, 1, 3, 2, 1])
    [3, 1, 2]
    """
    unique = []
    for item in items:
        if item not in unique:  # linear scan of the growing result list
            unique.append(item)
    return unique


def word_freq(text):
    """Return ``{word: count}`` for the whitespace-separated words of ``text``.

    Words are compared case-sensitively and punctuation stays attached to its
    word. Keys are inserted in first-occurrence order. Empty or
    whitespace-only ``text`` gives ``{}``.

    >>> word_freq("a b a")
    {'a': 2, 'b': 1}
    """
    words = text.split()
    freq = {}
    for word in words:
        if word not in freq:
            freq[word] = words.count(word)  # full rescan per distinct word
    return freq


def pairs_with_sum(nums, target):
    """Return the distinct value pairs ``(a, b)`` of ``nums`` with ``a + b == target``.

    A pair must come from two *different positions* of ``nums``: ``[3]`` has
    no pair summing to 6, while ``[3, 3]`` has ``(3, 3)``. Every pair is
    normalised so that ``a <= b``, de-duplicated by value, and the result is
    returned as a sorted list of tuples. ``nums`` is never modified.

    >>> pairs_with_sum([1, 4, 2, 3, 3, 5], 6)
    [(1, 5), (2, 4), (3, 3)]
    """
    found = set()
    n = len(nums)
    for i in range(n):
        for j in range(i + 1, n):  # every pair of positions
            if nums[i] + nums[j] == target:
                a, b = nums[i], nums[j]
                found.add((a, b) if a <= b else (b, a))
    return sorted(found)


def top_k(items, k):
    """Return the ``k`` largest elements of ``items`` in descending order.

    ``k <= 0`` gives ``[]``; ``k >= len(items)`` gives every element, sorted
    descending. Equal elements are all kept: ``top_k([5, 5, 1], 2) == [5, 5]``.
    The result always equals ``sorted(items, reverse=True)[:k]``.
    """
    if k <= 0:
        return []
    return heapq.nlargest(k, items)


def common_prefix_len(strings):
    """Return the length of the longest prefix shared by every string in ``strings``.

    An empty sequence gives 0; a single string gives its own length. Lengths
    are counted in code points.

    >>> common_prefix_len(["interview", "internet", "interval"])
    5
    """
    if not strings:
        return 0
    lo = min(strings)
    hi = max(strings)
    length = 0
    for a, b in zip(lo, hi):
        if a != b:
            break
        length += 1
    return length
