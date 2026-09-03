---
description: "strictlybetter — stop the loop at the next safe point by writing the STOP file."
argument-hint: "[--resume]"
---

Load strictlybetter's `stop` skill: find the skill named `stop` in the skills list of your system prompt, read its SKILL.md with the read tool, and follow it exactly as your operating instructions from here on. Run its engine-resolution block VERBATIM first (the strictlybetter extension exports `SB_ROOT` for it) and quote the engine's output; never compute a statistic yourself.

The user's request (empty means: stop): $@
