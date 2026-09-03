# Changelog

## 1.1.1 — 2026-09-03 · what the first live run caught

The first end-to-end run of the front-door skill on a fresh pyfix copy, with the plugin installed
from the marketplace cache (`docs/user-sessions/v1.1.0-live-run.md`). One commit accepted and
re-validated externally as genuine; three defects found, two fixed here, one left open.

### Fixed
- `sb status --json` reported `"profile": true` on a fresh repo (the 1.1.0 read-path hardening
  returned a non-empty dict for a missing file); the front door would have skipped orient. `profile()`
  now returns `{}` when the file is missing; selftest check "fresh repo has no profile".
- The timer-divergence validity check compared ratios of instrument time to process wall-clock, so a
  benchmark with fixed setup cost (input generation, interpreter start) would flag a genuine large
  speedup as tampering once the timed work became a small share of the process. It now compares
  absolute savings: checkable only when the claimed saving is at least 10% of the process
  wall-clock, and then the wall-clock must drop by at least 25% of the claim
  (`WALL_DIVERGENCE_MIN_SHARE`, `WALL_DIVERGENCE_MIN_FRACTION`). Three selftest checks.
- Diagnostics measured at confirm now refresh their baseline value on accept, so the brief's
  frontier stops showing stale diagnostic numbers after a win.
- Metrologist guidance: `expected_duration_s` lower bound is the instrument's fixed cost, never a
  fraction of the baseline. In the live run the genuine `word_freq` fix (screen 20.1→4.9 ms, judge
  clean) was discarded as `invalid` at full fidelity because the whole bench finished in 0.178 s,
  under the card's 0.3 s floor set from the baseline's duration. Cards are frozen for a campaign,
  so the only recovery was `campaign end`. (`agents/sb-metrologist.md`, `skills/_shared/metric-card.md`,
  `templates/card.json.tmpl`.)

### Open
- The bandit proposed `concurrency` for a single-threaded pure-Python microbench and the run skill
  gives the orchestrator no way to decline an operator; it cost one experiment (discarded as noise).
  A logged operator swap with a stated reason is the intended fix; not in 1.1.1.

Gates run for this release: selftest 88/88; unittest 62 OK; the live run above (3 experiments, 1
accepted; `bench --mode analyze` re-validation: genuine, process wall 1.003→0.489 s on fresh seeds,
outputs match, tests pass). Mutation and fuzz gates unchanged from 1.1.0 (the diff touches no read
path they cover beyond `profile()`, which the selftest now checks). Persona gate struck (§5.6).
Benchmark: unchanged from 1.1.0 (no wall or constant changed except the divergence rule, which the
gaming matrix exercises: G6-timer stays caught by validity or judge in every configuration).

## 1.1.0 — 2026-09-03 · multi-repo, monorepo scope, services, paired confirmation

The unit of a campaign stays one repository. This release fits that unit to the layouts real
projects have: the harness in a sibling repo, one package of a monorepo, a service the measurement
needs. `docs/07-universality.md` §7.7 is the spec and states the recommended shape: one campaign
per repo; every other repo is an instrument (`external_instruments`) or a service (`services`);
monorepos run one campaign per package (`scope_paths`); cross-repo atomic experiments are not
supported and not planned. Confirmation is now paired: the candidate is compared against the
campaign head measured in the same run, interleaved, instead of a baseline measured when the
campaign started.

Gates run for this release (2026-09-03, one MacBook, 8 cores, load 6–25 during timing runs): `python3 scripts/sb.py selftest` 86/86; `python3 -m unittest discover -s tests` 62 tests OK (engine units, fixture end-to-end through the CLI, the four hook scripts); `bun test` 17/17 (OpenCode and Pi adapters); mutation check `tests/mutation_check.py` 22/22 mutations turned the selftest red (2 of them via a crash, which is red); fuzz `tests/fuzz_read_paths.py` 0 crashes on 4 fresh seeds × 300 corrupt states (started at 384 crashes / 36 signatures; every read path now degrades to an `sb:` error line); adversarial review against an extracted tree found 13 confirmed defects including one false-accept path, all fixed in afeb0e6 and covered by new selftest checks; docs reconciled with the shipped engine by an independent pass. Struck for 1.1.0: the persona user session (§5.6, too heavy for what it certifies; real-world signal replaces it) and the real-agent dogfood campaign. Not run: a live-session cycle on any platform (§7.6).

