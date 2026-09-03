/**
 * strictlybetter — PreCompact pins (OpenCode V1: experimental.session.compacting)
 * ===============================================================================
 *
 * When a campaign is running, hooks/pre-compact.sh prints at most six lines that must
 * survive summarization (campaign id, branch and head, the harness-computes rule, the
 * frozen paths, where edits are allowed). This adapter pushes them into the compaction
 * context. Silent otherwise.
 */

import { runHook } from "./run-hook.js"

export function createPreCompactHook(root: string, directory: string) {
  return {
    async "experimental.session.compacting"(_input: any, output: { context?: string[] }) {
      try {
        const pins = await runHook(root, "pre-compact.sh", directory)
        if (pins && Array.isArray(output?.context)) output.context.push(pins)
      } catch {}
    },
  }
}
