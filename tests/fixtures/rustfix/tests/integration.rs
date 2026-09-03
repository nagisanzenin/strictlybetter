//! Integration tests: every public function is cross-checked against a naive
//! reference implementation on seeded random inputs. Frozen instrument.

use slowcrate::{common_prefix_len, count_words, dedupe, top_k};
use std::collections::{BTreeMap, HashSet};

struct Lcg(u64);

impl Lcg {
    fn next_u64(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.0 >> 33
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next_u64() % n
    }
}

fn ref_dedupe(items: &[u64]) -> Vec<u64> {
    let mut seen = HashSet::new();
    items.iter().copied().filter(|x| seen.insert(*x)).collect()
}

fn ref_count_words(text: &str) -> Vec<(String, usize)> {
    let mut map: BTreeMap<String, usize> = BTreeMap::new();
    for w in text.split_whitespace() {
        *map.entry(w.to_string()).or_insert(0) += 1;
    }
    map.into_iter().collect()
}

fn ref_top_k(items: &[u64], k: usize) -> Vec<u64> {
    let mut v = items.to_vec();
    v.sort_by(|a, b| b.cmp(a));
    v.truncate(k);
    v
}

fn ref_prefix(strings: &[&str]) -> usize {
    if strings.is_empty() {
        return 0;
    }
    let chars: Vec<Vec<char>> = strings.iter().map(|s| s.chars().collect()).collect();
    let mut n = 0;
    while let Some(&c) = chars[0].get(n) {
        if !chars.iter().all(|s| s.get(n) == Some(&c)) {
            break;
        }
        n += 1;
    }
    n
}

#[test]
fn dedupe_matches_reference() {
    let mut rng = Lcg(1234);
    for _ in 0..300 {
        let n = rng.below(60) as usize;
        let items: Vec<u64> = (0..n).map(|_| rng.below(16)).collect();
        assert_eq!(dedupe(&items), ref_dedupe(&items), "{items:?}");
    }
}

#[test]
fn count_words_matches_reference() {
    let mut rng = Lcg(99);
    let vocab = ["a", "bb", "ccc", "Dd", "e.", "f", "gg", "h"];
    let seps = [" ", "  ", "\n", "\t"];
    for _ in 0..300 {
        let n = rng.below(40) as usize;
        let sep = seps[rng.below(seps.len() as u64) as usize];
        let words: Vec<&str> = (0..n)
            .map(|_| vocab[rng.below(vocab.len() as u64) as usize])
            .collect();
        let text = words.join(sep);
        assert_eq!(count_words(&text), ref_count_words(&text), "{text:?}");
    }
}

#[test]
fn top_k_matches_reference() {
    let mut rng = Lcg(7);
    for _ in 0..300 {
        let n = rng.below(50) as usize;
        let items: Vec<u64> = (0..n).map(|_| rng.below(200)).collect();
        let k = rng.below(n as u64 + 4) as usize;
        assert_eq!(top_k(&items, k), ref_top_k(&items, k), "{items:?} k={k}");
    }
}

#[test]
fn common_prefix_matches_reference() {
    let mut rng = Lcg(55);
    for _ in 0..300 {
        let n = rng.below(8) as usize;
        let base_len = rng.below(7) as usize;
        let base: String = (0..base_len)
            .map(|_| if rng.below(2) == 0 { 'a' } else { 'b' })
            .collect();
        let owned: Vec<String> = (0..n)
            .map(|_| {
                let extra = rng.below(6) as usize;
                let tail: String = (0..extra)
                    .map(|_| ['a', 'b', 'c'][rng.below(3) as usize])
                    .collect();
                format!("{base}{tail}")
            })
            .collect();
        let strings: Vec<&str> = owned.iter().map(String::as_str).collect();
        assert_eq!(common_prefix_len(&strings), ref_prefix(&strings), "{strings:?}");
    }
}

#[test]
fn dedupe_does_not_reorder_or_lose_values() {
    let items = [9u64, 8, 9, 7, 8, 6];
    let out = dedupe(&items);
    assert_eq!(out, vec![9, 8, 7, 6]);
    let set: HashSet<u64> = items.iter().copied().collect();
    assert_eq!(out.len(), set.len());
}
