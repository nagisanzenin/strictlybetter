# 10 · Implementation plan

Repo `nagisanzenin/strictlybetter`, product `strictlybetter`, Claude Code first, then the omniplugin port ladder. This plan follows the conventions the sibling plugins (engram, effortmining, dosimeter, production-grade, omniplugin) converged on, so a maintainer of one can maintain this.

## 10.1 Principles inherited from the sibling plugins

1. **The harness computes, the model narrates.** `scripts/sb.py` owns measurement, statistics, ledger, baseline, budget, and every verdict. Skills say "run this and report what it printed; do not paraphrase or round the numbers." (effortmining `effort-bench`, engram `learn`.)
2. **Stdlib-only, zero-network engine**, AST-verified in selftest, `selftest` count as a README badge, `VERSION` constant pinned to `plugin.json` by a selftest. (engram, dosimeter, omniplugin rule R3: the shell is the only universal ABI.)
3. **Blind judgment by construction.** The judge's payload has no field for the experimenter's reasoning, by schema, not by instruction. Its JSON is a proposal; the CLI owns pass/fail. (engram assessor, effortmining grader.)
4. **Hooks degrade to silence and always `exit 0`**, except the frozen-path guard, whose whole purpose is to deny. Hook stdout is a prompt-injection surface; validate before echo. (omniplugin `templates/session-hook.sh`, engram `session-start.sh`.)
5. **One state home** (`.strictlybetter/` in the target repo, `SB_HOME` override), append-only `.jsonl` with idempotency ids, free text via `--file` or stdin never argv, atomic writes, `handlers` dict plus a `mutating` set behind a file lock.
6. **Re-anchor from disk** at every phase: the skill's first block runs `sb status` and `sb next` and trusts them over conversational memory. (engram §0 block, production-grade re-anchoring protocol, redswarm `loop.py open`.)
7. **Constants fixed before data.** κ, τ, patience, λ, promotion fraction live in a constants block with the comment "do not tune these to results." Changes are versioned. (effortmining.)
8. **Every gate misses its own bug class.** The release protocol is copied from engram and adapted, including the post-release independent review with the standing instruction to find a number that is wrong in the direction that reassures.

## 10.2 Repository layout

```
strictlybetter/
  README.md  LICENSE  CHANGELOG.md  RELEASE_PROTOCOL.md  CLAUDE.md
  docs/                         # this theory; docs/00-* is the cold-start doc
  .claude-plugin/plugin.json    # {name: strictlybetter, version, description, author, homepage, keywords}
  .claude-plugin/marketplace.json
  skills/
    strictlybetter/             # front door: status → orient/instrument/gate 1 → run
    orient/  metrics/  run/  status/  distill/  stop/  bench/
    _shared/
      engine-resolution.md      # RUN THIS BLOCK VERBATIM; fails closed
      metric-card.md            # the card schema, for agents that write cards
      ledger.md                 # the ledger contract, for agents that read it
      judge-protocol.md         # payload shape, checklist, verdict JSON
      subagents.md              # items by file path, one child per judgment, no dialogue
  agents/                       # orienteer, metrologist, experimenter ×3 tiers, judge, distiller (10.5)
  hooks/
    hooks.json
    session-start.sh            # SessionStart startup|resume|clear|compact → sb session-start
    frozen-guard.sh             # PreToolUse Edit|MultiEdit|Write|NotebookEdit → sb guard --stdin; exit 2 denies
    pre-compact.sh              # PreCompact → re-pin campaign invariants
    stop-driver.sh              # Stop → sb status --json; continue while running, within iteration_cap
  scripts/
    sb.py                       # the engine
  archetypes/*.json             # discovery priors and default cards per archetype (07-universality.md)
  operators/*.md                # operator library: when to use, tier, expected diff size, default prior
  templates/                    # card.json.tmpl, campaign.json.tmpl, hypothesis.json.tmpl (+ schema),
                                # verdict.json.tmpl (+ schema), profile.md.tmpl (+ schema),
                                # inheritance.md.tmpl, report.md.tmpl, judge-checklist.md
  tests/                        # stdlib unittest for sb.py; fixture repos under tests/fixtures/ (pyfix, rustfix, greenfield)
  bench/                        # meta-benchmark: run_bench.py, results/ (10.7)
  INSTALL-<PLATFORM>.md         # one per port, as ports are verified (10.8); none in 1.0.0
```

