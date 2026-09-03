# Spawning strictlybetter's agents

strictlybetter delegates five jobs to separate agents, and the separation is load-bearing:

| Agent | Job | Why it must be separate |
|---|---|---|
| `sb-orienteer` | repo → profile JSON | fresh eyes; runs every command it reports, once |
| `sb-metrologist` | profile → metric cards | writes `gaming_risks` before anyone has a reason to be lenient |
| `sb-experimenter-{low,medium,high}` | one pre-registered hypothesis → a diff in one worktree | fresh context per experiment (no rot, no cross-talk); tier pinned by frontmatter because the Agent tool has no per-spawn effort parameter |
| `sb-judge` | one promoted diff → a fixed verdict | **blind**: a judge that has read the experimenter's reasoning judges the argument, not the diff |
| `sb-distiller` | ledger → inheritance body | reads the ledger, not the conversation; the body must work for a reader with no context |

On Claude Code these are registered agents: spawn `strictlybetter:sb-judge` (or the bare
name if your platform strips the namespace) with the Agent tool. Every spawn is a fresh
context. Never fork.

**If your platform's Agent tool does not offer these types** (ZCode, OpenCode's generic agents, any
host that only lists `general-purpose`-style agents): spawn a general agent and put this sentence
BEFORE the task text, with the absolute path under the plugin root:

> You are strictlybetter's `<name>`. First Read your full agent definition at `<plugin-root>/agents/<name>.md` and follow it exactly. Then:

The agent files are self-contained for this. Two consequences on such platforms: the `effort:`
frontmatter (tier pinning of the three experimenters) is silently dropped, so `sb cost --tier` is
the orchestrator's self-report rather than an enforced tier; and the judge's Read-only tool list is
advisory, so state in the task text that it must not run commands.

## Rules that do not bend

- **Payloads go by file path, never inline.** Write the JSON under
  `.strictlybetter/inbox/` (the one directory the guard lets you write while a campaign
  runs, along with `tmp/`) and pass the path. A diff or a hypothesis in a task string is a
  prompt-injection surface and, for anything that later reaches a shell, a command-injection
  hole.
- **One child per judgment.** One experimenter per hypothesis, one judge per promoted
  experiment, one distiller per distill. Reusing a child for a second item produces one
  opinion stated twice and leaks the first item into the second.
- **No dialogue in the task text.** Not the cycle so far, not "the last one was noise so be
  bolder", not "I think this one is clean". An experimenter receives its task file; a judge
  receives its payload path and nothing else. The list of inputs in each agent's file is
  exhaustive.
- **Spawn in parallel when independent.** Up to `max_parallel` experimenters at once (one
  message, several Agent calls). The engine serializes timing-sensitive measurements behind
  its own lock; you do not have to.
- **Never do the agent's job inline.** If the Agent tool is unavailable, stop and say so.
  There is no mode where the orchestrator implements a hypothesis (the guard hook denies
  it) or judges its own promoted diff.

## Tier by operator (which experimenter to spawn)

| Operator | Agent |
|---|---|
| `config`, `docs`, `test-add` | `sb-experimenter-low` |
| `algorithmic`, `allocation`, `caching`, `bugfix`, `numerics`, `data` | `sb-experimenter-medium` |
| `concurrency`, `model`, `refactor-enabling`, `dependency` | `sb-experimenter-high` |

Record the tier with `$SB cost <id> --wall-s <s> --tier <low|medium|high>`.

## Task text for an experimenter (the whole of it)

> Implement the strictlybetter experiment in `<repo>/.strictlybetter/inbox/task-e0007.json`. Edit only inside the worktree it names; do not run the benchmark yourself more than twice; return `DONE e0007` or `BLOCKED: <reason>`.

`task-<id>.json` (written by the orchestrator, never by hand-typing the diff; `commands`
values are the profile's strings or null):

```json
{"id": "e0007", "worktree": "<abs path>", "hypothesis": "<abs path to hyp json>",
 "frozen_paths": [...], "protected_paths": [...],
 "commands": {"test": "...", "bench": "...", "build": null, "lint": "..."},
 "inheritance": "<abs path or null>", "archive_hints": ["<abs path>.diff", ...]}
```

## Reading a return value

- `DONE <id>`: the worktree holds the change. Continue with `$SB submit <id>`.
- `BLOCKED: <reason>`: the agent could not implement the hypothesis as pre-registered
  (target missing, hypothesis already true, would need a frozen path, would need a
  dependency outside the `dependency` operator). Do not retry it in the same cycle.
  `$SB discard <id> --reason manual:blocked` and record the reason in the cycle summary;
  the distiller reads it from the ledger.
- Anything else (prose, a question, a partial diff description): treat as `BLOCKED:
  malformed return`. The agent had no one to ask; a question is a failure to follow the
  one-line rule, not an invitation to answer it.
- A judge return that is not exactly the four-key JSON: spawn a fresh judge once; if it
  fails again, `$SB discard <id> --reason harness-error --archive` and say so. Never
  hand-write a verdict.
