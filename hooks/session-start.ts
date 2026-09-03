/**
 * strictlybetter — Session Start Hook (OpenCode V1)
 * =================================================
 *
 * experimental.chat.system.transform fires on every LLM request; the first call per
 * plugin instance (one process per session under V1) runs hooks/session-start.sh in
 * the project directory and pushes its one line — "[strictlybetter] campaign … running"
 * or "… HALTED" — into the system prompt. Silent when there is no state home, no
 * campaign, or any failure. Wrapped in try/catch — never crash the host.
 */

import { runHook } from "./run-hook.js"

export function createSessionStartHooks(root: string, directory: string) {
  let firstTransform = true
  return {
    async "experimental.chat.system.transform"(_input: any, output: { system: string[] }) {
      try {
        if (!firstTransform) return
        firstTransform = false
        const nudge = await runHook(root, "session-start.sh", directory)
        if (nudge) output.system.push(`\n${nudge}`)
      } catch {}
    },
  }
}
