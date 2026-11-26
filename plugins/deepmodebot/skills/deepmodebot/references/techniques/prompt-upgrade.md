# prompt-upgrade

**Use when:** a user prompt is terse, messy, typo-heavy, vague, or bundles multiple unnumbered asks ("review my prompt", "improve my prompt", "convert to a deepmode prompt", "fix my prompt"), OR automatically in **Route** step 2 before executing any underspecified prompt so deepmodebot never misinterprets intent or drops scope.

Users naturally type fast shorthand. Never take a sloppy prompt literally into a shallow fix or guess silently past missing requirements.

## Procedure

1. **Inspect repo reality first.** Read the relevant paths, recent `git status`/`git diff`, and available checks/verify skills so intent is grounded in actual files instead of guesswork.
   Done when the real files and checks touched by the user's request are identified.
2. **Compile the full-scope Deepmode prompt.** Pipe the raw prompt through the deterministic upgrader:
   ```bash
   python -B "<this installed skill>/assets/prompt-tools/prompt_tools.py" upgrade --stdin --root "<project-root>" --json <<'EOF'
   <raw user prompt>
   EOF
   ```
  Review the flagged weaknesses (`shorthand_or_vague`, `multi_part_unnumbered`, `missing_acceptance_oracle`, `missing_gap_overclaim_check`, `watered_down_or_optional_hardcore`) and sharpen the compiled prompt so it states:
  - **Hardcore Mode by default (`references/principles/hardcore-mode.md`):** aim for the true first-principles architectural ceiling (real algorithms, parallel/async execution, solvers, crisp native representations/LODs, full end-to-end integration). Automatically promote any "(Optional hardcore mode)" or "bonus" technical tier into a mandatory numbered deliverable unless the user explicitly asks for a throwaway prototype or minimal patch.
  - **Decoded intent & numbered full-scope deliverables:** every explicit and implied part numbered; never shrink or drop compound clauses ("X also Y also Z").
  - **Repo grounding & containment:** exact files/surfaces to inspect first; root-only writes (`references/contain.md`).
  - **Gap & overclaim check:** verify every claim, count, and "works/passes" statement against current files or fresh runs; hunt for missing edge cases, unbacked docs/claims, and silent gaps.
  - **Real-artifact verification & self-grill gate:** exact failing-without-fix test or real-app run after final edits, `self_grill.py check-diff` (including `hardcore-craft-depth` anti-toy check), and `no-comments` cleanup.
  - **Reversible assumptions vs hard stops:** resolve reversible ambiguity from repo evidence and state assumptions; pause only on real hard stops or irreversible forks.
   Done when the full-scope prompt covers every deliverable, names its verification oracle, and includes the gap and overclaim check.
3. **Execute or return.**
   - **Default (action request):** execute the upgraded full-scope prompt immediately without waiting for confirmation; mirror its numbered deliverables in the scope ledger.
   - **Prompt-only mode** (the user asked to review, rewrite, or improve a prompt without running it): print the weaknesses caught, the decoded intent, and the ready-to-run full-scope `/deep ...` prompt.
   Done when execution has started on the full-scope prompt, or the ready-to-run upgraded prompt is delivered in prompt-only mode.

**Done when** every implied deliverable is captured in a full-scope prompt with a real-artifact oracle and gap/overclaim audit, and either executed or returned ready to run.
