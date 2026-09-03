/**
 * strictlybetter — Combined V1+V2 Entrypoint (OpenCode)
 * =====================================================
 *
 * The single module behind `main`, `exports["."]`, and `exports["./server"]`.
 *
 * OpenCode 1.x resolves npm plugin entries by probing exports["./server"] FIRST and
 * falling back to `main`; OpenCode 2.x resolves the bare name (exports["."]) on its
 * current line and probed ./server on the earlier next line. Every probe chain
 * therefore lands on whatever ./server or . points at, so runtime-specific files
 * behind those keys cannot work (engram issue #19: V1 loaded a V2-only module and
 * died on "must default export an object with server()").
 *
 * Both validators tolerate the union shape:
 *   V1 readV1Plugin — requires default.server to be a function, ignores unknown keys.
 *   V2 PluginModule — requires default.id (string) + default.setup (function), ignores
 *                     unknown keys.
 * So `{ id, server, setup }` loads under every line. The runtime-specific modules
 * stay importable directly (tests, the ./v2 subpath, local-checkout configs).
 */

import { server } from "./index.js"
import { setup } from "./v2.js"

export { server, setup }

export default {
  id: "strictlybetter",
  server,
  setup,
}
