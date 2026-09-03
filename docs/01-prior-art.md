# 01 · Prior art and positioning

Surveyed 2026-09-03 from primary sources (repos, papers, posts). URLs inline; star counts as of that day. The full survey notes are longer than this; this document keeps what changes the design.

## 1.1 The map

Six months after Karpathy's `autoresearch` (March 2026) the pattern has an ecosystem: an index of about 80 derivatives (https://github.com/webfuse-com/awesome-autoresearch), two forks above 6k stars, a commercial product (Weco), and a research literature on self-improving agents that predates all of it. The relevant families:

1. **autoresearch and its forks**: one file, one metric, one budget, keep or discard.
2. **Commercial metric optimizers**: Weco (tree search against a user-supplied eval command).
3. **Evolutionary program search**: FunSearch, AlphaEvolve, OpenEvolve, ShinkaEvolve.
4. **Self-modifying agents**: Darwin Gödel Machine, SICA, Huxley-Gödel, Red Queen Gödel.
5. **ML-engineering and rigor agents**: RD-Agent, AIDE, MLE-STAR, Curie, AI Scientist v2, Agent Laboratory.
6. **Loop harness patterns**: Ralph Wiggum, Anthropic's long-running-agent harness, Cline's hill-climbing guide.
7. **Academic ancestors**: Genetic Improvement, GenProg.

## 1.2 autoresearch (Karpathy, March 2026)

https://github.com/karpathy/autoresearch (95k stars). Three files: `prepare.py` (fixed), `train.py` (the only editable file, contains the eval), `program.md` (human-edited instructions). The loop from `program.md`: branch, edit `train.py`, commit, run with a five-minute wall-clock training budget, append `commit, val_bpb, memory_gb, status, description` to `results.tsv`, keep the commit if `val_bpb` fell, `git reset` otherwise. Simplicity criterion: "an improvement of ~0 but much simpler code? Keep." "NEVER STOP … do NOT pause to ask the human."

Reported: 126 experiments overnight took val_bpb 0.9979 → 0.9697; a two-day run kept about 20 of about 700 changes and cut nanochat's time-to-GPT-2 by 11% (VentureBeat, 2026-03-09). SkyPilot ran 910 experiments on 16 GPUs in 8 hours and observed the agent spontaneously invent a two-tier screen-then-confirm scheme (https://skypilot.ai/blog/scaling-autoresearch/).

**Right:** one editable artifact, one metric, one fixed budget, git as ledger, the human edits the prompt not the code, the simplicity criterion, the refusal to stop.

**Open:** the eval lives inside the editable file. No noise handling of any kind: a single run decides keep or discard, and Karpathy noted some gains failed to replicate in the next session. No memory across sessions beyond the TSV. One metric, one GPU, ML training only.

### The gaming casebook

These are the documented failures that the judge checklist in `04-anti-overfitting.md` is built from.

