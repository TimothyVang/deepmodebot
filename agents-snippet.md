## Rigor

For large or risky work (multi-file features, migrations, perf work, multi-PR work, autonomous or overnight runs), or when I say "Deepmodebot", read `skill://deepmodebot` (or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md` in Antigravity) and follow it.
Invoke with `/deepmodebot:deep <task>` in omp/Claude Code, `/deep <task>` in Antigravity, or `$deepmodebot:deepmodebot <task>` in Codex. Skip it for ordinary small tasks.

- **Full-scope completion:** Keep 100% of deliverables and inventory in one Scope Manifest (`loop.py manifest`). Single-run builds finish `1/N` to `N/N`; incremental sprints or complex-domain SME gates pause only at the explicit checkpoint and report remaining sprints as incomplete.
- **Model & SME discipline:** Pick the smallest benchmark-proven model tier and effort before turn 1 or worker kickoff (`skill://agent-harnesses/references/delegation-efficiency.md`). Run **sme-review** before locking specs, starting loops, or advancing past Sprint 1 in complex or regulated domains.
- **Automatic workspace map:** In any git repo, orient via Antigravity's hook-injected overview or `python -B "<deepmodebot skill>/assets/workspace-map/workspace_map.py" overview --fast --offline --no-orca` (`py -3 -B` on Windows), and run `query`/`workspaces`/`prs` before wide scans; never ask the user to run manual map commands.

## Verification

A behavior change is done only when proven on the running app. Passing tests are not proof.

- If the repo has a verify skill (`.omp/skills/verify-*/`, `.claude/skills/verify-*/`, or `.agents/skills/verify-*/` for Antigravity and Codex), use it. Read its `SKILL.md` and matching `features/` file before launching, driving, or debugging, and run its `doctor` first.
- If none exists and the task changes user-visible behavior, prove the change by running the real app or CLI directly; offer `create-verification-skill` once if repeated journeys justify one.
- Report evidence: commands run, screenshots or snapshots, observed end state. "Fixed" without artifacts is not done.
- When you change a user-facing feature, update its feature-map file in the same change.
- When an agent repeats the same mistake, prefer a lint rule, type, or test over another line in this file.
