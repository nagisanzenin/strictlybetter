---
name: strictlybetter
description: "Universal research loop: orient on this repo, discover metrics, run pre-registered experiments, keep only strictly-better changes. Use when the user wants the repo/project improved automatically, mentions strictlybetter, a research loop, autoresearch, optimizing a metric, or continuous improvement."
argument-hint: "[what to improve, in your words] | continue"
---

# /strictlybetter — the front door

You are the **orchestrator**. The engine (`scripts/sb.py`) owns every number: measurement,
sigma, the acceptance rule, the ledger, the ratchet, the budget. You run commands, spawn
agents by file path, and report what the engine printed. You never compute a statistic,
never write `baseline.json`, never edit repository files while a campaign runs (the
PreToolUse guard denies it), and never paraphrase or round the engine's numbers.

Read `skills/_shared/subagents.md` from `$SB_ROOT` before the first spawn.

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

## 1 · Route on what the engine says

Read the `status --json` output from §0 and take exactly one branch:

| `status --json` says | Do |
|---|---|
| `"campaign": null` and `"profile": false` | §2, then §3, then §4 |
| `"campaign": null`, profile true, `cards` empty or no goal card has a measured sigma | §3, then §4 |
| `"campaign": null`, cards baselined | §4 (gate 1) |
| `"status": "running"` | §5: one cycle |
| `"status": "halted"` | print the `halt_reason` line from `$SB status` verbatim, then say: *"The campaign halted and needs a human look. `sb campaign resume` after review (clears the STOP file and the consecutive-error counters), or `/strictlybetter:status` for the numbers."* Stop. |
| `"status": "ended"` | print the report path (`.strictlybetter/reports/<campaign>.md`) and say a new campaign starts at gate 1 (§4). Stop unless the user asked for a new campaign. |

Between the two human gates the loop asks nothing. If something needs a human, it halts
and says why; it does not ask.

## 2 · No profile → orient

Invoke the `strictlybetter:orient` skill (Skill tool) and follow it to the end: it spawns
`sb-orienteer`, validates the JSON, runs `$SB profile write --file`, and shows the
profile. Then continue to §3.

## 3 · No cards → instrument

Invoke the `strictlybetter:metrics` skill and follow it to the end: it spawns
`sb-metrologist`, adds every card, runs `$SB baseline` (5 repeats per metric; say up front
that this takes a while, because sigma is measured, not declared), probes every goal and
guardrail candidate for monotonicity, demotes failures to diagnostic, and prints
`$SB card list`. Then continue to §4.

## 4 · GATE 1 — one structured question, recommended set first

Render the measured facts the user needs (stored numbers; nothing is computed here):

```bash
python3 - "$SB_REPO" <<'PY'
import json, os, sys
home = os.environ.get("SB_HOME") or os.path.join(sys.argv[1], ".strictlybetter")
bp = os.path.join(home, "baseline.json")
b = json.load(open(bp)) if os.path.exists(bp) else {}
print(f"{'metric':24} {'kind':10} {'direction':9} {'sigma':>12} {'screen s':>9} {'confirm s':>10} probe")
for f in sorted(os.listdir(os.path.join(home, "metrics"))):
    c = json.load(open(os.path.join(home, "metrics", f)))
    lv = (b.get(c["id"]) or {}).get("levels") or {}
    sig = (c.get("noise") or {}).get("sigma")
    print(f"{c['id']:24} {c['kind']:10} {c['direction']:9} {str(sig):>12} {str((lv.get('screen') or {}).get('secs_per_run')):>9} {str((lv.get('confirm') or {}).get('secs_per_run')):>10} {(c.get('probe') or {}).get('monotonic')}")
PY
sed -n '/## Protected paths/,/^$/p' "$SB_REPO/.strictlybetter/profile.md"
```

Build the **recommended set**:

- **goals**: cards of kind `goal` whose `probe` is `True` and whose sigma is not `None`
  (or direction `equal`). If the user named an aim in the arguments, put the matching
  goal first. One or two goals; more dilutes the batch.
- **guardrails**: every card of kind `guardrail` that passed its probe. Hygiene guardrails
  are added by the engine whether or not you list them.
- **diagnostics**: everything else that baselined (recorded, never decides).
- **budget**: `{"experiments": 30}` by default. Add `"hours"` when the user gave a time.
- **protected paths**: the profile's proposed list. Frozen paths come from the cards.
- **branch**: `sb/<campaign-id>`; **id**: `YYYY-MM-DD-<short-slug>`.

Ask **one** `AskUserQuestion` with the recommended set as the first option, in this shape:

> Start campaign `<id>`? Goals: `<g>` (sigma s, ~N s/run). Guardrails: `<…>`. Diagnostics: `<…>`. Budget: 30 experiments. Protected: `<paths>`. Frozen: `<paths>`. Branch `sb/<id>`.
> Options: **Start with this set (recommended)** / **Edit goals or guardrails** / **Change budget or paths** / **Not now**.

"Edit" and "Change" answers are the user's edits; apply them and start. No second question
unless the edit names a card that does not exist. Then write the campaign file with the
Write tool (the inbox is the one writable place) and start:

```bash
# .strictlybetter/inbox/campaign.json — every key the engine reads; omit what you do not set
# {"id": "2026-09-03-parse-perf", "goals": ["bench_ms"], "guardrails": ["tests_failed", "bench_checksum"],
#  "diagnostics": ["loc"], "composition": "pareto", "budget": {"experiments": 30},
#  "plateau_patience": 8, "protected_paths": ["…"], "frozen_paths": [], "branch": "sb/2026-09-03-parse-perf",
#  "max_parallel": 2, "distill_every": 8, "iteration_cap": 200, "notes": "<the user's aim, their words>",
#  "archetype_priors": {"algorithmic": [3, 3], "config": [1, 3]}}      # optional: the pack's operator_priors
$SB campaign start --file "$SB_REPO/.strictlybetter/inbox/campaign.json"
$SB status
```

`campaign start` freezes the set, hashes the frozen paths, creates the branch, and baselines
any metric that lacks a baseline at this commit. It refuses when a goal has no valid
baseline or no measured sigma; if it does, print its message and stop (the metrics skill
demotes the offender). `archetype_priors` is the `operator_priors` object from
`$SB_ROOT/archetypes/<archetype-id>.json` when that file exists; leave it out otherwise.

## 5 · Running → one cycle

Invoke the `strictlybetter:run` skill and follow its procedure exactly once. The Stop hook
re-invokes it while the campaign is running with budget left; you do not loop yourself.
When the run skill's distill step says `stop:*`, it ends the campaign and prints the
report path; that is gate 2, and the branch plus report are the deliverable. Merging,
opening a PR, tagging: human acts.

## What you never do

- Edit a file outside `.strictlybetter/inbox/` or `.strictlybetter/tmp/` while a campaign runs.
- Compute a delta, a sigma, a threshold, or "roughly N%": quote the engine's line.
- Ask the user anything between gate 1 and gate 2. Halts are for humans; questions are not.
- Spawn an agent with a diff, a hypothesis, or a summary of the session in its task text.
