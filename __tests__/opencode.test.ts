/**
 * OpenCode adapter smoke suite — bun's built-in runner (`bun test __tests__`), zero deps.
 * Exercises the V1 server, the V2 setup, self-extract ownership rules, the agent
 * transform, and the hook shapes against a temp project. No OpenCode binary needed;
 * the live checks are in INSTALL-OPENCODE-V2.md.
 */
import { describe, it, expect, beforeEach, afterEach } from "bun:test"
import { tmpdir, homedir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs"
import { resolve } from "node:path"
import entry from "../.opencode-plugin/entry"
import { server } from "../.opencode-plugin/index"
import v2Default, { createV2Setup, extractionScope, registerHook, resolveWorkspaceDirectory } from "../.opencode-plugin/v2"
import { selfExtract, transformAgentForOpenCode, readVersionRecord, sha256, VERSION_FILE, COMMANDS_DEF } from "../.opencode-plugin/install"
import { toolMap } from "../.opencode-plugin/agents"
import { guardedPath } from "../hooks/frozen-guard"

const ROOT = resolve(import.meta.dir, "..")
const GLOBAL_STAMP = resolve(homedir(), ".config", "opencode", VERSION_FILE)

let tmp: string
beforeEach(() => {
  tmp = mkdtempSync(resolve(tmpdir(), "sb-oc-test-"))
  writeFileSync(resolve(tmp, "opencode.json"), "{}")
})
afterEach(() => rmSync(tmp, { recursive: true, force: true }))

const target = () => resolve(tmp, ".opencode")

function mkCtx(directory?: string) {
  const location = directory ? { directory, workspaceID: "ws_test" } : undefined
  const calls = {
    reloads: [] as string[],
    disposed: [] as string[],
    sessionHooks: {} as Record<string, (input: any) => Promise<void> | void>,
    shellHooks: {} as Record<string, (input: any) => Promise<void> | void>,
    toolHooks: {} as Record<string, (input: any) => Promise<void> | void>,
  }
  const reg = (label: string) => ({ dispose: async () => { calls.disposed.push(label) } })
  const ctx = {
    command: { reload: async () => { calls.reloads.push("command") }, list: async () => ({ location, data: [] }) },
    skill: { reload: async () => { calls.reloads.push("skill") } },
    agent: { reload: async () => { calls.reloads.push("agent") }, list: async () => ({ location, data: [] }) },
    session: { hook: async (name: string, cb: any) => { calls.sessionHooks[name] = cb; return reg(`session.${name}`) } },
    shell: { hook: async (name: string, cb: any) => { calls.shellHooks[name] = cb; return reg(`shell.${name}`) } },
    tool: { hook: async (name: string, cb: any) => { calls.toolHooks[name] = cb; return reg(`tool.${name}`) } },
  }
  return { ctx, calls }
}

describe("package entry shapes", () => {
  it("combined entry is { id, server, setup }", () => {
    expect(entry.id).toBe("strictlybetter")
    expect(typeof entry.server).toBe("function")
    expect(typeof entry.setup).toBe("function")
  })
  it("v2 default is a plain { id, setup }", () => {
    expect(v2Default.id).toBe("strictlybetter")
    expect(typeof v2Default.setup).toBe("function")
  })
})

describe("agent translation", () => {
  it("toolMap denies every mutating tool the agent did not list", () => {
    expect(toolMap("Read")).toEqual({ read: true, edit: false, write: false, bash: false, patch: false })
    const full = toolMap("Read, Edit, Write, Bash, Glob, Grep")
    expect(full).toMatchObject({ read: true, edit: true, write: true, bash: true, glob: true, grep: true, patch: false })
  })
  it("transforms sb-judge.md to a read-only subagent and is idempotent", () => {
    const src = readFileSync(resolve(ROOT, "agents", "sb-judge.md"), "utf-8")
    const out = transformAgentForOpenCode(src)
    expect(out).toContain("name: sb-judge")
    expect(out).toContain("mode: subagent")
    expect(out).toContain("hidden: true")
    expect(out).toContain("  read: true")
    expect(out).toContain("  edit: false")
    expect(out).toContain("  bash: false")
    expect(out).toMatch(/^description: "/m)          // quoted: the description holds ": "
    expect(transformAgentForOpenCode(out)).toBe(out)
    expect(out).toContain("EXACTLY this JSON and nothing else")  // body carried verbatim
  })
})

describe("selfExtract", () => {
  it("extracts skills (with _shared), transformed agents, and generated commands; then no-ops", () => {
    const r = selfExtract(ROOT, tmp, "1.2.0")
    expect(r.target).toBe(target())
    expect(r.freshlyExtracted).toBe(true)
    expect(existsSync(resolve(target(), "skills", "run", "SKILL.md"))).toBe(true)
    expect(existsSync(resolve(target(), "skills", "_shared", "engine-resolution.md"))).toBe(true)
    expect(readFileSync(resolve(target(), "agents", "sb-judge.md"), "utf-8")).toContain("mode: subagent")
    for (const name of Object.keys(COMMANDS_DEF)) expect(existsSync(resolve(target(), "commands", `${name}.md`))).toBe(true)
    expect(existsSync(resolve(target(), "scripts"))).toBe(false)   // the engine is never extracted
    const rec = readVersionRecord(target())
    expect(rec.version).toBe("1.2.0")
    expect(Object.keys(rec.files || {}).length).toBeGreaterThan(10)
    const again = selfExtract(ROOT, tmp, "1.2.0")
    expect(again.freshlyExtracted).toBe(false)
    expect(again.report).toBeUndefined()
  })

  it("on a version bump: refreshes our unmodified copies, preserves user edits, never touches user files", () => {
    selfExtract(ROOT, tmp, "1.2.0")
    const edited = resolve(target(), "skills", "run", "SKILL.md")
    writeFileSync(edited, "# my edited run skill\n")
    // Simulate a stale copy WE wrote: rewrite the file and record its hash as ours.
    const stale = resolve(target(), "skills", "status", "SKILL.md")
    writeFileSync(stale, "stale shipped content\n")
    const vf = resolve(target(), VERSION_FILE)
    const rec = JSON.parse(readFileSync(vf, "utf-8"))
    rec.files["skills/status/SKILL.md"] = sha256("stale shipped content\n")
    writeFileSync(vf, JSON.stringify(rec))
    // A user's own command that shares a generated name is never overwritten.
    const userCmd = resolve(target(), "commands", "sb-run.md")
    writeFileSync(userCmd, "---\ndescription: mine\n---\nmy own\n")

    const r = selfExtract(ROOT, tmp, "9.9.9")
    expect(r.freshlyExtracted).toBe(false)
    expect(r.prevVersion).toBe("1.2.0")
    expect(readFileSync(edited, "utf-8")).toBe("# my edited run skill\n")
    expect(r.report!.preserved).toContain("skills/run/SKILL.md")
    expect(readFileSync(stale, "utf-8")).toBe(readFileSync(resolve(ROOT, "skills", "status", "SKILL.md"), "utf-8"))
    expect(r.report!.written).toContain("skills/status/SKILL.md")
    expect(readFileSync(userCmd, "utf-8")).toContain("my own")
    expect(readVersionRecord(target()).version).toBe("9.9.9")
  })
})

describe("V1 server", () => {
  it("bridges agents, the skills path and the commands on first run only", async () => {
    const plugin: any = await server({ directory: tmp })
    const cfg: any = {}
    await plugin.config(cfg)
    expect(cfg.agent["sb-judge"].mode).toBe("subagent")
    expect(cfg.agent["sb-judge"].tools).toMatchObject({ read: true, edit: false, write: false, bash: false })
    expect(cfg.agent["sb-experimenter-low"].tools).toMatchObject({ edit: true, bash: true })
    expect(cfg.skills.paths).toContain(resolve(target(), "skills"))
    expect(cfg.command["strictlybetter"].template).toContain("`strictlybetter` skill")
    expect(cfg.command["sb-run"].template).toContain("`run` skill")
    // second process, same version: disk discovery owns it now → no bridge
    const plugin2: any = await server({ directory: tmp })
    const cfg2: any = {}
    await plugin2.config(cfg2)
    expect(cfg2.agent).toBeUndefined()
    expect(cfg2.command).toBeUndefined()
  })

  it("exports SB_ROOT into every shell and never throws the guard without a campaign", async () => {
    const plugin: any = await server({ directory: tmp })
    const out = { env: {} as Record<string, string> }
    await plugin["shell.env"]({ cwd: tmp }, out)
    expect(out.env.SB_ROOT).toBe(ROOT)
    expect(out.env.OPENCODE_PLUGIN_ROOT).toBe(ROOT)
    await plugin["tool.execute.before"]({ tool: "edit" }, { args: { filePath: resolve(tmp, "a.py") } })
    await plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "rm -rf /" } })
    const sys = { system: [] as string[] }
    await plugin["experimental.chat.system.transform"]({}, sys)
    expect(sys.system).toEqual([])   // no state home → silence
    const cmp = { context: [] as string[] }
    await plugin["experimental.session.compacting"]({}, cmp)
    expect(cmp.context).toEqual([])
  })

  it("guardedPath maps OpenCode edit/write args and ignores other tools", () => {
    expect(guardedPath("edit", { filePath: "/x" })).toBe("/x")
    expect(guardedPath("write", { path: "y" })).toBe("y")
    expect(guardedPath("bash", { command: "ls" })).toBeNull()
    expect(guardedPath("edit", {})).toBeNull()
  })
})

