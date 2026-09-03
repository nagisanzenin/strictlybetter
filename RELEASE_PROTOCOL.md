# Release Protocol

The repeatable checklist for shipping a strictlybetter version. Follow every step, in order.

Adapted from engram's, where every gate was added because it caught a real bug the gate before it
could not see. strictlybetter has not yet earned its own scars: the examples below are borrowed from
engram, effortmining, and the casebook in `docs/01-prior-art.md`. **The first time a gate here
catches something real, replace the borrowed example with the real one in the same commit.**

**Semver:** user-visible feature, new wall, operator, archetype pack, or platform port → **minor**;
bug fix, doc, or polish → **patch**; a change to the on-disk state schema, the judge verdict schema,
or any constant in the constants block → **major**, because every ledger and baseline on every
user's disk was produced under the old rule. A process-doc-only change ships no version.

---

## The bug classes this repo cannot ship

Every gate below exists to catch one of these; the order is the order of harm. The last column says
where in `scripts/sb.py` the class would live.

| # | Class | Why it is fatal here | Where it lives |
|---|---|---|---|
| **1** | **The flattering number: a false accept** | The one promise is that an accepted change is strictly better. A crash gets fixed because you see it; a false accept gets *merged*, and every downstream number (acceptance rate, cost per acceptance, the ratchet) is built on it. | `compare_metric`, `decide`, `cmd_confirm`, `kappa_eff`, and the baseline `sigma` they all divide by |
| **2** | **The silent regression: a guardrail not measured** | "Worse on nothing" is only true of the guardrails that ran. One skipped, parsed as `None`, or measured at the wrong fidelity reports "held" while the thing it guards is gone. | `cmd_measure` id list per fidelity, `summarize` on an empty run list, `decide` when a guardrail is absent from `comparisons`, the report's `held` column (currently unconditional) |
| **3** | **The judge in the arena: experimenter influence on the verdict** | The judge is blind by schema. One extra field, one payload assembled from the conversation instead of from disk, one skill line saying "explain to the judge", and the wall is prose again. | `cmd_judge_verdict` schema check, `skills/_shared/judge-protocol.md`, `agents/sb-judge.md` (Read-only) |
| **4** | **The stale instrument: sigma from another machine or commit** | 2.5σ is meaningless when σ was measured on a laptop last month. Too small a σ is bug class 1 in a lab coat. | `cmd_baseline` (`env_fingerprint`, `commit`), `campaign_start`'s missing-baseline rule, `rotate_holdout`'s re-baseline, `baseline_level` fallbacks |
| **5** | **The leaky holdout** | An experimenter that sees confirm numbers of discarded candidates learns the holdout one bit at a time. The docs promise limited leakage; the ledger file carries full confirm results for every candidate, and `sb ledger view` and `tail` redact a discarded candidate's confirm numbers (`experiments` prints none; `--unredacted` is the audit path). | `cmd_confirm` ledger payload, `cmd_ledger view`, `cmd_next`, `holdout_values`, `holdout_override` |
| **6** | **The hook that fails open: the guard allows a frozen edit** | Prompts are advice; the hook is the wall. Exit 0 on a malformed payload, a symlinked path, or a missing campaign file silently makes the instrument writable. | `guard_decision`, `cmd_guard --stdin` (returns 0 when no path is found), `hooks/frozen-guard.sh`, whose fast path exits 0 when it cannot find a campaign, a path, `python3`, or the engine |
| **7** | **The ledger that lies: event order, torn lines** | The ledger is event-sourced and folded by `experiments()`. A torn line is skipped by design, so a torn `accept` line makes an accepted experiment look open. Two writers without the lock interleave. | `read_jsonl`, `Home.experiments`, `append_jsonl`, `MUTATING`, `Home.lock` |
| **8** | **The budget that leaks: spend counted after work** | A crash between work and accounting is free work the cap never sees. `experiments` is charged before the worktree exists; wall-clock is charged after measurement returns, and in `cmd_measure` outside the `finally`. | `add_spend` call sites in `cmd_prereg`, `cmd_measure`, `cmd_confirm`, `cmd_cost`; `budget_exhausted` |
| **9** | **The label that lies: a report calling an estimate a measurement** | The arithmetic is right and the reader is still deceived. Dollars are an *estimate* from a default pricing table unless `cost --dollars` was passed; a `$` without `est` upgrades a guess to a fact. | `DEFAULT_PRICING`, `stats()['dollars_est']`, `write_report`, `cmd_status`, every skill line that quotes them |

