---
name: deep
description: "One command (/deep) for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Use when invoked via /deep."
---

# /deep

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) and follow its **Route** section first: look around, auto-route by intent and vagueness (concrete tasks run directly; draft plans take **grill**; open architecture/research gaps or high-vagueness ambitions take **tournament**), size concrete work, select model/effort/cadence before starting, then execute.
Don't ask which skill, playbook, or approach to use; answer observable questions by running them.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/` for a global plugin install, or via `omp_resolve`).

Before turn 1, loop 1, or worker kickoff, switch down to the smallest benchmark-proven model tier and `medium` or lower effort for S, search, mechanical, or oracle-backed M work (`skill://agent-harnesses/references/delegation-efficiency.md`). Reserve flagship `L` for planning, hard debugging, security, and final review; skip Fast/Ultrafast modes, batch spawns, and back off or rotate model family on 429s.

Apply **Full-scope completion** before execution and before your final reply. A sample, preview, or first batch is progress, not delivery; continue remaining actionable items without asking whether to finish.
For complex or questionable domain specs, run **sme-review** (and **questionnaire** for unverified P0/P1 domain rules) before locking a spec, starting a loop, or Sprint 2+. Split multi-PR or customer-facing specs into incremental sprints (Sprint 1 = smallest end-to-end feedback slice) instead of a Big Bang release.

Keep every write inside the project root per **Contain the work**: scratch and temp files in `.scratch/`, worktrees in `.worktrees/`, never system temp or folders outside the repo.
No repo yet → create a named one first.

Read the matched playbook for M or L tasks; S uses the fast path.
Follow its local-delivery or publication path and read only references that change the work.
With no remote or a local-review request, ordinary S/M work stays uncommitted in the starting tree.
Prove it through the real app or CLI and review the diff. Risky work keeps full checks. "Open a PR, I'll review it" is publication and needs the exact-head panel.

Reuse an existing project verification skill when present (`.agents/skills/verify-<app>/`, `.omp/skills/verify-<app>/`, or `.claude/skills/verify-<app>/`).
Otherwise exercise the real app or CLI directly and retain its output.
Create a reusable verification skill only when the user asks for one or repeated journeys justify it, never as a prerequisite for a one-off local task. Do not replace runtime proof with unit tests alone.

Decide and act without asking within the requested delivery target.
Publication includes commits, pushes, PRs, and merges on an exact-head panel pass. Local delivery does not silently become publication.
Ask once at the end only for hard stops, at tournament's proposal gate, or at a human SME gate on unverified P0/P1 domain rules. Claiming an issue in someone else's project still needs permission before starting.

Apply this to what the user asked for.
