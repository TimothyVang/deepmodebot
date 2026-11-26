# modernize-pr

**Use when:** evaluating an aging or stalled PR/branch ("modernize this PR", "revive this old branch", "is this PR still worth landing?") that has drifted behind `main` before spending tokens blindly rebasing merge conflicts.

1. **Extract original intent & proof.** Read the PR description, linked issue, review history, and `git diff $(git merge-base origin/main <branch>)..<branch>` to list the exact problem the PR solved and what tests/evidence it originally carried.
2. **Measure trunk drift across 3 axes.** Compare `merge-base..origin/main` on touched subsystems:
   - **Already solved or superseded:** trunk fixed the bug or shipped a cleaner replacement;
   - **Architectural shift:** touched modules were refactored, moved, or replaced (`git log -M --stat merge-base..origin/main -- <paths>`), making mechanical conflict resolution wrong;
   - **Cleanly rebaseable:** trunk changes are orthogonal or localized.
3. **Render an explicit 3-way verdict before editing:**
   - **`MODERNIZE`:** intent still holds and design fits current trunk → rebase/merge onto `origin/main` in an isolated worktree, adapt to current types/conventions, run full checks + real-app proof, and route to `babysit` / **pr-review**.
   - **`SALVAGE-SLICE`:** problem still matters, but the PR's implementation targets obsolete architecture → extract the valid test cases/domain insights and rebuild cleanly from `origin/main` via `feature` or `bug-fix` instead of fighting stale conflicts.
   - **`CLOSE`:** trunk superseded it or product direction dropped it → cite the exact trunk commits/PRs that obsoleted it and recommend closing without code churn.

**Done when** original intent and trunk drift are cited by commit/file, one explicit verdict (`MODERNIZE`, `SALVAGE-SLICE`, or `CLOSE`) is backed by diff evidence, and (when `MODERNIZE` or `SALVAGE-SLICE` applies) the updated branch passes current trunk checks and runtime proof.
