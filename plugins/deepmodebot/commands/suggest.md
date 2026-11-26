---
description: "Scan the repo for real gaps, overclaims, missing checks, and debt, and suggest ranked full-scope /deep prompts ready to run"
argument-hint: "[optional focus area, e.g. 'auth', 'docs overclaims', 'tests', or leave blank for full repo]"
---

Read `skill://deepmodebot` (**Contain the work** and **Non-negotiables**) and `skill://deepmodebot/references/techniques/suggest.md` in full, then run **suggest** on the current repository.

Run `python -B "<deepmodebot skill dir>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 8 --ui --json`, verify every candidate gap and overclaim against the real files (drop false positives), and present ranked, copy-paste-ready **Hardcore Mode full-scope `/deep ...` prompts** backed by exact `file:line` evidence alongside the clickable `.scratch/gen-ui/suggest/index.html` A2UI v1.0 visual cockpit.

Focus: $ARGUMENTS
