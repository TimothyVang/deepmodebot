---
name: deep
description: "Zero-human-thought autopilot (/deep): decodes messy prompts, asks 1-3 upfront choices ONLY when intent is ambiguous, then autonomously runs research, gap-audit, build, gates, and proof."
---

# /deep

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) and run **Route** (`Steps 0-5`). In Antigravity, `skill://<name>/<path>` is `../../../skills/<name>/<path>` (or via `omp_resolve`).

- **0. Confirm intent first:** Apply the main skill’s Route Step 0 before prompt upgrades, routing, or execution. Carry its intent statement into the chosen workflow.
- **1. Auto-chain research, full-scope leverage map & semantic route:** Use the hook-injected **workspace-map** overview (or run `workspace_map.py`), run `autoroute.py menu` → JSON → `autoroute.py verify --strict`, automatically chain **research** / **prior-art** (`gap_audit.py` + `trending.py` + `dmb-net`) and `prompt_tools.py suggest --root "<root>" --limit 0` (`deepmodebot gate gap`) so open/audit goals reveal **100% of verified high-leverage tasks** across all subsystems (never capped at 1–3), and default to **Hardcore Mode**.
- **2. Full-scope build, gates & proof:** Track 100% scope in one manifest on M/L/multi-item work, keep writes in root, pass `deepmodebot gate slop|reward|ui|perf|sec|gap` + anti-reward-hacking provenance/judge checks + real-artifact proof + **self-grill**, leave ordinary local S/M uncommitted, and use Opening a PR + 3-seat panel when publishing.
Apply this to what the user asked for.
