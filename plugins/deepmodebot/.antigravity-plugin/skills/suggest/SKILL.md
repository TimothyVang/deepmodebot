---
name: suggest
description: "Scan the repo (/suggest) for real gaps, overclaims, missing tests, lying comments, and workaround smells, then suggest ranked full-scope /deep prompts backed by file:line evidence. Use when invoked via /suggest or when the user asks for prompt suggestions or a gap/overclaim audit."
---

# /suggest

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) for **Contain the work** and **Non-negotiables**, then read `skill://deepmodebot/references/techniques/suggest.md` in full and run **suggest** on the active repository.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Run `python -B "<deepmodebot skill dir>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 8 --ui --json`, verify every gap and overclaim against real files, and return ranked **Hardcore Mode full-scope `/deep ...` prompts** with exact `file:line` receipts plus a link to the `.scratch/gen-ui/suggest/index.html` A2UI v1.0 visual cockpit.

Apply this to what the user asked for.
