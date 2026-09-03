# Engine resolution (shared contract)

Every strictlybetter skill starts with the block below, pasted verbatim as its first body
block. It finds `scripts/sb.py`, fails closed when it cannot, and defines `$SB` so that every
later command in the skill reads `$SB <command> …`. Nothing stateful happens outside
`$SB`: the engine owns measurement, statistics, the ledger, the baseline, the budget, and
every verdict. Skills run commands and report what they printed.

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

## Why each line is the way it is

- **`--repo` is always passed.** `sb()` bakes in `--repo "$SB_REPO"`, the git toplevel of the
  directory the skill was invoked from. The engine's state home is `<repo>/.strictlybetter`
  (or `$SB_HOME` when set), and every worktree it creates lives under it. Running the engine
  from inside an experiment worktree without `--repo` would resolve the *worktree* as the
  repo and corrupt state; the function makes that impossible.
- **A function, not a string.** Claude Code's Bash tool on macOS runs zsh, and zsh does not
  word-split an unquoted `$SB` (`"python3 /path/sb.py --repo /repo"` becomes one
  command name and fails with "no such file or directory"). `SB=sb` expands to the
  function name in both shells, and the function quotes its paths, so a checkout under a
  path with spaces also works.
- **Fail closed.** With no engine there is nothing safe to do; `python3 ""` dumps a usage
  error at the user and every later command silently does nothing.
- **If a later command reports `sb: command not found` or `SB_PY: unbound`,** the shell
  state was reset between calls. Re-run this block first; it is idempotent and takes under
  a second.
- `$SB_ROOT` is the plugin root: `$SB_ROOT/agents/*.md`, `$SB_ROOT/archetypes/<id>.json`,
  `$SB_ROOT/templates/*`, `$SB_ROOT/bench/run_bench.py`.

## Re-anchor (second block of every skill)

```bash
$SB status --json                                             # the truth on disk
$SB status --json | grep -q '"campaign": null' || $SB next    # the cold-start brief, when a campaign exists
```

Trust these two outputs over anything in conversational memory. Compaction, a resumed
session, or a previous turn's summary can all be stale; the ledger cannot.

## Command surface (exact flags, from `build_parser()` in `scripts/sb.py`)

| Command | Flags | Notes |
|---|---|---|
| `init` | | creates the state home; idempotent |
| `profile write\|show` | `--file P` | write requires `archetypes` (non-empty), `commands`, `purpose` |
| `card add\|list\|validate\|show\|probe` | `[ID] --file P --repeats N` | `add` reads a card JSON; `probe` applies `degradation.apply` in a throwaway worktree (default 2 repeats); `validate` exits 1 on problems |
| `baseline` | `--metric ID -k/--repeats N --levels screen,confirm` | default 5 repeats at `screen` and `confirm`; all cards when no campaign |
| `campaign start\|show\|end\|halt\|resume` | `--file P --reason R --no-baseline --repeats N --allow-unusable` | `start` refuses while one is running or a goal's minimum detectable effect is unusable (`--allow-unusable` overrides, gate-1 decision); `end` writes the report; `resume` clears STOP |
| `next` | `--json --seed N` | the brief; works on halted/ended campaigns too |
| `prereg` | `--file P` | hypothesis JSON; prints `{id, worktree, base_commit, prereg_hash}` |
| `submit ID` | | commits the worktree; prints `{ok, violations, …}`; exit 1 when not ok |
| `measure ID` | `--fidelity screen\|full\|confirm --repeats N --keep-runs` | |
| `judge ID` | `--fidelity screen\|full` | statistical verdict: `promote`, `retry-screen`, `discard`, `accept-naive` |
| `judge-verdict ID` | `--file P` | stores the blind judge's JSON; rejects any key outside `verdict\|pattern\|evidence\|recommended_check` |
| `confirm ID` | `--force` | full + confirm fidelity from a clean checkout with holdout |
| `accept ID` | `--force` | fast-forwards the campaign branch; ratchets |
| `discard ID` | `--reason R --archive` | reason must start with `noise\|regression\|integrity\|gamed\|build-failed\|timeout\|budget\|invalid\|harness-error\|manual` |
| `cost ID` | `--tokens-in N --tokens-out N --wall-s S --dollars D --tier T` | run BEFORE accept/discard so the bandit sees the cost |
| `distill-stats` | `--json` | plateau, false-promotion, decision (`continue`, `explore:levelN`, `stop:*`) |
| `status` | `--json` | `{"campaign": null, …}` when none |
| `report` | | writes and prints `.strictlybetter/reports/<campaign>.md` |
| `budget` | | counters and what is exhausted |
| `guard [PATH]` | `--stdin` | exit 2 = deny (used by the PreToolUse hook) |
| `stop` | | writes the STOP file |
| `ledger view ID \| tail -n N \| experiments` | `--unredacted` | `view` redacts discarded candidates' holdout numbers unless `--unredacted` (audit only) |
| `inheritance write\|show` | `--file P` | body must contain `## ` sections |
| `worktree new\|drop\|path\|list ID` | `--commit C` | `path` prints where an experiment's worktree is |
| `session-start`, `doctor`, `selftest` | | |
| `drive` | `--command C --cycles N --timeout S --verbose` | headless loop; shells out once per cycle |

Global flags go before the command: `--repo`, `--home`, `--version`.
