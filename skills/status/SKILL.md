---
name: status
description: "Show the strictlybetter campaign state: status line, the cold-start brief, and the budget counters, all quoted from the engine. Use when the user asks how the campaign / research loop is going, what is left, or what the next batch looks like."
argument-hint: ""
---

# /strictlybetter:status

Three engine commands, quoted. Nothing computed here.

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
$SB --version | grep -q '^sb 1\.' || { echo "strictlybetter: engine did not answer (expected sb 1.x)" >&2; return 2 2>/dev/null || exit 2; }   # major version only; exact patch level is not asserted
```

## 0 · Re-anchor (never trust conversational memory)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

## 1 · Print, verbatim

```bash
$SB status
$SB status --json | grep -q '"campaign": null' || { $SB next; $SB budget; }
$SB campaign show 2>/dev/null | grep -q '"composition": "frontier"' && $SB frontier   # frontier campaigns: the members and the preferred point
$SB campaign show 2>/dev/null | grep -q '"audits": \[$' && $SB status --json | python3 -c 'import json,sys; s=json.load(sys.stdin); print("audits_run", s["audits_run"], "audit_wall_s", s["audit_wall_s"], "iterations_per_hour", s["iterations_per_hour"]); [print("proxy", p, json.dumps(f)) for p, f in s["proxy_fidelity"].items()]'   # proxy-ladder campaigns: the audit counters and each proxy's fidelity record
```

With no campaign, `status` says how many cards and whether a profile exists; suggest
`/strictlybetter` to start. Otherwise the three outputs are the answer: the status line
(experiments, accepted, promoted, budget left, branch, head, wall, estimated dollars), the
brief (frontier, accepted so far, dead ends, open experiments, operator mix), and the budget
counters. In a frontier campaign `sb frontier` is a fourth: the members with their confirm
medians, `retired:<by>` marks, and `*` on the preferred point. In a campaign with `audits` (a
proxy ladder, docs/15) the fourth is the `status --json` extract: `audits_run`, `audit_wall_s`,
`iterations_per_hour`, and one `proxy_fidelity` line per proxy (`audits`, `agree`,
`false_promotions`, `misses`, `exchange_rates`), quoted as printed; the proxy's current `trust`
is on its card (`$SB card show <id>` if the user asks). Add at most two sentences of your own, none of them a number the engine did not
print. A `halted` status gets its `halt_reason` repeated and the sentence
*"`sb campaign resume` after review."*
