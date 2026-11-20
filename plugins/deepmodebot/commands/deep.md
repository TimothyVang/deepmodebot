---
description: "One command for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Ordinary local work stays uncommitted for review; publication uses an exact-head verifier gate."
argument-hint: "<anything: a task, a PR number, 'what can I work on', 'start a new app that ...', 'drive the board', 'grill me on ...'>"
---

Read `skill://deepmodebot` and follow **Route** first; settle observable questions by running them. Let `<deepmodebot skill>` be the disk directory `skill://deepmodebot` resolves to (in Claude Code: `${CLAUDE_PLUGIN_ROOT}/skills/deepmodebot` for a plugin install, `${CLAUDE_PROJECT_DIR:-.}/.claude/skills/deepmodebot` project-local, or `~/.claude/skills/deepmodebot` user-level).

- **Orient automatically:** In git repos, run `python -B "<deepmodebot skill>/assets/workspace-map/workspace_map.py" overview --fast --offline --no-orca` (`py -3 -B` on Windows), then `query`/`workspaces`/`prs` before wide scans; on strictly read-only routes (`investigation`, local `pr-review`, `pr-thread`), skip `overview` when no `.scratch/workspace-map.db` exists.
- **Scope, tier & proof:** Pick the smallest tier/effort before turn 1, track 100% scope in one manifest on M/L/multi-item work (Size S inline), keep writes in root (`.scratch/`, `.worktrees/`), leave ordinary local S/M edits uncommitted with real-artifact proof, and use Opening a PR + the 3-reviewer panel to publish.

Request: $ARGUMENTS