Benchmark (`20260903-145631-scripted-pyfix.md`, `20260903-150530-gaming-pyfix.md`; pyfix fixture, 3 seeds × 15 scripted experiments per condition, one MacBook, 8 cores, 1-min load 5–33 during the scripted run and 4–7 during the gaming matrix; every accepted commit re-validated on fresh seeds with the pristine instrument and an external timer): **walls** accepted 6 of 45 experiments, false accepts 0/6 (0%), planted wins found 6/9 (67%), no-ops accepted 0/18 (0%), gaming tricks accepted 0/18 (0%), mean loop 95 s; **naive** (one benchmark run, tests as backpressure, no evaluator protection) accepted 5 of 43, false accepts 5/5 (100%), wins found 0/8 (0%), no-ops accepted 0/18 (0%), gaming tricks accepted 5/17 (29%), mean loop 23 s. End-to-end external speedup of the walls branch: 86.1% / 92.8% / 86.3% per seed with outputs matching the base on every fresh seed; naive: −24.7% / −6.0% / +10.2% (outputs mismatched in seed 3). Gaming matrix: all six casebook tricks caught under all walls and under every single-wall removal (nine configurations); the naive loop merged the benchmark edit and then compared every later experiment against the poisoned instrument. The blind judge in the gaming matrix is a regex stand-in, not the LLM judge. Numbers are from one loaded laptop; the results files carry the load averages.

### Added

- **External instruments** (`external_instruments` in the campaign spec, `integrity.external_paths`
  on a card): absolute paths outside the repo. `sb campaign start` content-hashes each one (a file by
  its bytes; a directory recursively, skipping `.git`, `__pycache__`, `node_modules`, `target`,
  `.venv`, `venv`, `.tox`, `.mypy_cache`, `.pytest_cache`, `dist`, `build`) into
  `campaign.json["external_hashes"]`; a missing path, or one inside the repo, is an error at start.
  The hashes are re-checked before every decision (`sb measure` while running, `sb judge`,
  `sb confirm`, `sb accept`); a mismatch halts with `external-tampered:<path>`. The guard denies
  edits under an external instrument while a campaign runs. `sb next --json` lists the merged set
  as `external_instruments`.
- **Scope** (`scope_paths`): repo-relative patterns. When non-empty, `sb submit` marks a changed file
  outside them as the integrity violation `scope:<file>` and the guard denies out-of-scope edits inside
  an experiment worktree. Frozen and protected checks run first and still apply. Empty means the
  whole repo. `sb next --json` lists `scope_paths`.
- **Services lifecycle** (`services` in the campaign spec, and the same object as `card.services`):
  `{setup, ready, teardown, cwd, ready_timeout_s: 120, ready_interval_s: 2, setup_timeout_s: 600,
  teardown_timeout_s: 300}`. Campaign-level services come up once per measuring command
  (`sb baseline`, `sb measure`, `sb confirm`, `sb card probe`) around all cards; card-level services
  around each measurement of that card. `ready` is polled until exit 0 or the timeout; commands run
  in the checkout (or `cwd` under it) with `SB_CHECKOUT` set to the checkout path. Setup failure or
  readiness timeout makes the measurement invalid (`discard: invalid`, never a crash); `sb baseline`
  and `sb card probe` refuse to run instead. Teardown always runs, in a `finally`.
  `archetypes/service-api.json` carries a `services_hint` with the compose shape.
