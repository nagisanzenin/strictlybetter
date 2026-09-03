# Develop the strictlybetter OpenCode adapter

## Local setup

1. Clone the repo and create an `opencode.json` in a **throwaway project** (never in the
   repo you are optimizing until you mean it):

   ```bash
   git clone https://github.com/nagisanzenin/researchloop
   mkdir /tmp/sb-play && cd /tmp/sb-play && git init -q
   cat > opencode.json <<EOF
   {
     "\$schema": "https://opencode.ai/config.json",
     "plugin": ["/absolute/path/to/researchloop"]
   }
   EOF
   ```

2. `opencode debug config` in that directory shows the bridged `agent`/`command`/`skills`
   entries after the first start; `opencode debug skill` lists the eight skills.

3. Tests: `bun test __tests__` (bun's built-in runner; the adapter has zero dependencies).

## How it works

The package entry is the combined adapter `.opencode-plugin/entry.ts` — default export
`{ id, server, setup }` — behind `package.json`'s `"main"`, `exports["."]`, and
`exports["./server"]`. OpenCode 1.x calls `server()` (`index.ts`); OpenCode 2.x calls
`setup()` (`v2.ts`, also reachable via `exports["./v2"]`). When OpenCode loads the plugin:

1. `config()` (V1) / `setup()` (V2) runs `selfExtract()` — copies `skills/` and
   `agents/` (transformed) to `.opencode/` in the project and generates `commands/`.
2. On first execution the V1 bridge registers agents, commands and the skills path via
   `cfg.*`; V2 reloads its command/skill/agent domains. Later sessions use disk discovery.
3. Every shell gets `SB_ROOT` (the package root) so the skills find the engine, which is
   **not** extracted.
4. Hooks: the session nudge, the frozen-path guard (`tool.execute.before` → throw), the
   PreCompact pins. No Stop hook: use `sb drive --command`.

## Structure

| Path                | Purpose                                                                    |
| ------------------- | -------------------------------------------------------------------------- |
| `.opencode-plugin/` | TypeScript source (entry, index=V1, v2, install, agents, logger)           |
| `hooks/*.ts`        | V1 hook adapters; each just runs the sibling `hooks/*.sh` script           |
| `hooks/*.sh`        | The shared hook implementations (Claude Code, Codex, ZCode use them as-is) |
| `scripts/sb.py`     | The engine (stays at the package root)                                     |
| `skills/`, `agents/`| Extracted into `.opencode/` for discovery                                  |
| `package.json`      | npm manifest — `main`/`.`/`./server` → `entry.ts`, `./v2` → `v2.ts`        |
