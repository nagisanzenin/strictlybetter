# 08 · Memory and inheritance

The loop's memory has two layers with different readers. The **ledger** is for machines and audits. The **inheritance body** is for whoever starts the loop tomorrow, agent or human, with an empty context window.

## 8.1 The ledger

`ledger.jsonl`, append-only, one line per experiment, extended in place as phases complete. Fields:

```
id, campaign, ts_start, ts_end,
operator, target, hypothesis, predicted, prereg_hash,
branch, diff_hash, diff_lines, new_deps,
screen: {metric: value}, full: {…}, confirm: {metric: [repeats]},
judge: {verdict, pattern, notes},
verdict: accepted | discarded, reason,
cost: {tokens_in, tokens_out, dollars, wall_s, model_tier},
archived: bool, archive_key
```

Properties:

- Written by the harness only. Agents submit; the harness records.
- Every accepted commit's message contains its ledger line's summary, so `git log` on the campaign branch is a readable experiment history even without the file.
- The ledger is the replay buffer: the bandit, the plateau detector, the cost report, and the distiller all read from it and nothing else.
- Ledgers are committed on the campaign branch. Projects with many campaigns can archive old ledgers; the global ratchet in `baseline.json` carries forward what matters.

## 8.2 The inheritance body

`inheritance.md` is rewritten (not appended) by the distiller at every DISTILL. It is modeled on an operations manual for cold-start use, not on an incident log. Fixed sections:

1. **How to run the loop here.** Verified commands, machine requirements, how long a screen and a confirm take, what to do if a metric is quarantined.
2. **Current frontier.** The best confirmed value of every ratcheted metric, with sigma, and the commit that set it.
3. **What works here.** Operator classes and targets with confirmed effect sizes. "Allocation changes in `parse/` returned +4..12% four times. Config changes never exceeded noise."
4. **Dead ends.** Hypotheses tried and discarded, grouped, with the reason, so they are not retried. Includes the diff hash so an agent can look at what was attempted.
5. **Noise realities.** Which metrics are noisy on this machine, measured sigmas, what quarantine decisions were made, and whether repeats were increased.
6. **Open hypotheses.** Things the loop thinks are promising but has not tried, with why (usually cost or exploration level).
7. **Gotchas.** Environment facts that cost time: a bench that needs a warm cache, a test that needs a service, a flag that silently changes measurement.
8. **Mechanisms (science projects).** The accumulated explanations from pre-registrations that were confirmed.

The distiller writes for a reader with no context. Every claim points to ledger ids. The document should let a new agent produce a good first hypothesis batch within one read.

## 8.3 What is inherited across projects

Some knowledge is not project-specific:

- Archetype priors for the bandit (which operator classes tend to pay off for `rust-crate`).
- Noise floor expectations per metric type (how many repeats criterion needs on a laptop).
- Gaming patterns the judge has seen, as a growing checklist.

These live in the plugin's own data directory, are updated by an explicit `sb distill --global` step, and are never written automatically from a single project. The default is conservative: project memory is rich, global memory is slow-moving.

## 8.4 Memory as regularization

The inheritance body is a prior. It should make the next campaign's first batch better than random, and it should stop the loop from re-running its own failures. It should not become a straitjacket: at exploration level 2 the experimenter is explicitly allowed to revisit dead ends with a new mechanism, because the code has changed since they were recorded.

The ledger is the ground truth. When the inheritance body and the ledger disagree, the ledger wins and the distiller is re-run.

## 8.5 Handing off to humans

At campaign end the loop produces one branch, one ledger, one inheritance body, and a short campaign report:

- goals and their movement (before, after, sigma, number of accepted changes)
- guardrails and their status
- cost: dollars, hours, experiments, cost per accepted improvement
- the list of accepted commits with one line each
- what the distiller recommends next

The report is the pull request description. A reviewer who reads only it should know what changed, how much it helped, how sure the loop is, and what it cost.
