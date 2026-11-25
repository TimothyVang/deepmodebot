---
name: suggest
description: "Scan the repo (/suggest) for gaps, overclaims, missing tests, and smells; output ranked file:line-backed /deep prompts."
---

# /suggest

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) for **Contain the work** and **Non-negotiables**, then read `skill://deepmodebot/references/techniques/suggest.md` in full and run **suggest** on the active repository.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Run `python -B "<deepmodebot skill dir>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 8 --ui --json`, verify every gap and overclaim against real files, and return ranked **Hardcore Mode full-scope `/deep ...` prompts** with exact `file:line` receipts plus a link to the `.scratch/gen-ui/suggest/index.html` A2UI v1.0 visual cockpit.

Apply this to what the user asked for.
