#!/usr/bin/env bash
# strictlybetter — Codex glue installer.
# Copies the TOML subagent ports into your Codex agents dir and runs the engine selftest.
# Idempotent; safe to re-run. Claude Code users don't need this.
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AGENTS_DIR="$CODEX_HOME/agents"

echo "strictlybetter: installing Codex subagent ports"
echo "  repo:        $REPO_ROOT"
echo "  codex home:  $CODEX_HOME"

if [ ! -d "$REPO_ROOT/codex/agents" ]; then
  echo "strictlybetter: error: codex/agents not found under $REPO_ROOT" >&2
  exit 1
fi

mkdir -p "$AGENTS_DIR"
n=0
for f in "$REPO_ROOT"/codex/agents/*.toml; do
  [ -e "$f" ] || continue
  cp "$f" "$AGENTS_DIR/"
  echo "  + $(basename "$f") -> $AGENTS_DIR/"
  n=$((n + 1))
done
echo "strictlybetter: installed $n agent(s)."

# Sanity: the shared engine must run.
if command -v python3 >/dev/null 2>&1; then
  echo "strictlybetter: running selftest…"
  python3 "$REPO_ROOT/scripts/sb.py" selftest >/dev/null 2>&1 \
    && echo "strictlybetter: selftest OK" \
    || echo "strictlybetter: WARNING — selftest did not pass; run it directly to see why" >&2
fi

cat <<EOT

Next steps:
  1. Route B only (skills installed without 'codex plugin add'): tell the skills where the
     engine is, because no plugin-root variable is set on that route:
       export SB_ROOT="$REPO_ROOT"     # add to your shell rc
  2. Install the skills (if not via 'codex plugin add'):
       npx skills add nagisanzenin/researchloop
  3. In Codex, invoke skills as \$strictlybetter / \$run / \$status …, and the agents
     explicitly, e.g. "\$sb-judge, judge the experiment in <payload path>".

See INSTALL-CODEX.md for the full story and caveats.
EOT
