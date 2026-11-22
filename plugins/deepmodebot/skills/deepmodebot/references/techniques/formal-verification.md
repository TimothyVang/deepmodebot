# formal-verification

**Use when:** concurrency races, retries, multi-device sync, state machines, parsers, custom algorithms, mathematical proofs, Lean/Coq/TLA+/SMT formalizations, or UI invariants where unit tests miss breaking orders or edge cases ("formal verification", "model-check", "TLA+", "statechart", "Lean proof", "Comparator", "prove this theorem/invariant", "property-based UI", "Bombadil"). Formal checks complement runtime verification; they are not a silver bullet.

## Choose the target, falsify early, and decompose

1. **Pick the highest-risk invariant or theorem.** State the property/claim and its failure harm in one plain sentence each.
   Done when the target files, symbols, invariant/theorem sentence, and failure harm are written down.
2. **Falsify on small cases first ("Checking beats believing").** Before spending proof search or TLA+/Lean cycles, run a quick Python (`sympy`, exact `Fraction`/`int`, or property-based `Plausible`) probe over $n=0,1,2,3,4$, degenerate inputs, and sign/equality boundaries to catch false subgoals in seconds (`alphabeta` guard).
   Done when small-$n$ / boundary falsification passes or refutes the conjecture upfront.
3. **Let the question pick the tool (backed by `assets/formal-verification/verify_proof.py`):**
   - **Event/step order or distributed state** → **TLA+ / TLC** over a faithful model, plus a user-POV **Mermaid statechart** (max 6 boxes per view, marking broken rules and shortest path).
   - **Mathematical theorem or algorithmic property at every size** → **Lean 4** (`lake build` + `#print axioms` restricted to `[propext, Classical.choice, Quot.sound]`), **Coq/Rocq**, or **Z3/SMT**, verified with `verify_proof.py audit-static`.
   - **Multi-lemma proof or multi-module invariant** → initialize a **Claim-DAG ledger** (`verify_proof.py dag init`), prove tractable `ready_leaves` first, and discharge temporary `sorry` stubs bottom-up (`Prove2Me` / `Fable 5.2` pattern).
   - **UI state invariants under arbitrary interaction** → property-based UI explorer (**Bombadil** `always(...)` invariants over real browser state).
   - **No formal kernel fits** → run generated/exhaustive Python checks via `verify_proof.py able-to-fail --script <verify.py>`, never a detached toy model.
   Done when the tool, exact command, and scope bounds/assumptions are named.

## Rules that keep verification honest

- **Statement Alignment & `Challenge.lean` isolation.** Lean compilation proves internal consistency of the *formalized* file, not alignment with prose:
  - Keep target statements immutable in `Challenge.lean` with `formalization.yaml` mapping every hypothesis and quantifier ($\forall\exists$ vs $\exists\forall$, regularity bounds), and run **sme-review** (`references/techniques/sme-review.md`) against the prose spec.
  - Run `verify_proof.py audit-static --challenge Challenge.lean --solution Solution.lean` (`Comparator` gate: zero `sorry`, `admit`, custom `axiom`, `native_decide`, or `[extern]`).
- **Proven able to fail.** A check never seen failing proves nothing. Enforce `verify_proof.py able-to-fail` (`--mutate` breaks a bound, sign, or guard and must exit non-zero) and keep `.scratch/formal-verification/<slug>-receipt.json`.
- **Dual audit for informal lemmas.** In mixed or informal proofs (`dag update`), never mark a lemma proved without either kernel verification (`kernel_verified`) or two independent line-by-line auditor passes (`proved_dual_verified`, `Siege` rule).
- **Never weaken a property to pass, and replay every counterexample.** Report counterexamples in plain terms and replay each trace against real code.
- **Separate model drift from code bugs, and respect hard stops.** Record covered files + **sync commit SHA**; passing a proof verifies only within stated bounds and never waives one-way-door hard stops.

## Output

Plain-English invariant/theorem and harm, tool and bounds/assumptions, statement-alignment + static-escape check, `able-to-fail` receipt, run output (or Claim-DAG ledger), counterexample replay, and covered files + sync SHA.

**Done when** `verify_proof.py` passed (`audit-static` clean and `able-to-fail` proven), every counterexample was replayed (or zero violations found within stated bounds), and covered files plus sync SHA are recorded.
