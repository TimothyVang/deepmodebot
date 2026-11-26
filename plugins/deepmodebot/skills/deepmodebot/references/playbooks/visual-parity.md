# Visual Parity

Use when: migrating or reimplementing UI that must stay pixel-identical. You own pixel-exact equivalence; the baseline is the spec and you don't touch it. Equivalence is proven by image diff, not by eye.

## Steps
1. Before any migration, build a visual regression harness that screenshots the current component across its states (plus the target when matching two implementations). Done when the harness produces a baseline image for every state.
2. State the anti-shortcut clauses and hold them: no harness modifications, no baseline tampering, no component restructuring to make a diff pass.
3. Migrate shared primitives first as a blocking phase. Done when every shared primitive is migrated and its diff is zero.
4. Migrate one component at a time; parallelize with `task` agents, one owner per component with exclusive file ownership (`references/principles/separate-before-serializing-shared-state.md`). Done when every component has a migrated version.
5. Verify each component against its baseline by image diff on the matching surface via the repo's `verify-<app>` skill (in `.omp/skills/`, `.claude/skills/`, or `.agents/skills/`); if none, use omp `eval` `browser`, Playwright/CDP, or bash. Nonzero diff → investigate the pixel delta, fix, re-diff; loop per component until zero.
   - For animated components or transitions, record both reference and candidate at matching FPS and run `python -B "<frontend-ui skill>/scripts/motion_diff.py" <ref.mp4> <cand.mp4> --mode pixel` so start/duration timing (`<= 0.08 s`), easing curve (`RMSE <= 0.08`), and rest frames (`<= 0.5%`) match mathematically, not just on a static end frame.
6. Deliver per SKILL.md's delivery-target rule: for local review or a repo with no remote, leave verified S/M edits uncommitted (or on a non-default working branch) with zero-diff proof; for publication, commit per component or safe batch, run **Opening a PR** (`references/playbooks/opening-a-pr.md`), and land through **pr-conversation** or `references/playbooks/shipping.md` on a panel pass. Done when the requested delivery target holds.

## Gates
- No baseline, no parity claim. The baseline is a blocking prerequisite, not a follow-up.
- Baseline looks wrong → stop that comparison and report it with evidence; never edit it.
- Any nonzero diff is a fail.

## Evidence
- Components migrated with each diff result; baseline harness location; what's left.