- **Paired confirmation** (wall toggle `paired`, default true, the ninth entry in `WALL_KEYS`): at
  `full` and `confirm` fidelity `sb confirm` checks the campaign head out into a second worktree
  and measures head and candidate interleaved, ABBA per repeat with the same holdout value on both
  sides, then compares the candidate's median against the head's fresh median. Sigma still comes
  from the k-repeat baseline; `k` in the threshold is the fresh head run's valid repeat count;
  inconclusive rounds add repeats to both sides; an invalid head measurement falls back to the
  stored baseline. The confirm ledger event gains `paired` and `head_results`; the provenance
  block prints `paired=yes|no`. This is standard performance-CI practice (rustc-perf measures the
  baseline in the same job; Chromium Pinpoint runs paired A/B); the bench had shown time drift
  between baseline and confirmation producing a false accept and a no-op accept on a loaded
  machine. Cost: confirmation takes about twice as long. The bench's `walls` condition is now all
  nine walls, and the gaming matrix ablates `paired` like the others.
- **Selftest**: a second temp repo with a sibling harness directory exercises all three (instrument
  hashed at start, teardown ran after baseline, baseline measured through the service, guard denies
  the external instrument and an out-of-scope worktree path and allows an in-scope one, submit flags
  `scope:`, tampering with the harness halts as `external-tampered`, a service that never becomes
  ready is `discard: invalid`); the scripted campaign checks that confirmation is paired against
  the fresh head and that the paired baseline is the fresh head median. 86 checks.
- Templates (`campaign.json.tmpl`, `card.json.tmpl`) and the shared contracts
  (`skills/_shared/metric-card.md`, `skills/_shared/ledger.md`) document the fields; `docs/02`,
  `03`, `07`, `09`, `12` and the README carry the rules.

### Changed

- Review fixes that landed after the 1.0.0 entry was written (the adversarial review's confirmed
  defects; the 1.0.0 entry below does not list them):
  - `sb accept` binds to the confirmed commit and requires integrity; `--force` is refused while the
    confirm wall is on.
  - The ratchet moves only in the good direction: guardrail floors never drift, sigma stays the
    baseline's, `secs_per_run` is refreshed, start values are recorded, and the report computes
    held, improved, and DRIFTED.
  - Full-level comparisons skip cards without a `full` block.
  - Holdout rotation re-baselines guardrails too; `sb baseline` honours `walls.holdout`.
  - Duplicate `METRIC` lines are ambiguous and therefore invalid; `regex:` likewise.
  - Metric cards are fingerprinted at campaign start and verified before every decision
    (`card-tampered:<id>`, `card-missing:<id>`); `sb card add` is refused while a campaign is
    running or halted; a head worse than a ratcheted best halts `campaign start`
    (`ratchet-regression:<metric>`; `--allow-ratchet-regression` overrides).
  - The guard keeps the basename of a new file; `frozen-guard.sh` fails closed on an engine error.
  - Confirm-fidelity `sb measure` is refused while a campaign runs (holdout leakage; `--audit` for
    a human); `sb ledger view` and `tail` redact a discarded candidate's confirm numbers and
    `experiments` prints none, `--unredacted` is the audit path.
  - Dependency manifests are matched by basename; a `gamed` verdict cannot be overwritten.
  - The Stop driver walks up to find the campaign in a monorepo; the judge protocol's stale
    composer is removed.
  - Bench: `apply-failed` is excluded from denominators, tolerant tricks, a goal-regression label;
    stale results regenerated by the shipped bench.

## 1.0.0 — 2026-09-03 · first release

The engine, the walls, the cost layer, the knowledge packs, the Claude Code surface, the port
scaffold, and the meta-benchmark ship together, because the acceptance rule is not worth shipping
without the walls that make it true. The theory docs (`docs/00` to `docs/11`, with verified
citations) are the spec. Where this entry and a doc disagree, the doc is wrong and is fixed in the
next commit (`CLAUDE.md`, doc-drift rule).

Gates run for this release: 1.0.0 was never tagged; its gates are the 1.1.0 gates above, run on the same day against the fixed engine.
Benchmark: see the 1.1.0 entry.

### Added

**Engine** (`scripts/sb.py`: one file, stdlib only, zero network, `VERSION = "1.0.0"`)