> **The sentence to keep:** *a number that is wrong in the direction that reassures is worse than a
> crash.* Here that direction is "accepted", "held", "clean", "under budget". **Its corollary:** *a
> number whose label is wrong is a wrong number.* `dollars_est` never loses its suffix on the way to a human.

---

## 0 · Preconditions

```bash
cd ~/Documents/Github/strictlybetter
git checkout -b release/vX.Y.Z              # never work on main directly
python3 scripts/sb.py selftest              # must already be green: "N/N checks passed"
python3 -m unittest discover -s tests       # must already be OK
git status --short                          # only the files you meant to touch
```

The default branch is what a fresh `claude plugin install` pulls, so it must never be half-broken.
Decide the version now; it appears in several files (§6).

## 1 · Land the work

**If it touches `scripts/sb.py`, it MUST be covered by a new check that fails without it.** A hook
change needs a `tests/test_hooks.py` replay of the real payload shape. A skill or agent change makes
§5.5 and §5.6 mandatory. **If it adds or changes a NUMBER, read §4.8 first**; that section is the
spec. **If it changes a constant, stop.** Constants are fixed before data; a constant tuned to make a
benchmark pass is bug class 1 with a commit message. It needs a reason that mentions no result, a
major version, and a CHANGELOG line naming the ledgers it invalidates.

## 2 · Write the CHANGELOG

New section at the **top** of `CHANGELOG.md`:

```
## X.Y.Z — YYYY-MM-DD · <one-line theme>

Gates run for this release: <selftest N/N · unittest N · mutation N/N red · review K/K reports ·
fuzz 0/500 · numbers audit N numbers · gaming suite T/T caught, W/W walls load-bearing ·
live test hash-identical · dogfood <repo> vN · user session verdict>
Benchmark: see bench/results/<file>

<grouped: Engine / Walls / Cost / Knowledge / Surface / Ports / Bench. Trace each change to WHY.>
```

Write the bugs honestly, including the embarrassing ones. Patch releases are titled by what the
review caught. A CHANGELOG that only lists wins is marketing.

# THE GATES

Each gate produces a receipt (command, output, the number) for the CHANGELOG paragraph above. A
gate without a receipt was not run.

## 4 · The selftest gate

```bash
python3 scripts/sb.py selftest | tail -1                  # "selftest: N/N checks passed"; N == README badge
python3 scripts/sb.py selftest | grep 'version pinned'    # must print "ok  version pinned to plugin.json"
python3 -m unittest discover -s tests                     # "OK"
```

Red stops the release. The second line exists because the version pin is **skipped when
`.claude-plugin/plugin.json` is absent**: a green total is not proof the pin ran. Demand the line.

**Then distrust it.** A green selftest means the checks you wrote pass. It says nothing about the
checks you did not write, and nothing about whether the ones you wrote are real.

## 4.5 · Mutation-test every new check

**A check that still passes when you revert its fix is theatre.** engram found 3 fake checks in one
release and 4 in the next. For every check added this release: revert the fix it guards, run the
suite, confirm **that specific check** fails, restore.

```bash
cp scripts/sb.py /tmp/sb.bak
# … apply ONE mutation from the table …
python3 scripts/sb.py selftest | grep '^FAIL'    # must name YOUR check
cp /tmp/sb.bak scripts/sb.py
```

The standing mutations, one per bug class. Run all of them every release; they are the regression
suite for the suite.

