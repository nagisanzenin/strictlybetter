---
id: bugfix
title: Bugfix
expected_diff_size: small
tier: high
default_prior: [2, 3]
---

# bugfix

Fix the root cause of a failing or flaky test, a reproducible wrong output, or a guardrail that fails at baseline. The goal is a correctness metric (`tests_failed`, `golden_diff_lines`, `ref_error`, `error_rate`, `broken_links`). Small diff, high tier: finding the cause is the expensive part and a wrong fix is worse than none.

## When to use

- A correctness metric is the campaign's goal (a repo with failing tests, a pipeline whose golden diff is nonzero, a docs site with broken links).
- A flaky test is quarantined and the profile or ledger points at a real race, an order dependence, or an uninitialized value.
- An earlier experiment revealed a bug (discarded with `regression:<metric>` where the regression turned out to be pre-existing).
- A `test-add` hypothesis in an instrument campaign captured a failure that the next campaign now fixes.
- Not for: making the test pass by editing the test (frozen), or by special-casing the failing input.

## How to pre-register

Name the failing case (test id, ledger id, or reproduction command), the root cause as a mechanism ("the parser treats CRLF as two newlines because the line counter increments on both bytes"), and the fix location. Predict `tests_failed: -1` (or the count of tests that share the cause) and predict no movement on the performance goals, or state the expected cost. If the cause is a guess, say so and predict the fix will be `suspicious` until a `test-add` hypothesis pins the case; the loop prefers the pair.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | off-by-one in slicing, integer overflow in release mode, `unwrap` on user input, platform-specific paths |
| python-package | mutable default arguments, encoding assumptions, timezone-naive datetimes, float equality |
| node-frontend | stale closures, missing effect dependencies, unhandled promise rejections, key collisions |
| service-api | error mapping (500 where 4xx belongs), connection leaks, retry storms, unvalidated input |
| cli-tool | exit codes, stdin handling, terminal width, locale |
| ml-training | off-by-one in the eval split, tokenizer mismatch, shuffling the val set, lr schedule bugs |
| ml-inference | padding and masking errors, dtype mismatches, batch-order leakage |
| science-sim | boundary condition sign errors, unit mismatches, time-step stability, uninitialized ghost cells |
| data-pipeline | join key type mismatch, null handling, duplicate rows on retry |
| docs-site | broken anchors, stale code samples, wrong signatures |

## Gaming risks the judge should look for

- The fix special-cases the failing input (`if input == fixture: return expected`). The holdout catches it later; the judge should catch it now.
- The failing assertion is bypassed rather than satisfied: a broad `try/except`, a `Result` swallowed, an error mapped to success.
- The test now passes because the code under test no longer runs (a feature flag flipped, a branch made unreachable).
- A "fix" that moves the failure to a path the tests do not cover (the bug is still there for other inputs).
- A flaky test "fixed" by a retry loop or a sleep in the implementation, which hides the race and slows the goal.
- Log output or a receipt written by the diff to look like a passing run (the DGM faked-log case); the harness owns receipts.

## Example hypotheses

```json
{"id": "e0003", "operator": "bugfix", "target": "src/reader/lines.rs",
 "hypothesis": "test_crlf_line_numbers fails because the line counter increments on both bytes of CRLF; counting only LF fixes the off-by-one for every CRLF input.",
 "mechanism": "the failing assertion expects line 3 and gets 5 on a 3-line CRLF file; the counter is in next_byte and sees both 0x0D and 0x0A",
 "predicted": {"tests_failed": "-1", "bench_ns": "0", "clippy_warnings": "0"},
 "expected_diff_size": "small", "est_cost_s": 90}
```

```json
{"id": "e0121", "operator": "bugfix", "target": "pipeline/join.py",
 "hypothesis": "golden_diff_lines is 412 at baseline because the customer id is joined as int on one side and str on the other; casting both to str before the join restores the golden output.",
 "mechanism": "the 412 differing lines are all rows whose id has a leading zero; pandas silently converts the CSV column to int64 on the left table only",
 "predicted": {"golden_diff_lines": "-412", "row_count": "0", "runtime_s": "+0..3%"},
 "expected_diff_size": "small", "est_cost_s": 180}
```
