---
id: docs
title: Docs
expected_diff_size: small
tier: low
default_prior: [1, 6]
---

# docs

Documentation coverage and correctness: docstrings, API reference, broken links, examples that run, navigation. Only useful when a docs metric is a goal (`docs-site` archetype or a docs campaign on any project). Cold prior everywhere else; the bandit should never spend a slot on it when the goals are performance or correctness.

## When to use

- A docs campaign: `broken_links`, `api_doc_coverage`, `nav_snapshot_diff_lines`, or a doctest count is a goal.
- A diagnostic lists public symbols without docstrings, links that 404, examples that do not compile, or pages the nav does not reach.
- A `bugfix` on documentation: a wrong signature, a stale example, a claim the code no longer supports. This is the highest-value docs change and the one a coverage counter cannot see; pre-register it as `docs` with the specific wrong claim.
- Not for: comments in code that no metric reads, and not as filler when other operators are cold.

## How to pre-register

Name the symbol, page, or link set, the change, and the metric it moves with a count ("adds docstrings to the 14 public functions in `parse/` that interrogate lists; `api_doc_coverage: +6.5..7.0`"). For a correctness fix, name the wrong claim and the evidence. Predict `build_failed: 0` and `nav_snapshot_diff_lines: 0` unless the hypothesis is about navigation. Predict the readability diagnostic honestly if long technical text is added.

## Typical targets

| Archetype | Targets |
|---|---|
| docs-site | pages with broken links, undocumented API symbols, stale examples, missing nav entries |
| rust-crate | `//!` and `///` for public items, doctests that compile, `#![deny(missing_docs)]` readiness |
| python-package | docstrings on public functions and classes, README examples that run under doctest |
| node-frontend | component prop docs, storybook entries, README usage |
| service-api | OpenAPI descriptions and examples (the spec file itself is protected; descriptions inside the code's route decorators are artifact) |
| cli-tool | `--help` text, man pages, completion descriptions (subject to the help snapshot guardrail) |
| ml-training / ml-inference | model card, reproduction instructions, metric definitions |
| science-sim | method description, units, reference-case provenance |

## Gaming risks the judge should look for

- Template docstrings: "Docstring for X.", "TODO", the function name repeated. They satisfy every coverage counter. The judge reads a sample; if the added text carries no information beyond the signature, `gamed`.
- Symbols made private (leading underscore, `pub(crate)`, `@internal`) to shrink the denominator instead of documenting them.
- Links deleted instead of fixed; pages deleted instead of repaired; nav entries removed. The nav snapshot and a word-count diagnostic show the shrinkage.
- Readability raised by removing technical content or splitting sentences mechanically.
- A `--help` change that improves the docs metric and fails the help snapshot: correct behaviour is to propose the snapshot update at the human gate, not to regenerate the snapshot (frozen).
- Examples "fixed" by wrapping them in a code fence that is not doctested any more.

## Example hypotheses

```json
{"id": "e0009", "operator": "docs", "target": "mypkg/parse/__init__.py",
 "hypothesis": "The 14 public functions in mypkg.parse have no docstrings; documenting them with parameters, return values, and one example each raises coverage from 71.2% to about 78%.",
 "mechanism": "interrogate lists exactly 14 uncovered public callables in parse/; total public callables is 205, so 14/205 is 6.8 points",
 "predicted": {"api_doc_coverage": "+6.5..7.0", "build_failed": "0", "lint_errors": "0"},
 "expected_diff_size": "small", "est_cost_s": 240}
```

```json
{"id": "e0011", "operator": "docs", "target": "docs/guide/configuration.md",
 "hypothesis": "The configuration guide links to six anchors that were renamed in the 2.0 restructure; pointing them at the new anchors removes six of the nine broken links.",
 "mechanism": "lychee's fail_map lists the six anchors under configuration.md; the targets exist under new ids in docs/reference/settings.md",
 "predicted": {"broken_links": "-6", "build_failed": "0", "nav_snapshot_diff_lines": "0"},
 "expected_diff_size": "tiny", "est_cost_s": 60}
```