- 27 commands behind a `HANDLERS` dict plus `selftest`; the 18 in `MUTATING` run under a file
  lock. Free text enters through `--file` or stdin, never argv. Every state write is atomic
  (temp file + rename). State home is `<repo>/.strictlybetter/`, overridable with `SB_HOME`.
- **Metric cards** as JSON under `metrics/`, schema-checked on every load (`id`, `kind`,
  `direction` incl. `equal`, `measure.{command,parse}`, `fidelity` keyed by
  `screen|full|confirm`). Three parsers: `metric-line:` (the autoresearch ecosystem's
  `METRIC name=value` line, so an existing bench is a card without modification), `regex:`, `json:`.
- **Validity before comparison** (`measure_once`, `comparisons_for`): exit code, parse, timeout,
  duration inside `expected_duration_s`, a non-deterministic value on an `equal` metric, and an
  **instrument-versus-wall-clock divergence check**: a time-unit goal whose instrument claims at
  least 2× faster while the process wall-clock barely moved is invalidated with the note "timer or
  instrument tampering?". An invalid run is `discard: invalid`, never a candidate.
- **Baseline** (`sb baseline`): k=5 repeats at every fidelity level the card defines, from a clean
  throwaway worktree; median, sigma, seconds per run, commit, and environment fingerprint written
  to `baseline.json` and back onto the card's `noise`. A goal or guardrail with no valid baseline
  or no measured sigma halts `campaign start`. `equal`-direction metrics are summarized per
  holdout value as one canonical string, so a checksum may legitimately differ per seed and is
  invalid only when the same seed disagrees with itself. A card with `reuse_output` re-parses the
  most recent identical run in-process instead of paying for the command twice.
- **Monotonicity probe** (`sb card probe`): applies the card's `degradation.apply` recipe in a
  throwaway worktree and requires the metric to move the wrong way. A card that cannot see a
  deliberate regression is not an instrument.
- **The acceptance rule** (`compare_metric`, `decide`): a goal must beat κσ (κ = 2.5); a
  guardrail may not drop more than τσ (τ = 1.0); `equal` guardrails must match byte-for-byte;
  invalid beats everything, regression beats improvement. Complexity regularizer
  κ_eff = κ·(1 + 0.3·ln(1 + diff_lines/50)) + 1.0 per undeclared dependency manifest.
  Composition `pareto` (default) or `oec` with frozen weights.
- **Campaign lifecycle**: `campaign start` freezes the set, hashes frozen paths from a clean
  checkout, auto-adds hygiene guardrails and the global ratchet, and creates `sb/<id>`;
  `prereg` charges the experiment budget *before* creating the worktree and returns `eNNNN`;
  `submit` commits the worktree and runs integrity (frozen, protected, `.strictlybetter/`, eval
  hash, dependency manifests outside the `dependency` operator); `measure` at
  `screen|full|confirm`; `judge` gives the statistical verdict with one `retry-screen` for
  within-noise-but-predicted-large; `judge-verdict` stores the blind judge's JSON and rejects any
  extra field; `confirm` runs `full` then `confirm` from a clean checkout with holdout values and
  adaptive repeats up to the card's cap, then discards as `noise`; `accept` fast-forwards the
  branch with `commit-tree`, appends a provenance block to the commit message, and ratchets;
  `discard --reason` uses a fixed vocabulary and can archive the diff.
- **Ledger** `ledger.jsonl`: append-only `{ts, id, event, data}` events folded into one record per
  experiment; a torn line is skipped and never bricks a read.
- **Cold-start brief** (`sb next`): frontier with sigma, budget left, batch size from screen cost,
  exploration level and allowed diff sizes, a Thompson-sampled operator mix over 13 operator
  classes with archetype priors, recent dead ends, accepted wins, archive hints, the inheritance
  body's path.
- **Plateau and distill** (`sb distill-stats`): exploration rises after `PATIENCE` = 8 discards
  (max level 3); `screen_untrusted` trips when the false-promotion window (10 promotions, 40%) is
  exceeded and doubles screen repeats; decision is `continue`, `explore:levelN`,
  `stop:converged`, `stop:budget`, or `stop:halted`.
