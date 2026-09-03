---
name: sb-campaign
description: "Surface a running or halted strictlybetter campaign when a session starts — one ambient line, or nothing."
metadata:
  {
    "openclaw":
      {
        "emoji": "🔬",
        "events": ["command:new", "command:reset"],
        "requires": { "bins": ["python3"] },
      },
  }
---

# sb-campaign

The OpenClaw port of strictlybetter's re-anchor hook. On `/new` and `/reset` it runs
`sb.py session-start` against the research repository and delivers whatever that
prints as a chat reply.

`session-start` prints **at most one line, and usually nothing** — it stays silent
unless the repository holds a `.strictlybetter/` state home with a campaign that is
running or halted. That silence is the contract (ambient, never nagging), so the
handler never manufactures output of its own.

`command:new` and `command:reset` are the only two internal hook events whose
`event.messages` are routed back to the originating conversation, which is why the
nudge binds to those rather than `session:*` or `gateway:startup`.

## Which repository

A gateway process has no single project directory the way a terminal agent does. The
handler resolves the research repository, in order, from: the `SB_REPO` environment
variable of the Gateway process; a workspace directory carried on the event
(`event.context.workspaceDir`, `event.workspaceDir`, `event.cwd`), when OpenClaw
supplies one; else the Gateway's own working directory. Set `SB_REPO` when you run the
loop from a chat surface — without it the nudge is silent, never wrong.

## Failure behavior

Every failure path degrades to silence: no `python3`, no engine on disk, a non-zero
exit, a timeout, or unparseable output all return without pushing a message — and
delivery is guarded too, so a frozen, absent, or non-array `event.messages` is swallowed
rather than thrown. A research tool that breaks someone's chat session has already lost
more than the nudge was worth.

## Enabling

Installing the plugin registers the hook — `openclaw hooks info sb-campaign` reports it
ready and *"Managed by plugin"*, so `openclaw hooks enable` neither applies nor works
here. But the Gateway **skips internal hook discovery entirely** until something opts
in, and a plugin-provided hook pack does not count. Without the flag below the hook is
listed, ready, and never runs:

```bash
openclaw config set hooks.internal.enabled true
openclaw gateway restart
```

Verify with `openclaw --log-level debug gateway run`; the loader prints
`Registered hook: sb-campaign -> command:new, command:reset`.

## Discovery note

OpenClaw reads strictlybetter as a **Codex bundle** (`.codex-plugin/plugin.json` is
matched before any other marker, including `openclaw.plugin.json`). For Codex bundles
it treats the manifest's `hooks` value as a list of *directories* to scan for hook
packs. strictlybetter therefore declares no `hooks` key at all: Codex auto-discovers
`./hooks/hooks.json` by convention, and OpenClaw falls back to scanning `./hooks/`,
which is where this pack lives. Re-adding an explicit `"hooks": "./hooks/hooks.json"`
would point OpenClaw's scanner at a *file* and silently break this hook.

## What this port does not carry

OpenClaw's internal hooks have no tool-boundary deny and no Stop event, so on this
platform the frozen-path guard is the **gate-time** check in `sb submit` only, and the
loop is driven from a terminal with `sb drive --command` rather than by a Stop hook.
INSTALL-OPENCLAW.md spells both out.
