# 00 · Thesis: the universal research loop

**strictlybetter** is a plugin for agentic coders that turns any repository or science project into an optimization problem the agent can work on indefinitely, under a budget, without making the project worse.

The name is the acceptance rule. In Magic: The Gathering a card is *strictly better* than another when it is better in at least one respect and worse in none. In optimization this is Pareto dominance. Every change the loop keeps must be strictly better than the state it replaces, measured on a metric set the change's author could not influence, with the difference exceeding the measured noise of the instrument.

## The problem statement

Karpathy's `autoresearch` (March 2026) showed the shape of the thing: fix a training script, give an agent a five minute budget per run and one number to move, keep what improves the number, discard what does not, repeat overnight. It works because three things were done by hand before the loop started: someone chose the artifact to mutate, someone wrote the measurement, and someone decided what "better" means.

Six months later the pattern has about eighty derivatives (`01-prior-art.md`). The good ones added a noise floor, a worktree per attempt, and a `METRIC name=value` protocol. None of them does all of: discover the metrics from the repo, hold a guard set that must not regress, confirm on a holdout the experimenter never sees, enforce the evaluator boundary in the harness rather than in the prompt, and leave memory a cold-start agent can inherit.

Those three hand-made pieces are exactly what stops the pattern from being universal. A different repo needs a different measurement. A science project has a different notion of "better" than a CLI tool. A brownfield service has a dozen things that must not regress while one thing improves. A greenfield project has nothing to measure at all yet.

The thesis of this project is that the three pieces can be derived rather than hand-written, and that the loop around them can be made honest enough to run unattended:

1. **Orient.** Understand the project well enough to name its archetype, its build/test/bench commands, its constraints, and the paths the loop must never touch.
2. **Instrument.** Discover or build the metrics. Turn each into a *metric card*: a command that emits a number, a direction, a cost, a measured noise floor, and a list of the ways it can be gamed.
3. **Loop.** Hypothesize, experiment in isolation, judge against the noise floor with a confirmation run the experimenter cannot see, keep or discard, write everything down, distill, repeat.
4. **Inherit.** Leave a body of knowledge that lets a cold-start agent (or a human) resume the loop tomorrow without re-learning what failed yesterday.

## Ten claims

The docs in this directory each defend one or more of these.

**C1. The interface is universal, so the loop is universal.** Anything that can be expressed as (mutable artifact, command that emits numbers, direction, guardrails) is in scope: a Rust crate, a Python package, a web frontend, a training script, a simulation with a reference solution, a data pipeline with a golden output. Universality lives in the metric-card interface, not in the loop body. See `07-universality.md`.

**C2. Metric sets are first-class, versioned objects. There is no fixed metric.** A campaign carries a set of goal metrics (optimize), guardrail metrics (must not regress), and diagnostic metrics (observe only). Different campaigns run different sets. The set is chosen at a human gate, then frozen for the campaign. See `02-metrics.md`.

**C3. Noise is handled by a measured floor at screen and an exact test at confirm.** Every metric has an empirically measured noise floor from repeated baseline runs, and at screen an improvement smaller than that floor is not promoted. Acceptance is decided at confirm by an exact paired randomization test on a pre-registered number of interleaved (candidate, head) pairs, at a per-test alpha split over the campaign's experiment budget, so a campaign of null candidates produces a false accept with probability at most alpha. See `04-anti-overfitting.md` and `13-statistical-guarantees.md`.

**C4. Overfitting in a code loop means optimizing the instrument instead of the property.** The defenses are layered because each catches a different class: a noise floor at screen plus an exact paired sign-flip test at confirm, a frozen instrument the experimenter cannot edit, a holdout the experimenter never sees, pre-registration of the hypothesis before the run, and a blind judge that reads the diff for gaming patterns. See `04-anti-overfitting.md`.

**C5. Regression is prevented by a ratchet, not by review.** Once a metric's best value is established, it becomes a floor. The global ratchet is the union of every metric any past campaign ever optimized, so a later perf campaign cannot silently regress an earlier accuracy campaign. The frontier only moves outward. See `02-metrics.md` and `03-loop.md`.

**C6. Cost is controlled with multi-fidelity measurement and bandits over operators.** Cheap screening runs promote to full runs promote to confirmation. Hypothesis classes are bandit arms whose payout is learned per repo. Expensive models are used where judgment is needed; cheap tiers where the work is mechanical. See `05-cost-and-speed.md`.

**C7. Indefinite is not infinite.** The loop runs in campaigns with budgets and plateau detection. When a metric set saturates, the loop escalates exploration, switches metric sets, or declares convergence and stops spending. See `06-search.md`.

**C8. The loop measures itself.** Cost per accepted improvement and wall-clock per accepted improvement are tracked and reported. "Super optimized" is an operational claim only if it is measured. See `05-cost-and-speed.md`.

**C9. Memory is a deliverable.** The ledger (append-only, machine-readable, every experiment) and the inheritance body (distilled, human-readable, what works here and what does not) are outputs of equal rank with the code changes. See `08-memory-and-inheritance.md`.

**C10. Humans sit at the boundaries, not inside the loop.** Humans approve the metric set, scope, budget and protected paths before a campaign, and review the resulting branch after. Inside the campaign there are no questions. See `09-governance.md`.

## What this is not

- Not a test generator, a linter, or a refactoring tool. Those are operators the loop may use.
- Not an autonomous deployer. The loop ends at a branch and a ledger; merging to main and shipping are human acts unless explicitly configured otherwise.
- Not a benchmark chaser. A metric set that can be gamed will be gamed; the design spends most of its complexity making sure that gaming is caught rather than merged.
- Not tied to one agent platform. The deterministic core is a small Python CLI; the agent-facing surface is markdown. Ports to other agentic coders follow the omniplugin playbook.

## Reading order

`00-thesis` → `02-metrics` → `03-loop` → `04-anti-overfitting` → `05-cost-and-speed` → `06-search` → `07-universality` → `08-memory-and-inheritance` → `09-governance` → `01-prior-art` → `10-implementation-plan`. Prior art is placed after the theory deliberately: the design should be judged on its own terms first, then against what exists.