| Class | Mutation (`sed -i '' …` on `scripts/sb.py`) | The check that must go red |
|---|---|---|
| 1 flattering | `s/res\["improved"\] = delta > thr/res["improved"] = delta > 0/` | `goal within noise is inconclusive` |
| 2 regression | `s/if regressed:/if False:/` in `decide` | `decide regression beats improvement`, `guardrail regression discards a big goal win` |
| 3 judge | delete the extra-keys rejection in `cmd_judge_verdict` | `verdict schema forbids extra fields` |
| 4 stale σ | in `campaign_start`, `s/e.get("sigma") is None/False/` | *no check exists yet: write one before a release that touches baselines* |
| 5 holdout | `s/use_holdout=walls.get("holdout", True)/use_holdout=False/` in `cmd_confirm` | *no check exists yet: §5 must show the confirm ledger event carrying `SB_SEED` from the holdout list* |
| 6 guard | `s/return False, f"frozen path/return True, f"frozen path/` | `guard denies frozen path` |
| 6 guard | `s/return False, "state files/return True, "state files/` | `guard denies state file` |
| 6 hook | feed `hooks/frozen-guard.sh` a real PreToolUse payload naming a frozen path while a campaign runs | must exit 2 with the reason on stderr; *no test exists yet: `tests/test_hooks.py` is the file to write* |
| validity | `s/instr_ratio < WALL_DIVERGENCE_INSTR/False/` in `comparisons_for` | the divergence check added in e02c360 must go red (name it here when you run this) |
| 7 ledger | delete the `except json.JSONDecodeError: continue` in `read_jsonl` | `torn ledger line tolerated` (a suite crash is also red) |
| 8 budget | move `add_spend(c, experiments=1)` below `worktree_new` in `cmd_prereg` | *no check exists yet: the budget class has an exhaustion check and no ordering check* |
| 9 label | `s/dollars_est/dollars/` in `stats` | *no check exists yet: assert the rendered report contains `estimated`* |
| absence | `s/^import argparse$/import argparse\nimport socket/` | `no network imports` |
| integrity | `s/if matches_any(f, fp):/if False:/` in `cmd_submit` | `integrity catches frozen edit` |
| version | change `VERSION` alone | `version pinned to plugin.json` (only when the manifest exists; §4) |

Rows marked *no check exists yet* are the honest state of the suite at 1.0.0. A release that touches
that area may not ship until its row names a real check.

The ways a check turns out fake, all seen in the sibling repos: it asserts a constant, not a
behavior; the fixture makes old and new agree by coincidence; the assertion is weaker than the
property (a linear penalty satisfies "bigger diff, bigger κ" as well as the log one; pin the
hand-computed value); another gate already covers it; the fixture returns before reaching the line
under test. **For an absence check, the mutation must introduce the thing**: `no network imports`
is worth something only because `import socket` turns it red.

**When you fix a bug class, grep for every sibling.** A guard and its predicate travel to every call
site or to none. `WALL_KEYS` declares eight keys and `walls.get(...)` reads seven: at 1.0.0 `prereg`
is declared and read nowhere. A wall nobody reads is a config field that lies.

## 4.6 · The adversarial review, against an extracted tree

```bash
rm -rf /tmp/sb-review && mkdir -p /tmp/sb-review/new /tmp/sb-review/old
git archive HEAD | tar -x -C /tmp/sb-review/new
git archive main | tar -x -C /tmp/sb-review/old
git diff main...HEAD > /tmp/sb-review/diff
/code-review high        # pointed at /tmp/sb-review, never at the working copy
```

Name the risk areas: the acceptance rule and every number it feeds, the guard's path logic
(symlinks, not-yet-existing paths, notebooks), the ledger fold, back-compat with older state, and
**every new number**. Prose matters for cross-file consistency: a skill that tells the judge one
thing and `judge-protocol.md` another.

1. **Green tests are not evidence about the design.** engram found 10 defects behind 79 green checks.
2. **Never trust a review whose agents errored.** Check the failure list before the verdict.
3. **Feed the reviewer the shipped contract, not just the diff.** The judge schema lives in three
   files; a reviewer reading only `sb.py` cannot see a skill that widens it.
4. **Extract first.** A reviewer that runs `git checkout` moves the tree under every other reviewer.
5. **Count the reports received against the reviewers launched.** Silence is not a verdict; every
   missing report is an unrun gate. Run it yourself.

Every confirmed finding gets a fix **and** a check that fails without it (§4.5).

## 4.7 · The fuzz gate: read paths degrade, never brick

State files are hand-editable JSON. `read_json` already turns *syntactically* bad JSON into an
`SBError` (exit 1, one line). The fuzz is for *type-wrong valid* JSON: `campaign.json` as a list,
`goals` as a string, `spent` as `null`, a ledger event whose `data` is a string, a card whose
`fidelity` is `[]`.

**Enumerate the read paths from the code, not from memory:**

