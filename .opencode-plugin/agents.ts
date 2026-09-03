/**
 * strictlybetter — Agent Registration (OpenCode)
 * ==============================================
 *
 * Reads agents/*.md (Claude Code frontmatter + body) and registers them via
 * cfg.agent during the first-execution bridge, as mode: "subagent", hidden: true.
 *
 * The Claude `tools:` list is translated to OpenCode's { tool: boolean } map with
 * OpenCode's lowercase tool names, and every MUTATING tool the agent did not list is
 * set to false explicitly — the judge's Read-only restriction is load-bearing (it is
 * what keeps the blind judge from touching the worktree), and OpenCode only restricts
 * tools that are named.
 *
 * `effort:` has no OpenCode equivalent: the three experimenter tiers run at the
 * session model's default effort here (INSTALL-OPENCODE-V2.md says so).
 *
 * Per-file try/catch — one corrupt agent is skipped; others load normally.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { parseFrontmatter } from "./parse-frontmatter.js"

const CLAUDE_TO_OPENCODE: Record<string, string | null> = {
  Read: "read",
  Edit: "edit",
  MultiEdit: "edit",
  Write: "write",
  Bash: "bash",
  Glob: "glob",
  Grep: "grep",
  WebFetch: "webfetch",
  WebSearch: "websearch",
  NotebookEdit: null, // no OpenCode counterpart
}

/** Tools that change the world; denied unless the agent listed them. */
export const MUTATING_TOOLS = ["edit", "write", "bash", "patch"]

/** Translates a Claude Code `tools:` value ("Read, Edit, Bash") to OpenCode's map. */
export function toolMap(tools: string | undefined): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  for (const raw of (tools || "").split(",")) {
    const t = raw.trim()
    if (!t) continue
    const mapped = t in CLAUDE_TO_OPENCODE ? CLAUDE_TO_OPENCODE[t] : t.toLowerCase()
    if (mapped) out[mapped] = true
  }
  for (const m of MUTATING_TOOLS) if (!(m in out)) out[m] = false
  return out
}

/** Finds the agents directory. */
export function resolveAgentsDir(root: string): string | null {
  const dir = resolve(root, "agents")
  return existsSync(dir) ? dir : null
}

/** Reads all *.md files from agents/ and registers them in cfg.agent. Skips already-registered names. */
export function registerAgents(cfg: any, root: string) {
  const agentsDir = resolveAgentsDir(root)
  if (!agentsDir) return
  cfg.agent = cfg.agent || {}
  for (const file of readdirSync(agentsDir)) {
    if (!file.endsWith(".md")) continue
    try {
      const content = readFileSync(resolve(agentsDir, file), "utf-8")
      const { attrs, body } = parseFrontmatter(content)
      const name = attrs.name || file.replace(/\.md$/, "")
      if (cfg.agent[name]) continue
      const agentCfg: Record<string, any> = {
        mode: "subagent",
        hidden: true,
        prompt: body,
        tools: toolMap(attrs.tools),
      }
      if (attrs.description) agentCfg.description = attrs.description
      cfg.agent[name] = agentCfg
    } catch {}
  }
}
