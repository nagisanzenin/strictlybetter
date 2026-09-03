/**
 * Pi extension smoke suite — a fake `pi` object stands in for the host. Proves the
 * env export, the fire-and-forget nudge, child/headless inertness, and the guard's
 * fast path and deny path. The live pi transport is not verified here (INSTALL-PI.md).
 */
import { describe, it, expect, beforeEach, afterEach } from "bun:test"
import { tmpdir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs"
import { resolve } from "node:path"
import extension, { campaignExists } from "../pi/strictlybetter"

const ROOT = resolve(import.meta.dir, "..")
const ENGINE = resolve(ROOT, "scripts", "sb.py")

function fakePi(exec: (cmd: string, args: string[]) => Promise<any>) {
  const handlers: Record<string, any> = {}
  const calls: string[][] = []
  return {
    handlers,
    calls,
    pi: {
      on(event: string, handler: any) { handlers[event] = handler },
      exec(cmd: string, args: string[]) { calls.push([cmd, ...args]); return exec(cmd, args) },
    },
  }
}
const ui = (hasUI: boolean) => ({ hasUI, ui: { notify: (_t: string) => {} } })
const tick = () => new Promise((r) => setTimeout(r, 5))

let savedRoot: string | undefined, savedChild: string | undefined, savedHome: string | undefined
beforeEach(() => { savedRoot = process.env.SB_ROOT; savedChild = process.env.SB_CHILD; savedHome = process.env.SB_HOME; delete process.env.SB_ROOT; delete process.env.SB_CHILD; delete process.env.SB_HOME })
afterEach(() => {
  if (savedRoot === undefined) delete process.env.SB_ROOT; else process.env.SB_ROOT = savedRoot
  if (savedChild === undefined) delete process.env.SB_CHILD; else process.env.SB_CHILD = savedChild
  if (savedHome === undefined) delete process.env.SB_HOME; else process.env.SB_HOME = savedHome
})

describe("pi extension", () => {
  it("exports SB_ROOT pointing at the package root and respects an existing value", () => {
    const f = fakePi(async () => ({ stdout: "", stderr: "", code: 0 }))
    extension(f.pi as any)
    expect(process.env.SB_ROOT).toBe(ROOT)
    process.env.SB_ROOT = "/elsewhere"
    extension(fakePi(async () => ({ stdout: "", stderr: "", code: 0 })).pi as any)
    expect(process.env.SB_ROOT).toBe("/elsewhere")
  })

  it("nudges once per session, on the first prompt, from the engine's session-start line", async () => {
    const f = fakePi(async () => ({ stdout: "[strictlybetter] campaign c1 running: 3 experiments\nextra\nthird", stderr: "", code: 0 }))
    extension(f.pi as any)
    f.handlers.session_start({ type: "session_start", reason: "startup" }, ui(true))
    await tick()
    expect(f.calls[0]).toEqual(["python3", ENGINE, "--repo", process.cwd(), "session-start"])
    const first = f.handlers.before_agent_start({}, ui(true))
    expect(first.message.customType).toBe("strictlybetter-nudge")
    expect(first.message.content).toBe("[strictlybetter] campaign c1 running: 3 experiments\nextra")  // two lines max
    expect(f.handlers.before_agent_start({}, ui(true))).toBeUndefined()
  })

  it("is inert without a UI, in a child, and on a killed probe", async () => {
    const f = fakePi(async () => ({ stdout: "[strictlybetter] x", stderr: "", code: 0 }))
    extension(f.pi as any)
    f.handlers.session_start({ type: "session_start", reason: "startup" }, ui(false))
    await tick()
    expect(f.calls.length).toBe(0)
    process.env.SB_CHILD = "1"
    f.handlers.session_start({ type: "session_start", reason: "new" }, ui(true))
    await tick()
    expect(f.calls.length).toBe(0)
    delete process.env.SB_CHILD
    const k = fakePi(async () => ({ stdout: "[strictlybetter] torn", stderr: "", code: 0, killed: true }))
    extension(k.pi as any)
    k.handlers.session_start({ type: "session_start", reason: "startup" }, ui(true))
    await tick()
    expect(k.handlers.before_agent_start({}, ui(true))).toBeUndefined()
  })

  it("guard: fast path without a campaign, deny on exit 2, allow on anything else", async () => {
    const f = fakePi(async () => ({ stdout: "", stderr: "strictlybetter guard: denied edit to /r/bench.py: frozen path\n", code: 2 }))
    extension(f.pi as any)
    expect(await f.handlers.tool_call({ type: "tool_call", toolName: "edit", input: { path: "/r/bench.py" } }, ui(true))).toBeUndefined()
    expect(f.calls.length).toBe(0)                                       // no campaign → python never started
    expect(await f.handlers.tool_call({ type: "tool_call", toolName: "bash", input: { command: "ls" } }, ui(true))).toBeUndefined()

    const home = mkdtempSync(resolve(tmpdir(), "sb-pi-home-"))
    try {
      writeFileSync(resolve(home, "campaign.json"), "{}")
      process.env.SB_HOME = home
      expect(campaignExists(process.cwd())).toBe(true)
      const r = await f.handlers.tool_call({ type: "tool_call", toolName: "edit", input: { path: "/r/bench.py" } }, ui(true))
      expect(r).toEqual({ block: true, reason: "strictlybetter guard: denied edit to /r/bench.py: frozen path" })
      expect(f.calls.at(-1)).toEqual(["python3", ENGINE, "--repo", process.cwd(), "guard", "/r/bench.py"])
      const ok = fakePi(async () => ({ stdout: "", stderr: "", code: 0 }))
      extension(ok.pi as any)
      expect(await ok.handlers.tool_call({ type: "tool_call", toolName: "write", input: { path: "x.py" } }, ui(true))).toBeUndefined()
      const boom = fakePi(async () => { throw new Error("no exec") })
      extension(boom.pi as any)
      expect(await boom.handlers.tool_call({ type: "tool_call", toolName: "write", input: { path: "x.py" } }, ui(true))).toBeUndefined()
    } finally {
      rmSync(home, { recursive: true, force: true })
    }
  })
})