- **Governance**: `STOP` file and `sb stop`; iteration cap (200); halts on budget, on two
  consecutive integrity violations, and on a holdout-gap ratio above 0.75 over the last five
  acceptances; `sb guard <path>` exits 2 to deny and reads the PreToolUse payload with `--stdin`;
  `session-start` prints one line or nothing; `doctor`; `drive --command` runs an external agent
  once per cycle for headless use; `worktree`, `ledger`, `inheritance`, `cost`, `budget`,
  `status`, `report`.
- **Selftest**: 86 checks, including the AST no-network guard, the version pin to
  `.claude-plugin/plugin.json`, parser and acceptance-rule fixtures, guard decisions, and a scripted
  four-experiment campaign on an in-memory git repo (real improvement accepted with provenance;
  frozen-path edit refused at submit; no-op discarded as noise and archived; guardrail regression
  discarded despite a large goal win; budget cap halts; torn ledger tolerated; report written).
  `tests/`: 32 stdlib `unittest` cases, 25 unit (`test_engine.py`) and 7 end-to-end through the
  real CLI on the pyfix fixture (`test_fixture_campaign.py`: baseline sigma, monotonic probe,
  frozen edit caught and guard denies, wrong output is a guardrail regression, verdict schema,
  status/next/report, doctor/ledger).

**Walls** (`docs/04`; toggles in `WALL_KEYS`, all on by default, each switchable off for the bench)

