/**
 * strictlybetter — OpenCode V2 Plugin Adapter
 * ===========================================
 *
 * OpenCode 2.0 (beta, the `opencode2` binary) replaces the V1 contract — default
 * export `{ id, server }` returning mutable-config hooks — with `{ id, setup(ctx) }`,
 * where ctx exposes typed domains (command, skill, agent, tool, session, shell) with
 * transform/hook/reload methods. V2 does not load V1 plugins; the combined entry in
 * entry.ts serves both. This file mirrors engram's v2.ts design rules:
 *
 * 1. ZERO @opencode-ai/* imports — a plain `{ id, setup }` is a valid V2 plugin.
 * 2. Feature-detect every domain, tolerate both hook call forms (fn-form
 *    `domain.hook(name, cb)` and mapped `domain.hook[name](cb)`); every registration
 *    is optional-chained AND try/caught, including callback bodies.
 * 3. Reuse the V1 extraction byte-for-byte; `.opencode/` is shared by both engines.
 *
 * What maps where (V1 → V2)
 *   config hook self-extract            → setup() body (once per workspace instance)
 *   first-execution bridge              → not needed: extract, then domain reload()
 *   experimental.chat.system.transform  → session context hook pushing a SystemPart,
 *                                         once per sessionID
 *   shell.env                           → shell create.before mutating input.env
 *   tool.execute.before (the guard)     → tool execute.before, IF the beta exposes it
 *                                         (feature-detected; unverified — see
 *                                         INSTALL-OPENCODE-V2.md)
 *   experimental.session.compacting     → no verified V2 equivalent; the pins are
 *                                         dropped here (the skills re-anchor from
 *                                         `sb status` on every invocation anyway)
 *
 * Workspace directory (NOT process.cwd())
 *   V2 runs plugins inside a background service shared across projects, so
 *   process.cwd() is the service's directory. Every location-scoped domain API
 *   responds with { location: { directory, … }, data }; setup asks agent.list(),
 *   then command.list(). No location → HOOKS-ONLY: nothing is extracted, nothing is
 *   written (a wrong-directory write is strictly worse than a missing feature).
 *   Extraction additionally requires the location to OWN an opencode config file, or
 *   to be the global config dir (extractionScope) — the service instantiates plugins
 *   for locations beyond the configuring project.
 */

import { existsSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { selfExtract, getVERSION } from "./install.js"
import { runHook, runHookSync } from "../hooks/run-hook.js"
import { guardedPath } from "../hooks/frozen-guard.js"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")

/**
 * Registers a hook on a domain, tolerating both call forms seen across V2 builds.
 * Returns the Registration (or undefined when the domain/hook is absent).
 */
export async function registerHook(
  domain: any,
  name: string,
  cb: (input: any) => Promise<void> | void,
): Promise<{ dispose?: () => Promise<void> } | undefined> {
  if (!domain) return undefined
  const hook = domain.hook
  if (typeof hook === "function") return await hook.call(domain, name, cb)
  if (hook && typeof hook[name] === "function") return await hook[name](cb)
  return undefined
}

/** Resolves the workspace directory from location-wrapped domain responses; null when none reports one. */
export async function resolveWorkspaceDirectory(ctx: any): Promise<string | null> {
  for (const domain of [ctx?.agent, ctx?.command]) {
    try {
      const res = await domain?.list?.()
      const dir = res?.location?.directory
      if (typeof dir === "string" && dir) return dir
    } catch {}
  }
  return null
}

/** Extraction is allowed only where the location owns an opencode config, or is the global config dir. */
export function extractionScope(dir: string | null): string | null {
  if (!dir) return null
  const home = process.env.HOME || process.env.USERPROFILE || "/tmp"
  const globalDir = resolve(home, ".config", "opencode")
  if (resolve(dir) === globalDir) return dir
  if (existsSync(resolve(dir, "opencode.json")) || existsSync(resolve(dir, "opencode.jsonc"))) return dir
  return null
}

export interface V2SetupDeps {
  /** Overrides the directory used for target detection (tests). */
  directory?: string
  /** Overrides the nudge runner (tests). */
  runNudge?: (dir: string) => Promise<string>
}

export function createV2Setup(deps: V2SetupDeps = {}) {
  const runNudge = deps.runNudge || ((dir: string) => runHook(root, "session-start.sh", dir))

  return async function setup(ctx: any): Promise<(() => Promise<void>) | void> {
    const registrations: Array<{ dispose?: () => Promise<void> } | undefined> = []
    try {
      const dir = deps.directory || (await resolveWorkspaceDirectory(ctx))
      const extractDir = extractionScope(dir)

      if (extractDir) {
        const result = selfExtract(root, extractDir, getVERSION(root), undefined)
        if (result.freshlyExtracted || (result.report && result.report.written.length)) {
          try { await ctx?.skill?.reload?.() } catch {}
          try { await ctx?.agent?.reload?.() } catch {}
          try { await ctx?.command?.reload?.() } catch {}
        }
      }

      // The nudge, once per SESSION (V1 ran one process per session; same cadence).
      const nudgedSessions = new Set<string>()
      try {
        const r = await registerHook(ctx?.session, "context", async (sc: any) => {
          try {
            if (!dir) return
            const sessionID = String(sc?.sessionID ?? "")
            if (nudgedSessions.has(sessionID)) return
            if (nudgedSessions.size > 512) nudgedSessions.clear()
            nudgedSessions.add(sessionID)
            const nudge = await runNudge(dir)
            if (nudge && Array.isArray(sc?.system)) sc.system.push({ type: "text", text: `\n${nudge}` })
          } catch {}
        })
        if (r) registrations.push(r)
      } catch {}

      // SB_ROOT / OPENCODE_PLUGIN_ROOT on every shell execution.
      try {
        const r = await registerHook(ctx?.shell, "create.before", (shell: any) => {
          try {
            shell.env["SB_ROOT"] = root
            shell.env["OPENCODE_PLUGIN_ROOT"] = root
            if (process.env.SB_HOME) shell.env["SB_HOME"] = process.env.SB_HOME
          } catch {}
        })
        if (r) registrations.push(r)
      } catch {}

      // The guard — feature-detected. If the beta exposes a tool execute.before hook
      // with V1's {tool, args} shape, a denied edit throws with the engine's reason;
      // any other shape (or no such hook) leaves the gate-time `sb submit` check as
      // the only wall, exactly as documented for hosts without a pre-edit hook.
      try {
        const r = await registerHook(ctx?.tool, "execute.before", (input: any) => {
          let denial: string | null = null
          try {
            if (!dir) return
            const tool = input?.tool ?? input?.name
            const args = input?.args ?? input?.input
            const p = guardedPath(tool, args)
            if (!p) return
            const abs = p.startsWith("/") ? p : resolve(dir, p)
            const payload = JSON.stringify({ tool_name: String(tool), tool_input: { file_path: abs } })
            const res = runHookSync(root, "frozen-guard.sh", dir, payload)
            if (res && res.status === 2) denial = res.stderr.trim() || "strictlybetter guard: denied"
          } catch {
            denial = null
          }
          if (denial) throw new Error(denial)
        })
        if (r) registrations.push(r)
      } catch {}
    } catch {}

    return async () => {
      for (const registration of registrations) {
        try { await registration?.dispose?.() } catch {}
      }
    }
  }
}

export const setup = createV2Setup()

export default {
  id: "strictlybetter",
  setup,
}
