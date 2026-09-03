# 07 · Universality: archetypes, greenfield, and science projects

Universality is a property of the interface, not of the loop body. Anything that can be wrapped as (artifact, measurement command, direction, guardrails) is in scope. This document lists how the loop adapts to project archetypes, how it handles projects with no instruments yet, and how it treats science projects.

## 7.1 Archetypes

An archetype is a discovery prior: default metric cards, default protected paths, default operator priors, and known noise sources. A project can match more than one (a Rust service with a Python data pipeline). Archetypes live in `archetypes/*.json` in the plugin, one file per row of the table below, with the fields `id`, `title`, `match` (file, directory, language, and dependency signals), `confidence_notes`, `commands`, `protected_paths`, `frozen_paths_hint`, `default_cards` (complete metric cards with `{{placeholders}}` for the metrologist to fill), `operator_priors`, `hygiene_guardrails`, `noise_sources`, and `notes`. The orienteer matches them from build files and directory shape; the engine never reads a pack directly, it sees only the cards the metrologist adds and the `archetype_priors` the campaign spec carries.

| Archetype | Default goals (candidates) | Default guardrails | Known noise sources |
|---|---|---|---|
| `rust-crate` | criterion benches, compile time, binary size, unsafe count | `cargo test`, `cargo clippy -D warnings`, public API surface (via `cargo public-api`), MSRV build | CPU frequency scaling, incremental cache state |
| `python-package` | test count/pass, coverage, mutation score, import time, benchmark suite | pytest, mypy/pyright errors, ruff | interpreter warm-up, hash randomization |
| `node-frontend` | bundle size, Lighthouse perf/a11y, TTI, test pass | tsc, eslint, unit tests, visual snapshots | network stubs, headless timing |
| `service-api` | p50/p95 latency at fixed RPS, error rate, RSS, cold start | integration tests, contract tests, security scan count | load generator jitter, GC, connection reuse; a database or compose stack the measurement needs is declared once as the campaign's `services` (§7.7) |
| `cli-tool` | startup time, binary size, help completeness, test pass | tests, shell completion, `--help` snapshot | shell startup, disk cache |
| `ml-training` | val loss / bpb / accuracy at fixed budget, tokens/s, peak memory | held-out test split (confirm only), determinism check, train loss sanity | seed, dataloader order, GPU clocks, nondeterministic kernels |
| `ml-inference` | latency, throughput, accuracy on eval set | accuracy floor, memory | batch composition, warm-up |
| `science-sim` | error vs reference solution, wall-clock to convergence, iterations to tolerance | conservation checks, reproducibility across seeds, reference-case match | floating point order, thread count |
| `data-pipeline` | rows/s, end-to-end runtime, cost per run | golden-output diff, schema validation, row counts | I/O contention, cache |
| `docs-site` | link rot, readability, API coverage, build time | build passes, snapshot of nav | none significant |
| `library-generic` | tests, coverage, API stability | build, lint | per-language |

The `TEMM1E`/`skyclaw` project would match `rust-crate` plus `service-api`. A candidate campaign there is compile time and binary size with clippy and the public API as guardrails.

## 7.2 Brownfield: derive, then confirm

Brownfield projects already carry instruments. The orienteer's job is to find them and the metrologist's job is to *reuse* before inventing: an existing `cargo bench`, a `make test`, a CI job that prints a number, a notebook cell with a headline table. Reuse matters for two reasons: the maintainers already trust these numbers, and the noise characteristics have often been implicitly tuned.

After discovery, the human gate shows a proposal: "these are your goals, these are your guardrails, these paths will be frozen, this is the budget". The user edits and confirms. Nothing runs before that.

## 7.3 Greenfield: instrument first

A project with no tests, no benches, and no reference outputs has nothing the loop can optimize honestly. The first campaign is an **instrument campaign**:

