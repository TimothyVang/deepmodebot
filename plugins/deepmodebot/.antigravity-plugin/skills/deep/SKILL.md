---
name: deep
description: "Zero-human-thought autopilot (/deep): decodes messy prompts, asks 1-3 upfront choices ONLY when intent is ambiguous, then autonomously runs research, gap-audit, build, gates, and proof."
---

# /deep

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) and run **Route** (`Steps 0-5`). In Antigravity, `skill://<name>/<path>` is `../../../skills/<name>/<path>` (or via `omp_resolve`).

- **0. Decode & 1-shot upfront clarify:** Decode typos, shorthand, URLs, and compound clauses (`prompt_tools.py upgrade` + `clarify`). Never ask facts answerable from the repo or docs. Only when human intent has `2+` materially different product/scope outcomes, call `ask_question` **once upfront** (`1-3` `(Recommended)`-first options; in `-p` headless mode, pick `(Recommended)`). Once clear or answered, finish 100% end-to-end on your own without punting commands or stopping mid-run.
- **1. Auto-chain research, gap-audit & semantic route:** Use the hook-injected **workspace-map** overview (or run `workspace_map.py`), run `autoroute.py menu` → JSON → `autoroute.py verify --strict`, automatically chain **research** / **prior-art** (`gap_audit.py` + `trending.py` + `dmb-net`) and `deepmodebot gate gap` when relevant, and default to **Hardcore Mode**.
- **2. Full-scope build, gates & proof:** Track 100% scope in one manifest on M/L/multi-item work, keep writes in root, pass `deepmodebot gate slop|ui|perf|sec|gap` + real-artifact proof + **self-grill**, leave ordinary local S/M uncommitted, and use Opening a PR + 3-seat panel when publishing.
Apply this to what the user asked for.
