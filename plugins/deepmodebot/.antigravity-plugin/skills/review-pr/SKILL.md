---
name: review-pr
description: "Review a PR the deepmodebot way: parallel reviewer subagents, findings verified against the code, one comment-only review (asks first on someone else's repo). Use when invoked via /review-pr."
---

# /review-pr

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md` for **Contain the work**, **Autonomy**, **Secrets**, and subscription rules) and `skill://deepmodebot/references/techniques/pr-review.md` (`../../../skills/deepmodebot/references/techniques/pr-review.md`) in full, then follow them to review the requested PR in PR mode on this repo.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Run every step yourself, including the parallel `reviewer` subagents (`invoke_subagent`, or `omp_task` when using the `omp` MCP server) and the verification checks.
Don't ask which lenses or models to use.
Post the review as a comment on the user's repo's PR without asking; on someone else's repo, show the body and ask first.
Never approve or request changes. Fix-ups and merges follow deepmodebot's Autonomy section: merge only on a panel pass.

Apply this to the PR number or URL the user specified.
