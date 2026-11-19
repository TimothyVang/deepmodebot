---
description: "One command for fixing, building, reviewing, planning and shipping. deepmodebot routes and sizes the task, proves it on the real artifact, and reports. Ordinary local work stays uncommitted for review; publication uses an exact-head verifier gate."
argument-hint: "<anything: a task, a PR number, 'what can I work on', 'start a new app that ...', 'drive the board', 'grill me on ...'>"
---

Read `skill://deepmodebot` and follow its **Route** section first: look around, route by intent and vagueness (concrete tasks run directly, draft plans take **grill**, open architecture/research gaps or vague ambitions take **tournament**), size concrete work, select model/effort/cadence before starting, then execute.
Don't ask me which skill, playbook, or approach to use; settle observable questions by running them. In Claude Code, `skill://<name>/<path>` means `<path>` in `${CLAUDE_PLUGIN_ROOT}/skills/<name>/` (plugin install) or `~/.claude/skills/<name>/` (manual install).

Before turn 1, loop 1, or worker kickoff, switch down to the smallest benchmark-proven model tier and `medium` or lower effort for S, search, mechanical, or oracle-backed M work (`skill://agent-harnesses/references/delegation-efficiency.md`). Reserve flagship `L` for planning, hard debugging, security, and final review; skip Fast/Ultrafast modes, batch spawns, and back off or rotate model family on 429s.

Apply **Full-scope completion** before execution and before your final reply. Keep 100% of Total Scope in one machine-checked Scope Manifest (`loop.py manifest`); classify "all/every/full set" candidates in `"inventory"` (zero unclassified `pending` items). Slicing never shrinks scope: single-run builds drive `1/N` to `N/N` without stopping early.
In incremental Sprint mode or complex/questionable domains (`active_sprint: 1` or `sme_gate: "required"`), run **sme-review** (and **questionnaire** for unverified P0/P1 rules), land Sprint 1 with verified proof, and pause ONLY at the explicit sprint/SME checkpoint. Sprint 2..N stay explicitly queued/deferred in the manifest (`scope_complete: false`) and are reported as remaining scope (incomplete, never done). On quota/cost cap, sprint checkpoint (`exit 6`), or SME gate, the manifest + `latest-summary.json` is the exact zero-loss resume ledger.

Keep every write inside the project root per **Contain the work**: scratch/temp in `.scratch/`, worktrees in `.worktrees/`, never system temp or outside folders. No repo yet → create a named one first.

Read the matched playbook for M or L tasks; S uses the fast path. Follow its local-delivery or publication path and read only references that change the work. With no remote or a local-review request, ordinary S/M work stays uncommitted in the starting tree; prove it on the real app or CLI and review the diff. Risky work keeps full checks; "open a PR" is publication and needs the 3-reviewer exact-head panel.

Reuse an existing project verification skill when present; otherwise exercise the real app or CLI directly and retain its output. Create a reusable verification skill only when requested or justified by repeated runs, never for a one-off local fix. Tests alone are not proof.

Decide and act without asking within the requested delivery target. Publication covers commits, pushes, PRs, and merges on an exact-head panel pass; local delivery never silently publishes. Ask once at the end only for hard stops, at tournament's discovery-only or explicitly requested proposal gate, or at a human SME gate on unverified P0/P1 domain rules. An original build request continues with Champion after the proposal. Claiming an issue in someone else's repo still needs permission first.

Request: $ARGUMENTS
