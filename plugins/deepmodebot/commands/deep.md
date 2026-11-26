---
description: "Zero-human-thought autopilot (/deep): decodes messy prompts, asks 1-3 clarifying choices upfront ONLY when human intent is genuinely ambiguous, then autonomously chains SOTA research, gap-audit, Hardcore Mode build, gates, real-app proof, and self-grill."
argument-hint: "<raw human thought, bug, URL/org, feature, PR, or messy multi-part goal>"
---

Read `skill://deepmodebot` and run the **Zero-Human-Thought Autopilot** (`Route` Steps `0-5`). Let `<deepmodebot skill>` be the disk directory `skill://deepmodebot` resolves to (`${CLAUDE_PLUGIN_ROOT}/skills/deepmodebot` in Claude Code plugin installs).

- **0. Decode & 1-shot upfront clarify:** Decode shorthand/typos/compound clauses (`prompt_tools.py upgrade` + `clarify`). Never ask facts you can inspect in the repo, git, or docs. If human intent has `2+` materially different product/scope interpretations, ask **once upfront** (`1-3` `(Recommended)`-first choices via `AskUserQuestion` in Claude Code or `ask` in `omp`; in `-p` headless mode, pick `(Recommended)` and log it). Once clear or answered, run 100% end-to-end with zero mid-run hand-holding.
- **1. Auto-chain research, full-scope leverage map & semantic route:** Orient via `workspace_map.py`, route semantically (`autoroute.py menu` → JSON → `autoroute.py verify --strict`), automatically chain adversarial SOTA **research** / **prior-art** (`gap_audit.py` + `trending.py` + `dmb-net`) and `prompt_tools.py suggest --root "<root>" --limit 0` (`deepmodebot gate gap`) so open/audit goals surface **100% of verified high-leverage tasks** across all subsystems (`Wave 1 P0` / `Wave 2 P1` / `Wave 3 P2`, never capped at 1–3), and default to **Hardcore Mode**.
- **2. Full-scope build, gates & proof:** Track 100% scope in one manifest on M/L/multi-item work, keep writes inside root, pass `deepmodebot gate slop|reward|ui|perf|sec|gap` + anti-reward-hacking provenance/judge checks + real-artifact proof + **self-grill**, leave ordinary local S/M edits uncommitted, and use Opening a PR + the 3-seat verifier panel when publishing.
Request: $ARGUMENTS
