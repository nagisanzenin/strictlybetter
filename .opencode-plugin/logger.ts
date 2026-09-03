/**
 * strictlybetter — Plugin Logger (OpenCode V1)
 * ============================================
 *
 * Writes structured logs to OpenCode's server-side log via client.app.log() and
 * shows a TUI toast for warnings. Every call is best-effort: a logger that throws
 * would turn a diagnostic into a broken session.
 */

export function createPluginLogger(client: any): (msg: string) => void {
  function writeLog(level: "debug" | "info" | "warn" | "error", message: string) {
    try {
      client?.app?.log?.({ service: "strictlybetter", level, message })
    } catch {}
  }

  return (msg: string) => {
    const level = msg.includes("WARNING") ? "warn" : "info"
    writeLog(level, msg)
    if (level === "warn") {
      try {
        client?.tui?.showToast?.({
          body: { title: "strictlybetter", message: msg, variant: "warning", duration: 15000 },
        })?.catch?.(() => {})
      } catch {}
    }
  }
}
