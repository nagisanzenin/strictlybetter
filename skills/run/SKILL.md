---
name: run
description: "Run exactly one strictlybetter cycle: read the brief, pre-register a batch, spawn tiered experimenters into worktrees, submit, screen-measure, judge, blind-judge, confirm, accept or discard, record cost, distill on schedule. Use when a campaign is running and the Stop hook or the user says to continue it."
argument-hint: ""
---

# /strictlybetter:run — ONE CYCLE

This is the loop body. Follow the numbered procedure exactly once; the Stop hook re-invokes
it while the campaign is running with budget left. No improvisation: every decision below is
the engine's, and every number you print is quoted from its output. You are the
HYPOTHESIZE agent; every other role is a spawned agent or the engine.

Three rules that the guard hook and the ledger enforce, restated so they survive
compaction: **never edit files yourself during a campaign** (the guard denies it), **never
compute a statistic** (no deltas, no percentages, no "roughly"), **never paraphrase the
engine's numbers** (quote the line).

```bash
# Resolve the engine. RUN THIS BLOCK VERBATIM — do not substitute a path you guessed.
# Order: ZCode's plugin root (ZCode also exports the legacy CLAUDE_PLUGIN_ROOT, so its own
# var is checked first), Claude Code, Codex, an explicit checkout (SB_ROOT), the Claude Code
# plugin cache (newest version), and LAST the working tree's git toplevel (a contributor
# running inside the strictlybetter checkout). First one that holds scripts/sb.py wins.
SB_PY=""
SB_CACHE="$(find "$HOME/.claude/plugins/cache" -maxdepth 5 -path '*/strictlybetter/*/scripts/sb.py' 2>/dev/null | sort | tail -n 1)"
for d in "${ZCODE_PLUGIN_ROOT:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CODEX_PLUGIN_ROOT:-}" "${SB_ROOT:-}" \
         "${SB_CACHE%/scripts/sb.py}" "$(git rev-parse --show-toplevel 2>/dev/null)"; do
  [ -n "$d" ] && [ -f "$d/scripts/sb.py" ] && SB_PY="$d/scripts/sb.py" && break
done
if [ -z "$SB_PY" ]; then
  echo "strictlybetter: engine not found — set SB_ROOT to your strictlybetter checkout" >&2
  return 2 2>/dev/null || exit 2   # FAIL CLOSED: proceeding would run `python3 ""`
fi
SB_ROOT="${SB_PY%/scripts/sb.py}"
SB_REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
sb() { python3 "$SB_PY" --repo "$SB_REPO" "$@"; }   # a FUNCTION, not a string: zsh does not
SB=sb                                                 # word-split "$SB"; both shells run `sb`
$SB --version   # must print `sb 1.1.1`; anything else means this block did not run
```

## 0 · Re-anchor (never trust conversational memory)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

## (a) The brief

```bash
$SB next --json > "$SB_REPO/.strictlybetter/inbox/brief.json"; $SB next
$SB campaign show | python3 -c 'import json,sys; c=json.load(sys.stdin); print("max_parallel", c["max_parallel"], "distill_every", c["distill_every"])'
```

From the brief take: `status`, `batch_size`, `operator_mix` (a list of `[operator, count]`),
`allowed_diff_sizes`, `frontier`, `goals`, `guardrails`, `recent_dead_ends`, `accepted_so_far`,
`archive_hints`, `inheritance` (path or null), `frozen_paths`, `protected_paths`,
`open_experiments`, `stop_requested`. Note `max_parallel` and `distill_every` from `campaign show`.

- `status` is not `running` → print the brief's `halt_reason` and stop.
- `stop_requested` true or `batch_size` 0 → skip to (f).
- `open_experiments` non-empty → those are a previous cycle's unfinished ids. For each, resume
  at the step its `$SB ledger view <id>` record shows (no `commit`: its worktree may hold
  uncommitted work, run (d) from `submit`; has `judge_stat` but no `confirm`: continue from
  the judge; has `confirm`: accept or discard). Finish them before pre-registering new ones.
- Read the inheritance body if present (`Read` the path) and the last few dead ends.

## (b) Hypothesize: write `batch_size` files

You write these yourself, one JSON per hypothesis, with the Write tool, at
`$SB_REPO/.strictlybetter/inbox/hyp-<n>.json`:

