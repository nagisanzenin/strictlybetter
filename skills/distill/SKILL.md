---
name: distill
description: "Distill the strictlybetter ledger now: run the engine's plateau/bandit/false-promotion statistics, spawn the distiller to rewrite the inheritance body, store it, show the decision. Use when the user asks what the loop has learned, wants the inheritance body refreshed, or a campaign just ended."
argument-hint: ""
---

# /strictlybetter:distill — DISTILL

The engine computes; the distiller writes for a reader with no context; every claim points at ledger ids.

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
$SB --version   # must print `sb 1.1.0`; anything else means this block did not run
```

## 0 · Re-anchor (never trust conversational memory)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

## 1 · Statistics (engine)

```bash
$SB distill-stats --json | tee "$SB_REPO/.strictlybetter/inbox/stats.json"
```

Quote `decision`, `experiments`, `accepted`, `discard_reasons`, `false_promotion_rate_window`,
`screen_untrusted`, `by_operator`, `wall_s_per_accept`, `dollars_per_accept`,
`holdout_gap_mean_last5`, `budget_left`. `distill-stats` needs a campaign (running, halted,
or ended); with none, say so and stop.

## 2 · Distiller (agent, once)

Spawn `sb-distiller` (`strictlybetter:sb-distiller`) with:

> Distill the strictlybetter ledger at `<SB_REPO>/.strictlybetter/ledger.jsonl` into an inheritance body. Current body: `<SB_REPO>/.strictlybetter/inheritance.md` (may be missing). Stats: `<SB_REPO>/.strictlybetter/inbox/stats.json`. Template: `<SB_ROOT>/templates/inheritance.md.tmpl`. Write the new body to `<SB_REPO>/.strictlybetter/inbox/inheritance.md`. Return `DONE <path>`.

## 3 · Store and show

```bash
$SB inheritance write --file "$SB_REPO/.strictlybetter/inbox/inheritance.md"
$SB inheritance show | head -n 40
```

Then print the decision line: `continue` (keep cycling), `explore:levelN` (plateau; bigger
diffs allowed next), `stop:converged` (the engine ended the campaign), `stop:budget:<dim>`
(halted on a budget), `stop:halted` (needs a human). For any `stop:*` also run `$SB report`
and print the report path.
