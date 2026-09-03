---
id: test-add
title: Test-add
expected_diff_size: small
tier: medium
default_prior: [2, 3]
---

# test-add

Add a test that captures a bug, a missing case, or a property. This operator improves the instrument, not the artifact, so it is legal only when tests are not frozen: in an **instrument campaign** (docs/07 §7.3, where the implementation is frozen instead) or in a campaign whose frozen set deliberately excludes the test directory. In an ordinary optimization campaign the harness rejects it as `integrity` and the bandit must not ask for it.

## When to use

- Instrument campaign with a coverage, mutation-score, or sensitivity goal: the loop is building the metric set the next campaign will use.
- A diagnostic lists an untested public function, a branch no test reaches, or a bug report with a reproduction.
- A previous experiment was discarded as `suspicious` because "the tests do not cover the dropped case": the missing test is the next hypothesis, in an instrument campaign.
- A flaky test needs a deterministic replacement (pair with `bugfix` for the root cause).

## How to pre-register

Name the function or behaviour under test, the case being captured, and what the test would have caught (a ledger id, an issue number, a mutation the current suite does not kill). Predict the instrument metric (`coverage_pct: +0.5..2`, `mutation_score: +1..3`, `tests_collected: +1`) and predict `tests_failed: 0` for a test that captures existing correct behaviour, or `tests_failed: +1` with a paired `bugfix` hypothesis for a test that captures a real bug. A test that asserts nothing is not a hypothesis; the pre-registration should state the assertion.

## Typical targets

| Archetype | Targets |
|---|---|
| rust-crate | property tests (`proptest`) on parsers and codecs, doc tests for public API, regression tests from fuzz findings |
| python-package | parametrized edge cases, hypothesis strategies, error-path tests |
| node-frontend | component behaviour tests, accessibility assertions, snapshot for a stable component |
| service-api | contract tests against the OpenAPI spec, error-status tests, auth edge cases |
| cli-tool | golden-output tests per subcommand, `--help` snapshot, exit-code tests |
| ml-training | shape and dtype tests, a tiny-overfit test (loss goes to zero on 8 examples), determinism test |
| ml-inference | eval-set integrity test (count, checksum), latency smoke test |
| science-sim | conservation test, convergence-order test, reference-case test with tolerance |
| data-pipeline | schema test, golden output test, idempotency test |
| docs-site | link test, nav snapshot |

## Gaming risks the judge should look for

- Coverage without verification: a test that calls the function and asserts `True`, or asserts on the return type only. The judge reads the assertion; if it cannot fail, the verdict is `gamed`.
- A test that encodes the current bug as expected behaviour (asserting the wrong value so the suite stays green).
- Tests that import the module and nothing else, added in bulk to raise a coverage or count goal.
- `xfail`, `skip`, or `#[ignore]` on the new test so it counts as collected without running.
- A test written against the implementation's private helpers so it passes for any refactor and catches nothing.
- In an instrument campaign, a change to the frozen implementation hidden inside a test-support file (a monkeypatch in `conftest.py` that "fixes" the code under test).

## Example hypotheses

```json
{"id": "e0012", "operator": "test-add", "target": "tests/test_dedup.py",
 "hypothesis": "dedup_rows has no test for rows that differ only in trailing whitespace; adding one raises mutation score because the strip() call is currently unkilled.",
 "mechanism": "mutmut reports the mutant that removes .strip() as survived; a two-row case with trailing spaces asserting one output row kills it",
 "predicted": {"mutation_score": "+1..2", "coverage_pct": "+0..0.5", "tests_failed": "0"},
 "expected_diff_size": "small", "est_cost_s": 60}
```

```json
{"id": "e0014", "operator": "test-add", "target": "tests/test_conservation.py",
 "hypothesis": "No test checks energy conservation over a long run; a 1,000-step test on the smallest case with a 1e-8 relative bound turns the conservation diagnostic into a guardrail the next campaign can freeze.",
 "mechanism": "the current baseline drift is 3e-10 over 1,000 steps; the bound leaves two orders of magnitude of headroom so honest solver changes pass and a wrong time step fails",
 "predicted": {"tests_collected": "+1", "tests_failed": "0", "instrument_sensitivity": "+1"},
 "expected_diff_size": "small", "est_cost_s": 120}
```
