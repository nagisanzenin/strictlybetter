/**
 * strictlybetter — Shell Environment Hook (OpenCode V1)
 * =====================================================
 *
 * Injects SB_ROOT and OPENCODE_PLUGIN_ROOT into every shell execution, pointing at the
 * package root — the npm cache entry or the git checkout — where scripts/sb.py lives.
 * The skills' engine-resolution waterfall reads SB_ROOT, so `$SB` resolves to the
 * engine that ships with the installed version (the engine is never extracted).
 * SB_HOME is forwarded when the host process carries it (state-home override).
 */

export function createShellEnvHook(packageRoot: string) {
  return {
    async "shell.env"(_input: any, output: { env: Record<string, string> }) {
      try {
        output.env["SB_ROOT"] = packageRoot
        output.env["OPENCODE_PLUGIN_ROOT"] = packageRoot
        if (process.env.SB_HOME) output.env["SB_HOME"] = process.env.SB_HOME
      } catch {}
    },
  }
}
