# strictlybetter

**A universal research loop for agentic coders. Every merge is strictly better.**

Point it at a repo or a science project. It works out what the project is, finds or builds the metrics that matter, measures how noisy they are, and then runs experiments under a budget: hypothesize, change, measure, judge, keep or discard, write it down, repeat. It keeps a change only when the change is *strictly better*: better on at least one goal metric by more than the measured noise, worse on nothing, confirmed on a measurement the experimenter never saw.

The name is Magic: The Gathering's term for a card that is better in at least one way and worse in none. In optimization that is Pareto dominance. It is also the loop's only acceptance rule.

## Status

**v0, theory phase (2026-09-03).** The design docs are complete; no code yet. Working name for the repo is `researchloop`; product name is `strictlybetter`. Read `docs/10-implementation-plan.md` for what gets built and in what order.

## Why this exists

Karpathy's `autoresearch` showed that an agent with one metric, a fixed time budget, and a keep-or-discard rule can improve a training script overnight. Six months on there are about eighty derivatives, and a documented casebook of agents gaming them: replacing the model with a search engine, hard-coding per-tournament offsets into `predict_proba`, compiling a C sort behind a Python benchmark. Three things were hand-made for the original to work: the artifact, the measurement, and the definition of "better". strictlybetter derives all three from the project and then makes the loop honest enough to run unattended on anything:

- **Any project.** Rust crate, Python package, web frontend, service, CLI, ML training, simulation with a reference solution, data pipeline. Universality lives in the *metric card* interface: a command that emits a number, a direction, a cost, a measured noise floor, and a list of the ways it can be gamed.
- **No fixed metric.** Each campaign carries its own set of goals, guardrails, and diagnostics. The set is frozen for the campaign, then the next campaign can pick a different one.
- **No regression.** Every metric any campaign ever optimized becomes a permanent guardrail with a ratcheted floor. The project's frontier only moves outward.
- **No overfitting.** Five walls: a measured noise floor with a confirmation run the experimenter never sees, a frozen instrument, a holdout, pre-registration, and a blind judge that reads every promoted diff against a gaming checklist.
- **Cost as a metric.** Multi-fidelity measurement, bandit allocation over hypothesis classes, and model tiering. The loop reports its own cost per accepted improvement.
- **Memory as a deliverable.** An append-only ledger of every experiment and a distilled inheritance body a cold-start agent reads tomorrow.

## The loop in one screen

```
ORIENT       understand the repo → profile.md
INSTRUMENT   discover/build metrics → metric cards, measured sigma, frozen eval hash
             ┌─ HYPOTHESIZE   pre-registered batch, operator mix from the bandit
             │  EXPERIMENT    isolated worktree, screen-fidelity measurement
             │  JUDGE         noise floor → blind judge → full + confirm on holdout
             │  COMMIT        fast-forward campaign branch, ratchet the baseline
             └─ DISCARD       ledger says why; interesting diffs archived
DISTILL      rewrite inheritance.md; continue | explore | switch set | stop
```

Humans sit at two gates: approve the metric set, budget, and protected paths before; review the branch and report after. Inside, no questions.

## Docs

| Doc | What it defends |
|---|---|
| [00 Thesis](docs/00-thesis.md) | The problem, ten claims, what this is not |
| [01 Prior art](docs/01-prior-art.md) | autoresearch, Weco, AlphaEvolve family, DGM, RD-Agent, Ralph, Genetic Improvement; what each got right and left open |
| [02 Metrics](docs/02-metrics.md) | Metric cards, metric sets, the acceptance rule, the global ratchet |
| [03 Loop](docs/03-loop.md) | Seven verbs, on-disk state, invariants, a worked pass |
| [04 Anti-overfitting](docs/04-anti-overfitting.md) | Goodhart's four variants and the five walls |
| [05 Cost and speed](docs/05-cost-and-speed.md) | Six levers and the loop's own meta-metric |
| [06 Search](docs/06-search.md) | Operators, bandits, plateaus, stepping stones, the archive |
| [07 Universality](docs/07-universality.md) | Archetypes, greenfield instrument campaigns, science projects |
| [08 Memory](docs/08-memory-and-inheritance.md) | The ledger and the inheritance body |
| [09 Governance](docs/09-governance.md) | Gates, protected paths, budgets, halts, provenance |
| [10 Implementation plan](docs/10-implementation-plan.md) | Plugin layout, deterministic core, milestones, meta-benchmark, release protocol |
| [11 ML principles](docs/11-ml-principles.md) | The mapping table |
| [Citations](docs/citations.md) | Verified sources for the theory |

## Lineage

Borrowed with attribution, and named in the docs where it matters:

- `autoresearch` (Karpathy): the loop shape, the one-metric fixed-budget discipline. From its ecosystem: the `METRIC name=value` line (pi, codex-autoresearch), the repeated-baseline noise floor (driveline), the screen-confirm-holdout pipeline with a false-promotion budget (autocontext), the backend re-measurement rule (Sindri), the immutable `evaluate.py` and the anomaly breaker (the tennis post-mortem).
- `engram` (this org): the release protocol, the blind assessor, "every gate misses its own bug class".
- `redswarm-decoded` (this org): the inheritance body for cold-start operation.
- `production-grade` (this org): approval gates, receipts.
- `effortmining` (this org): tier-pinned workers, the blind grader, the deterministic harness that the skill shells out to.
- `omniplugin` (this org): the multi-platform port playbook.
- Blum & Hardt's Ladder, Dwork et al.'s reusable holdout, Kohavi's guardrail metrics, Hyperband, MAP-Elites, Manheim & Garrabrant's Goodhart taxonomy: the statistics and search theory.

## Name

`strictlybetter` was chosen from about forty candidates after checking exact-name collisions on GitHub, npm, and PyPI. The agentic-tool namespace is crowded: `escapement`, `anneal`, `ladder`, `pawl`, `athanor`, `kodawari`, `jidoka`, `lamarck`, `labmate`, `ratchetlab` all have same-domain repos. `strictlybetter` has one unrelated 4-star fan site, and the npm and PyPI names are free. Runners-up, in case the name is ever revisited: `kodawari` (Japanese, the uncompromising pursuit of perfection in detail), `empiric`, `prokope` (Stoic Greek for progress), `neverworse`.

## License

MIT.