- The artifact being improved is the instrument itself (tests, benches, reference fixtures, an eval script).
- The goal metric is instrument quality: `sensitivity / (sigma × cost)` measured by probes, plus coverage of the stated spec.
- Frozen paths are inverted: the instrument is editable, the implementation is frozen. This prevents the loop from making tests pass by changing code during a campaign whose purpose is to build tests.
- The output is a metric set the next campaign can use, plus a human gate to confirm the instrument is measuring what the project actually cares about.

Instrument campaigns are also how brownfield projects add a metric they lack (for example, a service with tests but no latency measurement).

Not in v1.0: an engine-level instrument mode that inverts the roles automatically, and the instrument-quality ratio as a computed metric. An instrument campaign is built by hand in v1.0: the campaign's `frozen_paths` and the cards' `integrity.frozen_paths` list the implementation, the test and bench paths are left unfrozen, and the goal is a card that counts what the instrument covers (the `python-package` pack ships `coverage_pct` as a diagnostic for exactly this).

## 7.4 Science projects

A science project is a repo whose headline output is a number in a paper: an error rate, a convergence time, a fit quality, a reproduction of a published result. The loop treats it as any other archetype with three adjustments:

1. **The reference is the guardrail.** Reproducing the published or expected result within tolerance is a guardrail from the start; nothing that breaks reproduction is accepted, even if it improves the goal.
2. **Holdout is a slice of the problem space.** Confirmation runs use parameter settings, seeds, or datasets the experimenter never saw. A method that only works on the development case is discarded.
3. **Pre-registration is stricter.** The predicted effect must include a mechanism ("reducing the tolerance should cut iterations because the residual is dominated by …"). The distiller carries these mechanisms forward; they become the project's growing understanding, not just its numbers.

For ML training specifically, the loop follows the autoresearch shape (fixed budget per run, one headline metric) but adds the held-out test split as a confirm-only guardrail (a card with `skip: true` at screen and full), the determinism check (an `equal` guardrail), and the noise floor from repeated seeds (an `env` holdout on the confirm level). Most "improvements" found by an unguarded loop on a five-minute training run are seed noise; the noise floor is what makes overnight runs trustworthy.

## 7.5 Non-code artifacts

The artifact does not have to be source code:

- Prompts and agent configurations (measure with a frozen eval set; guardrail on cost and refusal rate).
- Configuration for a build or a deployment (measure build time, image size).
- A dataset filter or a curation script (measure downstream eval; guardrail on dataset size and class balance).

The rule is unchanged: the measurement must be a command the experimenter cannot edit, with a measured noise floor.

## 7.6 What universality costs

