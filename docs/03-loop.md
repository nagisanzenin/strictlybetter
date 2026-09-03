# 03 · The loop: seven verbs and a state machine

The loop is a state machine on disk. Agents perform verbs; the deterministic harness (`sb.py`) owns state transitions, measurement, statistics, and the ledger. An agent never computes a statistic and never writes `baseline.json`.

```
ORIENT ──► INSTRUMENT ──► ┌─► HYPOTHESIZE ─► EXPERIMENT ─► JUDGE ─► COMMIT ─┐
                          │                                    └──► DISCARD ─┤
                          └─────────────── DISTILL ◄───────────────────────┘
                                             │
                    continue | explore:levelN | stop:converged | stop:budget | stop:halted
```

## 3.1 State on disk

```
.strictlybetter/
  profile.json        # the orienteer's profile (archetypes, commands, purpose, constraints, protected paths)
  profile.md          # the same, rendered for humans by `sb profile write`
  metrics/*.json      # metric cards (02-metrics.md)
  campaign.json       # active set, walls, budget, spend, status, branch, eval hash, external_hashes, scope_paths, services, counters
  baseline.json       # per-metric levels {screen|full|confirm}, best, sigma, commit, fingerprint
  ratchet.json        # global ratchet: every past goal's best, sigma, commit, campaign, direction
  bandit.json         # operator-class statistics for this repo (alpha, beta, attempts, accepts, effect_sum, cost_s)
  ledger.jsonl        # append-only, event-sourced: one line per event (08-memory-and-inheritance.md)
  inheritance.md      # distilled knowledge for cold start, written by `sb inheritance write`
  reports/<id>.md     # campaign report, written by `sb report` and at `sb campaign end`
  holdout/<name>/     # `dir`-kind holdout inputs, copied into the clean checkout at confirm only
  wt/<id>/            # experiment worktrees (local)
  archive/<id>.diff   # diffs of interesting discards, for recombination (local)
  inbox/  tmp/        # the only two places an agent may write inside the state home; `sb judge-payload` writes inbox/judge-<id>.json (local)
  cache/              # reserved (local)
  STOP                # presence halts the loop at the next safe point (`sb stop`)
  guard.off           # presence disables the frozen-path guard (also SB_GUARD=off)
  lock  measure.lock  # file locks: mutating commands, timing-sensitive measurement (local)
```

The engine never commits the state home. Its own `.gitignore` excludes `wt/`, `archive/`, `tmp/`, `cache/`, `inbox/`, and the lock files; whether the rest (`ledger.jsonl`, `baseline.json`, `ratchet.json`, `metrics/`, `inheritance.md`, `reports/`) is committed on the campaign branch is the project's choice (`10-implementation-plan.md` §10.9). The `archive/` is referenced from the ledger by experiment id and `archive_key` and is never committed.

## 3.2 The seven verbs

### ORIENT (once per project, refreshed on demand)

Agent: `orienteer`. Reads the repo the way a senior engineer would on day one: build system, languages, entry points, tests, benches, CI, README, recent commits, open issues, existing `CLAUDE.md`/`AGENTS.md`. Produces the profile, stored with `sb profile write --file` (`profile.json`, rendered to `profile.md`):

- archetype(s), with confidence
- verified commands: build, test, lint, bench, run (each executed once to confirm; `sb doctor` re-runs them)
- constraints: toolchain versions, required services, data files, minimum hardware
- protected paths (proposed): eval code, fixtures, CI, secrets, lockfiles, generated code; the engine adds them to its default protected set
- "what this project is for", in two sentences, taken from the project's own words

The engine requires `archetypes`, `commands`, and `purpose`. Orientation ends with the profile shown to the user.

### INSTRUMENT (once per campaign)

Agent: `metrologist`. Turns the profile into candidate metric cards (`02-metrics.md` §2.6), added with `sb card add --file`. Then the harness, not the agent:

1. `sb baseline` runs each card `k` times at the campaign head from a clean throwaway worktree, at every fidelity level the card defines (`k = 5` fixed; `-k` raises it for noisy or cheap metrics), and records median, sigma (1.4826 × MAD for four or more repeats, sample standard deviation for two or three), and seconds per run per level. When the campaign spec declares `services`, `sb baseline` brings them up once around all cards (a card's own `services` around that card) and refuses to run if they never become ready.
2. Quarantines a metric whose confirm-level baseline has no valid median (it failed, timed out, or did not parse). A campaign that lists a quarantined metric, or a goal or guardrail with no measured sigma, halts at start. Not in v1.0: a disagreement bound that quarantines flaky-but-parsing metrics; raise `-k` and read the sigma instead.
3. Runs each card's monotonicity selftest with `sb card probe <id>`: a known degradation must make the metric worse (`02-metrics.md` §2.6). Not in v1.0: engine-run sensitivity probes; the metrologist runs those by hand.
4. `sb campaign start --file` hashes the frozen paths from a clean checkout and every `external_instruments` path in place, and stores the eval hash and `external_hashes` in `campaign.json`.
5. Writes `baseline.json` (and the card's `noise`).

Then the first human gate: the user picks goals, guardrails, budget, and confirms protected paths. `sb campaign start --file campaign.json` writes `campaign.json`, baselines any metric that lacks one at the head commit, computes each goal's minimum detectable effect (halting as `instrument-unusable` when it exceeds 50%, unless `--allow-unusable`), and creates the campaign branch.

### HYPOTHESIZE

Agent: `experimenter` (high-effort tier). Inputs: `sb next` (the cold-start brief: frontier, budget left, exploration level, allowed diff sizes, batch size, operator mix, recent dead ends, accepted wins, archive hints), the profile, the inheritance body, and diagnostics from the last accepted state (profiles, failing tests, hotspots, coverage gaps). Output: a batch of pre-registered hypotheses, each submitted with `sb prereg --file`:

```json
{"operator":"algorithmic","target":"src/parse/lexer.rs",
 "hypothesis":"The lexer re-scans whitespace on every token; a single skip loop should raise throughput.",
 "mechanism":"perf shows 31% of parse time in skip_ws; it is called once per token instead of once per run",
 "predicted":{"bench_throughput":"+5..15%"},
 "expected_diff_size":"small"}
```

The engine requires `operator` (one of the thirteen classes in `06-search.md`), `target`, `hypothesis`, and a non-empty `predicted` naming only metrics in the campaign; `mechanism` and `expected_diff_size` (default `small`) are stored. `sb prereg` assigns the id (`e0001`, `e0002`, …), charges the experiment budget, writes the ledger line, creates the worktree from the campaign head, and returns the id, the worktree path, and the pre-registration hash.

Pre-registration is enforced structurally: there is no worktree without a ledger line. A hypothesis whose diff turns out to target something else is a new hypothesis.

Batch size is set by the cost lever (`05-cost-and-speed.md` §5.7): more, cheaper hypotheses when screening is cheap; fewer when measurement is expensive.

### EXPERIMENT

`sb prereg` already created the worktree under `.strictlybetter/wt/<id>/` from the campaign head. Agent (tier chosen by operator class) implements the hypothesis inside the worktree only; while a campaign runs, the guard hook denies edits anywhere else, and, when the campaign sets `scope_paths`, edits inside the worktree that fall outside them. On completion the harness:

1. `sb submit <id>` commits the worktree and checks integrity: the diff touches no frozen path, no protected path, no `.strictlybetter/` state, no file outside `scope_paths` when they are set (`scope:<file>`), the eval hash is unchanged, and no dependency manifest changed unless the operator is `dependency`. A violation fails the submit (the experiment can only be discarded); two consecutive violations halt the campaign.
2. `sb measure <id> --fidelity screen` measures every goal and guardrail from the worktree, with the card's pinned environment plus `SB_FIDELITY=screen` and `SB_METRIC=<id>`; the campaign's `services` are brought up first when declared, and a setup failure or readiness timeout makes every card invalid.
3. Appends the results to the ledger (`measure` event).

The experimenter sees its screening numbers. It does not see holdout values, confirmation numbers, or other in-flight experiments.

### JUDGE

Three parts, all harness-driven.

**Validity**: before any number is compared, the run must be a run. Exit code zero (unless the card allows otherwise), no timeout, metric parsed, duration inside the card's `expected_duration_s` band, an `equal` metric that agrees with itself across repeats, and, for a minimize-direction metric with a time unit, an instrument that agrees with the process wall-clock (`04-anti-overfitting.md` §4.2). An invalid run is `discard: invalid`, never a candidate. The Gomoku case in `01-prior-art.md` (a "trained" agent reporting zero seconds of training) is the reason this check exists. Each run record keeps the exit code, seconds, value, holdout value, and the tails of stdout and stderr; the commit is on the `submit` event and the environment fingerprint on the baseline. Not in v1.0: a placeholder or constant-output check, and a per-run manifest with a config hash.

**Statistical**: `sb judge <id>` compares the screening numbers to the screen-level baseline with the acceptance rule. Outcomes: `discard` (invalid, a guardrail or goal regressed, or no goal moved and none is positive: `noise`), `promote` (a goal moved beyond κσ, scaled for the repeat counts on each side, `04-anti-overfitting.md` §4.2), or `retry-screen` (a goal is positive but within noise; one more screening pass is cheaper than a lost hypothesis, granted once, after which within-noise is `discard: noise`). With the confirm wall off (the naive benchmark condition) `promote` becomes `accept-naive`.

**Judgment**: for promoted candidates only, the `judge` agent is invoked blind. `sb judge-payload <id>` composes its input file in `inbox/`: the diff, the pre-registration, the screen comparisons, the metric cards' `gaming_risks`, the frozen paths, and the checklist path. It does not receive the experimenter's reasoning or conversation; the payload has no field for them. It answers with a fixed JSON verdict stored by `sb judge-verdict <id> --file`: `clean`, `suspicious` (with the pattern named and a `recommended_check`), or `gamed`. The engine rejects any field outside `verdict`, `pattern`, `evidence`, `recommended_check`. `suspicious` raises the confirmation repeats to the card's `max_repeats`; the `recommended_check` (for example, re-run with a fresh fixture) is for the orchestrator or the human, the engine does not execute it. `gamed` makes `sb confirm` refuse the candidate; two consecutive `gamed` verdicts halt the campaign.

Then `sb confirm <id>` runs, from a clean checkout of the experiment commit, `full` fidelity for every card that defines it (a `discard` there ends the candidate) and then `confirm` fidelity with holdout inputs and repeats. With the `paired` wall on (the default) the campaign head is checked out into a second worktree and measured interleaved with the candidate, ABBA per repeat, and the candidate is compared against that fresh head median rather than the stored baseline (`04-anti-overfitting.md` §4.2). Acceptance is decided on confirmation numbers only. Confirmation has three internal outcomes: `accept`, `discard`, and `inconclusive`. Inconclusive (the confirmation median is inside κσ while the screen was outside it) adds up to two repeats per goal per round up to the card's `max_repeats`; still inconclusive is `discard: noise`. The cap exists because "keep measuring until it wins" is the adaptive querying the Ladder guards against; the campaign's false-promotion budget (`05-cost-and-speed.md` §5.8) counts every promoted candidate that is then discarded, which includes every confirmation that ended inconclusive.

### COMMIT or DISCARD

**Commit**: `sb accept <id>` writes a new commit with the experiment's tree on top of the campaign head (the experiment must be parented on the current head; otherwise it is discarded and re-run on the new head), moves the campaign branch to it, updates `baseline.json` and `ratchet.json`, and appends a provenance block to the commit message (hypothesis, operator, pre-registration hash, per-metric baseline and confirmed value with sigma and threshold, judge verdict, confirmation rounds). Every accepted commit carries its own evidence.

**Discard**: `sb discard <id> --reason R [--archive]` removes the worktree. If the judge or the experimenter marked the attempt as interesting (moved a diagnostic, partial improvement, revealed a constraint), `--archive` saves the diff to `archive/<id>.diff` for recombination. The ledger records why it was discarded in a fixed vocabulary, the reason's prefix must be one of: `noise`, `regression:<metric>`, `integrity`, `gamed`, `build-failed`, `timeout`, `budget`, `invalid`, `harness-error`, `manual`. Without `--reason` the engine takes the confirm or judge reason.

Nothing is ever written to the user's main branch by the loop.

### DISTILL (every D experiments, and at campaign end)

Agent: `distiller`. Reads the ledger since the last distill and rewrites the inheritance body with `sb inheritance write --file` (`08-memory-and-inheritance.md`). The harness updates `bandit.json` at every accept and discard and computes plateau status in `sb distill-stats`. The decision that follows is mechanical:

| Condition | Decision |
|---|---|
| Budget remaining and acceptances within the last `patience` experiments | `continue` |
| No acceptance in `patience` experiments, exploration level < 3 | `explore:levelN` (raise the allowed diff size, `06-search.md`) |
| No acceptance in `patience` more experiments at exploration level 3 | `stop:converged` (the campaign is ended) |
| Budget exhausted in any dimension, or the iteration cap reached | `stop:budget:<dimension>` (the campaign is halted) |
| Integrity violations, `gamed` twice, holdout gap, manual halt, or `STOP` file | `stop:halted` |

Not in v1.0: a `switch-set` decision (end the campaign and propose the next set at a human gate). Ending a campaign and starting the next one with a different set is the orchestrator's or the human's act (`sb campaign end`, then `sb campaign start`).

## 3.3 Invariants the harness enforces

1. `baseline.json` and `ratchet.json` are written by the harness only: a confirmed acceptance ratchets them, `sb baseline` re-measures the noise, and the guard denies the state home to agents.
2. The campaign branch only moves forward, one accepted experiment at a time, each commit parented on the previous head with the experiment's exact tree.
3. Every experiment has a ledger line before it has a worktree, and a worktree before it has a diff.
4. No measurement used for acceptance is taken inside the experimenter's process or worktree state; confirmation is from a clean checkout.
5. Frozen paths, protected paths, state paths, dependency manifests, and the eval hash are checked at `sb submit`; `sb measure` refuses an experiment that failed integrity; the guard hook denies the edits at the tool boundary before that.
6. Budget counters are updated before an experiment starts, not after: `sb prereg` charges the experiment count before creating the worktree, and `sb measure` and `sb confirm` charge wall-clock even when the measurement fails (a crash cannot lose spend).
7. The loop never asks the user a question between the two human gates.

## 3.4 A worked pass

Rust crate, campaign `parse-perf`, goal `bench_throughput`, guardrails tests/clippy/api/binary size.

1. HYPOTHESIZE proposes six hypotheses; bandit favors `algorithmic` and `allocation` operators because the inheritance body notes past wins there.
2. EXPERIMENT runs three in parallel worktrees (machine has cores to spare; the bench is single-threaded and measurement is serialized).
3. Screening: e0042 +11% (κσ = 4.6%), e0043 +2% (noise), e0044 −1% with a clippy warning (regression).
4. e0042 promoted. Judge reads a 38-line diff, finds no gaming pattern. Full: +10.4%. Confirm on holdout seeds, 3 repeats: +9.8%, +10.1%, +10.6%. Guardrails hold. Accepted; `baseline.json` and `ratchet.json` ratchet.
5. e0043 discarded as `noise`; its diff archived because it touched the same function. e0044 discarded as `regression:clippy_warnings`.
6. Ledger has three experiment records; cost so far: 14 minutes, $1.90. Loop continues.