Root `commands/` and `agents/` are never added without a namespace-bleed audit (omniplugin pitfall). The Antigravity root `plugin.json` carries `{name, description}` only.

## 10.3 The engine: `scripts/sb.py`

Command surface (each a handler; `mutating` ones take the lock). `--repo` and `--home` select the repository and the state home (`SB_HOME` also works). Free text enters through `--file` (or stdin with `--file -`), never argv.

| Command | Does | Mutating |
|---|---|---|
| `init` | create `.strictlybetter/` and its `.gitignore` | yes |
| `profile write --file` / `profile show` | validate (`archetypes`, `commands`, `purpose`) and store the orienteer's JSON as `profile.json`, rendered to `profile.md` | yes / no |
| `card add --file` / `card list` / `card validate <id>` / `card show <id>` | schema-check and store a metric card (carrying old `noise` and `probe` forward); refuse to change a goal or guardrail card while a campaign runs; `validate` fails a goal or guardrail without measured noise, with a failed probe, or without `gaming_risks` | yes / no |
| `card probe <id> [--repeats]` | monotonicity selftest: apply the card's declared degradation in a throwaway worktree, require the metric to move the wrong way by more than sigma; stores `probe` on the card | yes (card) |
| `baseline [--metric ID] [-k N] [--levels]` | measure at the campaign head from a clean checkout, at every fidelity level the card defines, k = 5 repeats; write `baseline.json` (median, sigma, seconds per run, commit, environment fingerprint) and the card's `noise` | yes |
| `campaign start --file [--allow-unusable]` / `show` / `end [--reason]` / `halt [--reason]` / `resume` | freeze the set, add hygiene guardrails and the global ratchet, hash frozen paths, create the branch, baseline missing metrics, halt on a goal whose minimum detectable effect exceeds 50%; end (report written, worktrees dropped); halt; resume (clears the halt and `STOP`) | yes |
| `next [--json] [--seed]` | the cold-start brief: frontier, budget left, exploration level and allowed diff sizes, batch size, bandit operator mix, dead ends, wins, archive hints, inheritance path, open experiments, walls, minimum detectable effects, `max_parallel`, `distill_every`, `iteration_cap` | no |
| `prereg --file` | validate the hypothesis, charge the experiment budget, write the ledger line, create the worktree; returns the experiment id | yes |
| `submit <id>` | commit the worktree; integrity: frozen, protected, and state paths, eval hash, dependency manifests outside the `dependency` operator; two consecutive failures halt | yes |
| `measure <id> --fidelity screen\|full\|confirm [--repeats] [--keep-runs]` | run every goal and guardrail (and diagnostics above screen); validity checks; parse; append; allowed after a campaign has ended, for reproduction | yes |
| `judge <id> [--fidelity screen\|full]` | statistical verdict: discard / promote / retry-screen / inconclusive; anomaly flag; auto-`clean` verdict when the judge wall is off | yes |
| `judge-payload <id> [--out]` | compose the blind judge's input file (`inbox/judge-<id>.json`): diff, pre-registration, screen comparisons, `gaming_risks`, frozen paths, checklist path; no field for reasoning | no (writes `inbox/`) |
| `judge-verdict <id> --file` | store the blind judge's JSON; exactly `verdict, pattern, evidence, recommended_check`; `gamed` twice halts | yes |
| `confirm <id> [--force]` | clean checkout; full fidelity first, then confirm with holdout and repeats, adaptive up to `max_repeats` | yes |
| `accept <id> [--force]` / `discard <id> [--reason] [--archive]` | new commit on the campaign head with provenance, ratchet, bandit, rotation, gap halt / drop the worktree, optionally archive the diff, plateau counter, bandit | yes |
| `cost <id> --tokens-in --tokens-out [--wall-s] [--dollars] [--tier]` | record an experiment's spend; dollars estimated from the campaign's pricing when not given | yes |
| `distill-stats [--json]` | the stats block plus the decision (`continue`, `explore:levelN`, `stop:converged`, `stop:budget:<dim>`, `stop:halted`); trips `screen_untrusted` | yes |
| `status [--json]` / `report` / `budget` | the stats block, open experiments, head and branch; the campaign report as PR body (`reports/<id>.md`, written without the lock); budget counters | no |
| `guard <path>` / `guard --stdin` | exit 2 if a campaign is running and the path is frozen, protected, state, or outside an experiment worktree; `--stdin` reads the PreToolUse payload | no |
| `session-start` | one line if a campaign is running or halted, otherwise nothing | no |
| `doctor` | version, git, the profile's commands re-run (build or test failure is a problem), every card loads, campaign status | no |
| `selftest` | the badge: AST no-network, version pin to `plugin.json`, parser and acceptance-rule fixtures, guard decisions, a scripted four-experiment campaign on a temporary git repo | no |
| `stop` | write the `STOP` file | yes |
| `ledger view <id> [--unredacted]` / `ledger tail [-n]` / `ledger experiments` | one folded record (redacted for discards) / raw events / one line per experiment | no |
| `inheritance write --file` / `inheritance show` | store the distiller's body (must have `## ` sections); print it | yes / no |
| `worktree new\|drop\|path\|list <id>` | manual worktree management (`prereg` normally creates them) | yes |
| `drive --command "<agent cli>" --cycles N [--timeout] [--verbose]` | run an external agent command once per cycle until the campaign stops | no |

