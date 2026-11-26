# self-grill

**Use when:** auditing your own plan, assumptions, diff, tests, or checks before acting or before reporting done ("self-grill", "grill my checks", "grill this diff", "audit my checks", "check my assumptions"), or whenever the auto-router sets `self_grill` to `plan`, `checks`, or `both`. Skip for local size **S** edits unless the user asks.

Unlike **grill** (stress-testing a draft design tree) and **panel** (external merge verdict), **self-grill** is a fast, adversarial check on your own blind spots. Never rubber-stamp your own claim; every critical question ends with observed proof or a real fix.

## Two passes

- **Plan pass (`plan` or `both`):** run before editing when scope is ambiguous, cross-cutting, or touches a trust boundary. Expose hidden assumptions, XY framing (`references/principles/attack-the-premise.md`), unasked-for scope, and irreversible choices. Resolve facts by reading or running tools, observable forks via `references/playbooks/prototype.md`, reversible choices by deciding and logging, and hard stops by surfacing them clearly.
- **Checks pass (`checks` or `both`):** run after your last edit and before reporting done or opening a PR. Interrogate the diff, tests, and receipts so weak oracles, stale outputs, or missing failure paths get caught before the user or panel sees them.

## Procedure

1. **Inspect the real diff and seed questions.** Run the deterministic checker on the project root:
   ```bash
   python -B "<this installed skill>/assets/self-grill/self_grill.py" check-diff --root "<project-root>" --json
   ```
   For a tracked audit trail on M/L or risky work, initialize `--phase plan` before coding and refresh with `--phase both --refresh` after final edits (preserving plan answers while scanning the live diff):
   ```bash
   python -B "<this installed skill>/assets/self-grill/self_grill.py" init --root "<project-root>" --slug "<slug>" --phase both --refresh --json
   ```
   Done when the live diff size, tree digest, sensitive paths, and auto-generated adversarial questions are in hand.

2. **Grill every critical question against evidence.** Never answer from memory or compacted summaries. Check each of these failure modes when applicable:
   - **Check theater:** would the new or existing test fail if your fix were reverted (`references/principles/test-behavior-not-implementation.md`)? Are mocks hiding the real boundary?
   - **Exit-code and freshness honesty:** did every command run on the *current* working tree or HEAD SHA after the final edit, with raw exit code captured (never masked behind `| head` or `| tail`)?
   - **Scope completeness:** does every deliverable in the user's request map to an observed artifact or explicit blocker?
   - **No lying comments:** comments rot and lie, and AI agents read comments instead of code. Inspect every added code comment flagged by `self_grill.py check-diff` (`no-lying-comments`) and delete narration, banners, workarounds, and unsafe lint/type suppressions via `references/techniques/no-comments.md`.
   - **Trust boundaries and platform traps:** fail-closed auth/secrets/parsing, empty/zero/null inputs, idempotency, Windows CRLF and path handling, and root-only writes (`references/contain.md`).
   - **Workaround & foot-gun smells:** inspect every imperative timer (`setTimeout`/`requestAnimationFrame`/`requestIdleCallback`), raw `useEffect`, or unsafe type escape (`as any`, `as unknown as`) flagged by `no-workaround-smells` and fix the root cause instead of patching.
   - **Hardcore craft depth (`hardcore-craft-depth` / `hardcore-ceiling`):** did the plan and diff ship the true first-principles algorithm/architecture instead of a toy MVP, flat approximation, hardcoded stub (`NotImplementedError`, `TODO: later`, `placeholder`, `fake_`), or punting real craft to "(optional hardcore mode)"?
   - **Mathematical & formal proof soundness (`proof-and-math-soundness`):** when touching proofs (`.lean`, `.v`, `.tla`, `.smt2`, `.tex`) or math claims, run `assets/formal-verification/verify_proof.py audit-static` (zero `sorry`/`admit`/custom `axiom`/`native_decide`), check quantifier order ($\forall\exists$ vs $\exists\forall$), degenerate boundaries ($n=0,1,\emptyset$, strict vs weak inequalities, sign flips), NL-to-formal statement alignment, and require **two independent line-by-line audits** (`Siege` rule) when no proof kernel certifies the step.
   - **Verifiability is not reversibility:** passing tests, lints, or formal checks verify only under their stated assumptions and never waive hard stops on one-way doors (data loss, destructive migrations, external sends).
   - **Deletion test:** can any new wrapper, flag, config knob, or prose block be deleted without losing behavior (`references/principles/laziness-protocol.md`)?
   Done when every question has an observed command output, a verified `file:line`, or a concrete `n/a` reason.

3. **Confession + Adaptive Hotspot Prosecutor + Sieve (with `PRM800K` convincing-wrong-answer targeting).** Before replying on M/L or sensitive work, never grade your own homework inline and never demand an unguided 200-item chat dump. Instead:
   - **Part B1 (Builder Confession — target the most plausible wrong steps):** write down every shortcut, regex/math approximation, untested path, or stretched claim you *know* you made, deliberately spotlighting the *most convincing* derivations, bounds, and citations where subtle sign/quantifier/off-by-one bugs hide (`PRM800K` active-learning rule).
   - **Pack 1-file bundle:** run `python -B "<this installed skill>/assets/self-grill/self_grill.py" bundle --root "<project-root>" --slug "<slug>" --claims-stdin --confession "<confession>" --json` to write `.scratch/self-grill/<slug>/prosecutor-bundle.md` (supports `--files` in non-git workspaces and preserves `.lean`/`.tla` proof bodies).
   - **Part B2 (Fresh Adaptive Prosecutor + Sieve):** spawn one bounded read-only `reviewer` pinned to a low-tier model (`Model: "flash"` / `@smol` / `haiku` / `gpt-6-luna`, `2–4` batched turns; never `inherit` Carbon/Pro/Opus unless requested) reading `prosecutor-bundle.md` (~75% hotspot code/proof probes, ~25% claims-vs-code; brainstorm 50+ candidates first, then **sieve** to 100%-provable P0/P1/P2 bugs and overclaims with `file:line` + trigger input).
   - **Fix before replying:** fix every valid P0/P1 at the root cause, re-run real checks, and refresh the ledger before answering the user.
   Done when all proven P0/P1 prosecutor findings are fixed and re-verified on the current tree.

4. **Record verified receipts and enforce the freshness gate.** Record each question via `self_grill.py answer` (`proven` requires a disk-verified `file:line` inside the repo, `cmd:<cmd> -> exit 0`, or URL; trivial strings like `"ok"` are rejected), then run:
   ```bash
   python -B "<this installed skill>/assets/self-grill/self_grill.py" verdict --dir "<grill-dir>" --strict --json
   ```
   `verdict --strict` checks both critical receipts and live `tree_digest` freshness (stamping `.scratch/self-grill/latest-pass.json` on `PASS`), failing with `NEEDS_WORK` if files changed after `init`.
   Done when `verdict --strict` returns `PASS` (exit 0) on the current `tree_digest` or names every remaining blocker.

**Output:** concise self-grill summary (only when asked directly; otherwise fold proven checks into the final reply without naming internal machinery): `measured_size`, critical questions checked, any fixes triggered by the grill, and `PASS` / `BLOCKED`.

**Done when** every critical question is backed by a fresh receipt on the current tree or resolved with a verified fix, and `self_grill.py verdict --strict` exits 0 (or names every remaining blocker).
