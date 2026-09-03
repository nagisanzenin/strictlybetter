# 03 · The loop: seven verbs and a state machine

The loop is a state machine on disk. Agents perform verbs; the deterministic harness (`sb.py`) owns state transitions, measurement, statistics, and the ledger. An agent never computes a statistic and never writes `baseline.json`.

```
ORIENT ──► INSTRUMENT ──► ┌─► HYPOTHESIZE ─► EXPERIMENT ─► JUDGE ─► COMMIT ─┐
                          │                                    └──► DISCARD ─┤
                          └─────────────── DISTILL ◄───────────────────────┘
                                             │
                               continue | explore | switch-set | stop
```

## 3.1 State on disk

```
.strictlybetter/
  profile.md          # archetype, commands, constraints, protected paths, human notes
  metrics/*.yaml      # metric cards (02-metrics.md)
  campaign.yaml       # active set, budget, status, branch
  baseline.json       # per-metric best confirmed value + sigma + commit
  ledger.jsonl        # append-only: one line per experiment, all phases
  inheritance.md      # distilled knowledge for cold start (08-memory.md)
  archive/            # diffs of interesting discards, for recombination
  bandit.json         # operator-class statistics for this repo
  STOP                # presence halts the loop at the next safe point
```

Everything is committed on the campaign branch except `archive/` (kept local, referenced by hash in the ledger).

## 3.2 The seven verbs

### ORIENT (once per project, refreshed on demand)

Agent: `orienteer`. Reads the repo the way a senior engineer would on day one: build system, languages, entry points, tests, benches, CI, README, recent commits, open issues, existing `CLAUDE.md`/`AGENTS.md`. Produces `profile.md`:

- archetype(s), with confidence
- verified commands: build, test, lint, bench, run (each executed once to confirm)
- constraints: toolchain versions, required services, data files, minimum hardware
- protected paths (proposed): eval code, fixtures, CI, secrets, lockfiles, generated code
- "what this project is for", in two sentences, taken from the project's own words

Orientation ends with the profile shown to the user.

### INSTRUMENT (once per campaign)

Agent: `metrologist`. Turns the profile into candidate metric cards (`02-metrics.md` §2.6). Then the harness, not the agent:

1. Runs each candidate `k` times at the current commit (`k = 5` default, more for noisy metrics) to measure sigma and cost.
2. Quarantines metrics whose repeats disagree beyond a sanity bound (flaky tests, timing on a loaded machine).
3. Runs the probe experiments the metrologist proposed and records sensitivity.
4. Hashes the frozen paths and stores the eval hash.
5. Writes `baseline.json`.

Then the first human gate: the user picks goals, guardrails, budget, and confirms protected paths. `campaign.yaml` is written and the campaign branch is created.

### HYPOTHESIZE

Agent: `experimenter` (high-effort tier). Inputs: profile, inheritance body, the last N ledger entries, bandit statistics, diagnostics from the last accepted state (profiles, failing tests, hotspots, coverage gaps). Output: a batch of pre-registered hypotheses, each:

```json
{"id":"e0042","operator":"algorithmic","target":"src/parse/lexer.rs",
 "hypothesis":"The lexer re-scans whitespace on every token; a single skip loop should raise throughput.",
 "predicted":{"bench_throughput":"+5..15%"},
 "expected_diff_size":"small","est_cost_s":90}
```

Pre-registration is enforced: the ledger line exists before any code changes. A hypothesis whose diff turns out to target something else is a new hypothesis.

Batch size is set by the cost lever (`05-cost-and-speed.md`): more, cheaper hypotheses when screening is cheap; fewer when measurement is expensive.

### EXPERIMENT

Harness creates a worktree from the campaign head (`sb worktree new e0042`). Agent (tier chosen by operator class) implements the hypothesis inside the worktree only. On completion the harness:

1. Checks integrity: diff touches no frozen or protected path; eval hash unchanged.
2. Measures every goal and guardrail at `screen` fidelity from the worktree.
3. Appends results to the ledger.

