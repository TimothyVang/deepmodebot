# Refactoring

Use when: changing structure while behavior stays fixed, including a language port. You own the contract. Not Feature (adds behavior) or Bug fix (corrects it). Language ports use their dedicated steps below; structural refactors use the general sequence. Other large or cross-cutting structural work → the **figure-it-out** technique (`references/techniques/figure-it-out.md`).

## Language ports

Use the two accounts in `references/rust-migration-case-studies.md` as evidence, not a mandate to choose Rust or one cutover strategy.

1. **Freeze the oracle & record `cases.jsonl`.** Pin the source revision, run consumer tests, and record real `(args, stdin, env, stdout, stderr, exit/return)` tuples from the unchanged runtime into a read-only `cases.jsonl` corpus (disable parser recursion caps such as `serde_json`'s 128-depth limit so deep AST/config trees record intact). Keep fixtures, schemas, and thresholds outside implementers' write scope. Done when baseline commands, `cases.jsonl`, and protected paths are recorded.
2. **Inventory behavior via one shared bridge-eligibility check.** Map each public entrypoint, callback, I/O path, state owner, cancellation/disposal pair, and packaging target to its destination and proof. Planner (`analyze`), profiler, and FFI bridge generator must share one eligibility predicate (covering overloads, `.d.ts` aliases, and host-only callbacks) so no slice is scheduled that the bridge refuses. Record IEEE-754 shortest-roundtrip float tie rules (`ryu`/`zmij`), ordering, and release-only behavior. Done when every surface has an owner, destination, and acceptance case.
3. **Pilot with stdin-preserving shadow fallback.** Choose incremental closed slices or all-at-once cutover; isolate build output dirs per target (`CARGO_TARGET_DIR` per-app subdir) so binaries never overwrite each other. During incremental strangler slices, let glue hand unsupported inputs back to `original::run_with_stdin(args, consumed_bytes)` without losing already-read stdin, and check every ported case against `cases.jsonl`. Done when the pilot compiles, links, starts, and passes replay.
4. **Turn failures into work.** Group compiler/runtime/replay failures by owning slice; use Self-authoring (`references/playbooks/self-authoring.md`) for bounded repair loops. A repeated translation mistake updates the shared porting recipe and adds a `cases.jsonl` regression case. For parallel slices, follow **coworkers** (`references/techniques/coworkers.md`) on small/mid model tiers (`skill://agent-harnesses/references/delegation-efficiency.md`). Done when each queue item has a reproduced failure, owner, and replay closure.
5. **Check parity and completeness separately.** Replay the full `cases.jsonl` oracle in release mode and compare externally visible outputs. Independently reconcile the inventory against current source (including upstream churn) and **mechanically fail completion while any `original::` fallback call remains in glue**. Done when every row is proven with zero `original::` fallbacks; stubs or skipped tests never close rows.
6. **Close the migration.** Migrate callers, delete superseded implementations and shadow harnesses in each closed slice, and record workload-matched latency/memory measurements; keep merge, rollout, and release readiness distinct. Done when the native runtime boundary holds end to end.

The language-port steps are the acceptance sequence, not a prerequisite to structural redesign. Preserve the architecture and valid branches unless the target runtime boundary requires a change. Keep the behavior pin, real-artifact proof, and SKILL.md delivery-target rules below; mandatory subtraction and reader-load reduction do not apply. Judge the port against its stated migration objective.

Apply clean cutover to each closed slice: migrate its callers and delete its superseded implementation. Source implementations outside that slice may remain during an incremental port. Any temporary internal interop needs an approved boundary, owner and removal criterion; it cannot leave duplicate completed implementations or override repository rules. A separately approved structural redesign follows the sequence below.

## Structural refactoring steps

1. Pin the behavior contract: run the **how** technique (`references/techniques/how.md`), then write a characterization test, snapshot, or equivalence harness capturing current behavior before structure moves.
   No coverage → write the pin first. Type check and lint are not a pin.
   Done when the pin runs green on the unchanged code and you have its command.
2. Name the structure the code is missing (`references/principles/model-the-domain.md`). Boring code stays when its shape is clear and local. The reshape must delete branches or invalid states, not add indirection.
   Done when the missing structure is named in one sentence, with the branches or invalid states it deletes.
3. Name the target shape: module layout, types, call graph as if built today (`references/principles/foundational-thinking.md`, `references/principles/redesign-from-first-principles.md`).
   Target changes a module or public interface with two or more viable shapes → run the **architect** technique (`references/techniques/architect.md`) first.
   Done when the target layout is written down, and an architect verdict exists when it was required.
4. Subtract before you add (`references/principles/subtract-before-you-add.md`): delete dead code, collapse one-caller wrappers, drop redundant validators, remove orphan references.
   Ship the smallest change reaching the target (`references/principles/laziness-protocol.md`); revert speculative "might help" cleanups.
   Done when the subtraction is committed with the pin green and no speculative cleanup remains in the diff.
5. Move in small behavior-preserving steps, each keeping the pin green.
   - API reshapes: migrate every caller and delete the old API in the same wave (`references/principles/migrate-callers-then-delete-legacy-apis.md`). No shims, no parallel old/new paths.
   - Spot-check every rename against the files; renames miss usages in strings, prose, back-references.
   - Delegate mechanical edits to a default `task` agent on a small/mid model tier (`skill://agent-harnesses/references/delegation-efficiency.md`; reserve flagship `L` for hard boundary design and final review) with scope: file paths, names being moved, behavior to hold, exclusive file ownership.
   - Done when the code matches the target shape, the pin is green, and a grep for each old name returns no usages.
6. Prove behavior unchanged on the real artifact, not "it compiles" (`references/principles/prove-it-works.md`).
   Larger reshapes: equivalence check (old-vs-new output diff script, recorded baseline replay, or smoke run on the matching surface via the project `verify-<app>` skill).
   Done when the real-artifact run or equivalence check shows no behavior difference, with its run path recorded.
7. Confirm it is worth keeping: the diff must lower reader load somewhere (`references/principles/minimize-reader-load.md`); else revert. Done when the reader-load reduction is named, or the change is reverted.
8. Deliver per SKILL.md's delivery-target rule: for local review or a repo with no remote, leave verified S/M edits uncommitted in the starting working tree with the pin green (no default-branch commit or push). For publication, sequence commits (subtraction, reshape, follow-on cleanup, each green per `references/principles/sequence-verifiable-units.md`), commit, and run **Opening a PR** (`references/playbooks/opening-a-pr.md`).
   Done when the pin passes and the requested delivery target holds (verified uncommitted local tree, or green commits with the PR open).

## Gates

- No structure moves before the pin exists and is green.
- Unit tests and characterization pins must mock or block live production inference and paid external APIs so refactor test loops cannot burn production budgets (`https://www.youtube.com/watch?v=6TjFjHPjVH0`, 06:33).
- Verify renamed architectural abstractions in code, not just plans: confirm each "agent", "skill", or runtime actually implements the promised contract rather than aliasing a stub or leaving scheduled outputs empty (`https://www.youtube.com/watch?v=6TjFjHPjVH0`, 04:00–07:59).
- Never translate the test suite alongside a language port; rewritten tests stop being a trusted oracle. Require an unchanged language-independent suite that predates the port and runs against both implementations, or optimize the existing runtime in place (`https://www.youtube.com/watch?v=TvsF67C2F54`, 04:16-04:59, 17:14-17:30).
- Cleanup reveals a missing feature or real bug → split it out; ship the structural change first against the pinned contract. A redesign is allowed only when named and routed to Feature.
- Any step turns the pin red → stop and fix before the next step.
- Structural refactors without a reader-load reduction are reverted. Language ports instead prove their stated migration objective.

## Evidence

- The structure that changed.
- The pin it was held against.
- The equivalence proof (run path and outcome).
- The reader-load delta for a structural refactor, or the runtime-boundary objective and closed-slice inventory for a language port.
- What shipped and what got reverted. No new behavior.
