/**
 * strictlybetter — Pi extension (https://pi.dev)
 *
 * Three jobs, all ambient:
 *
 * 1. SB_ROOT — export the package root into pi's process env so the skills'
 *    engine-resolution block finds `scripts/sb.py` from any bash call, wherever
 *    the package was installed (git, npm, local path). Pi's exec API and its bash
 *    tool both spawn children from process.env, so one assignment reaches every
 *    shell the skills run (omniplugin R1, the in-process refinement).
 *
 * 2. The nudge — once per session start (startup / new / resume / reload), run
 *    `sb.py session-start` for the current working directory; if a campaign is
 *    running or halted there, show one TUI notice and inject one custom message on
 *    the next user prompt so the model sees the same fact the human does.
 *
 * 3. The guard — on every `edit` / `write` tool call while a campaign is running
 *    in the cwd, ask `sb.py guard <path>`; exit 2 blocks the call with the engine's
 *    one-line reason. This is the PreToolUse deny of Claude Code in pi's dialect
 *    (`tool_call` handlers may return { block: true, reason }). Anything else —
 *    no campaign, no engine, a timeout, an unexpected event shape — allows, which is
 *    the documented fail-open shape of this hook class; `sb submit` re-checks
 *    integrity at gate time regardless.
 *
 * Contract: ambient, never nagging — at most one nudge per session, and on ANY
 * failure degrade to silence (or, for the guard, to allow), never to repetition or
 * a broken host. Every handler is wrapped; nothing here may crash pi.
 *
 * Spawned children (experimenters, the blind judge, the distiller — see
 * skills/_shared/subagents.md) run with SB_CHILD=1 and without a UI (`ctx.hasUI` is
 * false in `-p` and `--mode json`): either condition makes the NUDGE inert so a
 * judge's context is never polluted. The GUARD stays on in children: an
 * experimenter child edits inside its worktree and must be denied the instrument
 * exactly like the parent would be.
 *
 * Types below are structural on purpose. A type-only import of pi's package would
 * drag pi into this package's dependency graph, which also serves OpenCode users.
 * The shape is checked against the pi 0.83.x / 0.74.x extension API engram ships on.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

type ExecResult = { stdout: string; stderr: string; code: number | null; killed?: boolean };

interface SessionStartEvent {
	type: "session_start";
	reason: "startup" | "reload" | "new" | "resume" | "fork";
}

interface BeforeAgentStartResult {
	message?: { customType: string; content: string; display: boolean };
}

interface ToolCallEvent {
	type: "tool_call";
	toolName: string;
	input: Record<string, unknown>;
}

interface ToolCallResult {
	block?: boolean;
	reason?: string;
}

interface Ctx {
	hasUI: boolean;
	ui: { notify(text: string, level?: "info" | "warning" | "error"): void };
}

interface PiLike {
	exec(command: string, args: string[], options?: { timeout?: number }): Promise<ExecResult>;
	on(event: "session_start", handler: (ev: SessionStartEvent, ctx: Ctx) => void | Promise<void>): void;
	on(
		event: "before_agent_start",
		handler: (ev: unknown, ctx: Ctx) => BeforeAgentStartResult | undefined,
	): void;
	on(
		event: "tool_call",
		handler: (ev: ToolCallEvent, ctx: Ctx) => Promise<ToolCallResult | undefined> | ToolCallResult | undefined,
	): void;
}

const GUARDED_TOOLS = new Set(["edit", "write"]);

/** Directory of this file — jiti (pi's loader) provides import.meta.url; keep a CJS fallback. */
function selfDir(): string | null {
	try {
		return path.dirname(fileURLToPath(import.meta.url));
	} catch {
		/* fall through */
	}
	try {
		// @ts-ignore — defined when the loader transpiled us to CJS
		if (typeof __dirname === "string") return __dirname;
	} catch {
		/* fall through */
	}
	return null;
}