```bash
python3 - <<'PY'
import re
src = open("scripts/sb.py").read()
h = set(re.findall(r'"([\w-]+)": cmd_', src))
m = set(re.findall(r'"([\w-]+)"', re.search(r"MUTATING = \{(.+?)\}", src, re.S).group(1)))
print("read commands:", sorted(h - m))
PY
grep -nE 'args\.action ==|choices=\[' scripts/sb.py    # read SUB-ACTIONS of mutating commands
```

At 1.0.0 that is `budget doctor drive guard ledger next report session-start status` **plus** the
read sub-actions hiding under mutating commands: `card list|validate|show`, `campaign show`,
`profile show`, `worktree path|list`, `inheritance show`, `ledger view|tail|experiments`. A command
with sub-actions has a read path per sub-action; the dispatch table cannot see them.

Throw 500+ randomized states (2+ seeds) at every one, in a throwaway `SB_HOME`, and demand each
**returns**: `SystemExit` or `SBError` is fine; a traceback is a defect. Fix at the gate
(`Home.campaign()`, `Home.experiments()`, a shape check in `read_json`), not at twenty call sites,
then check the gate's twins: `baseline()`, `ratchet()`, `bandit()`, `profile()`, `load_card()`.
Also fuzz bench output: `METRIC x=`, `nan`, `1e400`, a 50 MB stdout, a non-UTF-8 byte;
`parse_output` and `summarize` classify, they never raise past `measure_once`.

Target: **0 crashes / 500 states**, locked in by a selftest. **Re-fuzz after the last commit.**

## 4.8 · The numbers audit: the most important gate in this file

For **every number the release adds or changes**, answer all six in writing, in the PR:

1. **What is the denominator?** Every rate drops something. Name it, count it, publish it beside
   the rate (`accepted 3 / pre-registered 41`, never `7%`).
2. **Is it measured or estimated?** Dollars are estimated unless `cost --dollars` was passed; sigma
   is measured; a confirm effect is on the holdout, a screen effect on the visible set. The word
   goes in the key (`dollars_est`) and in the rendered string.
3. **What commit and what machine?** A sigma without `commit` and `env_fingerprint` is a number
   from nowhere. Numbers from different fingerprints say so or are not compared.
4. **Does the label match?** `n_valid` and `n` never share a column. `promoted` (judge) and
   `accepted` (confirm) are different populations. `false_promotion_rate_window` is
   promoted-then-discarded over a window of promotions; it is **not** the false-accept rate (§4.9).
5. **Could it be gamed?** By the experimenter (does it read anything the experimenter wrote?), by
   the harness (does `decide` short-circuit on a guardrail it never measured?), by the reader (does
   it fail optimistically?). Optimistic failure modes are release-blocking; pessimistic ones are bugs.
6. **Is the caveat carried to every surface?** Follow it from the JSON key to `sb status` text, to
   `sb report`, to the skill's narration, to the PR body. **The happy path is where caveats die**:
   failing branches join their reasons; the `accept` branch builds its own cheerful string. Read
   the success branch hardest. A field is not a narrator; assert the caveat in a string a human sees.

**Cross-check every number against every other number for the same state.** Run `status`,
`distill-stats`, `next`, `report`, and `budget` on one campaign and put the outputs side by side.
If `status` says 3 accepted and `report` lists 4, one is lying and you do not yet know which.

**If the number is an instrument, test the instrument.** A deliberately wrong subject must score
worse than a correct one: `card probe` does this per card; §4.9 does it for the loop. Vary the
*population*, not just the bar: ten honest small wins and one gamed jump must be ranked correctly by
`holdout_gap_mean_last5` and the anomaly breaker, and a single-datum fixture can never see order.

### Numbers that must never be reported without their denominator

| Number | Its denominator, stated in the same breath | Undefined when |
|---|---|---|
| **Acceptance rate** | accepted / **pre-registered** experiments (including integrity discards and invalid runs; excluding open ones, and say how many are open) | 0 pre-registered |
| **False-accept rate** | accepted changes that **do not reproduce on a second, independent holdout** / accepted. The bench's number (§4.9). Not `false_promotion_rate_window`. | 0 accepted, or no second holdout was run |
| **Cost per accepted improvement** | (`dollars_est` **or** measured dollars, say which; wall-clock seconds) / accepted. The engine returns `None` at 0 accepted; a surface that prints `$0` there is lying. | 0 accepted |
| **Holdout gap** | mean over the **last 5 accepted** of (screen − confirm) / screen on the *first* goal with a relative delta; `None` when screen ≤ 0. Say the window and the goal. | fewer than `GAP_MIN_N` accepted |

