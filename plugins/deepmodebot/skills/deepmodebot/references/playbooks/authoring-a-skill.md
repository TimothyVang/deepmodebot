# Authoring a Skill

Use when: creating or modifying a skill (`SKILL.md` plus references). You own the skill's voice.

## Steps

1. Read the **writing-for-agents** technique (`references/techniques/writing-for-agents.md`) before writing. Done when you have read it end to end in this session.
2. Before adding prose, check the ladder: can architecture/data structures prevent the mistake? Then a lint rule or test? Only then a skill/rule; human review last (`references/principles/encode-lessons-in-structure.md`).
   Done when each new rule names its rung (structure, lint, test, or prose) and why no lower rung fits.
3. Write or edit the skill:
   - When in doubt, delete. Keep only prose that changes a decision.
   - Tell it to do the thing; skip the reason unless the rule is confusing without one.
   - Match tone to scope.
   - Point at structural sources (types, READMEs, config) instead of restating them.
   - Delegate to other skills by path; don't restate them.
   - Route on the request's wording. A file in the repo is evidence for a route, never its trigger, or unrelated work in that repo gets captured.
   - One owner per trigger: search every installed skill's description and the router's rows for the new trigger words, and narrow the ones that lose.
   - Done when the edit is saved and the trigger search shows no other skill or router row claiming the new trigger words.
4. Validate: `python -B "<deepmodebot skill dir>/scripts/check_skill.py" <skill dir>` (`py -3 -B` on Windows) prints `ok`. It verifies frontmatter `name` and `description`, `references/` and `scripts/` links (`.md/.py/.sh/.json/.txt`), and `skill://<name>/<file>` paths for installed skills; missing external `skill://` targets print as notes (when `omp` is installed) and do not fail exit 0, and `assets/` paths must be spot-checked separately.
5. Structural skill (routing, gates, scripts) → write test cases; subjective skill → skip. A routing change is tested with fresh read-only `scout` agents given only the request: one per new route, plus one near-miss that must not match. Each answers with the skill, playbook, and the table row that decided it.
   Done when every route scout names the intended row and the near-miss scout does not, or the skill is recorded as subjective.
6. Repeatedly-hit workflow not captured anywhere → propose a new skill. Done when each such workflow is listed in the report as a proposal, or the report says there were none.
7. Deliver per SKILL.md's delivery-target rule: for local review or a repo with no remote, leave verified S/M edits uncommitted in the working tree and report proof; for publication, run **Opening a PR** (`references/playbooks/opening-a-pr.md`). Done when the requested delivery target holds.

## Gates

- Skill folder outside git → archive it (`tar -czf`) before the first edit, and name the archive in the report.
- Validation (step 4) must pass before reporting done.
- A rule that a lint, type, or test could enforce goes there instead of prose.

## Evidence

- Summary of the skill.
- Key design decisions.
- Validation notes: frontmatter check, referenced files, link resolution, test cases run or why skipped.
