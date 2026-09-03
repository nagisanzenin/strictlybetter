# strictlybetter

<p align="center">
  <img src="assets/banner.png" alt="strictlybetter — a ratchet that only turns forward: every merge is strictly better" width="100%">
</p>

**Your coding agent improves your repo overnight. Nothing it merges is ever worse.**

Point it at any repo or science project. It figures out what to measure, learns how noisy the measurement is, then runs experiments under a budget you set: propose a change, measure it in an isolated worktree, keep it only if it is *strictly better*, log everything, repeat. In the morning you get a branch, a report, and a memory file for the next run.

*Strictly better* is Magic: The Gathering's term for a card that is better in at least one way and worse in none. It is the loop's only acceptance rule.

`selftest 69/69` · one stdlib Python file, zero network · Claude Code, Codex, OpenCode, Hermes, Antigravity, OpenClaw, Pi, DeepSeek Harness, ZCode

---

## 60-second start

```bash
claude plugin marketplace add nagisanzenin/strictlybetter
claude plugin install strictlybetter@strictlybetter
cd your-repo
claude
```

```
/strictlybetter
```

That is the whole interface. The first run asks you exactly one question (which metrics to optimize, which to protect, how many experiments to spend). Every later run continues the campaign without asking anything.

Other platforms: the same skill text and engine, installed per [Install](#install) below.

---

## What you get

| | |
|---|---|
| A branch `sb/<campaign>` | Only confirmed improvements, one commit each, fast-forward from where you started. Your main branch and working tree are never touched. |
| A report `.strictlybetter/reports/<campaign>.md` | What moved, by how much, how sure the loop is, what it cost. Written to be the pull request description. |
| Provenance in every commit message | Hypothesis, before and after numbers, noise, judge verdict, confirmation repeats. Auditable without any other file. |
| A memory `.strictlybetter/inheritance.md` | What worked, what did not, what is noisy here. The next campaign (or the next agent) starts from it instead of from zero. |
| A ledger `.strictlybetter/ledger.jsonl` | Every experiment, every phase, append-only. |

---

## What happens when you run it

**1. Orient** (once). An agent reads the repo the way a senior engineer would on day one: build system, tests, benches, CI, README, recent commits. It writes a profile and shows it to you.

**2. Instrument** (once per campaign). An agent reuses the instruments you already have before inventing any: your `make test`, your benches, your eval script, your CI jobs. Each becomes a *metric card*: a command that prints a number, which direction is good, the ways it could be gamed, and a known way to make it worse. The engine then measures every card five times at your current commit to learn its noise, and proves each card can detect a deliberate regression. A metric that cannot see a plausible win on your machine is refused, with the reason.

**3. Gate 1: one question.** You see the proposal with real numbers (noise per metric, seconds per run) and pick:

- **Goals**: what to improve.
- **Guardrails**: what must not get worse. Tests passing and lint are always included.
- **Budget**: experiments, hours, or dollars.
- **Protected paths**: what the loop may never edit. CI, secrets, lockfiles, and the instruments themselves are protected by default.

**4. Loop.** Each cycle the engine writes a brief (frontier, budget left, dead ends, which kinds of change have paid off here). The orchestrator writes a batch of pre-registered hypotheses. Experimenter agents implement them in isolated worktrees. Then, for each:

```
screen measure → statistical judgment → blind judge reads the diff
   → confirmation from a clean checkout on inputs the experimenter never saw
   → accept (branch moves, floor ratchets)   or   discard (reason logged, diff archived)
```

On Claude Code the Stop hook keeps cycles going until the budget is spent, the loop plateaus, something needs a human, or you say `/strictlybetter:stop`.

**5. Gate 2.** The loop stops at a branch and a report. Merging is your decision. It never opens a pull request or touches main.

---

## Why it will not fool you

Six months of autoresearch-style loops produced a casebook of agents gaming their own metrics: replacing the model with a search engine and reporting zero training time, hard-coding per-tournament offsets into `predict_proba`, compiling a C sort behind a Python benchmark, editing the test. Every one of those is caught here by construction, not by asking the agent nicely:

| The trick | What stops it |
|---|---|
| Editing the benchmark, the tests, or the fixtures | A pre-edit hook denies the write; a hash of the frozen files is re-checked before every measurement; the metric cards themselves are fingerprinted. |
| A lucky run that looks like a win | Every metric has a measured noise floor. A goal must beat it by 2.5σ. Then it is re-measured from a clean checkout on held-out inputs; the number that promoted it is thrown away. |
| Special-casing the benchmark's inputs or seeds | Confirmation uses seeds and slices the experimenter never saw, rotated every ten accepts. A growing gap between screen and confirm halts the campaign. |
| Making a guardrail a little worse each time | Floors only move in the good direction. A guardrail that slipped keeps its old floor. Every past goal becomes a permanent guardrail. |
| Talking the reviewer into it | The judge sees only the diff, the pre-registration, the numbers, and a checklist. Its verdict schema has no field for reasoning. Two `gamed` verdicts in a row halt the campaign. |
| Printing a fake `METRIC` line from application code | Two lines for one metric is an invalid run. A timing goal that claims 2× faster while the process took the same wall-clock is invalid. |
| Rewriting everything and getting lucky | Larger diffs must clear a higher bar; new dependencies add a full sigma. Only the `dependency` operator may touch a manifest. |
| Quietly spending more than you said | Budget is charged before work starts. Hard caps on experiments, hours, dollars, and iterations. A `STOP` file halts at the next safe point. |

Prompts are advice. Hooks and hashes are walls.

---

## Install

| Platform | Install | Invoke |
|---|---|---|
| **Claude Code** | `claude plugin marketplace add nagisanzenin/strictlybetter` then `claude plugin install strictlybetter@strictlybetter` | `/strictlybetter` |
| **OpenAI Codex** | `codex plugin marketplace add nagisanzenin/strictlybetter` then `codex plugin add strictlybetter@strictlybetter` · [INSTALL-CODEX.md](INSTALL-CODEX.md) | `$strictlybetter` |
| **OpenCode** | [INSTALL-OPENCODE-V2.md](INSTALL-OPENCODE-V2.md) | `/strictlybetter` |
| **Hermes** | [INSTALL-HERMES.md](INSTALL-HERMES.md) | `/skill strictlybetter` |
| **Google Antigravity** | `agy plugin install https://github.com/nagisanzenin/strictlybetter` · [INSTALL-ANTIGRAVITY.md](INSTALL-ANTIGRAVITY.md) | `/strictlybetter` |
| **OpenClaw** | [INSTALL-OPENCLAW.md](INSTALL-OPENCLAW.md) | `/strictlybetter` |
| **Pi** | [INSTALL-PI.md](INSTALL-PI.md) | `/strictlybetter` |
| **DeepSeek Harness** | [INSTALL-DSH.md](INSTALL-DSH.md) | `/strictlybetter` |
| **ZCode** | [INSTALL-ZCODE.md](INSTALL-ZCODE.md) | `/strictlybetter` |

Requirements: Python 3.10+, git. The engine never touches the network.

Platforms differ only in how hooks fire. Without a pre-edit hook, the gate-time integrity check in `sb submit` still rejects a frozen-path edit. Without a Stop hook, `sb drive` runs cycles. The honest per-platform verification table is [docs/12-platforms.md](docs/12-platforms.md); as of 2026-09-03 no platform has a full live-session cycle on record yet.

---

## Commands

| Command | Does |
|---|---|
| `/strictlybetter` | The front door. Orients, instruments, asks the one question, then runs cycles. Run it again to continue. |
| `/strictlybetter:status` | Campaign state, the brief, budget counters. |
| `/strictlybetter:stop` | Halt at the next safe point. `sb campaign resume` to continue after you have looked. |
| `/strictlybetter:distill` | Rewrite the inheritance body from the ledger now. |
| `/strictlybetter:orient`, `:metrics`, `:run` | The individual phases, if you want to drive them by hand. |
| `/strictlybetter:bench` | Benchmark the loop itself (below). |

Everything the skills do goes through one engine you can also run directly:

```bash
python3 scripts/sb.py status        # or: next · report · budget · ledger view <id> · doctor
python3 scripts/sb.py selftest      # 69 checks, including a full campaign on a temp repo
```

`python3 scripts/sb.py --help` is the full command reference.

---

## What projects it works on

Anything that can be expressed as *a command that prints a number, a direction, and things that must not regress*. Eleven archetype packs carry discovery priors and default cards:

Rust crate · Python package · Node frontend · service/API · CLI tool · ML training · ML inference · scientific simulation · data pipeline · docs site · generic library

Examples of goals the packs know how to measure: benchmark throughput, compile time, binary size, bundle size, p95 latency, validation loss at a fixed training budget, error against a reference solution, rows per second. Guardrails: tests, lint, type errors, public API surface, output checksums, a held-out test split, reproduction of a published result.

A greenfield project with no tests or benches yet gets an *instrument campaign* first: the loop builds the measurement before it optimizes anything.

Science projects get three extra rules: reproducing the reference result is a guardrail from the start, confirmation uses parameter settings the experimenter never saw, and every hypothesis must name a mechanism.

---

## Cost

The loop reports its own **cost per accepted improvement** in dollars and minutes, and refuses to spend confirmation-grade measurement on a candidate that has not earned it:

- Cheap screening runs first; only promising candidates get the full and confirmation runs.
- A bandit learns which kinds of change pay off *in this repo* and stops proposing the ones that never do.
- Mechanical edits go to a cheap model tier; judgment goes to a strong one.
- If too many screening winners fail confirmation, the engine distrusts the screening fidelity and raises repeats rather than keep guessing.

Nothing is optimized at the expense of correctness: the noise floor is never lowered to save money, confirmation is never skipped, the judge is never skipped.

---

## Is it actually better than a naive loop?

The loop benchmarks itself (`/strictlybetter:bench` or `python3 bench/run_bench.py`). Three modes:

- **scripted**: 15 scripted experiments (3 real algorithmic wins, 6 no-ops, 6 gaming tricks from the casebook) through the real engine, with every wall on versus the naive autoresearch-skill shape (one benchmark run, tests as backpressure, no evaluator protection). Every accepted commit is then re-validated on fresh seeds with the pristine instrument and an external timer, so a change that only fooled the loop's own instrument counts as a false accept.
- **gaming**: the six tricks under all walls and with each wall removed in turn. The matrix names which wall catches which trick.
- **analyze**: the same re-validation for a campaign real agents ran.

Results are written by the engine to `bench/results/` and are the only source of quotable numbers. The current release's numbers, with their denominators and the machine they came from, are on the "Benchmark" line of [CHANGELOG.md](CHANGELOG.md). Timings are from one laptop and say so.

---

## Docs

Start with [00 Thesis](docs/00-thesis.md), then [02 Metrics](docs/02-metrics.md) and [04 Anti-overfitting](docs/04-anti-overfitting.md).

| | |
|---|---|
| [01 Prior art](docs/01-prior-art.md) | autoresearch and ~80 derivatives, Weco, AlphaEvolve, DGM, RD-Agent, Ralph; the gaming casebook; positioning |
| [03 Loop](docs/03-loop.md) | The seven verbs, on-disk state, invariants |
| [05 Cost](docs/05-cost-and-speed.md) · [06 Search](docs/06-search.md) · [07 Universality](docs/07-universality.md) | Levers, operators, bandits, archetypes, greenfield, science |
| [08 Memory](docs/08-memory-and-inheritance.md) · [09 Governance](docs/09-governance.md) | Ledger, inheritance body, gates, halts, provenance |
| [10 Implementation plan](docs/10-implementation-plan.md) · [11 ML principles](docs/11-ml-principles.md) · [12 Platforms](docs/12-platforms.md) | Layout, engine surface, milestones with status, ML mapping, port ladder |
| [Citations](docs/citations.md) | Verified sources for the theory (the Ladder, reusable holdout, Goodhart taxonomy, Hyperband, MAP-Elites) |

Maintainers: [CLAUDE.md](CLAUDE.md), [RELEASE_PROTOCOL.md](RELEASE_PROTOCOL.md), [CHANGELOG.md](CHANGELOG.md).

---

## Lineage

`autoresearch` (Karpathy) and its ecosystem; `engram` (release protocol, blind assessor); `redswarm-decoded` (the inheritance body); `production-grade` (gates, receipts); `effortmining` (tier-pinned workers, blind grader, the harness the skill shells out to); `omniplugin` (the port ladder). Blum & Hardt's Ladder, Dwork et al.'s reusable holdout, Kohavi's guardrail metrics, Manheim & Garrabrant's Goodhart taxonomy.

The name was chosen from about forty candidates after checking GitHub, npm, and PyPI for collisions. Runners-up: `kodawari`, `empiric`, `prokope`, `neverworse`.

MIT.
