---
description: "One command for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Ordinary local work stays uncommitted for review; publication uses an exact-head verifier gate."
argument-hint: "<anything: a task, a PR number, 'what can I work on', 'start a new app that ...', 'drive the board', 'grill me on ...'>"
---

Read `skill://deepmodebot` and follow **Route** first; settle observable questions by running them. In Claude Code, `skill://<name>/<path>` is `${CLAUDE_PLUGIN_ROOT}/skills/<name>/<path>` (or `~/.claude/skills/<name>/<path>`).

- **Orient automatically:** In git repos, run `python -B "<deepmodebot skill>/assets/workspace-map/workspace_map.py" overview --fast --offline --no-orca` (`py -3 -B` on Windows), then `query`/`workspaces`/`prs` before wide scans.
- **Scope, tier & proof:** Pick the smallest tier/effort before turn 1, track 100% scope in one manifest, keep writes in root (`.scratch/`, `.worktrees/`), leave local S/M uncommitted with real-artifact proof, and use the 3-reviewer panel to publish.

Request: $ARGUMENTS