```json
{"operator": "algorithmic", "target": "src/parse/lexer.rs",
 "hypothesis": "The lexer re-scans whitespace on every token; a single skip loop should raise throughput.",
 "predicted": {"bench_throughput": "+5..15%"},
 "mechanism": "removes an O(n) rescan per token in the hot loop",
 "expected_diff_size": "small"}
```

Rules: `operator` comes from `operator_mix` (spend the counts); `target` is a real path or
symbol; `predicted` names only campaign metrics, goals first; `expected_diff_size` is one of
`allowed_diff_sizes`; `mechanism` is one sentence a judge could check; do not repeat a
`recent_dead_ends` entry (same operator + target) without a **new** mechanism; prefer the
frontier's diagnostics and `archive_hints` over guesswork. A good hypothesis is small,
falsifiable, and names where the time or bytes actually go.

## (c) Pre-register and spawn experimenters

For each hypothesis file, in order:

```bash
H="$SB_REPO/.strictlybetter/inbox/hyp-1.json"
$SB prereg --file "$H"            # → {"id": "e0007", "worktree": "...", "base_commit": "...", "prereg_hash": "..."}
```

`prereg` writes the ledger line before any diff exists, creates the worktree from the
campaign head, and charges the budget. If it errors (STOP file, budget exhausted, unknown
operator, a predicted metric not in the campaign) print the message; fix the hypothesis file
only for the last two causes and retry once; otherwise skip to (f).

Then write `$SB_REPO/.strictlybetter/inbox/task-<id>.json` (Write tool) exactly as
`skills/_shared/subagents.md` shows: `id`, `worktree`, `hypothesis` (the hyp file's absolute
path), `frozen_paths`, `protected_paths`, `commands` (from `profile.json`), `inheritance`,
`archive_hints`. Pick the tier by operator: `config|docs|test-add` → `sb-experimenter-low`;
`algorithmic|allocation|caching|bugfix|numerics|data` → `sb-experimenter-medium`;
`concurrency|model|refactor-enabling|dependency` → `sb-experimenter-high`. Note the wall-clock
(`date +%s`) and spawn with exactly this task text:

> Implement the strictlybetter experiment in `<abs path to task-<id>.json>`. Edit only inside the worktree it names; do not run the benchmark yourself more than twice; return `DONE <id>` or `BLOCKED: <reason>`.

Spawn up to `max_parallel` experimenters in one message. Wait for all returns. Record the
seconds each took.

## (d) Per experiment, in return order

Work through this list for each id; stop at the first branch that ends it.

