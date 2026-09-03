/**
 * strictlybetter — OpenCode V1 Plugin
 * ===================================
 *
 * Self-extract + first-execution bridge (the engram pattern, thinned)
 * -------------------------------------------------------------------
 *
 * The package lives under ~/.cache/opencode/node_modules/ and OpenCode does NOT
 * scan the npm cache for skills/agents/commands. So:
 *
 *   config hook → selfExtract() copies skills/ and agents/ (transformed) into the
 *                 project's .opencode/ (or ~/.config/opencode/) and generates the
 *                 commands/ files — install.ts, never overwriting a file the user
 *                 edited (sha256-ownership).
 *   first run   → a bridge registers the same agents, the skills path and the
 *                 commands through cfg.* so everything works in THIS session;
 *                 from the next start OpenCode's disk discovery takes over.
 *
 * The engine stays at the package root: hooks/shell-env.ts exports SB_ROOT into
 * every shell, and the skills' resolution waterfall picks it up. Version bump =
 * npm update; nothing to re-extract for the engine.
 *
 * Hook surface (V1 SDK names, verified present in the opencode 1.18.23 binary)
 * ------------------------------------------------------------------------------
 *   experimental.chat.system.transform → hooks/session-start.sh  (the nudge, once)
 *   shell.env                          → SB_ROOT / OPENCODE_PLUGIN_ROOT / SB_HOME
 *   tool.execute.before                → hooks/frozen-guard.sh   (throw = deny)
 *   experimental.session.compacting    → hooks/pre-compact.sh    (the pins)
 *   (no Stop hook exists in V1 → the loop is driven by `sb drive --command`,
 *    see INSTALL-OPENCODE-V2.md)
 *
 * ZERO @opencode-ai/* imports: the V1 loader only requires default.server to be a
 * function, and every type here is structural — so this file cannot break when
 * the SDK reshuffles its exports, and it loads with the SDK absent.
 *
 * Every hook body is wrapped in try/catch — no strictlybetter failure may crash the host.
 */

import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { registerAgents } from "./agents.js"
import { createSessionStartHooks } from "../hooks/session-start.js"
import { createShellEnvHook } from "../hooks/shell-env.js"
import { createFrozenGuardHook } from "../hooks/frozen-guard.js"
import { createPreCompactHook } from "../hooks/pre-compact.js"
import { selfExtract, getVERSION, COMMANDS_DEF } from "./install.js"
import { createPluginLogger } from "./logger.js"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")

/** In-memory command definitions for the first-execution bridge (V1 `cfg.command`). */
export function bridgeCommands(): Record<string, { description: string; template: string }> {
  const out: Record<string, { description: string; template: string }> = {}
  for (const [name, def] of Object.entries(COMMANDS_DEF)) {
    out[name] = {
      description: def.description,
      template: `# /${name}\n\nLOAD AND FOLLOW the \`${def.skill}\` skill (use the skill tool; its SKILL.md is the whole procedure). Run its engine-resolution block VERBATIM first — \`SB_ROOT\` is exported into every shell by the plugin — and quote the engine's output; never compute a statistic yourself.\n\nArguments: $ARGUMENTS`,
    }
  }
  return out
}

export interface V1Input { client?: any; $?: any; directory?: string }

export const server = async ({ client, directory }: V1Input) => {
  const cwd = directory || process.cwd()
  return {
    async config(input: any) {
      try {
        const cfg = input as any
        const logger = createPluginLogger(client)
        const result = selfExtract(root, cwd, getVERSION(root), logger)
        const target = result.target
        if (result.freshlyExtracted) {
          registerAgents(cfg, root)
          cfg.skills = cfg.skills || {}
          cfg.skills.paths = cfg.skills.paths || []
          if (!cfg.skills.paths.includes(resolve(target, "skills"))) cfg.skills.paths.push(resolve(target, "skills"))
          cfg.command = cfg.command || {}
          for (const [name, def] of Object.entries(bridgeCommands())) {
            if (!cfg.command[name]) cfg.command[name] = def
          }
        }
      } catch {}
    },
    ...createSessionStartHooks(root, cwd),
    ...createShellEnvHook(root),
    ...createFrozenGuardHook(root, cwd),
    ...createPreCompactHook(root, cwd),
  }
}

export default {
  id: "strictlybetter",
  server,
}
