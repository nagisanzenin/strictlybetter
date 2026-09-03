# 10 · Implementation plan

Repo `nagisanzenin/researchloop`, product `strictlybetter`, Claude Code first, then the omniplugin port ladder. This plan follows the conventions the sibling plugins (engram, effortmining, dosimeter, production-grade, omniplugin) converged on, so a maintainer of one can maintain this.

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
researchloop/
  README.md  LICENSE  CHANGELOG.md  RELEASE_PROTOCOL.md  CLAUDE.md
  docs/                         # this theory; docs/00-* is the cold-start doc
  .claude-plugin/plugin.json    # {name: strictlybetter, version, description, author, homepage, keywords}
  .claude-plugin/marketplace.json
  skills/
    strictlybetter/SKILL.md     # front door: status → orient/instrument/gate 1 → run
    sb-orient/SKILL.md
    sb-metrics/SKILL.md         # discovery, cards, monotonicity selftest, baseline
    sb-run/SKILL.md             # one cycle per invocation; Stop hook re-invokes
    sb-status/SKILL.md
    sb-distill/SKILL.md
    sb-stop/SKILL.md
    _shared/
      engine-resolution.md      # RUN THIS BLOCK VERBATIM; fails closed
      metric-card.md            # the schema, for agents that write cards
      ledger.md                 # the schema, for agents that read it
      judge-protocol.md         # payload shape, checklist, verdict JSON
      subagents.md              # items by file path, one child per judgment, no dialogue
  agents/
    sb-orienteer.md             # repo → profile.md (JSON via --file)
    sb-metrologist.md           # profile → candidate cards + gaming_risks + probes
    sb-experimenter-low.md      # byte-identical except effort:; tier by operator class
    sb-experimenter-medium.md
    sb-experimenter-high.md
    sb-judge.md                 # blind; effort: medium; tools: Read only
    sb-distiller.md             # ledger → inheritance.md
  hooks/
    hooks.json
    session-start.sh            # SessionStart startup|resume|clear|compact → sb session-start
    frozen-guard.sh             # PreToolUse Edit|MultiEdit|Write|NotebookEdit → sb guard <path>; exit 2 denies
    pre-compact.sh              # PreCompact → re-pin campaign invariants
    stop-driver.sh              # Stop → if campaign running and budget left: continue (max-iterations cap)
  scripts/
    sb.py                       # the engine
  archetypes/*.yaml             # discovery priors and default cards per archetype
  operators/*.md                # operator library: when to use, tier, expected diff size
  templates/                    # profile.md, campaign.yaml, inheritance.md, card skeletons
  tests/                        # pytest for sb.py; fixture repos under tests/fixtures/
  bench/                        # meta-benchmark (10.7)
  INSTALL-<PLATFORM>.md         # one per port (10.8)
```

Root `commands/` and `agents/` are never added without a namespace-bleed audit (omniplugin pitfall). The Antigravity root `plugin.json` carries `{name, description}` only.

## 10.3 The engine: `scripts/sb.py`

Command surface (each a handler; `mutating` ones take the lock):

| Command | Does | Mutating |
|---|---|---|
| `init` | create `.strictlybetter/`, templates, `.gitignore` entries | yes |
| `profile write --file` | validate and store the orienteer's JSON as `profile.md` | yes |
| `card add --file` / `card validate` | schema-check a metric card; refuse a goal without measured sigma | yes / no |
| `card probe <id>` | monotonicity selftest: apply the card's declared degradation in a throwaway worktree, assert the metric moves the wrong way | no (throwaway) |
| `baseline [--metric] [--repeats k]` | measure at the campaign head from a clean checkout, compute sigma, write `baseline.json` and the environment fingerprint | yes |
| `campaign start --file` / `campaign end` | freeze the set, hash frozen paths, create branch, inherit the global ratchet | yes |
| `next` | the cold-start brief: frontier, budget, plateau level, bandit mix, batch size, top diagnostics, archive hints, ranked open hypotheses | no |
| `prereg --file` | write the ledger line before any diff exists; returns the experiment id | yes |
| `worktree new <id>` / `worktree drop <id>` | isolated worktree with shared build cache | yes |
| `guard <path>` | exit 2 if a campaign is running and the path is frozen, protected, or outside the active worktree | no |
| `integrity <id>` | diff touches no frozen/protected path; eval hash unchanged | no |
| `measure <id> --fidelity screen\|full\|confirm` | run every goal and guardrail; validity checks; parse; append | yes |
| `judge <id>` | statistical verdict: discard / promote / retry-screen / inconclusive | yes |
| `judge-verdict <id> --file` | store the blind judge's JSON; schema-checked | yes |
| `confirm <id>` | clean checkout, holdout, repeats; adaptive up to the cap | yes |
| `accept <id>` / `discard <id> --reason` | fast-forward and ratchet / drop and optionally archive | yes |
| `distill-stats` | plateau level, bandit update, false-promotion rate, cost per acceptance, holdout gap trend | yes |
| `status` / `report` | human-readable state; campaign report as PR body | no |
| `budget` | counters; refuses to start work past a cap | no |
| `session-start` | at most two lines or nothing; dedupe fail-closed | no |
| `doctor` | verify commands in the profile still run; toolchain fingerprint | no |
| `selftest` | the badge; includes AST no-network, version pin, schema round-trips, a scripted full campaign on an in-memory fixture | no |

Validity checks inside `measure`: exit code, metric parsed, duration within a band of the baseline's duration, output not equal to a placeholder or zero when the baseline was not, run manifest recorded (`commit, config_hash, seeds, env_fingerprint`). A number without a manifest is refused.

Metric parsing supports `regex:`, `json:` path, and `metric-line:` (the `METRIC name=value` convention of the autoresearch ecosystem, for compatibility with existing benches).

## 10.4 The driver: how the loop runs unattended on Claude Code

Claude Code has no per-spawn effort parameter and a context window that rots. The driver design keeps the orchestrating session small and every experiment in fresh context:

1. `/strictlybetter` (front door) runs `sb status`. If no profile: orient. If no campaign: instrument, then gate 1 as one structured question with the recommended set first. If a campaign is running: one cycle.
2. **One cycle** = `sb next` → spawn one experimenter subagent per hypothesis (tier from the operator class; hypothesis, profile, inheritance body and archive hints passed **by file path**) → each returns `DONE <id>` or `BLOCKED: <reason>` → `sb integrity`, `sb measure --fidelity screen`, `sb judge` → for promoted: spawn `sb-judge` blind, `sb judge-verdict`, `sb confirm`, `sb accept|discard` → every D cycles `sb distill-stats` and the distiller.
3. **Continuation**: the Stop hook checks `sb status --json`; while `status == running`, budget remains, and the iteration counter is below `max_iterations`, it re-injects "continue the campaign" (the Ralph pattern; the cap is the primary safety, the budget the second, the `STOP` file the third).
4. **Compaction**: the PreCompact hook re-pins the campaign id, the frozen paths, and the sentence "you never compute a statistic and never write baseline.json" so they survive summarization (dosimeter's pins, driveline's rehydration).
5. **Headless**: `sb drive --platform claude --cycles N` shells out to `claude -p` once per cycle for overnight or CI use; each cycle starts from disk, so no context is shared between cycles by design.

The frozen-path guard is a PreToolUse hook: during a campaign, an edit to a frozen or protected path, or to any path outside the active worktree, is denied at the tool boundary with a one-line reason. Gate-time `sb integrity` runs regardless, for platforms without pre-edit hooks.

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

| # | Milestone | Exit criterion |
|---|---|---|
| M0 | Theory, name, repo (done 2026-09-03) | docs 00–11 and citations in the repo |
| M1 | **Engine**: `sb.py` with cards, baseline, worktrees, measure, judge, confirm, accept/discard, ledger, status, next, selftest; two fixture repos (a Python package with a slow function and tests; a Rust crate with a criterion bench and clippy) | A **scripted, LLM-free** experimenter drives a full campaign on both fixtures; ledger, baseline, report produced; every selftest check mutation-tested (revert the fix, the check goes red) |
| M2 | **Claude Code plugin v0.1**: skills, agents, hooks, gate 1, one-cycle driver, Stop-hook continuation | Ten real experiments on the Python fixture end to end; then dogfood on `dosimeter` (stdlib engine, tests; goals: selftest wall-clock, import time) in a copy of the repo, never the installed plugin; ≥ 1 confirmed acceptance, 0 guardrail regressions; post-release review finds nothing that reassures falsely |
| M3 | **Walls**: frozen-path guard hook, eval hash, holdout rotation, blind judge with the casebook checklist, validity gate, anomaly breaker, pre-registration enforcement, instrument campaign mode | A scripted **gaming experimenter** attempts every casebook trick (evaluator edit, test skip, input special-case, benchmark narrowing, hard-coded outputs, ctypes escape, zero-duration run, faked log); each is caught by a named wall; removing any single wall lets at least one trick through (the walls are mutation-tested too) |
| M4 | **Cost**: fidelity ladder, early kill, bandit, tiered experimenters, parallel worktrees, cost accounting, meta-metric report, false-promotion budget | Cost per accepted improvement on the Python fixture at most half of M2's, at the same false-accept rate on a fresh holdout |
| M5 | **Universality**: archetype packs (rust-crate, python-package, node-frontend, service-api, ml-training, science-sim), instrument-first mode, `metric-line:` compatibility | One campaign each on three archetypes; a greenfield fixture goes from no tests to a usable metric set via an instrument campaign |
| M6 | **Meta-benchmark + v1.0**: `bench/` with 3 to 5 target repos; compare against a naive loop (no walls) on false-accept rate and cost per acceptance; release protocol run in full | Naive loop's false-accept rate on holdout is reported beside ours; RELEASE_PROTOCOL gates all pass with numbers in CHANGELOG |
| M7 | **Ports** (omniplugin ladder): L0 manual skills + engine must always work; then Codex, OpenCode, Hermes, Pi, Antigravity, DeepSeek Harness, ZCode via the 17-question intake | Each port verified live or split Verified / Not-verified in its `INSTALL-*.md` |

Dogfood beyond `dosimeter` is the user's call per repo. `skyclaw`/TEMM1E is under a zero-risk policy and would run only on a branch, with compile time and binary size as goals and clippy plus the public API as guardrails, after explicit approval.

## 10.7 The meta-benchmark

The loop's own claim is testable. `bench/` holds:

- **Targets**: the two fixtures, plus three public repos with known improvable metrics and a reference "expert" improvement for comparison.
- **Conditions**: strictlybetter with all walls; the same engine with walls disabled (single run, no holdout, no judge), which approximates the popular autoresearch skills.
- **Measures**: accepted improvements and their confirmed effect on a fresh holdout; **false-accept rate** (accepted changes that do not reproduce on a second independent holdout); guardrail regressions; dollars and minutes per accepted improvement; judge overhead.
- **Report**: a table per target per condition, written by the engine, never hand-edited.

If the walls do not reduce the false-accept rate at acceptable cost, the thesis is wrong and the docs say so.

## 10.8 Release protocol (adapted from engram)

Gates, in order, each with a written receipt: selftest; mutation-test every new check; adversarial review against an extracted tree (`git archive | tar`), counting reports received against reviewers launched; fuzz the engine's read paths over corrupt state (0 crashes over 500 garbage states); numbers audit (six questions per new number; denominators published beside rates); live test in a throwaway state dir with real state hashed before and after; uncontaminated dogfood pinned to the release tree in a copy; a persona user session in fresh context with a binding verdict; post-release independent review with the instruction "find a number that is wrong in the direction that reassures." CHANGELOG entries carry a "gates run for this release" paragraph and patch releases are titled by what the review caught.

## 10.9 Decisions still open

- Whether the experimenter default is one subagent per hypothesis (fresh context, more tokens) or an in-session edit (cheaper, rots). Plan assumes subagent; M4 measures the difference.
- Python floor (3.10 is the sibling plugins' floor).
- Dedicated measurement host over SSH in v1 or v1.x.
- Whether `.strictlybetter/ledger.jsonl` is committed on the campaign branch (plan: yes) or kept local with only the report committed.
- Public or private at v1.0. The repo starts private.
