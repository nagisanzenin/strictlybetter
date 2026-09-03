---
description: "strictlybetter — run exactly one research-loop cycle: prereg, experiment, submit, judge, blind-judge, confirm, accept or discard."
argument-hint: ""
---

Load strictlybetter's `run` skill: find the skill named `run` in the skills list of your system prompt, read its SKILL.md with the read tool, and follow it exactly as your operating instructions from here on. Run its engine-resolution block VERBATIM first (the strictlybetter extension exports `SB_ROOT` for it) and quote the engine's output; never compute a statistic yourself.

The user's request (empty means: one cycle): $@