describe("V2 setup", () => {
  it("extracts into the located workspace, reloads domains, registers hooks, disposes cleanly", async () => {
    const { ctx, calls } = mkCtx(tmp)
    const nudges: string[] = []
    const setup = createV2Setup({ runNudge: async (dir) => { nudges.push(dir); return "[strictlybetter] campaign x running" } })
    const cleanup = await setup(ctx)
    expect(existsSync(resolve(target(), "skills", "run", "SKILL.md"))).toBe(true)
    expect(calls.reloads).toEqual(["skill", "agent", "command"])
    const sc = { sessionID: "s1", system: [] as any[] }
    await calls.sessionHooks["context"](sc)
    await calls.sessionHooks["context"](sc)                  // same session: once
    expect(sc.system.length).toBe(1)
    expect(sc.system[0].text).toContain("[strictlybetter] campaign x running")
    expect(nudges).toEqual([tmp])
    const shell = { env: {} as Record<string, string>, cwd: tmp }
    await calls.shellHooks["create.before"](shell)
    expect(shell.env.SB_ROOT).toBe(ROOT)
    await calls.toolHooks["execute.before"]({ tool: "edit", args: { filePath: resolve(tmp, "a.py") } })  // no campaign → allow
    await (cleanup as any)()
    expect(calls.disposed.sort()).toEqual(["session.context", "shell.create.before", "tool.execute.before"])
  })

  it("goes hooks-only when no domain reports a location — nothing written anywhere", async () => {
    const { ctx, calls } = mkCtx(undefined)
    const before = existsSync(GLOBAL_STAMP)
    await createV2Setup({ runNudge: async () => "nope" })(ctx)
    expect(existsSync(target())).toBe(false)
    expect(existsSync(GLOBAL_STAMP)).toBe(before)
    expect(calls.reloads).toEqual([])
    const sc = { sessionID: "s1", system: [] as any[] }
    await calls.sessionHooks["context"](sc)
    expect(sc.system).toEqual([])                          // no dir → no nudge either
  })

  it("resolves the workspace from location-wrapped responses and scopes extraction", async () => {
    expect(await resolveWorkspaceDirectory(mkCtx(tmp).ctx)).toBe(tmp)
    expect(await resolveWorkspaceDirectory(mkCtx(undefined).ctx)).toBeNull()
    expect(extractionScope(tmp)).toBe(tmp)
    const bare = mkdtempSync(resolve(tmpdir(), "sb-bare-"))
    try { expect(extractionScope(bare)).toBeNull() } finally { rmSync(bare, { recursive: true }) }
    expect(extractionScope(null)).toBeNull()
  })

  it("registerHook tolerates both call forms and absent domains", async () => {
    const seen: string[] = []
    expect(await registerHook({ hook: (n: string) => { seen.push("fn:" + n); return { dispose: async () => {} } } }, "context", () => {})).toBeDefined()
    expect(await registerHook({ hook: { context: () => { seen.push("obj"); return {} } } }, "context", () => {})).toBeDefined()
    expect(await registerHook(undefined, "context", () => {})).toBeUndefined()
    expect(seen).toEqual(["fn:context", "obj"])
  })
})
