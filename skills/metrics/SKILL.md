---
name: metrics
description: "Discover and instrument metrics for strictlybetter: spawn the metrologist, add the cards, measure the noise floor (sigma) with repeated runs, probe monotonicity, demote what fails. Use when a profile exists but no baselined metric cards do, or the user wants to add or re-measure a metric."
argument-hint: "[--repeats N]"
---

# /strictlybetter:metrics — INSTRUMENT

One agent proposes metric cards; the engine measures them. Nothing about a metric lives only
in an agent's head, and no sigma is ever declared.

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

## 1 · Preconditions

`"profile": true` in `status --json`; otherwise invoke `strictlybetter:orient` first. A
running campaign freezes its goal and guardrail cards (`card add` refuses to change them);
new cards can still be added as diagnostics.

## 2 · Spawn the metrologist (once)

```bash
mkdir -p "$SB_REPO/.strictlybetter/inbox/cards"
python3 -c 'import json,sys; print(" ".join((a.get("id") if isinstance(a,dict) else a) for a in json.load(open(sys.argv[1]))["archetypes"]))' "$SB_REPO/.strictlybetter/profile.json"
```

Spawn `sb-metrologist` (`strictlybetter:sb-metrologist`) with this task text, one archetype
pack path per archetype id printed above (skip ids with no file under `$SB_ROOT/archetypes/`):

> Write strictlybetter metric cards for the project profiled at `<SB_REPO>/.strictlybetter/profile.json`. Archetype packs: `<SB_ROOT>/archetypes/<id>.json` [, …]. Card schema: `<SB_ROOT>/skills/_shared/metric-card.md`. Write one card JSON per metric into `<SB_REPO>/.strictlybetter/inbox/cards/`. Do not write anywhere in the repository tree. Return `DONE <n> cards`.

## 3 · Add the cards

```bash
for f in "$SB_REPO"/.strictlybetter/inbox/cards/*.json; do $SB card add --file "$f" || echo "REJECTED $f"; done
$SB card list
```

A rejected card is reported with the engine's reason and skipped; do not repair it by hand.

## 4 · Measure the noise floor

Say this first, then run it: *"Measuring the noise floor: 5 repeats of every card at screen and
confirm fidelity. Sigma is measured, not declared; the engine refuses a goal without one.
Expect roughly 10 × the sum of the per-run times."*

```bash
$SB baseline                       # default 5 repeats; `-k 3` only if the user asked for speed
```

The output has one line per card and level: `median`, `sigma`, `n`, seconds, and `INVALID`
with the reason when a run was not a run. Quote it; do not summarize it into "about".

## 5 · Probe monotonicity (every goal and guardrail candidate)

```bash
for id in $(python3 -c 'import json,os,sys; d=sys.argv[1]; print(" ".join(f[:-5] for f in sorted(os.listdir(d)) if json.load(open(os.path.join(d,f)))["kind"] in ("goal","guardrail")))' "$SB_REPO/.strictlybetter/metrics"); do
  echo "== probe $id"; $SB card probe "$id" || echo "PROBE FAILED $id"
  $SB card validate "$id" || echo "VALIDATE FAILED $id"
done
```

`card probe` applies the card's `degradation.apply` in a throwaway worktree; the metric must
get worse by more than sigma. A card that fails probe or validate cannot decide anything:
demote it to `diagnostic` and say so, quoting the probe `detail`:

```bash
F="$SB_REPO/.strictlybetter/inbox/cards/<id>.json"
python3 - "$F" <<'PY'
import json, sys
p = sys.argv[1]; c = json.load(open(p)); c["kind"] = "diagnostic"
json.dump(c, open(p, "w"), indent=2); print("demoted", c["id"])
PY
$SB card add --file "$F"          # keeps the measured noise and probe result
```

A goal that failed *only* because the degradation recipe did not apply (rc≠0) is a broken
recipe, not a broken metric: spawn the metrologist once more for that card only, with the
engine's error in the task file, then re-probe.

## 6 · Report

```bash
$SB card list
```

Print it verbatim, then one line per demotion with its reason. Return to the caller (the
front door continues to gate 1) or stop.