/** True when a campaign file exists for the cwd (or SB_HOME). Cheap; runs before every guarded edit. */
export function campaignExists(cwd: string): boolean {
	try {
		const home = process.env.SB_HOME;
		if (home && fs.existsSync(path.join(home, "campaign.json"))) return true;
		return fs.existsSync(path.join(cwd, ".strictlybetter", "campaign.json"));
	} catch {
		return false;
	}
}

export default function strictlybetterExtension(pi: PiLike) {
	const dir = selfDir();
	const root = dir ? path.dirname(dir) : null; // this file lives at <root>/pi/strictlybetter.ts
	const engine = root ? path.join(root, "scripts", "sb.py") : null;
	const usable = !!(engine && fs.existsSync(engine));

	if (usable && !process.env.SB_ROOT) {
		process.env.SB_ROOT = root!;
	}

	let pending: string | null = null;
	let probeGen = 0;

	// Deliberately NOT async and nothing awaited: pi awaits session_start handlers
	// before rendering the TUI and before completing /new and /resume, so an awaited
	// exec here would freeze startup for up to the full timeout when the engine is
	// slow. Fire the probe and let the result land whenever it lands.
	pi.on("session_start", (ev, ctx) => {
		try {
			if (!usable || !ctx.hasUI || process.env.SB_CHILD) return;
			if (ev.reason !== "startup" && ev.reason !== "new" && ev.reason !== "resume" && ev.reason !== "reload")
				return;
			pending = null;
			const gen = ++probeGen;
			void pi
				.exec("python3", [engine!, "--repo", process.cwd(), "session-start"], { timeout: 15000 })
				.then((res) => {
					if (gen !== probeGen) return; // a newer session start owns `pending` now
					// A timed-out/signal-killed child resolves code 0 with killed=true —
					// and possibly a truncated stdout fragment. Silence, never a torn nudge.
					const out = res.code === 0 && !res.killed ? res.stdout.trim().split("\n").slice(0, 2).join("\n") : "";
					if (!out) return; // nothing to say — total silence
					pending = out;
					try {
						ctx.ui.notify(out.split("\n")[0].slice(0, 120), "info");
					} catch {
						/* notice is best-effort; the injected message below still lands */
					}
				})
				.catch(() => {
					if (gen === probeGen) pending = null; // silence over repetition
				});
		} catch {
			pending = null;
		}
	});

	pi.on("before_agent_start", (_ev, ctx) => {
		try {
			if (!pending || !ctx.hasUI || process.env.SB_CHILD) return undefined;
			const content = pending;
			pending = null; // one nudge per session, consumed on the first prompt
			return { message: { customType: "strictlybetter-nudge", content, display: true } };
		} catch {
			return undefined;
		}
	});

	// The guard. Registered defensively: if this pi build has no tool_call event the
	// registration is a no-op and the gate-time check in `sb submit` remains the wall.
	try {
		pi.on("tool_call", async (ev) => {
			try {
				if (!usable) return undefined;
				const tool = String(ev?.toolName ?? "").toLowerCase();
				if (!GUARDED_TOOLS.has(tool)) return undefined;
				const p = ev?.input?.path ?? ev?.input?.file_path ?? ev?.input?.filePath;
				if (typeof p !== "string" || !p) return undefined;
				const cwd = process.cwd();
				if (!campaignExists(cwd)) return undefined; // fast path: no campaign, python never starts
				const abs = path.isAbsolute(p) ? p : path.resolve(cwd, p);
				const res = await pi.exec("python3", [engine!, "--repo", cwd, "guard", abs], { timeout: 8000 });
				if (res.code === 2 && !res.killed) {
					const reason = (res.stderr || "").trim().split("\n")[0] || "strictlybetter guard: denied";
					return { block: true, reason };
				}
				return undefined;
			} catch {
				return undefined; // allow — the documented fail-open shape; submit re-checks
			}
		});
	} catch {
		/* no tool_call event on this build */
	}
}
