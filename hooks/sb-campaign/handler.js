/**
 * strictlybetter re-anchor hook — OpenClaw port.
 *
 * Runs `sb.py session-start` on /new and /reset and delivers its output as a chat
 * reply. The engine prints at most one line and stays silent when the repository
 * has no running or halted campaign, so this handler only forwards; it never
 * composes a nudge.
 *
 * Silence is also the failure mode. No python3, no engine, no repository, non-zero
 * exit, timeout, empty stdout — every path returns without pushing a message.
 */

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// hooks/sb-campaign/handler.js -> plugin root, when the pack runs from inside the
// installed plugin (the bundle route). A standalone `openclaw hooks install <dir>`
// COPIES the pack into the state dir, where ../.. holds no engine — that route sets
// SB_ROOT in the Gateway environment instead (INSTALL-OPENCLAW.md, Route B).
const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
function resolveEngine() {
  const fromEnv = process.env.SB_ROOT ? join(process.env.SB_ROOT, "scripts", "sb.py") : null;
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  return join(PLUGIN_ROOT, "scripts", "sb.py");
}
const ENGINE = resolveEngine();

const TIMEOUT_MS = 10_000;
const MAX_OUTPUT_BYTES = 64 * 1024;

/** The engine's own cap is one line; the shared hook allows two. Truncate rather than trust. */
const MAX_LINES = 2;

/** The research repository: SB_REPO, a workspace dir on the event, else the Gateway's cwd. */
export function resolveRepo(event) {
  const candidates = [
    process.env.SB_REPO,
    event?.context?.workspaceDir,
    event?.workspaceDir,
    event?.cwd,
    process.cwd(),
  ];
  for (const c of candidates) {
    if (typeof c === "string" && c && existsSync(c)) return c;
  }
  return null;
}

const handler = async (event) => {
  if (event?.type !== "command") return;
  if (event.action !== "new" && event.action !== "reset") return;
  if (!existsSync(ENGINE)) return;
  const repo = resolveRepo(event);
  if (!repo) return;
  // Fast path: no state home (and no SB_HOME override) → nothing to say, python never starts.
  if (!process.env.SB_HOME && !existsSync(join(repo, ".strictlybetter"))) return;

  let stdout = "";
  try {
    ({ stdout } = await execFileAsync("python3", [ENGINE, "--repo", repo, "session-start"], {
      cwd: repo,
      timeout: TIMEOUT_MS,
      maxBuffer: MAX_OUTPUT_BYTES,
      windowsHide: true,
    }));
  } catch {
    return; // missing python3, non-zero exit, timeout, oversized output
  }

  const nudge = String(stdout ?? "")
    .split("\n")
    .map((line) => line.replace(/[\x00-\x08\x0b-\x1f]/g, "").trimEnd())
    .filter(Boolean)
    .slice(0, MAX_LINES)
    .join("\n");

  if (!nudge) return;

  // Delivery is guarded too, not just the engine call: the contract this hook
  // advertises is silence on every failure path, not "the host logged my exception".
  try {
    event.messages.push(nudge);
  } catch {
    /* frozen, absent, or non-array messages — nothing to deliver into */
  }
};

export default handler;
