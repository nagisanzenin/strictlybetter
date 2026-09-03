# CLAUDE.md — maintainer notes for strictlybetter

**What this repo is.** strictlybetter (github.com/nagisanzenin/strictlybetter) is a research loop for agentic
coders. Pointed at a repo, it derives the project's metrics into *metric cards*, measures their
noise, and runs pre-registered experiments under a budget, keeping a change only when it is
strictly better: better on a goal by more than κσ, worse on no guardrail, confirmed on a holdout
the experimenter never saw, and passed by a judge that never saw the experimenter's reasoning.
The deterministic engine is one stdlib file, `scripts/sb.py`; agents narrate what it prints.
The theory lives in `docs/00` to `docs/11` and is the spec. Cold start: `docs/00-thesis.md`,
then `docs/10-implementation-plan.md`.

## Invariants (a PR that breaks one is wrong by definition)

1. **The harness computes, the model narrates.** Every statistic, verdict, budget counter, and
   state write happens in `sb.py`. A skill says "run this and report what it printed"; it never
   paraphrases, rounds, or re-derives a number. An agent never writes `baseline.json`.
2. **Constants are fixed before data.** κ, τ, λ, patience, repeats, windows, halt thresholds
   live in the constants block at the top of `sb.py` under "do not tune these to results". A
   change there needs a reason that mentions no result, a major version, and a CHANGELOG line.
3. **No network in the engine.** The selftest parses the AST for banned imports; the mutation
   that proves the check is `import socket`. Subprocesses run the project's own commands only.
4. **Hooks degrade to silence and exit 0, except the guard.** `sb guard` exits 2 to deny a
   write to a frozen or protected path, to state files, or outside the active worktree while a
   campaign runs. Every other hook prints at most one validated line or nothing. Hook stdout is
   a prompt-injection surface.
5. **The judge schema forbids reasoning.** `judge-verdict` accepts exactly
   `verdict, pattern, evidence, recommended_check` and rejects any other key. The judge agent has
   Read-only tools and receives the diff, the pre-registration, the numbers, and the cards'
   `gaming_risks`, by file path. Never the transcript.
6. **Never bump a version without the grep** in `RELEASE_PROTOCOL.md` §6. `VERSION` in `sb.py`,
   `.claude-plugin/plugin.json`, and the README badge move together; the selftest pins the first
   two, but only when the manifest exists.
7. **A number in a report must trace to a file under `bench/results/`.** Any figure quoted in
   README, CHANGELOG, a doc, or a release note (acceptance rate, false-accept rate, cost per
   accepted improvement, holdout gap) names the results file it came from and carries its
   denominator. No file, no number. Results files are written by the engine, never hand-edited.
8. **Doc-drift rule.** `docs/` is the spec, but code is what runs. If code and a doc disagree,
   fix the doc in the same commit as the code change and say so in CHANGELOG. If the code is
   wrong instead, fix the code and add the check that would have caught it. Never leave the two
   disagreeing on purpose; a doc that overclaims is a label that lies.
9. **State is JSON, append-only where it is a log, atomic where it is a file.** Free text enters
   the engine through `--file` or stdin, never argv. Mutating commands take the lock.

## Where things live

| Path | What |
|---|---|
| `scripts/sb.py` | the engine: constants, cards, measurement, acceptance rule, ledger, campaign verbs, guard, selftest |
| `tests/test_engine.py`, `tests/test_fixture_campaign.py` | stdlib `unittest`: engine units; end-to-end through the real CLI on pyfix |
| `tests/fixtures/` | `pyfix`, `rustfix`, `greenfield` fixture repos, their `fixture-cards/`, `make_fixture.py` |
| `docs/` | the theory (00 thesis … 10 implementation plan, 11 ML mapping, citations) |
| `archetypes/*.json` | discovery priors per project archetype: default cards, protected paths, operator priors |
| `operators/*.md` | operator library, one file per class in `OPERATORS` |
| `templates/` | profile, campaign spec, inheritance body, card skeletons |
| `skills/` | Claude Code skills; `skills/_shared/` holds the schemas and the judge protocol |
| `agents/` | orienteer, metrologist, experimenter ×3 tiers, judge, distiller |
| `hooks/` | `hooks.json`, session-start, frozen-guard, pre-compact, stop-driver |
| `bench/` | meta-benchmark; `bench/results/` is the only source of quotable numbers |
| `.strictlybetter/` (in a *target* repo) | `profile.json`, `metrics/*.json`, `campaign.json`, `baseline.json`, `ratchet.json`, `bandit.json`, `ledger.jsonl`, `inheritance.md`, `wt/`, `archive/`, `reports/`, `STOP` |
| `RELEASE_PROTOCOL.md`, `CHANGELOG.md` | how a version ships; what shipped and which gates ran |

## How to run

```bash
python3 scripts/sb.py selftest                 # the badge; must end "N/N checks passed"
python3 -m unittest discover -s tests          # engine unit tests
python3 tests/fixtures/make_fixture.py pyfix /tmp/x   # throwaway repo for a live campaign
python3 scripts/sb.py --repo /tmp/x init       # then card add / probe / campaign start / prereg …
python3 bench/run_bench.py --mode gaming --fixture pyfix    # every trick caught by a named wall
python3 bench/run_bench.py --mode scripted --fixture pyfix  # walls vs naive → bench/results/
```

The docstring at the top of `sb.py` is the command reference. Never run a campaign against a
real repo you have not copied first, never against the installed plugin cache, and never against
skyclaw/TEMM1E without the explicit approval its zero-risk policy requires.

## Releasing

Follow `RELEASE_PROTOCOL.md` in full: selftest, mutation-test every new check, adversarial review
against an extracted tree, fuzz the read paths, the six-question numbers audit, the gaming suite,
the live fixture test with state hashed before and after, an uncontaminated dogfood in a copy, a
persona user session with a binding verdict, then merge, tag, release, and the post-release review
whose standing instruction is to find a number that is wrong in the direction that reassures.
Every gate produces a receipt and the receipts go in the CHANGELOG's "Gates run" paragraph.

## Porting

Platforms are added one at a time along the omniplugin ladder
(`github.com/nagisanzenin/omniplugin`, the 17-question intake): L0 manual skills + engine must
always work; each port gets an `INSTALL-<PLATFORM>.md` and an honest row in
`RELEASE_PROTOCOL.md` §7.6. Shared skill files are read by every platform at once, so write
capability tests ("if your only spawn mechanism is …"), never platform names, and hand every
edited skill to an uncontaminated agent on a different platform before shipping.

## Lineage

engram (release protocol, blind assessor), effortmining (tier-pinned workers, blind grader,
harness-first), dosimeter (constants before data), redswarm-decoded (the inheritance body),
production-grade (gates and receipts), omniplugin (ports). Copy their conventions; cite them.