The experimenter sees its screening numbers. It does not see holdout values, confirmation numbers, or other in-flight experiments.

### JUDGE

Two parts, both harness-driven.

**Statistical**: compare screening numbers to baseline with the acceptance rule. Outcomes: `discard` (no goal moved beyond κσ, or a guardrail broke), `promote` (moved beyond κσ at screen), or `retry-screen` (within noise but predicted large; one more screening repeat is cheaper than a lost hypothesis).

**Judgment**: for promoted candidates only, the `judge` agent is invoked blind: it receives the diff, the metric cards' `gaming_risks`, the pre-registration, and the numbers. It does not receive the experimenter's reasoning or conversation. It answers with a fixed JSON verdict: `clean`, `suspicious` (with the pattern named), or `gamed`. `suspicious` triggers a targeted extra check (for example, re-run with a fresh fixture) rather than an automatic discard.

Then the harness runs `full` and `confirm` fidelity from a clean checkout of the worktree's commit, with holdout inputs. Acceptance is decided on confirmation numbers only.

### COMMIT or DISCARD

**Commit**: fast-forward the campaign branch to the experiment commit; update `baseline.json`; ratchet floors; write the ledger entry's summary into the commit message (hypothesis, effect sizes, sigma, confirmation repeats, judge verdict). Every accepted commit carries its own evidence.

**Discard**: the worktree is removed. If the judge or the experimenter marked the attempt as interesting (moved a diagnostic, partial improvement, revealed a constraint), the diff is saved to `archive/` for recombination. The ledger records why it was discarded in a fixed vocabulary: `noise`, `regression:<metric>`, `integrity`, `gamed`, `build-failed`, `timeout`, `budget`.

Nothing is ever written to the user's main branch by the loop.

### DISTILL (every D experiments, and at campaign end)

Agent: `distiller`. Reads the ledger since the last distill and rewrites `inheritance.md` (`08-memory-and-inheritance.md`). The harness updates `bandit.json` from acceptance outcomes and computes plateau status. The decision that follows is mechanical:

| Condition | Decision |
|---|---|
| Budget remaining and acceptances in the last `patience` experiments | continue |
| No acceptance in `patience` experiments, exploration level < max | explore (raise operator step size, `06-search.md`) |
| No acceptance at max exploration, other metric sets have headroom | switch-set (ends campaign, proposes next at a human gate) |
| No acceptance at max exploration, nothing else has headroom | stop: converged |
| Budget exhausted | stop: budget |
| Integrity violation, harness error streak, or `STOP` file | stop: halted |

## 3.3 Invariants the harness enforces

1. `baseline.json` changes only on a confirmed acceptance.
2. The campaign branch only moves by fast-forward to experiment commits.
3. Every experiment has a ledger line before it has a diff.
4. No measurement used for acceptance is taken inside the experimenter's process or worktree state; confirmation is from a clean checkout.
5. Frozen paths, protected paths, and the eval hash are checked before every measurement.
6. Budget counters are updated before an experiment starts, not after (a crash cannot lose spend).
7. The loop never asks the user a question between the two human gates.

## 3.4 A worked pass

Rust crate, campaign `parse-perf`, goal `bench_throughput`, guardrails tests/clippy/api/binary size.

1. HYPOTHESIZE proposes six hypotheses; bandit favors `algorithmic` and `allocation` operators because the inheritance body notes past wins there.
2. EXPERIMENT runs three in parallel worktrees (machine has cores to spare; the bench is single-threaded and measurement is serialized).
3. Screening: e0042 +11% (κσ = 4.6%), e0043 +2% (noise), e0044 −1% with a clippy warning (regression).
4. e0042 promoted. Judge reads a 38-line diff, finds no gaming pattern. Full: +10.4%. Confirm on holdout seeds, 3 repeats: +9.8%, +10.1%, +10.6%. Guardrails hold. Accepted; baseline ratchets.
5. e0043 discarded as `noise`; its diff archived because it touched the same function. e0044 discarded as `regression:clippy_warnings`.
6. Ledger has three lines; cost so far: 14 minutes, $1.90. Loop continues.