Validity checks inside `measure`: exit code zero (unless the card sets `allow_nonzero_exit`), no timeout, metric parsed, duration inside the card's `expected_duration_s` band, an `equal` metric that agrees with itself across repeats; and, at judge time, the instrument-versus-wall-clock divergence check for minimize-direction metrics with a time unit. Each run record keeps the exit code, seconds, value, holdout value, and output tails; the commit is on the `submit` event and the environment fingerprint on the baseline. Not in v1.0: a placeholder or constant-output check and a per-run manifest with a config hash.

Metric parsing supports `regex:` (last match, first capture group), `json:` dotted path into the stdout JSON, and `metric-line:` (the last `METRIC name=value` line, the convention of the autoresearch ecosystem, for compatibility with existing benches). A card's `expected_duration_s` must be a two-number list; a placeholder string is ignored.

## 10.4 The driver: how the loop runs unattended on Claude Code

Claude Code has no per-spawn effort parameter and a context window that rots. The driver design keeps the orchestrating session small and every experiment in fresh context:

1. `/strictlybetter` (front door) runs `sb status`. If no profile: orient. If no campaign: instrument, then gate 1 as one structured question with the recommended set first. If a campaign is running: one cycle.
2. **One cycle** = `sb next` → `sb prereg --file` per hypothesis → spawn one experimenter subagent per hypothesis (tier from the operator class; hypothesis, profile, inheritance body and archive hints passed **by file path**) → each returns `DONE <id>` or `BLOCKED: <reason>` → `sb submit <id>`, `sb measure <id> --fidelity screen`, `sb judge <id>` → for promoted: `sb judge-payload <id>`, spawn `sb-judge` blind on that file, `sb judge-verdict <id> --file`, `sb confirm <id>`, `sb accept <id>` or `sb discard <id> --reason` → every `distill_every` experiments `sb distill-stats` and the distiller (`sb inheritance write --file`).
3. **Continuation**: the Stop hook checks `sb status --json`; while `status == running`, budget remains, `STOP` is absent, and its per-session counter is below the campaign's `iteration_cap` (default 200), it re-injects "run one more cycle" (the Ralph pattern; the cap is the primary safety, the budget the second, the `STOP` file the third). A no-progress guard stops it after three continuations without a new experiment; `SB_DRIVER=off` disables it for a shell.
4. **Compaction**: the PreCompact hook re-pins the campaign id, the frozen paths, and the sentence "you never compute a statistic and never write baseline.json" so they survive summarization (dosimeter's pins, driveline's rehydration).
5. **Headless**: `sb drive --command "<agent cli>" --cycles N` runs the given command (for example a `claude -p` invocation of the run skill) once per cycle while the campaign is running and no `STOP` file exists, for overnight or CI use; each cycle starts from disk, so no context is shared between cycles by design.

