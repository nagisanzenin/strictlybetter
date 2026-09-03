# Metric card (shared contract)

A metric card is one JSON file under `.strictlybetter/metrics/<id>.json`, added with
`$SB card add --file <path>`. It is everything the engine needs to trust a number: a
command that emits it, how to parse it, the direction of "better", how noisy it is
(measured, never declared), what must stay frozen for the number to mean anything, and how
it could be gamed. Agents write cards into `.strictlybetter/inbox/`; only the engine writes
into `metrics/`. Transcribed from `validate_card`, `fidelity_spec`, `measure_once`,
`summarize`, `holdout_values`, and `cmd_card_probe` in `scripts/sb.py`, and docs/02.

```json
{
  "id": "bench_ms",
  "title": "bench.py median wall-clock, sum over functions",
  "kind": "goal",
  "direction": "minimize",
  "unit": "ms",
  "measure": {
    "command": "python3 bench.py",
    "parse": "metric-line:bench_ms",
    "cwd": ".",
    "timeout_s": 300,
    "env": {"SB_BENCH_SIZE": "3000", "SB_BENCH_REPEATS": "5"},
    "expected_duration_s": [0.2, 120],
    "allow_nonzero_exit": false
  },
  "fidelity": {
    "screen":  {"repeats": 1, "env": {"SB_BENCH_SIZE": "1200", "SB_BENCH_REPEATS": "3"}},
    "full":    {"repeats": 1},
    "confirm": {"repeats": 3, "max_repeats": 6,
                "holdout": {"kind": "env", "var": "SB_SEED", "values": [1913, 8241, 6607]}}
  },
  "acceptance": {"kappa": 2.5, "tolerance_sigma": 1.0},
  "integrity": {"frozen_paths": ["bench.py", "tests/", "run_tests.py"]},
  "degradation": {"apply": "python3 - <<'EOF'\nimport re;p='slowlib/core.py';s=open(p).read();assert 'def dedupe_preserve_order' in s;s=s.replace('def dedupe_preserve_order(', 'import time\\ndef dedupe_preserve_order(',1).replace('    result = []', '    time.sleep(0.002)\\n    result = []',1);open(p,'w').write(s)\nEOF", "expected": "worse"},
  "gaming_risks": [
    "the hot function branches on the fixture's length or a sentinel value",
    "results memoized on the exact benchmark input so repeats after the first are free",
    "a C extension, ctypes call, or subprocess to another toolchain introduced without the dependency operator"
  ],
  "contention_safe": false,
  "hygiene": false,
  "noise": null
}
```

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | `[A-Za-z0-9_.-]{1,64}`; the file name and the name used in campaigns, predictions, and the ledger |
| `title`, `unit` | no | for humans and the report |
| `kind` | yes | `goal` (must improve beyond κσ), `guardrail` (must not drop beyond τσ), `diagnostic` (recorded at full/confirm, never decides) |
| `direction` | yes | `maximize`, `minimize`, or `equal` (a value that must not change: a checksum, an API snapshot, a golden output; strings allowed) |
| `measure.command` | yes | shell command run from a **clean checkout** of the commit under test, never from the experimenter's shell |
| `measure.parse` | yes | one of the three forms below |
| `measure.cwd` | no | subdirectory of the checkout to run in (default `.`) |
| `measure.timeout_s` | no | default 600; a timeout is an invalid run, never a number |
| `measure.env` | no | extra environment; the engine adds `SB_FIDELITY`, `SB_METRIC`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=0` unless you set them |
| `measure.expected_duration_s` | no | `[lo, hi]` validity band in seconds; a run outside it is invalid (a zero-second "win" is the Gomoku case, docs/01). `lo` is the instrument's fixed cost (startup plus input generation), never a fraction of the baseline: a real 25× speedup must still be a valid run. |
| `measure.allow_nonzero_exit` | no | default false: a non-zero exit is an invalid run. Set true only for instruments that report a count and exit non-zero by design |
| `fidelity.<level>` | no | per-level overrides of any `measure` key plus `repeats`, `max_repeats`, `holdout`, `skip`. Levels: `screen` (what experiments see; cheapest), `full` (run at confirm time when present), `confirm` (harness only, holdout, repeats). Defaults: `repeats` 1 (confirm: 3), `max_repeats` = repeats (confirm: 3). `skip: true` at `screen` and `full` makes a confirm-only metric (a held-out test split the experimenter never sees) |
| `acceptance.kappa` | no | default 2.5; goal must move by more than `kappa_eff × sigma` |
| `acceptance.tolerance_sigma` | no | default 1.0; as a guardrail, may not drop more than this many sigma. **Use `0` for deterministic guardrails** (test failures, lint counts, checksums): any drop regresses |
| `integrity.frozen_paths` | no | paths hashed at campaign start and denied to the experimenter: the bench, the tests, fixtures, eval scripts, reference outputs. Patterns: `dir/` prefix, glob (`*.pem`), or exact path |
| `integrity.external_paths` | no | absolute paths **outside** the repo this number depends on (a harness in a sibling repo). Merged with the campaign's `external_instruments`, content-hashed at campaign start into `campaign.json` `external_hashes`, re-checked before every decision (halt `external-tampered:<path>`), and denied to the experimenter by the guard. A path inside the repo is refused at start: use `frozen_paths`. Part of the card fingerprint |
| `services` | no | `{setup, ready, teardown, cwd, ready_timeout_s: 120, ready_interval_s: 2, setup_timeout_s: 600, teardown_timeout_s: 300}`, the same shape as the campaign spec's `services`. Brought up around each measurement of this card, in the checkout (or `cwd` under it) with `SB_CHECKOUT` set to the checkout path; `ready` is polled until exit 0 or the timeout; `teardown` always runs. Setup failure or readiness timeout makes the measurement invalid, never a crash. Use the campaign-level `services` for what every card needs. Part of the card fingerprint |
| `degradation.apply` | for probe | a shell recipe, run in a throwaway worktree, that must make the metric **worse by more than sigma**. Anchor it (assert the target text exists) so a stale recipe fails loudly instead of silently doing nothing. `card probe` refuses a card without it |
| `gaming_risks` | yes in spirit | strings handed to the blind judge; `card validate` flags an empty list. Name the cheap tricks that would move *this* number without improving the property |
| `contention_safe` | no | `true`: may run concurrently with other measurements (counts, checksums). `false` (default): timing-sensitive, the engine serializes it behind `measure.lock` |
| `reuse_output` | no | `true`: this card re-parses another card's identical command (a checksum printed next to a timing) and reuses that run's output instead of paying for the command twice |
| `hygiene` | no | `true`: the engine adds this guardrail to **every** campaign whether or not the user listed it (build passes, tests pass, lint clean). Set it on the archetype pack's `hygiene_guardrails` |
| `noise` | engine | written by `sb baseline`: `{sigma, samples, method, measured_at, environment_fingerprint}`. Author it as `null`; a hand-written sigma is a lie the engine will overwrite |
| `title`, `cost` | ignored | not read by the engine; cost is measured (`secs_per_run` per level in `baseline.json`) |
| `probe` | engine | written by `card probe`: `{monotonic, detail, at, commit}` |

## `parse` forms

- `metric-line:NAME` reads the last line matching `METRIC NAME=value` on stdout (then stderr). The autoresearch ecosystem convention; an existing bench script that prints it is a card without modification. Non-numeric values are allowed for `direction: equal`.
- `regex:PATTERN` takes group 1 of the **last** match (whole match when there is no group), multiline, stdout then stderr.
- `json:a.b.0` parses the whole stdout as JSON (or the last line that is JSON) and walks the dotted path; list indices are integers.

## Holdout (`fidelity.confirm.holdout`)

Confirmation uses inputs the experimenter never saw. Three kinds:

- `{"kind": "env", "var": "SB_SEED", "values": [1913, 8241, 6607]}`: repeat *i* sets the variable to `values[i % n]`. The measured command must actually read the variable, or the holdout is inert (say so in `gaming_risks`).
- `{"kind": "arg", "values": [...]}`: the literal `{holdout}` in the confirm command is replaced with the value.
- `{"kind": "dir", "name": "hidden-tests", "dest": "tests/hidden", "values": ["fixture"]}`: `.strictlybetter/holdout/<name>` is copied into the checkout at `<dest>` before measuring. `values` must be a non-empty list for the copy to happen (engine quirk); the entries are otherwise unused.

After every 10 acceptances the engine rotates `env`/`arg` holdout values and re-baselines confirm.

## Validity (what makes a run a number)

A run is **invalid**, and never compared, when: the command times out; it exits non-zero and `allow_nonzero_exit` is false; the parse finds nothing; the duration is outside `expected_duration_s`; or, for `direction: equal`, repeats disagree. A goal or guardrail with an invalid run discards the experiment as `invalid`. A card whose baseline is invalid quarantines the metric and the campaign will not start on it.

**Usability gate.** At `campaign start` the engine computes each goal's minimum detectable effect from its measured sigma and confirm repeats and prints it. A goal that cannot detect an effect smaller than 50% on this host is unusable (`instrument-unusable:<metric>`) and the campaign halts; `--allow-unusable` is a gate-1 human override. A screen fidelity with a cheaper command and more `confirm.repeats` is how a noisy metric earns its way back.

## Card quality rules for the metrologist

1. **Reuse before inventing.** A `make bench`, a CI job that prints a number, a pytest-benchmark suite, an eval script the maintainers already trust outranks any archetype default. The maintainers' noise is already tuned.
2. Every frozen instrument lives in `integrity.frozen_paths`. If the command is a script in the repo, the script is frozen. If the script lives in a sibling repo, its absolute path goes in `integrity.external_paths` (docs/07 §7.7); it is hashed and denied the same way.
3. Every card needs a working `degradation.apply`: the engine will run it. Verify the anchor exists; do not apply it to the repo yourself.
4. `direction: equal` guardrails (checksums, snapshots) are the cheapest regression wall a project can have. Add one whenever the bench can hash its outputs.
5. A timing metric gets `contention_safe: false` and `screen.repeats ≥ 1`; a count gets `contention_safe: true` and `tolerance_sigma: 0`.
6. Fill archetype placeholders (`{{package}}`, `{{package_dir}}`, `{{bench_path}}`, `{{bench_test}}`, `{{hot_module}}`, `{{hot_function}}`) from the profile's `template_vars`; drop a card whose tool is not installed rather than shipping a command that exits 3.


## Fields added in 1.1.2

| Field | Required | Meaning |
|---|---|---|
| `targets` | goals: yes | Repo-relative paths whose change would move the metric (the code under test, not the instrument). `campaign start` halts a goal whose targets are all frozen or protected (issue #3). |
| `control` | no | `true` keeps a goal whose targets are all frozen as a deliberate negative control instead of halting. |
| `measure.warmup` / `fidelity.<level>.warmup` | no | Unmeasured warm-up runs before the recorded ones. Default 1 for time-unit metrics (`unit` in ms/s/us/ns/min), 0 otherwise (issue #4). |
| screen `repeats` for time-unit metrics | no | Defaults to 2 (median) when the screen level does not set `repeats` (issue #4). |

Cost: `sb cost <id> --wall-s S --tier T` with no tokens records `dollars: null` and the campaign's dollar figure reads `n/a (tokens not reported)`; set `SB_EST_TOKENS='{"low":[in,out],"medium":[in,out],"high":[in,out]}'` in the environment for an order-of-magnitude estimate, labelled `token_source: env-estimate` in the ledger (issue #6).


## Instrument design rules (from the external-adversary gate)

A timing instrument that discards results and hashes once is blind to deferred work, background
threads, and in-process memoisation: five of eight blind attacks passed the statistical screen
that way and were stopped only by the judge. Prefer instruments that consume the result inside
the timed region, hash every repeat, and isolate repeats (fresh process or cleared module state).
Where the instrument cannot, say so in `gaming_risks`; the judge reads them.
