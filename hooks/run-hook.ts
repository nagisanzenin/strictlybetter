/**
 * strictlybetter — shared runner for the shell hooks (OpenCode + pi adapters)
 * ===========================================================================
 *
 * The four hooks under hooks/*.sh are the single implementation of the ambient
 * surface; the TypeScript adapters only translate host events into those scripts.
 * Every script self-resolves the engine from its own location, reads the project
 * from its cwd, and degrades to silence — so an adapter passes a cwd and, for the
 * guard, the Claude-shaped payload on stdin, and reads exit code + streams.
 *
 * The three plugin-root variables of OTHER hosts are stripped from the child env:
 * an OpenCode session started from inside a Claude Code or ZCode hook would
 * otherwise hand this script a foreign root (and, for ZCode, flip its output to
 * JSON, which OpenCode would then print verbatim into the system prompt).
 */

import { spawnSync, execFile } from "node:child_process"
import { existsSync } from "node:fs"
import { resolve } from "node:path"

export interface HookResult { status: number | null; stdout: string; stderr: string }

const FOREIGN_ROOT_VARS = ["ZCODE_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "CODEX_PLUGIN_ROOT", "SB_HOOK_FORMAT"]

export function hookEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env }
  for (const k of FOREIGN_ROOT_VARS) delete env[k]
  return env
}

export function hookPath(root: string, name: string): string | null {
  const p = resolve(root, "hooks", name)
  return existsSync(p) ? p : null
}

/** Synchronous — used by the guard, whose verdict must precede the tool call. */
export function runHookSync(root: string, name: string, cwd: string, input = "", timeoutMs = 8000): HookResult | null {
  const script = hookPath(root, name)
  if (!script) return null
  try {
    const r = spawnSync("bash", [script], { cwd, input, env: hookEnv(), timeout: timeoutMs, encoding: "utf-8", windowsHide: true })
    return { status: r.status, stdout: String(r.stdout ?? ""), stderr: String(r.stderr ?? "") }
  } catch {
    return null
  }
}

/** Asynchronous — used by the nudge and the compaction pins. Resolves to "" on any failure. */
export function runHook(root: string, name: string, cwd: string, timeoutMs = 10000): Promise<string> {
  const script = hookPath(root, name)
  if (!script) return Promise.resolve("")
  return new Promise((done) => {
    try {
      const child = execFile("bash", [script], { cwd, env: hookEnv(), timeout: timeoutMs, windowsHide: true }, (err, stdout) => {
        done(err ? "" : String(stdout ?? "").trim())
      })
      try { child.stdin?.end() } catch {}
    } catch {
      done("")
    }
  })
}
