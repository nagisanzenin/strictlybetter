---
description: "strictlybetter — run the meta-benchmark: the walled loop against a naive loop on fixture repos."
argument-hint: "[--help | runner arguments]"
---

Load strictlybetter's `bench` skill: find the skill named `bench` in the skills list of your system prompt, read its SKILL.md with the read tool, and follow it exactly as your operating instructions from here on. Run its engine-resolution block VERBATIM first (the strictlybetter extension exports `SB_ROOT` for it) and quote the engine's output; never compute a statistic yourself.

The user's request (empty means: the runner's defaults): $@
