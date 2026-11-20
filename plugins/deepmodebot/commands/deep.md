---
description: "One command for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Ordinary local work stays uncommitted for review; publication uses an exact-head verifier gate."
argument-hint: "<anything: a task, a PR number, 'what can I work on', 'start a new app that ...', 'drive the board', 'grill me on ...'>"
---

Read `skill://deepmodebot` and follow its **Route** section first: look around, route by intent and vagueness (concrete tasks run directly, draft plans take **grill**, open architecture/research gaps or vague ambitions take **tournament**), size concrete work, select model/effort/cadence before starting, then execute.
Don't ask which skill, playbook, or approach to use; settle observable questions by running them. In Claude Code, `skill://<name>/<path>` means `<path>` in `${CLAUDE_PLUGIN_ROOT}/skills/<name>/` (plugin install) or `~/.claude/skills/<name>/` (manual install).

Before turn 1, loop 1, or worker kickoff, switch down to the smallest benchmark-proven model tier and `medium` or lower effort for S, search, mechanical, or oracle-backed M work (`skill://agent-harnesses/references/delegation-efficiency.md`). Reserve flagship `L` for planning, hard debugging, security, and final review; skip Fast/Ultrafast modes, batch spawns, and back off or rotate model family on 429s.

Apply **Full-scope completion** before execution and before your final reply. A sample, preview, or first batch is progress, not delivery of the full request; continue remaining actionable work without asking whether to finish.
For complex or questionable domain specs, run **sme-review** (and **questionnaire** for unverified P0/P1 domain rules) before locking a spec, starting a loop, or Sprint 2+. Split multi-PR or customer-facing specs into incremental sprints (Sprint 1 = smallest end-to-end feedback slice) instead of a Big Bang release.

Keep every write inside the project root per **Contain the work**: scratch/temp in `.scratch/`, worktrees in `.worktrees/`, never system temp or outside folders. No repo yet → create a named one first.

Read the matched playbook for M or L tasks; S uses the fast path. Follow its local-delivery or publication path and read only references that change the work. With no remote or a local-review request, ordinary S/M work stays uncommitted in the starting tree; prove it on the real app or CLI and review the diff. Risky work keeps full checks; "open a PR" is publication and needs the exact-head panel.

Reuse an existing project verification skill when present; otherwise exercise the real app or CLI directly and retain its output. Create a reusable verification skill only when requested or justified by repeated runs, never for a one-off local fix. Tests alone are not proof.

Decide and act without asking within the requested delivery target. Publication covers commits, pushes, PRs, and merges on an exact-head panel pass; local delivery never silently publishes. Ask once at the end only for hard stops, or at tournament's proposal gate (and human SME gates on unverified P0/P1 domain rules). Claiming an issue in someone else's repo still needs permission first.

Request: $ARGUMENTS
