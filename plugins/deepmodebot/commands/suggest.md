---
description: "Map 100% of highest-leverage project tasks across every subsystem (capability gaps, SOTA multipliers, drift, stubs, perf, and verification) as ranked /deep prompts"
argument-hint: "[optional focus area, e.g. 'auth', 'product roadmap', 'perf', or leave blank for full project scope]"
---

Read `skill://deepmodebot` (**Contain the work** and **Non-negotiables**) and `skill://deepmodebot/references/techniques/suggest.md` in full, then build the complete **High-Leverage Task Map** for the current repository.

Run `python -B "<deepmodebot skill dir>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 0 --ui --json` (`py -3 -B` on Windows), verify every candidate against real files (drop false positives), add any domain/product/SOTA capability levers observed in the codebase, and present **all** verified high-leverage tasks grouped into `Wave 1 (P0)` / `Wave 2 (P1)` / `Wave 3 (P2)` (never truncate to 1–3 items) alongside the clickable `.scratch/gen-ui/suggest/index.html` A2UI v1.0 cockpit.

Focus: $ARGUMENTS