1. **BLOCKED or malformed return** → `$SB discard <id> --reason manual:blocked`. Done.
2. **Submit** → `$SB submit <id>`. Output `"ok": false` (exit 1) → `$SB discard <id> --reason integrity`. Done. (Two consecutive integrity failures halt the campaign; that is the engine's call.)
3. **Stale head check** (a parallel sibling may have been accepted since prereg):
   ```bash
   W="$($SB worktree path <id>)"; B="$(git -C "$W" rev-parse HEAD^)"; H="$($SB status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["head_commit"])')"
   [ "$B" = "$H" ] || echo "STALE <id>"
   ```
   `STALE` → `$SB discard <id> --reason manual:stale-head --archive` (the diff is archived; re-propose it on the new head next cycle if it still applies). Done.
4. **Screen** → `$SB measure <id> --fidelity screen` then `$SB judge <id>`. Read `"verdict"` from the judge's first line:
   - `retry-screen` → run `$SB measure <id> --fidelity screen` and `$SB judge <id>` once more, then continue with the new verdict.
   - `discard` → `$SB discard <id> --reason <reason> --archive` when the judge's `"improved"` list is non-empty or any goal comparison line shows a positive `delta`; without `--archive` otherwise. `<reason>` is the judge's `"reason"` when its prefix (before `:`) is one of `noise|regression|invalid`; else `noise`. Done.
   - `accept-naive` (confirm wall off) → `$SB confirm <id>` then `$SB accept <id>`. Done.
   - `promote` → continue.
5. **Blind judge** → `P="$($SB judge-payload <id>)"`, spawn `sb-judge` (`strictlybetter:sb-judge`) with only the payload path in the task text (*"Judge the strictlybetter experiment described in `<path>`. Return only the verdict JSON."*), write its four-key JSON to `$SB_REPO/.strictlybetter/inbox/verdict-<id>.json` with the Write tool, then `$SB judge-verdict <id> --file "$SB_REPO/.strictlybetter/inbox/verdict-<id>.json"`.
   - `gamed` → `$SB discard <id> --reason gamed`. Done.
   - `clean` or `suspicious` → continue (the engine adds repeats for `suspicious`).
6. **Confirm** → `$SB confirm <id>`. Read `"verdict"` from its first line.
7. **Cost** (before the final verb, so the bandit sees it) → `$SB cost <id> --wall-s <experimenter seconds> --tier <low|medium|high>`. Tokens are unknown on this platform; the dollars column is an estimate from zero tokens, and the cycle summary says "estimated".
8. **Final verb** → confirm `accept` → `$SB accept <id>` (fast-forwards the campaign branch, ratchets the baseline). If `accept` reports "not a fast-forward", treat as STALE in step 3. Confirm `discard` → `$SB discard <id> --reason <reason> --archive` with `<reason>` the confirm line's `"reason"` when its prefix is in the fixed vocabulary, else `noise`.

Judge payload (step 5): the engine composes it, so no transcript text can leak into it:

```bash
P="$($SB judge-payload <id>)"   # writes .strictlybetter/inbox/judge-<id>.json and prints the path
```

The file holds the diff, the pre-registration, the screen comparisons, the affected cards'
`gaming_risks`, the frozen paths, and the checklist path. Hand the judge that path and nothing else.

## (e) Cost is recorded per experiment

Step 7 above, every experiment, including discards. Nothing else to do here.

## (f) Distill on schedule

```bash
$SB distill-stats --json | tee "$SB_REPO/.strictlybetter/inbox/stats.json" | python3 -c 'import json,sys; s=json.load(sys.stdin); print("decision", s["decision"], "| experiments", s["experiments"], "accepted", s["accepted"], "| false-promotion window", s["false_promotion_rate_window"], "| budget left", s["budget_left"])'
```

- `decision` starts with `stop` → `$SB report`, then `$SB campaign end` **unless** `$SB status --json` says `halted` (a halt is for a human; ending it hides the reason). Print the report path `.strictlybetter/reports/<campaign>.md`. This is gate 2. Stop.
- Otherwise, if `experiments % distill_every == 0`, or `accepted` changed during this cycle: spawn `sb-distiller` (`strictlybetter:sb-distiller`) with this task text:

  > Distill the strictlybetter ledger at `<SB_REPO>/.strictlybetter/ledger.jsonl` into an inheritance body. Current body: `<SB_REPO>/.strictlybetter/inheritance.md` (may be missing). Stats: `<SB_REPO>/.strictlybetter/inbox/stats.json`. Template: `<SB_ROOT>/templates/inheritance.md.tmpl`. Write the new body to `<SB_REPO>/.strictlybetter/inbox/inheritance.md`. Return `DONE <path>`.

  then `$SB inheritance write --file "$SB_REPO/.strictlybetter/inbox/inheritance.md"`.
- `explore:levelN` → nothing extra; the next brief widens `allowed_diff_sizes` and the mix.

## (g) Cycle summary (three lines, quoted numbers)

```
cycle: <n> pre-registered, <k> accepted (<ids>), <m> discarded (<id: reason>, …), <b> blocked
frontier: <goal> best=<value> sigma=<sigma>  (from `$SB next`)
next: <decision from distill-stats> · budget left <…> · wall <…>s · dollars estimated $<…>
```

Then stop. The Stop hook decides whether another cycle runs.

## Errors you may see, and what they mean

- `sb: campaign status is 'halted' (…)`: the engine stopped itself (integrity twice, gamed twice, holdout gap, budget, baseline invalid). Print the reason; do not resume it yourself.
- `sb: <id> is not promoted` / `has no blind-judge verdict` / `was judged gamed`: you skipped a step; go back to it.
- `strictlybetter guard: denied edit …`: you or an agent tried to edit outside a worktree, a frozen path, or harness state. Do not retry the edit; the experiment is `BLOCKED`.
- `sb: hypothesis missing 'predicted'` / `unknown operator`: fix the hypothesis file and `prereg` again; nothing was charged.
