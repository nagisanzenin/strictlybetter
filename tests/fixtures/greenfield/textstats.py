"""textstats: a few plain-text statistics with no dependencies.

Usage:
    python3 textstats.py <file>

There are no tests and no benchmark yet; this module exists so a research
loop can practise building instruments for code that has none.
"""

import collections
import re
import sys

_WORD_RE = re.compile(r"[A-Za-z']+")
_SENTENCE_RE = re.compile(r"[.!?]+")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")


def counts(text):
    """Return ``(lines, words, chars)`` for ``text``.

    Lines are counted with ``str.splitlines``; words are whitespace-separated
    tokens; chars is the raw length of the text.
    """
    return len(text.splitlines()), len(text.split()), len(text)


def most_common_word(text):
    """Return the most frequent alphabetic word, lower-cased, or ``None``.

    Ties are broken by first occurrence.
    """
    words = _WORD_RE.findall(text.lower())
    if not words:
        return None
    return collections.Counter(words).most_common(1)[0][0]


def syllables(word):
    """Rough syllable estimate: number of vowel groups, at least one."""
    return max(1, len(_VOWEL_GROUP_RE.findall(word.lower())))


def readability_score(text):
    """Flesch reading-ease score for ``text``; higher is easier to read.

    Uses the standard formula 206.835 - 1.015 * (words / sentences)
    - 84.6 * (syllables / words). Returns 0.0 for text with no words.
    """
    words = _WORD_RE.findall(text)
    if not words:
        return 0.0
    sentences = max(1, len(_SENTENCE_RE.findall(text)))
    total_syllables = sum(syllables(w) for w in words)
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (total_syllables / len(words))


def stats(text):
    """Return every statistic as a dict."""
    lines, words, chars = counts(text)
    return {
        "lines": lines,
        "words": words,
        "chars": chars,
        "most_common_word": most_common_word(text),
        "readability": round(readability_score(text), 2),
    }


def main(argv):
    if len(argv) != 1:
        print("usage: textstats.py <file>", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        text = fh.read()
    for key, value in stats(text).items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