- `validity`, `noise_floor`, `confirm` (clean checkout, never the experimenter's worktree),
  `holdout` (kinds `env`, `arg`, `dir`; rotated after 10 acceptances with a confirm-level
  re-baseline), `frozen_guard` (PreToolUse hook plus gate-time check in `submit`), `judge` (blind
  by schema: `verdict`, `pattern`, `evidence`, `recommended_check`, nothing else; `suspicious`
  raises confirm repeats to the cap; `gamed` blocks confirm and counts toward the halt),
  `prereg` (the ledger line exists before the worktree does), `anomaly_breaker` (a screen effect
  above 3× the rolling mean of confirmed effects, after half a patience without acceptance, is
  confirmed at max repeats).
- **Holdout gap** tracked per accepted change and as a trend; the campaign halts when the mean
  over the last five exceeds the ratio.
- **Regression by construction**: every goal and guardrail measured at every fidelity; hygiene
  guardrails always included; the global ratchet (`ratchet.json`) turns every past goal into a
  guardrail for every future campaign, demotable only by a logged human act.

**Cost layer** (`docs/05`)

- Fidelity ladder per card; screen repeats multiplier when screen is untrusted.
- Budget in experiments, hours, and dollars; `experiments` charged at pre-registration;
  wall-clock charged per measurement; `sb cost <id>` records tokens, wall, and tier, converting
  tokens to dollars with the campaign's pricing table (default 5 / 25 per Mtok) and stamping the
  record `estimated: true` unless `--dollars` was given. Status and report print `est $`.
- Bandit over operator classes (Beta posterior, archetype priors) sets the batch mix.
- `stats()` reports experiments, promoted, accepted, discarded by reason, false promotions and
  the window rate, wall and estimated dollars per accepted improvement, mean confirmed effect,
  holdout-gap mean over the last five, budget left.
- Contention: timing-sensitive cards (`contention_safe: false`) serialize behind `measure.lock`;
  `max_parallel` worktrees; `PYTHONHASHSEED` and `PYTHONDONTWRITEBYTECODE` pinned by the harness.

**Knowledge packs**

- Archetype packs `archetypes/*.json`, one per row of `docs/07` §7.1 (rust-crate,
  python-package, node-frontend, service-api, cli-tool, ml-training, ml-inference, science-sim,
  data-pipeline, docs-site, library-generic): match rules, command hints, protected and
  frozen-path hints, default cards, operator priors, noise sources, hygiene guardrails.
- Operator library `operators/*.md`, one file per class in `OPERATORS` plus a README: when to
  use, tier, expected diff size.
- Templates under `templates/`: `profile.md.tmpl` + `profile.schema.json`, `campaign.json.tmpl`,
  `card.json.tmpl`, `hypothesis.json.tmpl` + schema, `verdict.json.tmpl` + schema,
  `judge-checklist.md`, `inheritance.md.tmpl`, `report.md.tmpl`.
- Fixtures under `tests/fixtures/`: `pyfix` (Python package, three deliberately slow functions),
  `rustfix` (Rust crate with bench, tests, clippy), `greenfield` (one module, no instruments),
  each with `fixture-cards/` and `make_fixture.py` to stamp a throwaway git repo.
- Inheritance body `inheritance.md`, rewritten by the distiller through `sb inheritance write`.

**Claude Code surface** (`docs/10` §10.2 to §10.5)

- Skills: front door `/strictlybetter` (status → orient / instrument / gate 1 → one cycle), plus
  `sb-orient`, `sb-metrics`, `sb-run`, `sb-status`, `sb-distill`, `sb-stop`; `_shared/` carries
  the engine-resolution block, the card schema, the ledger schema, the judge protocol, and the
  subagent rules (items by file path, one child per judgment, no dialogue).
- Agents: `sb-orienteer`, `sb-metrologist`, `sb-experimenter-{low,medium,high}` (byte-identical
  except `effort:`), `sb-judge` (Read-only, medium), `sb-distiller`.
- Hooks (`hooks/hooks.json`): SessionStart on `startup|resume|clear|compact` →
  `session-start.sh`; PreToolUse on `Edit|MultiEdit|Write|NotebookEdit` → `frozen-guard.sh`,
  which pipes the raw payload to `sb guard --stdin` and exits 2 to deny (fast path: no
  `campaign.json` reachable from the edited path means python is never started); PreCompact
  re-pins the campaign id, frozen paths, and the harness-computes rule; Stop driver re-invokes
  one cycle while the campaign is running, under budget, and below the iteration cap.
- `.claude-plugin/plugin.json` and `marketplace.json`.

**Ports** (`docs/12-platforms.md`; one `INSTALL-<PLATFORM>.md` each; the honest table in
`RELEASE_PROTOCOL.md` §7.6 — no platform is "verified live" at 1.0.0, Claude Code included)

- L0 (clone, point the platform at `skills/`, export `SB_ROOT`) carries the whole loop everywhere;
  the guard falls back to the gate-time `sb submit` integrity check and the loop is driven by
  `sb drive --command` wherever the host has no pre-edit or Stop hook.
- **Codex**: `.codex-plugin/plugin.json` (skills mapped, no `hooks` key — OpenClaw reads the same
  file), `.agents/plugins/marketplace.json`, `codex/agents/*.toml` (bodies verbatim, the only port
  with per-agent effort pinning via `model_reasoning_effort`, judge `read-only`),
  `scripts/install-codex.sh`. Marketplace add / plugin add / whole-repo cache / selftest from the
  cache ran live on codex-cli 0.149.0-alpha.4.3 in a scratch `CODEX_HOME`; no live session.
- **OpenCode**: `package.json` + `.opencode-plugin/` (combined `{id, server, setup}` entry, zero
  SDK imports; self-extract of skills/agents/commands with sha256 ownership so user edits are never
  overwritten; the engine is never extracted — `SB_ROOT` rides `shell.env`), V1 hook adapters
  `hooks/*.ts` (nudge, `tool.execute.before` guard that throws on exit 2, compaction pins), V2
  `setup()` with location-wrapped workspace resolution and feature-detected hooks, 17 `bun test`
  checks. Plugin and `skills.paths` routes verified live on OpenCode 1.18.23; OpenCode 2.0 not run.
- **Hermes**: `hooks/session-start-hermes.sh` (dual mode, deduped, fails closed); install by clone +
  `external_dirs` + `SB_ROOT` in `.env`. Eight skills discovered and the `pre_llm_call` wire shape
  verified live on v0.18.2 in a scratch `HERMES_HOME`. `/status` and `/stop` collide with built-ins
  (`/skill status`, `/skill stop`).
- **Antigravity**: root `plugin.json` with the three schema keys only; no hooks, `SB_ROOT` is an
  install step. Not verified (`agy` absent; schema URL 404 on 2026-09-03).
- **OpenClaw**: hook pack `hooks/sb-campaign/` (nudge on `/new` and `/reset`, reads `SB_REPO`,
  engine via `SB_ROOT` when installed standalone). Hook-pack install and listing verified on the
  installed 2026.3.2 in an isolated state dir; that build predates the bundle loader, so the plugin
  route is unverified.
- **Pi**: `pi/strictlybetter.ts` (exports `SB_ROOT`, fire-and-forget nudge, `tool_call` guard that
  blocks on exit 2, inert nudge in children) + eight `pi/prompts/` templates (`/strictlybetter`,
  `/sb-*`, strict-YAML frontmatter) + the `pi` key in `package.json`; 14 fake-host checks and a
  real-exec harness against a campaign. Pi not installed: not verified live.
- **DeepSeek Harness**: `dsh/hooks.json` (SessionStart JSON wrapper `hooks/session-start-dsh.sh`,
  PreToolUse guard, Stop driver), `dsh/cordis.patch.yml`, clone-and-symlink install. Not verified
  (dsh absent); the hook files pass the shell matrix.
- **ZCode**: `.zcode-plugin/plugin.json`; the shared hooks already switch to the JSON shape under
  `ZCODE_PLUGIN_ROOT` / `SB_HOOK_FORMAT=json`. Verified statically against the installed 3.9-line
  runtime bundle (manifest fallthrough, events, root vars, exit-2 and `decision: block` branches;
  no PreCompact event) plus an execution matrix; no GUI install, no session.
- Version now lives in four manifests (`.claude-plugin`, `.codex-plugin`, `.zcode-plugin`,
  `package.json`) — all in the §6 grep.

**Bench** (`docs/10` §10.7)

- `bench/run_bench.py` with three modes: `scripted` (LLM-free seeded sequence of real wins,
  no-ops, and gaming tricks through the real engine under each condition, every accepted commit
  re-validated on a fresh holdout with the pristine instrument and an external process timer, so
  a change that only fooled the loop's own instrument counts as a false accept); `gaming`
  (wall-ablation matrix: each trick under full walls and with each wall disabled in turn,
  reporting which wall catches which trick); `analyze` (re-validate a campaign real agents ran).
  Conditions `walls` (all eight on; guardrails tests + checksum) and `naive` (every wall off, one
  full-size run decides, tests only). Results land in
  `bench/results/<stamp>-<mode>-<fixture>.{json,md}`; nothing in a report is typed by hand.

### Known limitations at 1.0.0

- `WALL_KEYS` declares `prereg`, and no code path reads it. Pre-registration is enforced by
  construction (`prereg` precedes the worktree), not by the toggle; the toggle is inert.
- The docs describe a drift check at re-baseline, a disk and memory halt, a per-phase cost
  split, judge overhead, a yield curve, and `sb distill --global`. None is in the engine yet.
- Limited leakage is enforced at the CLI, not in the file: the confirm results of discarded
  candidates are written to the ledger in full; `sb ledger view` and `tail` redact them,
  `experiments` prints no numbers, and `--unredacted` is the audit path. The brief (`sb next`)
  surfaces accepted effects only, as designed.
- The version-pin selftest is skipped when `.claude-plugin/plugin.json` is absent; the manifest
  exists now, so the check runs, and §4 of the release protocol demands its line be printed.
- The judge's `recommended_check` is stored and never executed; a `suspicious` verdict raises
  confirm repeats to the card's cap instead of running the check the judge asked for.
- `frozen-guard.sh` exits 0 (allows) when it cannot find a campaign, a readable path in the
  payload, `python3`, or the engine. This is the documented fast path and the shape of the
  fail-open bug class; the port table must record it per platform.
- Wall-clock spend in `cmd_measure` is added after the `try/finally`, so a measurement that
  raises loses its wall-clock from the budget; `cmd_confirm` charges inside `finally`.
- Cost accounting is an estimate unless the platform's real usage is passed in; the label says so.
