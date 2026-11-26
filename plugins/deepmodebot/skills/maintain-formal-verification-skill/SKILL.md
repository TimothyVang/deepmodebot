---
name: maintain-formal-verification-skill
description: "Bring a project's formal verification back in line with the code after the code changes: find the commits that touched verified code, update the model, harness, or properties to describe the code as it is now, rerun, and say whether each failure is drift in the verification or a bug in the code. Use for /maintain-formal-verification-skill, \"is the model still true to the code\", or after merges and refactors that touched verified code without rechecking it."
---

# Maintain a formal verification skill

A formal check proves a property of what it describes. When the code changes and the verification does not, the check can keep passing while it describes code that no longer exists. That pass is the dangerous case, because it looks like a proof.
This skill is the upkeep loop for a verify skill that `skill://create-formal-verification-skill` (`../create-formal-verification-skill/SKILL.md`) generated, or for any project-local skill that runs a model checker, prover, or code-level verifier against named code.
The project-local skill handles a change that an agent makes while using that skill; this skill handles changes that skipped it across merges, refactors, and multi-commit drift.

Search the current harness's project skill directory: `.omp/skills/`, `.claude/skills/`, or `.agents/skills/` (Antigravity and Codex).
Preserve its existing discovery path and name. Keep evidence and mutation copies under ignored `.scratch/`.
Use `skill://statechart` (`../statechart/SKILL.md`) to read TLA+ outcomes; use `skill://maintain-verification-skill` (`../maintain-verification-skill/SKILL.md`) for empirical application verification.

## Outcomes

Give each check one outcome, and say which:

- **in sync**: no change since the last sync alters what the check describes, and the check passes.
- **updated**: the code changed, the verification now describes the new code, and the check passes.
- **bug**: the verification describes the current code, and the code breaks the property. This is a finding about the code. It is not drift.
- **blocked**: the check could not be brought back in line or could not run. Say exactly why.

A check can be both updated and bug: the update makes the verification describe the code again, and then the property fails on it.

## Edit scope

Edit only the verification: models, harnesses, property files, and the verify skill itself. Never edit product code during a run, unless the user asks you to. When a property fails on the current code, do not weaken the property or the model to make it pass. Report the failure.

## Pass

1. **Find the checks.** Find each project skill that runs a model checker, prover, or code verifier against named code (or the one the user named).
   Collect its property, covered code, bounds and assumptions, run command, and last sync commit. If no verify skill exists, stop and point at `/create-formal-verification-skill`. If it records no sync commit, use the last commit that changed the verification files and say so.
2. **Run it as it is.** Run each check once before changing anything and record the result. A pass here says only that the old description holds; a failure can be drift or a bug until step 5.
3. **Read every change to covered code.** Diff covered files from the sync commit to `HEAD`, read each commit message, and include uncommitted changes separately (a commit ID cannot identify dirty content).
   Track renamed, split, or moved covered functions plus new code touching guarded state. Classify each change against the model/harness:
   - **No effect:** formatting, comments, or uncovered paths that alter nothing the verification describes.
   - **The verification no longer describes the code:** split actions, added/removed branches, moved checks, new paths to guarded state, or changed value ranges. The model or harness must change.
   - **The promise changed on purpose:** intended behavior change backed by doc comments, tests, changelog, or commit messages. Update the property and cite that evidence.
   - **The promise may be broken:** behavior changed with no evidence the promise changed. Treat a resulting failure as a bug candidate.
4. **Update from the code, not from the result.** Update the model or harness so each changed part points to openable code and preserves indivisible code steps, before rerunning and without shaping it to pass.
   Change a property only when the promise changed on purpose, recording old wording, new wording, and cited evidence. Keep bounds unless invalid; report any reduced bound.
5. **Rerun and judge each result.**
   - **Pass:** break the new code the way the property guards against (removing a new check or reordering a step) inside an isolated `.scratch/` copy or worktree, confirm the check catches it, then remove only the scratch mutation without touching user edits.
   - **Fail:** replay the counterexample against the real code step by step. If any step cannot happen in code, fix the verification and state what was wrong.
     If every step can happen, report a bug: the introducing commit, the counterexample in the code's words, one-sentence harm, and an uncommitted reproduction if cheap.
6. **Update the verify skill.** Refresh covered files, commands, bounds, assumptions, and sync commit (recording dirty-tree diffs explicitly; never advance sync commit on a blocked check). Follow the updated verify skill once cold to confirm its steps run.

## Report

Tell the user, for each check:

- the outcome, and the commits that you read;
- what changed in the verification and why, with a short reason for each change: the code changed shape, or the promise changed on purpose (with the evidence);
- the rerun result, and the break that you used to show the updated check can still fail;
- each bug, in plain words: the counterexample as steps in the code's words, the harm, and the commit that introduced it;
- what the verification still does not cover, including new code that it should cover and does not.

Say outright which failures were drift in the verification and which were bugs in the code. For a check that passed before you updated it and fails after, say that the old pass was on a stale description.

Put the verification updates in a change of their own, separate from any product fix.

## Done when

Every discovered check has an outcome, current coverage, bounds, assumptions, and reproducible evidence.
Updated checks still catch a deliberate break; real failures remain findings, and blocked checks keep their prior sync commit.
Verification changes are separate from product fixes, with no unrelated working-tree edits removed.