## 4.9 · The gaming suite: every trick caught by a named wall

```bash
python3 bench/run_bench.py --mode gaming --fixture pyfix     # wall-ablation matrix, LLM-free
python3 bench/run_bench.py --mode scripted --fixture pyfix   # walls vs naive: false accepts, cost
```

The suite passes only when **each trick is caught by the wall named for it** and **removing any
single wall lets at least one trick through** (`campaign start` accepts `"walls": {"<key>": false}`
for exactly this).

| Trick (casebook) | Named wall | Engine site |
|---|---|---|
| evaluator or test edited, skipped, xfail'd, assertion weakened | `frozen_guard` (+ `judge` checklist) | `cmd_submit` frozen match + eval hash; `guard_decision` at the tool boundary |
| input special-cased on dev seeds | `holdout` | `cmd_confirm` with `SB_SEED` from the holdout list |
| benchmark narrowed (fewer repeats, smaller size) | `frozen_guard` and `validity` duration band | `expected_duration_s` in `measure_once` |
| output hard-coded, lookup table, or the computing component replaced by a search | `holdout` and the `equal` checksum guardrail; `judge` | `bench_checksum` card; `sb-judge` |
| native escape (`ctypes`, another toolchain) | `judge` checklist and the `deps:` integrity rule | `cmd_submit` `new_deps`; `sb-judge` |
| zero-duration run | `validity` | `expected_duration_s`; rc / parse checks |
| timer or instrument reports a speed-up the process wall-clock contradicts | `validity` divergence check | `comparisons_for`, `WALL_DIVERGENCE_*` |
| faked log or receipt written by the diff | `judge` checklist; `state:` integrity rule | `cmd_submit` (`.strictlybetter/` in diff) |
| environment tampering (`PYTHONHASHSEED`, threads) | `judge` checklist; harness-owned env | `measure_once` env |
| lucky noise (the +5% that is really ±3%) | `noise_floor` and `confirm` | `compare_metric`, `cmd_confirm` |
| sudden jump after a plateau | `anomaly_breaker` | `cmd_judge` → max confirm repeats |
| stale baseline: load, thermal state, or cache warmth changed since the baseline was measured, so a no-op reads as a win | `paired` | `measure_paired` (ABBA head vs candidate), `fresh_bases` → `comparisons_for(bases=…)` in `cmd_confirm` |

Two rows of the report go in the CHANGELOG: **tricks caught / attempted** (must be T/T) and
**walls load-bearing / declared** (must be W/W, or the surplus walls are decoration and the docs say
so). The naive condition (all walls off) is §4.8's deliberately wrong subject: its false-accept rate
must be **higher** than the walled condition's on the same fixture, or the thesis is wrong and the
docs say that too.

## 5 · The live test: drive the engine in a throwaway fixture

Selftest proves the units; this proves a campaign. Never on a real repo.

```bash
python3 tests/fixtures/make_fixture.py pyfix /tmp/sb-live && cd /tmp/sb-live
SB="python3 $HOME/Documents/Github/strictlybetter/scripts/sb.py"
$SB init
for c in bench_ms tests_failed bench_checksum loc; do
  $SB card add --file ~/Documents/Github/strictlybetter/tests/fixtures/pyfix/fixture-cards/$c.json; done
$SB card probe bench_ms                                  # degradation must hurt
$SB campaign start --file campaign.json                  # goals [bench_ms]; guardrails [tests_failed, bench_checksum]
$SB prereg --file hyp.json                               # → e0001 + worktree path
#   edit slowlib/core.py in the worktree: dedupe with a set
$SB submit e0001 && $SB measure e0001 --fidelity screen && $SB judge e0001
$SB judge-verdict e0001 --file verdict.json && $SB confirm e0001 && $SB accept e0001
$SB status; $SB report; $SB next; $SB budget; $SB distill-stats; $SB doctor
```

