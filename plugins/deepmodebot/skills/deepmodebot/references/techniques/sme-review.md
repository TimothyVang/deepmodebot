# sme-review

**Use when:** a customer specification, plan, sprint slice, or goal touches a **complex, regulated, or unfamiliar domain** (finance, healthcare, legal, compliance, industrial, specialized math/physics, proprietary business workflows), or when a specification's domain logic may not make sense as written. Run before locking a spec, before starting an unattended goal loop, and at sprint feedback checkpoints.

Code can be bug-free and match a written spec yet fail in the real world because the customer's specification itself missed a domain invariant. This technique pairs an automated **SME review lens** with a **human SME gate** when domain facts cannot be proven from the repo.

## Two tracks

| Track | When it runs | What it does |
|---|---|---|
| **SME lens** (automated) | Draft specs, goal-loop iterations, sprint demos, and complex-domain PRs | Reviews the spec, diff, or sprint output against `GLOSSARY.md`, `docs/adr/`, domain docs, and real-world domain invariants |
| **Human SME gate** (pause) | When P0/P1 domain questions or customer-spec contradictions cannot be settled from repo docs or a prototype | Pauses before `Tickets`, `Run a goal`, or Sprint 2+ and produces a targeted **questionnaire** (`references/techniques/questionnaire.md`) for the human SME or customer |

An AI SME lens never invents missing business or regulatory rules. Unverified P0/P1 domain assumptions escalate to the human SME gate instead of being guessed.

## Procedure

1. **Assess domain complexity.** Check whether the work relies on domain rules, legal/compliance limits, financial math, safety invariants, or customer workflows that are not self-evident from the codebase. Simple CRUD or purely technical refactors skip this technique and note why.
   Done when domain complexity is marked low (skip with reason) or complex (continue to step 2).
2. **Gather domain ground truth.** Read `GLOSSARY.md`, `docs/adr/`, existing domain tests, and any cited domain docs (`docs/research/`). Separate verified facts from assumptions in the customer spec or goal.
   Done when every domain assumption in the spec or goal is listed as verified (with source) or unverified.
3. **Run the SME lens.** Review the spec, sprint slice, or diff with a fresh `reviewer` (or default `task` agent on another model family when available), using the SME lens prompt below. Check whether the customer's requirements make sense together, not only whether code matches text.
   - **P0 critical:** domain-invalid behavior, unsafe state, regulatory breach, or contradictory requirements that make the workflow impossible.
   - **P1 high:** wrong business invariant, missing domain edge case (reversals, cutoffs, units, roles), or a sprint slice too artificial for an SME to evaluate.
   - **P2 medium:** glossary term drift (`Not:` list violation) or ambiguous domain boundary.
   Done when every SME lens finding is backed by the spec line, code, or domain rule it violates, or "no findings" is recorded.
4. **Gate on human SME when needed.** If any P0/P1 finding rests on external domain rules or unclear customer intent that repo evidence and prototyping cannot settle:
   - Stop before locking the spec, starting an unattended `Run a goal` loop, or launching Sprint 2+.
   - Write a focused **questionnaire** (`references/techniques/questionnaire.md`) with concrete examples, edge-case choices, and what each answer unblocks.
   - When answers return, update `GLOSSARY.md` (`references/techniques/domain-model.md`), `docs/adr/`, and `docs/specs/<slug>.md`, and log a trail row (`references/techniques/show-me-your-work.md`).
   Done when every unverified P0/P1 assumption is either answered by the human SME and recorded in the repo, or logged as an open blocker that holds downstream work.
5. **Re-check at sprint boundaries.** Inside multi-sprint builds or goal loops, rerun steps 3 and 4 at each sprint checkpoint on the live sprint deliverable before starting the next sprint.
   Done when the current sprint's deliverable passes the SME lens and any human SME feedback is folded into the next sprint's tickets or spec.

## SME lens prompt

> You are reviewing <spec / sprint slice / PR> through the **SME (Subject Matter Expert)** lens only. Read-only. Context: `<GLOSSARY.md, docs/adr/, domain docs, spec/diff paths>`.
>
> Evaluate whether the customer specification and implementation make sense in the real domain:
> 1. Do the user stories, state transitions, and Done when items contradict each other or leave impossible domain states?
> 2. What domain invariants or edge cases (units, rounding, cancellations, permissions, compliance, failure recovery) are missing or wrong?
> 3. On mathematical or formal specs (`Challenge.lean`, `.tla`, `.smt2`, formulas), does the formal statement match the natural-language theorem 1-to-1 without semantic drift (quantifier order $\forall\exists$ vs $\exists\forall$, domain/regularity bounds, strict vs weak inequalities, or vacuous truth on empty/zero cases)?
> 4. If this is an incremental sprint slice, can a real SME or customer meaningfully test and give feedback on it?
> 5. Which open questions cannot be answered from the repo and must go to a human SME before building further?
>
> Return each finding with **severity** (P0/P1/P2), **location**, **domain risk** (one sentence), and **how to resolve** (code/doc fix, prototype, or human SME question). Do not guess undocumented domain rules.

## Done when

Every complex-domain assumption is backed by cited repo/domain evidence or answered by a human SME and recorded in the spec, glossary, or ADRs, and all P0/P1 SME lens findings on the current spec or sprint slice are resolved or explicitly blocking further execution.