The frozen-path guard is a PreToolUse hook: during a campaign, an edit to a frozen or protected path, to the state home, or to any path outside an experiment worktree, is denied at the tool boundary with a one-line reason (`sb guard --stdin`, exit 2). Integrity at `sb submit` runs regardless, for platforms without pre-edit hooks.

## 10.5 Agents

| Agent | Effort | Sees | Returns |
|---|---|---|---|
| `sb-orienteer` | high | the repo; runs build/test/bench once each | profile JSON via `--file` |
| `sb-metrologist` | high | profile, archetype pack, existing CI | candidate cards with `gaming_risks` and a degradation recipe for the monotonicity probe |
| `sb-experimenter-{low,medium,high}` | pinned | one pre-registered hypothesis, profile, inheritance body, archive hints, its worktree; **not** other experiments, holdout, confirm numbers | `DONE` or `BLOCKED` |
| `sb-judge` | medium, Read only | diff, pre-registration, screen numbers, affected cards' `gaming_risks`, the checklist | fixed verdict JSON |
| `sb-distiller` | high | ledger slice, current inheritance body, `distill-stats` output | new inheritance body via `--file` |

Experimenter agents are byte-identical except `effort:` frontmatter (effortmining pattern). The judge's payload schema has no field for reasoning text.

## 10.6 Milestones

| # | Milestone | Exit criterion | Status at 1.0.0 |
|---|---|---|---|
| M0 | Theory, name, repo (done 2026-09-03) | docs 00–11 and citations in the repo | done |
| M1 | **Engine**: `sb.py` with cards, baseline, worktrees, measure, judge, confirm, accept/discard, ledger, status, next, selftest; two fixture repos (a Python package with a slow function and tests; a Rust crate with a criterion bench and clippy) | A **scripted, LLM-free** experimenter drives a full campaign on both fixtures; ledger, baseline, report produced; every selftest check mutation-tested (revert the fix, the check goes red) | shipped: engine, `pyfix`, `rustfix`, and `greenfield` fixtures, stdlib `unittest` suite, selftest with a scripted campaign; mutation-testing of every check is a release-protocol gate, receipts in CHANGELOG |
| M2 | **Claude Code plugin v0.1**: skills, agents, hooks, gate 1, one-cycle driver, Stop-hook continuation | Ten real experiments on the Python fixture end to end; then dogfood on `dosimeter` (stdlib engine, tests; goals: selftest wall-clock, import time) in a copy of the repo, never the installed plugin; ≥ 1 confirmed acceptance, 0 guardrail regressions; post-release review finds nothing that reassures falsely | hooks and skills ship in 1.0.0; the ten-experiment run and the dosimeter dogfood are open until their receipts are in CHANGELOG |
| M3 | **Walls**: frozen-path guard hook, eval hash, holdout rotation, blind judge with the casebook checklist, validity gate, anomaly breaker, pre-registration enforcement, instrument campaign mode | A scripted **gaming experimenter** attempts every casebook trick (evaluator edit, test skip, input special-case, benchmark narrowing, hard-coded outputs, ctypes escape, zero-duration run, faked log); each is caught by a named wall; removing any single wall lets at least one trick through (the walls are mutation-tested too) | shipped: eight wall toggles, guard hook, eval hash, holdout rotation (`env` and `arg` kinds), judge-verdict schema, validity gate with the wall-clock divergence check, anomaly breaker, structural pre-registration; `bench/run_bench.py --mode gaming` is the trick matrix. Not in v1.0: an engine-level instrument campaign mode (hand-built, `07-universality.md` §7.3) |
| M4 | **Cost**: fidelity ladder, early kill, bandit, tiered experimenters, parallel worktrees, cost accounting, meta-metric report, false-promotion budget | Cost per accepted improvement on the Python fixture at most half of M2's, at the same false-accept rate on a fresh holdout | shipped: fidelity ladder, Thompson bandit with archetype priors, `max_parallel` worktrees, `sb cost` accounting with tiers, the stats block, false-promotion budget with `screen_untrusted`. Not in v1.0: early kill, per-phase cost split. The halving exit criterion is open |
| M5 | **Universality**: archetype packs (rust-crate, python-package, node-frontend, service-api, ml-training, science-sim), instrument-first mode, `metric-line:` compatibility | One campaign each on three archetypes; a greenfield fixture goes from no tests to a usable metric set via an instrument campaign | eleven archetype packs and `metric-line:` ship in 1.0.0; the three-archetype campaigns and the greenfield instrument campaign are open |
| M6 | **Meta-benchmark + v1.0**: `bench/` with 3 to 5 target repos; compare against a naive loop (no walls) on false-accept rate and cost per acceptance; release protocol run in full | Naive loop's false-accept rate on holdout is reported beside ours; RELEASE_PROTOCOL gates all pass with numbers in CHANGELOG | `bench/run_bench.py` (scripted, gaming, analyze modes) ships with its first `pyfix` result under `bench/results/`; the public target repos are open |
| M7 | **Ports** (omniplugin ladder): L0 manual skills + engine must always work; then Codex, OpenCode, Hermes, Pi, Antigravity, DeepSeek Harness, ZCode via the 17-question intake | Each port verified live or split Verified / Not-verified in its `INSTALL-*.md` | open; no port is verified at 1.0.0 (the hooks read the Codex and ZCode plugin-root variables, which is scaffolding, not verification) |

