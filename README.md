# strictlybetter

**A universal research loop for agentic coders. Every merge is strictly better.**

Point it at a repo or a science project. It works out what the project is, finds or builds the metrics that matter, measures how noisy they are, and then runs experiments under a budget: hypothesize, change, measure, judge, keep or discard, write it down, repeat. It keeps a change only when the change is *strictly better*: better on at least one goal metric by more than the measured noise, worse on nothing, confirmed on a measurement the experimenter never saw, and passed by a judge that never saw the experimenter's reasoning.

The name is Magic: The Gathering's term for a card that is better in at least one way and worse in none. In optimization that is Pareto dominance. It is also the loop's only acceptance rule.

`selftest: 61/61` · engine `scripts/sb.py` 1.0.0 · stdlib only, zero network · 9 platforms

## Install

| Platform | Install | Then |
|---|---|---|
| **Claude Code** | `claude plugin marketplace add nagisanzenin/researchloop` then `claude plugin install strictlybetter@strictlybetter` | `/strictlybetter` in any repo |
| **OpenAI Codex** | `codex plugin marketplace add nagisanzenin/researchloop` then `codex plugin add strictlybetter@strictlybetter` → [INSTALL-CODEX.md](INSTALL-CODEX.md) | `$strictlybetter` |
| **OpenCode** | [INSTALL-OPENCODE-V2.md](INSTALL-OPENCODE-V2.md) | `/strictlybetter` |
| **Hermes** | [INSTALL-HERMES.md](INSTALL-HERMES.md) | `/skill strictlybetter` |
| **Google Antigravity** | `agy plugin install https://github.com/nagisanzenin/researchloop` → [INSTALL-ANTIGRAVITY.md](INSTALL-ANTIGRAVITY.md) | `/strictlybetter` |
| **OpenClaw** | [INSTALL-OPENCLAW.md](INSTALL-OPENCLAW.md) | `/strictlybetter` |
| **Pi** | [INSTALL-PI.md](INSTALL-PI.md) | `/strictlybetter` |
| **DeepSeek Harness** | [INSTALL-DSH.md](INSTALL-DSH.md) | `/strictlybetter` |
| **ZCode** | [INSTALL-ZCODE.md](INSTALL-ZCODE.md) | `/strictlybetter` |

Every port shares the same engine and the same skill text; what differs per platform is how hooks fire. Platforms without a pre-edit hook rely on the gate-time integrity check in `sb submit` instead of the guard; platforms without a Stop hook run cycles with `sb drive`. The honest per-platform verification table is in [docs/12-platforms.md](docs/12-platforms.md).

Requirements: Python 3.10+, git. Nothing else. The engine never touches the network.

## First run

```
/strictlybetter
```

1. **Orient.** An agent reads the repo the way a senior engineer would on day one and writes `.strictlybetter/profile.json`: archetype, verified build/test/bench commands, constraints, protected paths.
2. **Instrument.** An agent reuses your existing instruments (CI, `make test`, benches, eval scripts) before inventing any, and writes one *metric card* per metric: a command that prints a number, a direction, the ways it can be gamed, and a known degradation that must make it worse. The engine measures each card five times, computes its noise floor, and refuses any goal whose minimum detectable effect is above 50% on this machine.
3. **Gate 1.** You pick goals, guardrails, budget, and protected paths from the proposal. That is the last question until the campaign ends.
4. **Loop.** Each cycle: the brief (`sb next`), a pre-registered batch of hypotheses, tiered experimenter agents in isolated worktrees, screening measurement, statistical judgment, a blind judge for anything promising, confirmation on a holdout from a clean checkout, accept (fast-forward the campaign branch, ratchet the baseline) or discard (archive the diff, log why). On Claude Code the Stop hook keeps cycles going until the budget, a plateau, a halt, or `/strictlybetter:stop`.
5. **Gate 2.** The loop ends at a branch `sb/<campaign>`, a ledger, an inheritance body for the next cold start, and a report that is the pull request description. Merging is yours.

State lives in `.strictlybetter/` inside your repo. Nothing is written to your main branch or your working tree; experiments live in `.strictlybetter/wt/<id>/` worktrees.

## Why this exists

Karpathy's `autoresearch` showed that an agent with one metric, a fixed time budget, and a keep-or-discard rule can improve a training script overnight. Six months on there are about eighty derivatives, and a documented casebook of agents gaming them: replacing the model with a search engine, hard-coding per-tournament offsets into `predict_proba`, compiling a C sort behind a Python benchmark. Three things were hand-made for the original to work: the artifact, the measurement, and the definition of "better". strictlybetter derives all three from the project and then makes the loop honest enough to run unattended on anything:

- **Any project.** Rust crate, Python package, web frontend, service, CLI, ML training, simulation with a reference solution, data pipeline. Universality lives in the metric-card interface; eleven archetype packs carry discovery priors.
- **No fixed metric.** Each campaign carries its own goals, guardrails, and diagnostics, frozen for the campaign.
- **No regression.** Every metric any campaign ever optimized becomes a permanent guardrail with a ratcheted floor. The frontier only moves outward.
- **No overfitting.** Five walls: validity plus a measured noise floor plus a confirmation run the experimenter never sees, a frozen instrument enforced by a pre-edit hook and a gate-time hash (not by prompt text), a holdout, structural pre-registration, and a blind judge whose verdict schema has no field for reasoning.
- **Cost as a metric.** Screen, full, confirm fidelity; a bandit over hypothesis classes; tier-pinned experimenters; the loop reports its own cost per accepted improvement.
- **Memory as a deliverable.** An append-only event ledger and a distilled inheritance body a cold-start agent reads tomorrow.

## What the benchmark says

The loop is itself benchmarked (`bench/run_bench.py`; results are written by the engine to `bench/results/` and are the only source of quotable numbers). Three modes:

- **scripted**: a fixed, seeded sequence of 15 scripted experiments (3 real algorithmic wins, 6 no-ops, 6 gaming tricks from the casebook) fed through the real engine under two conditions, `walls` (everything on) and `naive` (the autoresearch-skill shape: one benchmark run, tests as backpressure, no checksum, no evaluator protection). Every accepted commit is then re-validated on fresh seeds with the pristine instrument and an external process timer, so a change that only fooled the loop's own instrument counts as a false accept.
- **gaming**: the six tricks under all walls and with each wall disabled in turn; the matrix names which wall catches which trick.
- **analyze**: the same re-validation for a campaign real agents ran.

The current results files are listed in [CHANGELOG.md](CHANGELOG.md) under the release's "Benchmark" line, with their denominators. Timings there are from one loaded laptop and say so.

## Docs

| Doc | What it defends |
|---|---|
| [00 Thesis](docs/00-thesis.md) | The problem, ten claims, what this is not |
| [01 Prior art](docs/01-prior-art.md) | autoresearch and its ecosystem, Weco, AlphaEvolve family, DGM, RD-Agent, Ralph, Genetic Improvement; positioning; the gaming casebook |
| [02 Metrics](docs/02-metrics.md) | Metric cards, metric sets, the acceptance rule, the global ratchet |
| [03 Loop](docs/03-loop.md) | Seven verbs, on-disk state, invariants |
| [04 Anti-overfitting](docs/04-anti-overfitting.md) | Goodhart's four variants and the five walls, with the engine's constants |
| [05 Cost and speed](docs/05-cost-and-speed.md) | Six levers and the loop's own meta-metric |
| [06 Search](docs/06-search.md) | Operators, bandits, plateaus, the archive |
| [07 Universality](docs/07-universality.md) | Archetypes, greenfield, science projects |
| [08 Memory](docs/08-memory-and-inheritance.md) | The event ledger and the inheritance body |
| [09 Governance](docs/09-governance.md) | Gates, protected paths, budgets, halts, provenance |
| [10 Implementation plan](docs/10-implementation-plan.md) | Layout, engine command surface, driver, milestones with status |
| [11 ML principles](docs/11-ml-principles.md) | The mapping table |
| [12 Platforms](docs/12-platforms.md) | Port ladder and the verification table |
| [Citations](docs/citations.md) | Verified sources for the theory |

Maintainers: [CLAUDE.md](CLAUDE.md), [RELEASE_PROTOCOL.md](RELEASE_PROTOCOL.md), [CHANGELOG.md](CHANGELOG.md).

## Engine in one screen

```
sb init · profile write · card add|probe · baseline · campaign start
sb next → prereg → (agent edits worktree) → submit → measure --fidelity screen → judge
       → judge-payload → (blind judge) → judge-verdict → confirm → accept | discard
sb distill-stats · status · report · budget · stop · ledger · inheritance · guard · doctor · selftest
```

`python3 scripts/sb.py selftest` runs 61 checks including a full campaign on a temporary repo with a planted win, a frozen-path edit, a no-op, and a guardrail regression.

## Lineage

`autoresearch` (Karpathy) and its ecosystem; `engram` (release protocol, blind assessor); `redswarm-decoded` (the inheritance body); `production-grade` (gates, receipts); `effortmining` (tier-pinned workers, the blind grader, the harness the skill shells out to); `omniplugin` (the port ladder). Blum & Hardt's Ladder, Dwork et al.'s reusable holdout, Kohavi's guardrail metrics, Hyperband, MAP-Elites, Manheim & Garrabrant's Goodhart taxonomy.

## Name

`strictlybetter` was chosen from about forty candidates after checking exact-name collisions on GitHub, npm, and PyPI. The agentic-tool namespace is crowded: `escapement`, `anneal`, `ladder`, `pawl`, `athanor`, `kodawari`, `jidoka`, `lamarck`, `labmate`, `ratchetlab` all have same-domain repos. `strictlybetter` has one unrelated 4-star fan site; npm and PyPI are free. Runners-up: `kodawari`, `empiric`, `prokope`, `neverworse`.

## License

MIT.
