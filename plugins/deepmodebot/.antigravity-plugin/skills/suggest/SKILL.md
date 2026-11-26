---
name: suggest
description: "Map 100% of highest-leverage project tasks (/suggest) across all subsystems; output wave-ranked file:line-backed /deep prompts."
---

# /suggest

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) for **Contain the work** and **Non-negotiables**, then read `skill://deepmodebot/references/techniques/suggest.md` in full and run **suggest** on the active repository.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Run `py -3 -B "<deepmodebot skill dir>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 0 --ui --json` (`python -B` on POSIX), verify every gap and overclaim against real files, add any domain/product/SOTA capability levers found in code/docs, and return the **complete wave-ranked High-Leverage Task Map (`1..N`, never truncated to 1–3)** with exact `file:line` receipts plus a link to `.scratch/gen-ui/suggest/index.html`.

Apply this to what the user asked for.