Dogfood beyond `dosimeter` is the user's call per repo. `skyclaw`/TEMM1E is under a zero-risk policy and would run only on a branch, with compile time and binary size as goals and clippy plus the public API as guardrails, after explicit approval.

## 10.7 The meta-benchmark

The loop's own claim is testable. `bench/` holds:

- **Targets**: the two fixtures, plus three public repos with known improvable metrics and a reference "expert" improvement for comparison.
- **Conditions**: strictlybetter with all walls; the same engine with walls disabled (single run, no holdout, no judge), which approximates the popular autoresearch skills.
- **Measures**: accepted improvements and their confirmed effect on a fresh holdout; **false-accept rate** (accepted changes that do not reproduce on a second independent holdout); guardrail regressions; dollars and minutes per accepted improvement; judge overhead.
- **Report**: a table per target per condition, written by the engine, never hand-edited.

In 1.0.0 `bench/run_bench.py` has three modes: `scripted` (a seeded sequence of real wins, no-ops, and gaming tricks through the real engine under the `walls` and `naive` conditions, every accepted commit re-validated on a fresh holdout with the pristine instrument and an external timer), `gaming` (the wall-ablation matrix: which wall catches which trick), and `analyze` (re-validate a campaign real agents ran). Results land in `bench/results/<stamp>-<mode>-<fixture>.{json,md}`; the `pyfix` fixture is the target shipped with 1.0.0.

If the walls do not reduce the false-accept rate at acceptable cost, the thesis is wrong and the docs say so.

## 10.8 Release protocol (adapted from engram)

Gates, in order, each with a written receipt: selftest; mutation-test every new check; adversarial review against an extracted tree (`git archive | tar`), counting reports received against reviewers launched; fuzz the engine's read paths over corrupt state (0 crashes over 500 garbage states); numbers audit (six questions per new number; denominators published beside rates); live test in a throwaway state dir with real state hashed before and after; uncontaminated dogfood pinned to the release tree in a copy; a persona user session in fresh context with a binding verdict; post-release independent review with the instruction "find a number that is wrong in the direction that reassures." CHANGELOG entries carry a "gates run for this release" paragraph and patch releases are titled by what the review caught.

## 10.9 Decisions still open

- Whether the experimenter default is one subagent per hypothesis (fresh context, more tokens) or an in-session edit (cheaper, rots). Plan assumes subagent; M4 measures the difference.
- Python floor (3.10 is the sibling plugins' floor).
- Dedicated measurement host over SSH in v1 or v1.x (not in 1.0.0).
- Whether `.strictlybetter/ledger.jsonl` is committed on the campaign branch (plan: yes) or kept local with only the report committed. In 1.0.0 the engine commits nothing under the state home; its `.gitignore` excludes only worktrees, archive, tmp, cache, inbox, and locks, so the project decides.
- Public or private at v1.0. The repo starts private.
