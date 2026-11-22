---
name: deep
description: "One command (/deep) for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Use when invoked via /deep."
---

# /deep

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) and follow **Route** first. In Antigravity, `skill://<name>/<path>` is `../../../skills/<name>/<path>` (or via `omp_resolve`).

- **Orient & route semantically:** Use the hook-injected fast offline git-only **workspace-map** overview if present (else `workspace_map.py overview --fast --offline --no-orca`, skipped on read-only routes without a DB), then run the 3-stage LLM semantic router (`assets/autoroute/autoroute.py menu` → LLM JSON decision → `autoroute.py verify --strict`), default to **Hardcore Mode**, and run **self-grill** before reporting done.
- **Scope, tier & proof:** Pick the smallest tier/effort before turn 1, track 100% scope in one manifest on M/L/multi-item work (Size S inline; `loop.py run` targets `omp|claude|codex`; `manifest`/`audit`/`check`/`status` work anywhere), keep writes in root, leave ordinary local S/M uncommitted with real-artifact proof, and use Opening a PR + the 3-reviewer panel to publish.

Apply this to what the user asked for.
