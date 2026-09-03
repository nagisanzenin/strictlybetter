//! Benchmark for slowcrate. Frozen instrument.
//!
//! Environment:
//!     SB_SEED           u64, default 0       seed for the input generator
//!     SB_BENCH_SIZE     usize, default 30000 problem size n
//!     SB_BENCH_REPEATS  usize, default 5     timed repeats per function; median kept
//!
//! Prints, one per line:
//!     METRIC <fn>_ms=<median ms, 3 decimals>   for each of the four functions
//!     METRIC bench_ms=<sum of the four medians, 3 decimals>
//!     METRIC bench_checksum=<16 hex chars>     FNV-1a 64 of the outputs
//!
//! Run with `cargo run --release --bin bench -q`.

use std::hint::black_box;
use std::time::Instant;

use slowcrate::{common_prefix_len, count_words, dedupe, top_k};

struct Lcg(u64);

impl Lcg {
    fn new(seed: u64) -> Self {
        // Scramble the seed so that seed 0 and seed 1 give unrelated streams.
        let mut lcg = Lcg(seed.wrapping_mul(0x9E3779B97F4A7C15) ^ 0xD1B54A32D192ED03);
        lcg.next_u64();
        lcg
    }

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

    fn word(&mut self, min_len: u64, max_len: u64) -> String {
        let len = min_len + self.below(max_len - min_len + 1);
        (0..len)
            .map(|_| (b'a' + self.below(26) as u8) as char)
            .collect()
    }
}

fn env_usize(name: &str, default: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(default)
}

fn env_u64(name: &str, default: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(default)
}

fn fnv1a(hash: &mut u64, bytes: &[u8]) {
    for &b in bytes {
        *hash ^= u64::from(b);
        *hash = hash.wrapping_mul(0x100000001b3);
    }
}

fn median(mut xs: Vec<f64>) -> f64 {
    xs.sort_by(f64::total_cmp);
    let n = xs.len();
    if n % 2 == 1 {
        xs[n / 2]
    } else {
        (xs[n / 2 - 1] + xs[n / 2]) / 2.0
    }
}

/// Time `f` `repeats` times; return (median ms, last output).
fn timed<T>(repeats: usize, mut f: impl FnMut() -> T) -> (f64, T) {
    let mut times = Vec::with_capacity(repeats);
    let mut out = None;
    for _ in 0..repeats {
        let t0 = Instant::now();
        let result = black_box(f());
        times.push(t0.elapsed().as_secs_f64() * 1000.0);
        out = Some(result);
    }
    (median(times), out.expect("repeats >= 1"))
}

fn main() {
    let seed = env_u64("SB_SEED", 0);
    let n = env_usize("SB_BENCH_SIZE", 30_000);
    let repeats = env_usize("SB_BENCH_REPEATS", 5).max(1);
    let mut rng = Lcg::new(seed);

    // dedupe: n values drawn from n distinct values, so roughly 63% are unique.
    let dedupe_items: Vec<u64> = (0..n).map(|_| rng.below(n as u64 + 1)).collect();

    // count_words: n words drawn from a vocabulary of n / 16 pseudo-words.
    let vocab: Vec<String> = (0..(n / 16).max(1)).map(|_| rng.word(3, 8)).collect();
    let words: Vec<&str> = (0..n)
        .map(|_| vocab[rng.below(vocab.len() as u64) as usize].as_str())
        .collect();
    let text = words.join(" ");

    // top_k: n values, k = 10.
    let topk_items: Vec<u64> = (0..n).map(|_| rng.below(10 * n as u64 + 1)).collect();
    let k = 10;

    // common_prefix_len: n strings sharing a 24-char prefix.
    let prefix = rng.word(24, 24);
    let owned: Vec<String> = (0..n)
        .map(|_| format!("{prefix}{}", rng.word(0, 12)))
        .collect();
    let strings: Vec<&str> = owned.iter().map(String::as_str).collect();

    let mut hash: u64 = 0xcbf29ce484222325;
    let mut total = 0.0;

    let (ms, out) = timed(repeats, || dedupe(&dedupe_items));
    fnv1a(&mut hash, format!("{out:?}").as_bytes());
    println!("METRIC dedupe_ms={ms:.3}");
    total += ms;

    let (ms, out) = timed(repeats, || count_words(&text));
    fnv1a(&mut hash, format!("{out:?}").as_bytes());
    println!("METRIC count_words_ms={ms:.3}");
    total += ms;

    let (ms, out) = timed(repeats, || top_k(&topk_items, k));
    fnv1a(&mut hash, format!("{out:?}").as_bytes());
    println!("METRIC top_k_ms={ms:.3}");
    total += ms;

    let (ms, out) = timed(repeats, || common_prefix_len(&strings));
    fnv1a(&mut hash, format!("{out:?}").as_bytes());
    println!("METRIC common_prefix_len_ms={ms:.3}");
    total += ms;

    println!("METRIC bench_ms={total:.3}");
    println!("METRIC bench_checksum={hash:016x}");
}
