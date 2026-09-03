/**
 * strictlybetter — Frozen-Path Guard (OpenCode V1: tool.execute.before)
 * =====================================================================
 *
 * The ONE hook whose purpose is to deny. OpenCode's `tool.execute.before` blocks a
 * tool call when the hook throws, which is the PreToolUse exit-2 of Claude Code in
 * this host's dialect. For OpenCode's `edit` and `write` tools the adapter builds the
 * Claude-shaped payload ({tool_name, tool_input: {file_path}}) hooks/frozen-guard.sh
 * expects and pipes it in; the script's fast path (no campaign.json reachable from
 * the edited path → python never starts) keeps this cheap on every ordinary session.
 *
 * Exit 2 → throw with the engine's one-line reason. Anything else, including the
 * adapter's own failures, allows — the documented fail-open shape of this hook class,
 * backed by the gate-time integrity check in `sb submit`.
 */

import { isAbsolute, resolve } from "node:path"
import { runHookSync } from "./run-hook.js"

const GUARDED: Record<string, string> = { edit: "Edit", write: "Write", multiedit: "MultiEdit", notebookedit: "NotebookEdit" }

export function guardedPath(tool: string, args: any): string | null {
  if (!GUARDED[String(tool || "").toLowerCase()]) return null
  const p = args?.filePath ?? args?.file_path ?? args?.path ?? args?.notebook_path
  return typeof p === "string" && p ? p : null
}

export function createFrozenGuardHook(root: string, directory: string) {
  return {
    async "tool.execute.before"(input: { tool: string; sessionID?: string; callID?: string }, output: { args: any }) {
      let denial: string | null = null
      try {
        const p = guardedPath(input?.tool, output?.args)
        if (!p) return
        const abs = isAbsolute(p) ? p : resolve(directory, p)
        const payload = JSON.stringify({ tool_name: GUARDED[String(input.tool).toLowerCase()], tool_input: { file_path: abs } })
        const r = runHookSync(root, "frozen-guard.sh", directory, payload)
        if (r && r.status === 2) denial = r.stderr.trim() || "strictlybetter guard: denied"
      } catch {
        denial = null
      }
      if (denial) throw new Error(denial)
    },
  }
}