Confirm with your own eyes: the accepted commit on `sb/<campaign>` carries the provenance block;
`baseline.json` moved only at `accept`; `ratchet.json` holds `bench_ms`; the confirm ledger event
shows holdout values, not `null`; `sb guard slowlib/core.py` exits 0 in the worktree and 2 in the
main tree; `sb guard bench.py` exits 2 anywhere; after `campaign end`, `guard` exits 0 again. Then
run a second experiment that edits `bench.py` and watch `submit` refuse it.

**Then the read-only pass with real state hashed before and after:**

```bash
H() { find .strictlybetter -type f ! -path '*/wt/*' ! -path '*/reports/*' ! -name 'lock' \
       ! -name 'measure.lock' -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256; }
H > /tmp/before
for c in status next budget doctor session-start report "ledger tail" "card list" "campaign show" \
         "worktree list" "inheritance show"; do $SB $c > /dev/null; done
H > /tmp/after && diff /tmp/before /tmp/after && echo READ-ONLY OK
```

`report` writes `reports/<campaign>.md` by documented design, so it is exempted; a gate that fires
every release is a gate nobody reads. Any other read command that changes the hash is a defect.

## 5.5 · The dogfood: uncontaminated, in a COPY, pinned to the release tree

Required when skills, agents, hooks, or the judge protocol change. Run on a **copy** of a real repo
(`dosimeter` is the standing M2 target), never on the user's working clone, never on skyclaw without
the explicit approval its zero-risk policy requires.

```bash
cp -R ~/Documents/Github/dosimeter /tmp/sb-dogfood && cd /tmp/sb-dogfood
# print the version the harness will LOAD, against the version you are SHIPPING:
python3 -c "import json;d=json.load(open('$HOME/.claude/plugins/installed_plugins.json'));\
print([v[0]['version'] for k,v in d['plugins'].items() if 'strictlybetter' in k.lower()])"
grep -m1 '"version"' ~/Documents/Github/strictlybetter/.claude-plugin/plugin.json
claude --plugin-dir ~/Documents/Github/strictlybetter      # the release tree, never the cache
```

Not equal, and not using `--plugin-dir` → stop. engram once certified a release against a plugin
cache four months behind `main`; the run passed and proved nothing. **Every gate that runs through a
platform tests whatever that platform has cached.** The engine gates are immune; this one is not.

**Give each agent exactly what the real skill gives it. Not one word more.** A "remember to pass
the id" in a dogfood prompt is a gap in the real contract: fix the skill, not the prompt. The judge
gets the diff, the pre-registration, the numbers, and the cards' `gaming_risks`, by file path; never
the experimenter's transcript.

Exit criterion (M2): ≥ 1 confirmed acceptance, 0 guardrail regressions, every number the skill
narrated matches `sb status --json`. Write down what surprised you; a surprise here is the release.

## 5.6 · The user session: a persona in fresh context, verdict binding

Everything above proves the system is correct. Nothing above proves a stranger gets through it.

A persona agent, in its own fresh context, gets **only** `README.md`, the front-door skill
`skills/strictlybetter/SKILL.md`, and a pyfix copy from `make_fixture.py`, and is told to make the
project faster without making it worse. The release agent plays the platform, following the
release-tree skills verbatim, and may not answer what the skill does not answer. **Do not fix
anything inside the session.** Write it down and keep going.

Cross-check every number the persona was shown against `sb status --json` and `sb report`
afterwards. File the report at `docs/user-sessions/vX.Y.Z-<persona>.md`:

```
## User session report — vX.Y.Z
PROVENANCE: <persona agent; what this certifies (flow, prose, numbers, the blind chain) and what
             it cannot (a real maintainer's repo, real days, an overnight run)>
fixture / experiments / accepted / minutes
WHAT WORKED · WHAT CONFUSED ME · WHAT I WOULD HAVE QUIT OVER
WHAT IT TOLD ME vs WHAT WAS TRUE   ← every number, checked against the state
WOULD A STRANGER GET THROUGH THIS?  yes / no        VERDICT:  ship / do not ship
```