- Discovery is heuristic. The archetype table will be wrong for unusual projects; the human gate exists to catch that.
- Some metrics are too noisy on a developer machine (sub-millisecond latency, GPU throughput on a shared box). The loop reports these as unusable rather than pretending (`sb campaign start` halts with `instrument-unusable` when a goal's minimum detectable effect exceeds 50%); a dedicated measurement host is a configuration option, not a requirement.
- Some projects have no cheap fidelity level (a full training run is the only measurement). The loop still works, with fewer, better-chosen hypotheses; the bandit and the diagnostics matter more.

## 7.7 Multi-repo, monorepo, and service-backed projects

A campaign is one git repository: one head commit, one branch, one worktree per experiment. Three campaign spec fields (`02-metrics.md` §2.3) fit that unit to the layouts real projects have.

**External instruments: `external_instruments`.** The harness often lives in a sibling repository: rustc-perf next to rust-lang/rust, lm-evaluation-harness next to a model repo, `redswarm-decoded/bench` next to `redswarm-hand`. The campaign spec lists such paths as absolute paths outside the repo; a card lists its own under `integrity.external_paths`. At `sb campaign start` every path is content-hashed into `campaign.json` under `external_hashes`: a file by its bytes, a directory recursively (skipping `.git`, `__pycache__`, `node_modules`, `target`, `.venv`, `venv`, `.tox`, `.mypy_cache`, `.pytest_cache`, `dist`, `build`). A path that does not exist, or that is inside the repo, is an error at start; inside the repo it belongs under `frozen_paths`. Before every decision (`sb measure` while running, `sb judge`, `sb confirm`, `sb accept`) the hashes are re-checked, and a mismatch halts the campaign with `external-tampered:<path>`. The guard denies any edit under an external instrument while a campaign is running. `sb next --json` lists the merged set as `external_instruments`.

**Scope: `scope_paths`.** A monorepo runs one campaign per package. `scope_paths` is a list of repo-relative patterns (`dir/` prefix, glob, or exact path, the same matcher as frozen paths). When it is non-empty, `sb submit` marks any changed file outside it as the integrity violation `scope:<file>`, and the guard denies edits inside an experiment worktree that fall outside it. Frozen and protected checks run first and still apply. An empty scope, the default, is the whole repo. `sb next --json` lists `scope_paths`.

**Services: `services`.** A measurement that needs a database, a compose stack, or a mock server declares it once instead of in every card's command. The object has `setup`, `ready`, `teardown`, `cwd`, `ready_timeout_s` (default 120), `ready_interval_s` (2), `setup_timeout_s` (600), and `teardown_timeout_s` (300). Campaign-level services are brought up once per measuring command (`sb baseline`, `sb measure`, `sb confirm`, `sb card probe`) around all cards; the same object on a card, `card.services`, is brought up around each measurement of that card. `ready` is polled until it exits 0 or `ready_timeout_s` passes. Commands run in the checkout (or `cwd` under it) with `SB_CHECKOUT` set to the checkout path, so a compose file can mount the code under test. A setup failure or a readiness timeout makes the measurement INVALID (`discard: invalid`, never a crash); `sb baseline` and `sb card probe` refuse to run instead. Teardown always runs, in a `finally`.

**The recommended shape.** One campaign per repo. The other repos are either instruments (`external_instruments`, frozen) or services (`services`, brought up around measurement). A cross-repo atomic experiment, one change spanning two repos, is not supported and is not planned; the industry answer is contracts and versioning, one repo per change. Monorepos run one campaign per package via `scope_paths`.

**Worked example, RedSwarm shape.** The campaign repo is the scanner client. The sibling harness directory is the instrument. The control plane the client talks to is a service, started from a compose file in the client repo that pins the control-plane image by tag. The harness prints `METRIC scan_seconds=…` and `METRIC findings_sha=…`, so the cards are `metric-line:` parsers and need no new code.

```json
{
  "id": "2026-09-03-hand-scan-time",
  "goals": ["scan_seconds"],
  "guardrails": ["findings_sha", "tests_failed"],
  "external_instruments": ["/Users/me/Documents/Github/redswarm-decoded/bench"],
  "scope_paths": [],
  "services": {
    "setup": "docker compose -f \"$SB_CHECKOUT/compose.yml\" up -d --build",
    "ready": "curl -sf localhost:9000/health",
    "teardown": "docker compose -f \"$SB_CHECKOUT/compose.yml\" down -v"
  },
  "budget": {"experiments": 40}
}
```

The `scan_seconds` card runs `python3 /Users/me/Documents/Github/redswarm-decoded/bench/run.py --target http://localhost:9000` from the checkout with `"parse": "metric-line:scan_seconds"` and lists the same harness directory under `integrity.external_paths`; `findings_sha` is an `equal` guardrail with `reuse_output: true` over the same command. An experimenter that edits the harness is denied by the guard. A harness edited from another session halts the campaign as `external-tampered:/Users/me/Documents/Github/redswarm-decoded/bench` before the next decision. A control plane that never answers `/health` makes that measurement invalid, so the candidate is discarded rather than accepted on a missing number. If the control plane itself needs improving, that is a second campaign in its own repo, with the client pinned as its service.
