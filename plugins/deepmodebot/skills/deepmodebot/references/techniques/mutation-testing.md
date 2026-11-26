# mutation-testing

**Use when:** line/branch coverage looks high (`90%+`) yet bugs still slip through, when auditing test quality ("check theater"), or when hardening parsers, state machines, billing, crypto, or concurrency logic with property-based/fuzz tests.

1. **Pick high-consequence targets.** Scope to modules where a silent wrong answer corrupts state, money, auth, or safety—never waste mutation cycles on trivial getters or generated glue.
2. **Generate semantic mutants (isolated in `.scratch/`).** Use a language runner (`mutmut`, `cargo-mutants`, `Stryker`, `go-mutesting`) or apply 5–10 targeted high-value mutations in an isolated `.scratch/` copy (never mutating uncommitted user edits in place):
   - Boundary flips (`<` ↔ `<=`, `==` ↔ `!=`, off-by-one slice bounds);
   - Guard deletion (drop authz/tenant check, idempotency check, or rollback branch);
   - State/order swaps (reorder lock/write steps, return cached/empty value early).
3. **Run the existing test suite per mutant.** Classify each as **killed** (a test failed for the right behavioral reason), **survived** (tests stayed green—check theater exposed!), or **equivalent** (observable behavior unchanged).
4. **Kill surviving mutants with behavioral + property-based tests.** Replace tautological/mock-heavy assertions with observable behavior checks (`references/principles/test-behavior-not-implementation.md`) and add shrinkable property-based invariants (`Hypothesis`, `fast-check`, `proptest`) or coverage-guided fuzz harnesses (`cargo-fuzz`, `atheris`, `libFuzzer`) asserting round-trip, idempotence, conservation, or crash-freedom across generated inputs.

**Done when** baseline and post-hardening mutant survival counts are measured on an isolated copy, every non-equivalent surviving mutant in critical paths is killed by a real behavioral or property-based test, and the working tree has zero leftover mutations.