**The verdict is binding.** A release the persona would not hand to a stranger does not ship, no
matter how green the other gates are. Real-world signal (an issue, the founder's own use) outranks a
simulated verdict; when they disagree, the next release says so here, with the original error kept.

## 6 · Bump the version, merge, tag, release

The version bump is a grep, not a memory:

```bash
grep -rnE '"version"|badge/version-|^VERSION =|selftest-[0-9]|[0-9]+/[0-9]+ checks' \
  .claude-plugin .codex-plugin .zcode-plugin package.json scripts/sb.py README.md INSTALL-*.md docs/12-platforms.md 2>/dev/null
```

| File | What to change |
|---|---|
| `.claude-plugin/plugin.json` | `"version"` (this is the one installs read) |
| `.codex-plugin/plugin.json`, `.zcode-plugin/plugin.json` | `"version"`, lockstep (Codex and ZCode installs read these; the Codex CLI reported `1.0.0` from it live) |
| `package.json` | `"version"` — what npm and pi install; stale here = npm ships old code under a new tag |
| `scripts/sb.py` | `VERSION`; the selftest pins it to the manifest, so a missed bump goes red **only if the manifest exists** (§4) |
| `README.md` | version badge (`badge/version-X.Y.Z`); selftest badge (`badge/selftest-N%2FN`) if the count changed |
| `INSTALL-*.md` | any selftest count they quote |

Re-run the grep after editing: **zero stale hits, or the badge lies.** Then:

```bash
V=X.Y.Z
git add -A && git commit                     # "release: vX.Y.Z — <theme>" (+ trailers)
git checkout main && git pull origin main
git merge --no-ff release/v$V -m "Merge: vX.Y.Z — <theme>"
git push origin main                         # ← the moment new installs see it
awk -v V="$V" '/^## /{on = index($0, "## " V) == 1; next} on' CHANGELOG.md > /tmp/relnotes.md
git tag -a "v$V" -m "v$V — <theme>" && git push origin "v$V"
gh release create "v$V" --title "v$V — <theme>" --notes-file /tmp/relnotes.md --latest
```

## 7 · Verify the release is real

```bash
gh release list -L 3                                             # vX.Y.Z shows "Latest"
git describe --tags --abbrev=0 origin/main                       # == vX.Y.Z
git show origin/main:.claude-plugin/plugin.json | grep version   # == X.Y.Z  (the one that matters)
```

## 7.5 · The post-release independent review

Every gate above is run by the person who wrote the code, on the code they believe is right. After
every release that touches the engine, spawn a reviewer against `main` with the shipped code (**not**
the diff), the list of what the pre-release review already found, and the standing instruction:
**"find a number that is wrong, especially one that is wrong in the direction that reassures: an
accept that should have been a discard, a `held` that was never measured, a `$` that is an estimate,
a sigma from another machine."** If it finds something, ship the patch immediately and title the
patch release by what the review caught. Three releases in an hour is not a failure; a wrong number
left standing is.

## 7.6 · The platform-port verification table

The omniplugin ladder (`docs/10` M7) adds platforms one at a time; this table must be honest per
platform, per release. "Verified live" means a real session on that platform ran a full cycle on a
fixture *from the release tree* and the guard denied a frozen edit there. Anything less is "Not
verified", in those words, here and in `INSTALL-<PLATFORM>.md`.

| Platform | Engine | Skills | Guard hook | Stop-driver | Status (2026-09-03) |
|---|---|---|---|---|---|
| Claude Code | `CLAUDE_PLUGIN_ROOT`; selftest 61/61 | native, `/strictlybetter:run` | PreToolUse exit 2 (exercised from the shell against a pyfix campaign) | Stop hook (block JSON exercised from the shell) | Not verified: no release-tree cycle in a live session on record |
| Codex | `CLAUDE_PLUGIN_ROOT` (Codex exports the legacy name); selftest 61/61 from the plugin cache | manifest-mapped, `$run`; marketplace add + plugin add ran live on codex-cli 0.149.0-alpha.4.3 in a scratch `CODEX_HOME` | shared hooks.json; binary carries PreToolUse; not fired live | shared hooks.json; binary carries Stop + `stop_hook_active`; not fired live | Not verified: no live session (no credentials in the scratch home) |
| OpenCode | `SB_ROOT` via `shell.env`, engine never extracted | extracted + `/sb-*`; 8 skills / 7 agents / 8 commands listed live on 1.18.23 (plugin route and `skills.paths` route) | V1 `tool.execute.before` throw, denied a frozen edit through the adapter against a campaign; V2 feature-detected | guard: hook-level (V1); **stop-driver: none — `sb drive --command`** | Not verified: OpenCode 2.0 (not installed), a model session, npm publish |
| Hermes | `SB_ROOT` in `~/.hermes/.env` | `external_dirs`; 8 discovered live on v0.18.2 (scratch `HERMES_HOME`); `/skill status`, `/skill stop` for the collisions | guard: gate-time only | stop-driver: none — `sb drive --command` | Not verified: a session; nudge wire shape verified live via `hermes hooks test` (context once, `{}` after) |
| Pi | `SB_ROOT` exported by the extension | `pi` manifest key + `/sb-*` templates; harness only | extension `tool_call` block, harness-verified against a campaign | stop-driver: none — `sb drive --command` | Not verified: pi not installed |
| Antigravity | `SB_ROOT` exported by the user | convention | guard: gate-time only | stop-driver: none — `sb drive --command` | Not verified: agy not installed; manifest is the three schema keys |
| DeepSeek Harness | `SB_ROOT` exported by the user | symlinks into `~/.agents/skills` | bridge PreToolUse registered; unverified | bridge Stop registered; unverified | Not verified: dsh not installed; hook files pass the shell matrix |
| OpenClaw | `SB_ROOT` in the Gateway env | Codex bundle on ≥ 2026.7; the installed 2026.3.2 predates the bundle loader | guard: gate-time only | stop-driver: none — `sb drive --command` | Not verified: hook pack installed and listed `✓ ready` on 2026.3.2 (isolated state); no Gateway firing, no plugin route |
| ZCode | `ZCODE_PLUGIN_ROOT` | convention + marketplace (GUI) | shared hooks.json exit 2; runtime bundle has the exit-2 branch; not fired live | shared hooks.json `decision: block`; runtime has the branch; not fired live | Not verified: static bundle read + 7-case execution matrix only; PreCompact is not an event on 3.9 |

A platform without a pre-edit hook keeps only the gate-time `sb submit` check; its row says
"guard: gate-time only", never a blank cell. Hand every edited shared skill to an uncontaminated
agent on a *different* platform and ask the three omniplugin questions (which mechanism applies to
you; trace the resolution block; could anything here make you do the wrong thing). Write capability
tests, never platform names.

## 8 · Tell existing users how to update

```
claude plugin marketplace update strictlybetter && claude plugin update strictlybetter@strictlybetter
```

then restart or `/reload-plugins`. State lives in the target repo, not the plugin cache, so it
survives an update; say so. Close the issues this release fixes with a real reply: what shipped, what
the wrinkle was, how to get it.

### One-glance checklist

- [ ] `release/` branch; selftest + unittest green to start; every engine change has a check that fails without it; no constant changed without a major bump
- [ ] CHANGELOG written with the gates paragraph and the benchmark pointer
- [ ] **§4** selftest N/N, N == badge; `version pinned to plugin.json` printed as `ok`; unittest OK
- [ ] **§4.5** every standing mutation run; every new check mutation-tested; no *no check exists yet* row for an area this release touched
- [ ] **§4.6** review against `/tmp/sb-review`; reports received == reviewers launched; findings fixed + checked
- [ ] **§4.7** fuzz 0 / 500; read paths from the dispatch table **plus sub-actions**; re-fuzzed after the last commit
- [ ] **§4.8** six questions in writing per new number; sibling commands cross-checked; every caveat reaches a string a human sees
- [ ] **§4.9** gaming suite T/T caught, W/W walls load-bearing; naive false-accept rate reported beside ours
- [ ] **§5** live fixture test; read-only pass hash-identical (report exempted)
- [ ] **§5.5** dogfood on a COPY, version printed first, agents given exactly the skill's inputs
- [ ] **§5.6** persona session in fresh context; report filed; verdict = ship
- [ ] **§6–7** grep zero stale; merged `--no-ff`; tag; `gh release … --latest`; `origin/main` manifest carries the version
- [ ] **§7.5** post-release review with the standing instruction · **§7.6** port table honest · **§8** update line published, issues closed with a reply

**The pattern, stated once:** every test you write confirms what you already believe. The things that
find real bugs are the ones you do not control: a fuzzer, a reviewer, a scripted gamer, and a user who
did not come back. Budget for all four, every release. They are the only measurement in the building
that is not looking in a mirror.
