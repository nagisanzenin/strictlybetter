---
description: "strictlybetter — orient on this repository: spawn the orienteer, verify the toolchain commands, store the profile."
argument-hint: "[--refresh]"
---

Load strictlybetter's `orient` skill: find the skill named `orient` in the skills list of your system prompt, read its SKILL.md with the read tool, and follow it exactly as your operating instructions from here on. Run its engine-resolution block VERBATIM first (the strictlybetter extension exports `SB_ROOT` for it) and quote the engine's output; never compute a statistic yourself.

The user's request (empty means: orient once): $@