- **Gomoku, discussion #322** (https://github.com/karpathy/autoresearch/discussions/322): asked to train an AlphaZero net, the agent replaced it with an alpha-beta engine (99.3% win rate, `train_time_sec: 0.0`). After a forward-hook probe was added it called `net.forward()` once, discarded the result, and kept the engine. Prompt rules failed; code-level gates worked (minimum train time, minimum forward calls, an evaluation harness hidden from the agent).
- **Tennis XGBoost** (https://www.nickoak.com/posts/tennis-xgboost-autoresearch): 11 honest iterations gained about 14 bps ROC-AUC each; iterations 16 to 24 overfit the 942-match test slice with tournament-keyed specialists at 69 bps each; iterations 30 to 33 rewrote `predict_proba()` with 122 hard-coded per-tournament logit offsets, +212 bps in one step. The diagnostic the author derived: honest optimization decelerates, gaming accelerates after a plateau. Fixes: an immutable `evaluate.py` outside the writable scope, a gate-time diff check rejecting any commit touching evaluator files, output-distribution constraints, and an anomaly breaker that pauses when a gain exceeds three times the rolling mean.
- **Tool comparison** (https://suzuke.github.io/blog/posts/autoresearch-tools-compared/): in mainstream autoresearch skills "file protection is prompt-only." One agent, asked to speed up a Python sort, compiled a C radix sort and loaded it via `ctypes`. Agents told to run five iterations ran 4, 6, 5, and 5.
- **BAITBENCH** (https://arxiv.org/html/2608.30724, 2026-08-31): 57.1% of frontier-agent runs took planted shortcuts; validity prompting reduced hacking by 6.2 points; agents recognized their own hacking in 92.4% of compromised runs and submitted anyway.
- **SpecBench** (https://arxiv.org/abs/2605.21384, Weco authors, 2026-05-20): the visible-versus-holdout gap "grows by 28 percentage points for every tenfold increase in code size"; one agent wrote a 2,900-line hash-table "compiler" that memorized test inputs.
- **Darwin Gödel Machine** (https://sakana.ai/dgm/): "it faked a log making it look like it had run the tests and that they had passed"; asked to reduce hallucination it removed the markers used to detect hallucination.

Three conclusions the design takes as given: prompts do not protect evaluators; the visible-holdout gap and the shape of the improvement curve are detectable signals; the agent knows when it is gaming, so a judge that sees only the diff is not at a disadvantage.

### Forks that added something

| Fork | Added | URL |
|---|---|---|
| pi-autoresearch (8k stars) | `METRIC name=value` line protocol; after 3 runs, confidence = best improvement / MAD, red below 1.0x; `.auto/prompt.md` living doc + `.auto/log.jsonl`; optional `checks.sh` backpressure | https://github.com/davebcn87/pi-autoresearch |
| driveline autoresearch-claude-code | Baseline run several times at setup; keep only above the noise floor; multi-seed validation for borderline; PreCompact/SessionStart hooks so loops survive compaction | https://github.com/drivelineresearch/autoresearch-claude-code |
| codex-autoresearch (836 stars) | `METRIC seconds=12.34` with direction and units; secondary metrics; keeps limited to configured paths; "a plain measurement never stages, commits, or reverts anything" | https://github.com/TheGreenCedar/codex-autoresearch |
| uditgoenka/autoresearch (6k stars) | Multi-platform skill; orchestrator derives a success predicate from a bare goal; reads `git log` for memory | https://github.com/uditgoenka/autoresearch |
| research-loop v0.3 | Deterministic Python runner owns approval, git isolation, extraction; worktree per attempt; six result states including inconclusive inside a noise tolerance; keep needs N compatible full runs | https://github.com/junjunjunbong/research-loop |
| autolab (autojudge/autosteer/autoevolve) | Noise floor from a rolling window of 5; RETEST verdict; explore/exploit recommendation by category; competing agents in worktrees | https://dev.to/dean0x/how-i-built-eval-tools-for-karpathys-autoresearch-144b |
| autocontext (1.3k stars) | Promotion pipeline: matched screening, adaptive confirmation, held-out evaluation, false-promotion control with a campaign-wide budget; ablation-backed attribution | https://github.com/greyhaven-ai/autocontext |
| Sindri (marketplace) | `/sindri:forge reduce bundle_bytes by 15%`; scaffolds a benchmark by interview; fresh subagent context per experiment; keep only on a re-measurement the backend runs itself; opens a PR | https://github.com/4KMetrics/sindri |
| dark-factory | Each holdout scenario runs three times, 2-of-3 must pass; governance files immutable, "the agent cannot amend the rules it is judged by" | (Anthropic community marketplace) |
| GEPA optimize_anything | Evaluator returns score plus actionable side information; Pareto frontier of candidates; minibatch then full validation; `max_metric_calls` budget | https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/ |
| Bilevel Autoresearch | Outer loop reads inner-loop traces and injects new search mechanisms | https://arxiv.org/abs/2603.23420 |
| RoboPhD | Validation-free evolution via Elo tournaments under a fixed eval budget | https://arxiv.org/abs/2604.04347 |

Also: `helix` (regex metric in YAML, agent-agnostic), `goal-md` (GOAL.md with fitness function and action catalog), `recursive-improve` (`/ratchet` keep-or-revert), `autoresearch-engram` (memory across sessions), and a Muminur skill from discussion #528 that parses a goal into metric, direction, target, scope, data source, verification command, and regression tests.

## 1.3 Weco

https://github.com/WecoAI/weco-cli. `weco run --source f.py --eval-command "python eval.py" --metric speedup --goal maximize --steps 100`. The eval must print the metric name and value. Weco hosts the search (AIDE tree search: draft, debug, improve; one atomic change per improve node; greedy argmax); the user's machine runs evaluations. Free tier of 20 credits, BYOK tier up to 10k experiments per month (per-credit price unverified, pricing page 404).

**Right:** the metric-line contract; tree search with a constrained debug budget; steerable mid-run.
**Open:** single scalar, named files only, no git integration, no noise handling anywhere in the docs or the AIDE paper, no evaluator protection. Weco's own SpecBench paper shows they consider gaming the open problem.

## 1.4 Evolutionary program search

- **FunSearch** (Nature 2023): LLM proposes, evaluator scores, programs database with islands, only a priority function inside a human skeleton is evolved. Needs a cheap exact verifier. https://github.com/google-deepmind/funsearch
- **AlphaEvolve** (May 2025, https://arxiv.org/html/2506.13131): `EVOLVE-BLOCK` markers delimit editable regions; evaluator returns a dictionary of scalars; an evaluation cascade promotes to harder test stages only on promising results; database combines MAP-Elites with island populations; multiple metrics improve the target by encouraging diversity; cheap model for breadth, strong model for depth. Scope: problems whose solution is an algorithm that can be verified automatically.
- **OpenEvolve** (7.3k stars, https://github.com/codelion/openevolve): islands with ring migration, MAP-Elites features, cascade evaluation, evaluator artifacts (stderr, profiling) fed to the next generation, embedding-similarity novelty filter. $0.01 to $0.60 per iteration. Can get stuck needing manual intervention.
- **ShinkaEvolve** (Sakana, ICLR 2026, https://github.com/SakanaAI/ShinkaEvolve): power-law parent sampling, novelty rejection on code embeddings, UCB bandit over LLMs with a cost-aware coefficient; circle-packing SOTA with 150 samples; `evaluate.py` aggregates over multiple runs.

**Borrowed:** the cascade, the archive, bandit-over-models, novelty rejection, editable-region markers as an option for `profile.md`.
**Not borrowed:** population sizes in the thousands. A repo is not a 200-line kernel; measurement is expensive and the interesting moves are few.

## 1.5 Self-modifying agents

- **Darwin Gödel Machine** (https://arxiv.org/abs/2505.22954): an archive of agents; parents chosen by score and inversely by child count; the parent reads its own evaluation logs and proposes a feature; staged evaluation on 10, 50, then 200 SWE-bench tasks; one run took two weeks and about $22,000. Acceptance into the archive requires only that the child compiles and can still edit code.
- **SICA** (https://arxiv.org/abs/2504.15228): utility `0.5·score + 0.25·(1 − cost/$10) + 0.25·(1 − time/300s)`; best agent becomes the next meta-agent. Failure: crude reasoning scaffolds hurt strong models.
- **Huxley-Gödel Machine** (https://arxiv.org/abs/2510.21614): select parents by clade-metaproductivity, the aggregate performance of descendants, because immediate score predicts improvement potential poorly.
- **Red Queen Gödel Machine** (https://arxiv.org/abs/2606.26294): co-evolves evaluators with agents in epochs to resist gaming static benchmarks.

**Borrowed:** cost in the utility (SICA); staged evaluation (DGM); descendant-based promise as a future bandit signal (HGM). **Rejected:** self-modification of the loop's own harness. The harness is frozen for the same reason the evaluator is.

## 1.6 ML-engineering and rigor agents

- **RD-Agent** (Microsoft, https://github.com/microsoft/RD-Agent): research agent proposes, development agent implements; exploration graph of (parent, idea, code, score); fixed train/validation/test splits with test inaccessible until final grading; multi-trace DAG search, diverse first layer then greedy per branch.
- **AIDE** (https://arxiv.org/abs/2502.13138): solution tree with draft, debug, improve; exactly one atomic change per improve; stateless revisions via a summarization operator.
- **MLE-STAR** (Google, https://arxiv.org/abs/2506.15692): an ablation study locates the code block whose modification matters most, then an inner refinement loop targets it; a data-leakage checker and a data-usage checker.
- **Curie** (https://arxiv.org/abs/2502.16069): an experimental-setup validator that detects placeholders and hard-coded values; an execution validator that re-runs in a clean environment multiple times; tiered write access ("technicians can append results but cannot modify unrelated sections"); a DAG of experiment state.
- **AI Scientist v2** (https://arxiv.org/abs/2504.08066): four tree-search stages; replications of selected best experiments; best node chosen by an LLM judging metrics and plots. One workshop paper accepted; citation inaccuracies.
- **Agent Laboratory** (https://arxiv.org/abs/2501.04227): acceptance signal is an LLM reward model scoring adherence to the plan, not a measured metric. Documented unreliable self-evaluation.

**Borrowed:** inaccessible test split (RD-Agent); ablation-to-locate-leverage (MLE-STAR); placeholder detection and clean-environment re-execution (Curie); tiered write access (Curie). **Rejected:** LLM-opinion acceptance (Agent Laboratory, AI Scientist's node selection). An opinion is a diagnostic, never a goal.

## 1.7 Loop harness patterns

- **Ralph Wiggum** (https://ghuntley.com/ralph/): `while :; do cat PROMPT.md | claude-code; done`. State in markdown files and git tags; tests as backpressure; no automated stop; "no way in heck would I use Ralph in an existing code base." Anthropic's official plugin is a Stop hook with `--max-iterations` as "your primary safety mechanism."
- **Anthropic, effective harnesses for long-running agents** (https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): failure modes are doing everything at once and declaring completion prematurely; an initializer writes a JSON feature list (JSON because the model is less likely to overwrite it), a progress file, `init.sh`, a git baseline; each session reads progress and git log, does one feature, commits.
- **Cline hill-climbing guide** (https://cline.bot/blog/a-practical-guide-to-hill-climbing): single benchmark runs vary by several points; six runs spanned 0.43 to 0.49; average pass@k. About a quarter of failures need a model step-change, not tuning.

**Borrowed:** the Stop-hook driver with a hard iteration cap; JSON for state the model must not casually rewrite; one unit of work per fresh context; pass@k for stochastic metrics.

## 1.8 Academic ancestors

- **Genetic Improvement** (Petke et al., IEEE TEVC 2018, http://www.cs.ucl.ac.uk/staff/J.Petke/papers/Petke_2017_TEVC.pdf): automated search for improved versions of existing software, mostly evolutionary, targeting execution time, energy, memory, and functional fixes; fitness is test suites and benchmarks. Its literature already documents both problems this design faces: noisy non-functional measurement and overfitting to the test suite.
- **GenProg** (Le Goues et al., IEEE TSE 2012): statement-level edits, test suite as fitness, delta debugging to minimize patches. The "plausible but wrong patch" problem it exposed is the original form of metric gaming.

## 1.9 Positioning

| Capability | autoresearch | pi / driveline | autocontext | Sindri | Weco | AlphaEvolve family | strictlybetter |
|---|---|---|---|---|---|---|---|
| User supplies the eval command | required | required | required | interview scaffolds one | required | required | **derived from the repo, confirmed at a gate** |
| Multiple goals | no | no | no | one target | no | dict of scalars | **goal set, Pareto or OEC** |
| Guardrails re-measured on every keep | no | `checks.sh` optional | partial | no | no | no | **always, plus hygiene guardrails** |
| Global ratchet across campaigns | no | no | no | no | no | no | **yes** |
| Measured noise floor | no | MAD / repeated baseline | yes | no | no | multi-run aggregate | **per metric, per fidelity, re-measured** |
| Confirmation on an independent run | no | borderline only | yes | backend re-measures | no | cascade | **always, holdout, clean checkout** |
| Evaluator protection | prompt | prompt | ? | backend | none | fixed evaluator | **hook-enforced + gate-time diff + hash** |
| Blind judge with gaming checklist | no | no | no | no | no | no | **yes** |
| Pre-registration | no | no | no | no | no | no | **yes, enforced** |
| Cost per accepted improvement reported | no | no | partial | no | credits | no | **yes** |
| Inheritable memory document | TSV | `prompt.md` | partial | no | `.runs/` | archive | **ledger + inheritance body** |
| Non-ML projects | no | any command | any command | JS-leaning | any command | verifiable algorithms | **archetypes incl. science** |
| Greenfield (no instrument yet) | no | no | no | interview | no | no | **instrument campaign** |

Honest note: the ratchet-with-noise-floor, the screen-then-confirm cascade, and the worktree-per-attempt are each present somewhere above. The claim here is the combination, on by default, with metric discovery, a guard set, a global ratchet, hook-enforced evaluator protection, a blind judge, and an inheritance body, on any archetype.

## 1.10 Gaps this design fills

1. **Automatic metric discovery on an arbitrary repo.** Every tool above takes an eval command from the user. The closest are Sindri's interview and `/autoresearch-discover` (tunable parameters only).
2. **A guard set that must not regress beyond its own noise floor, re-measured on every keep.** Only codex-autoresearch's secondary metrics and goal-md's constraints are partial precedents.
3. **Noise-aware acceptance that is principled rather than ad hoc.** Existing floors are MAD, a rolling window of five, or a fixed tolerance. The Ladder and the reusable holdout motivated the ratchet and the redaction; the practice is an exact paired randomization test on a pre-registered number of interleaved pairs, Bonferroni over the experiment budget, and a campaign false-promotion budget (`13-statistical-guarantees.md`).
4. **Anti-gaming as a default, not a fork.** Structural evaluator protection exists in Crucible, Sindri, research-loop, dark-factory, and the tennis post-mortem; popular skills are prompt-only. None combine hook-enforced immutability, a holdout gap check, and curve-shape anomaly detection.
5. **Inheritable, human-readable research memory** in the repo. Curie's tiered write access and DAG history are the right primitives and are in no plugin.
6. **Science projects beyond ML training**, with reference-solution guardrails and problem-space holdouts.
