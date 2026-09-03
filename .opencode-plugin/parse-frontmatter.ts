/**
 * Parses YAML-ish frontmatter from a markdown string (one `key: value` per line).
 * Returns { attrs: { key: value, … }, body: string } — the remaining markdown body.
 * Falls back to { attrs: {}, body: text } for files without frontmatter.
 * Quoted values ("…") are unquoted; the agents' descriptions are quoted because they
 * contain colon-space sequences that a strict YAML parser would reject unquoted.
 */
export function parseFrontmatter(text: string): { attrs: Record<string, string>; body: string } {
  const match = text.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
  if (!match) return { attrs: {}, body: text }
  const attrs: Record<string, string> = {}
  for (const line of match[1].split("\n")) {
    const kv = line.match(/^([\w-]+):\s*(.*)$/)
    if (!kv) continue
    let v = kv[2].trim()
    if (v.length >= 2 && v.startsWith('"') && v.endsWith('"')) {
      try { v = JSON.parse(v) } catch { v = v.slice(1, -1) }
    }
    attrs[kv[1]] = v
  }
  return { attrs, body: match[2].trim() }
}
