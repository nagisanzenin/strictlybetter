//! slowcrate: four small pure functions.
//!
//! Two are written in a slow but correct way and have a well-known faster
//! algorithm (`dedupe`, `count_words`); two are already close to optimal
//! (`top_k`, `common_prefix_len`). The crate is a fixture for the
//! strictlybetter research-loop harness: `src/bin/bench.rs`, `tests/` and
//! `checks.sh` are frozen instruments, everything in this file is fair game.

/// Return the distinct values of `items` in first-occurrence order.
///
/// ```
/// assert_eq!(slowcrate::dedupe(&[3, 1, 3, 2, 1]), vec![3, 1, 2]);
/// ```
pub fn dedupe(items: &[u64]) -> Vec<u64> {
    let mut unique: Vec<u64> = Vec::new();
    for &item in items {
        // Linear scan of the growing result vector.
        if !unique.contains(&item) {
            unique.push(item);
        }
    }
    unique
}

/// Count whitespace-separated words, returned as `(word, count)` pairs sorted
/// by word ascending (byte order). Counting is case-sensitive and punctuation
/// stays attached to its word. Empty or whitespace-only text gives an empty
/// vector.
///
/// ```
/// let counts = slowcrate::count_words("b a b");
/// assert_eq!(counts, vec![("a".to_string(), 1), ("b".to_string(), 2)]);
/// ```
pub fn count_words(text: &str) -> Vec<(String, usize)> {
    let words: Vec<&str> = text.split_whitespace().collect();
    let mut counts: Vec<(String, usize)> = Vec::new();
    for word in &words {
        // Nested scan 1: have we already counted this word?
        if counts.iter().any(|(seen, _)| seen == word) {
            continue;
        }
        // Nested scan 2: count it by rescanning every word.
        let n = words.iter().filter(|w| *w == word).count();
        counts.push((word.to_string(), n));
    }
    counts.sort();
    counts
}

/// Return the `k` largest values of `items` in descending order.
///
/// `k == 0` gives an empty vector; `k >= items.len()` gives every value sorted
/// descending. Equal values are all kept.
///
/// ```
/// assert_eq!(slowcrate::top_k(&[5, 1, 9, 3, 7], 2), vec![9, 7]);
/// ```
pub fn top_k(items: &[u64], k: usize) -> Vec<u64> {
    if k == 0 || items.is_empty() {
        return Vec::new();
    }
    let k = k.min(items.len());
    let mut values = items.to_vec();
    let split = values.len() - k;
    values.select_nth_unstable(split);
    let mut top = values.split_off(split);
    top.sort_unstable_by(|a, b| b.cmp(a));
    top
}

/// Return the length, in chars, of the longest prefix shared by every string.
///
/// An empty slice gives 0; a single string gives its own char count.
///
/// ```
/// assert_eq!(slowcrate::common_prefix_len(&["interview", "internet", "interval"]), 5);
/// ```
pub fn common_prefix_len(strings: &[&str]) -> usize {
    let Some((first, rest)) = strings.split_first() else {
        return 0;
    };
    let mut prefix: Vec<char> = first.chars().collect();
    for s in rest {
        let shared = prefix
            .iter()
            .zip(s.chars())
            .take_while(|(a, b)| **a == *b)
            .count();
        prefix.truncate(shared);
        if prefix.is_empty() {
            break;
        }
    }
    prefix.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dedupe_empty() {
        assert!(dedupe(&[]).is_empty());
    }

    #[test]
    fn dedupe_keeps_first_occurrence_order() {
        assert_eq!(dedupe(&[3, 1, 3, 2, 1, 4, 2]), vec![3, 1, 2, 4]);
    }

    #[test]
    fn dedupe_all_same() {
        assert_eq!(dedupe(&[7, 7, 7]), vec![7]);
    }

    #[test]
    fn count_words_empty_and_whitespace() {
        assert!(count_words("").is_empty());
        assert!(count_words(" \n\t ").is_empty());
    }

    #[test]
    fn count_words_sorted_by_word() {
        let got = count_words("x\ty\nx  y\r\nz");
        assert_eq!(
            got,
            vec![("x".to_string(), 2), ("y".to_string(), 2), ("z".to_string(), 1)]
        );
    }

    #[test]
    fn count_words_case_sensitive_punctuation_kept() {
        let got = count_words("Dog dog dog. Dog");
        assert_eq!(
            got,
            vec![
                ("Dog".to_string(), 2),
                ("dog".to_string(), 1),
                ("dog.".to_string(), 1)
            ]
        );
    }

    #[test]
    fn top_k_edges() {
        assert!(top_k(&[], 3).is_empty());
        assert!(top_k(&[1, 2, 3], 0).is_empty());
        assert_eq!(top_k(&[2, 9, 4], 10), vec![9, 4, 2]);
    }

    #[test]
    fn top_k_duplicates_kept() {
        assert_eq!(top_k(&[5, 5, 1, 5], 2), vec![5, 5]);
        assert_eq!(top_k(&[5, 5, 1, 5], 4), vec![5, 5, 5, 1]);
    }

    #[test]
    fn common_prefix_edges() {
        assert_eq!(common_prefix_len(&[]), 0);
        assert_eq!(common_prefix_len(&["hello"]), 5);
        assert_eq!(common_prefix_len(&[""]), 0);
        assert_eq!(common_prefix_len(&["abc", "", "abd"]), 0);
        assert_eq!(common_prefix_len(&["abc", "xbc"]), 0);
        assert_eq!(common_prefix_len(&["ab", "abc", "abcd"]), 2);
    }

    #[test]
    fn common_prefix_counts_chars_not_bytes() {
        assert_eq!(common_prefix_len(&["naïveté", "naïve", "naïf"]), 3);
    }
}
