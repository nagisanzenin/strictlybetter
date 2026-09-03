---
name: bench
description: "Run the strictlybetter meta-benchmark: the walled loop against a naive loop on fixture repos, reporting false-accept rate and cost per accepted improvement. Use when the user asks to benchmark, validate, or compare strictlybetter itself (not the target project)."
argument-hint: "[--help | runner arguments]"
---

# /strictlybetter:bench — the meta-benchmark

The loop's own claim is testable (docs/10 §10.7). The runner is a separate program; this skill only drives it.

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

## 1 · Entry point

```bash
ls "$SB_ROOT/bench/" 2>/dev/null || echo "bench runner not installed in this checkout"
python3 "$SB_ROOT/bench/run_bench.py" --help
```

Follow the usage the runner prints; pass the user's arguments through unchanged. Do not
invent flags. Runs are long (each condition drives full campaigns on the fixture repos under
`tests/fixtures/`); say so before starting and prefer running it in the background.

## 2 · Results

Results land in `$SB_ROOT/bench/results/` (one directory or file per run, written by the
runner, never hand-edited). Print the path of the newest result and quote its summary table
verbatim. The two numbers that matter are the **false-accept rate** on a fresh holdout for
each condition (all walls vs naive) and **cost per accepted improvement**. If the walls do
not reduce the false-accept rate at acceptable cost, say so plainly; the thesis is
falsifiable and the docs promise to report it either way.
