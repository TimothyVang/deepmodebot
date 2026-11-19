# End-to-end

Use when: building, starting, or finishing a whole app, tool, or broad goal from a prompt or rough idea ("build me <app>", "turn this idea into a working product", "finish the full scope end to end", "don't stop at one slice or MVP").

Slicing sequences verification; it never shrinks Total Scope. On a rough idea, include real product essentials (persistence, boundary validation, error and empty states, wired entrypoints, and cold-start proof); in complex or unclear domains, clear them via **sme-review** (`sme_gate`) before Sprint 2+ so implied essentials never become wasteful scope creep.
Single-run builds drive `1/N` to `N/N` without stopping early. Incremental Sprint mode (`active_sprint: 1` or `sme_gate: "required"`) lands Sprint 1 with proof and pauses ONLY at the explicit sprint/SME checkpoint, reporting Sprint 2..N as remaining scope (incomplete, never done). Never substitute stubs or `TODO` markers; `laziness-protocol` deletes redundant code layers, never requested or implied capabilities.

## Steps

1. **Expand the prompt into a complete Scope Manifest.** Before writing feature code, turn 100% of the request into ONE machine-checked JSON manifest (`docs/specs/<slug>-manifest.json`, or `.scratch/goals/<slug>-manifest.json` for uncommitted local delivery):
   - Cover every capability a finished product needs: all user workflows (full lifecycle or CRUD, not create-only), persistent state across restarts (SQLite, files, or database unless ephemeral is requested), input validation, actionable error states, empty states, and complete CLI/API/UI entrypoints.
   - Decide reversible product details yourself and record each decision in a **show-me-your-work** trail (`references/techniques/show-me-your-work.md`). In complex or unclear domains, run **sme-review** (`references/techniques/sme-review.md`) and set `"sme_gate": "required"` on the manifest or Sprint 2+ slices until SME/user confirmation clears it (`"sme_gate": "cleared"`).
   - On greenfield work, run **prior-art** (`references/techniques/prior-art.md`) and `skill://deep-stack` (`references/any-app-stack.md`) to pick the stack, then continue straight into step 2 instead of stopping at `STACK.md`.
   - Format the manifest with `"product"` and `"slices"` (`[{"id", "title", "check", "sprint"?, "sme_gate"?}, ...]`, 3 to 8 vertical slices from core domain/persistence through full workflows and cold-start proof). Tag `"sprint": 1, 2, ...` when running incremental sprints.
   - For "all", "every", or "full set" work, record every candidate in `"inventory"` with `"id"` and `"status"` in `included` (optional `"slice"`), `duplicate` (`"representative"`), `non_target` (`"reason"`), `blocked` (`"evidence"` + `"unblock"`), or `pending`. Unclassified `pending` items fail `loop.py manifest`.
   Done when `python <this skill>/assets/loop/loop.py manifest <manifest.json> --dry-run` reports `manifest ok` (schema only; slice checks run later).
2. **Initialize the project and harden the inner loop.** Create the repo layout inside the project root (`SKILL.md` Contain the work), install dependencies locally, and set up deterministic local checks per **inner-loop** (`references/techniques/inner-loop.md`):
   - Fast static check (`fast_check`): typecheck, lint, and structural rules that run in seconds.
   - Behavioral test runner (`check`) and anti-slop guard (`forbid_slop: true` in `loop.py`, blocking inline suppressions, swallowed exceptions, `TODO`/`FIXME` comments, and `NotImplementedError` stubs).
   Done when `python <this skill>/assets/loop/loop.py audit <root>` reports `inner-loop audit (ready)` and `fast_check` passes on the clean skeleton.
3. **Give each slice a real behavioral check.** Write or wire each slice's `check` command so it fails before the slice is built and passes only when observable user behavior and persisted state work (`references/principles/test-behavior-not-implementation.md`, `references/principles/model-the-domain.md`).
   Done when every slice check drives real entrypoints and state rather than mock-only stubs.
4. **Build and verify every slice from `1/N` to `N/N` (or through the active sprint gate).** Sequence work one vertical slice at a time (`references/principles/sequence-verifiable-units.md`):
   - Write the goal contract once: `.scratch/goals/<slug>.md` with `manifest: <manifest.json>`, `fast_check`, `check` (cold-start end-to-end check), `protect` (tests, check scripts, and manifest), `forbid_slop: true`, and `protect_configs: true`. Omit `active_sprint` for single-run full delivery (`1/N` to `N/N`); set `active_sprint: 1` (and optional `checkpoint_every`) only for incremental Sprint mode.
   - In-session when remaining slices fit the context window: implement slice `k`, run `python <this skill>/assets/loop/loop.py check .scratch/goals/<slug>.md` (runs `fast_check`, slop guard against `HEAD`, all active manifest slices with `sprint <= active_sprint` plus inventory/SME gates, then `check`), and immediately start slice `k + 1` in the same turn.
   - Across fresh context windows or unattended runs: `python <this skill>/assets/loop/loop.py run .scratch/goals/<slug>.md`. On quota/cost cap, sprint checkpoint (`exit 6`), or `sme_gate: "required"`, the Scope Manifest + `latest-summary.json` (`scope`: `active_sprint`, `deferred_slices`, `inventory_counts`, `sme_gate_blocked`) form the exact zero-loss resume ledger; resume at the next queued slice without re-scanning.
   Done when `loop.py check .scratch/goals/<slug>.md` prints `check exit 0 (pass)` with zero `pending` inventory items, zero slop findings, and either `N/N` slices green (`scope_complete: true`) or the active sprint gate cleanly met with Sprint `n+1..N` recorded as deferred remaining scope (`scope_complete: false`).
5. **Prove the finished product from a cold start.** Run the built CLI, service, or UI from scratch against fresh persisted state (`references/principles/prove-it-works.md`):
   - Exercise the full primary workflow (or the active sprint's end-to-end journey), restart or re-invoke the process to prove state persisted, trigger invalid-input handling, and check the empty state.
   - Save command transcripts, outputs, or UI captures under `.scratch/evidence/<slug>/`.
   Done when the cold-start end-to-end run passes and its artifacts sit under `.scratch/evidence/<slug>/`.
6. **Self-review against the full manifest and deliver.** Run **no-comments** (`references/techniques/no-comments.md`) and **pr-review** in local mode (`references/techniques/pr-review.md`) with the Scope Manifest as the spec claim so any missing workflow, unwired flag, unclassified inventory item, or stubbed edge case is caught before delivery. Follow `SKILL.md` for local delivery versus Opening a PR (`references/playbooks/opening-a-pr.md`).
   Done when local `pr-review` has no open P0/P1 findings, active/all slices and the cold-start check pass, any deferred sprints are explicitly reported as remaining scope (incomplete), and the requested delivery target holds.

## Gates

- Single-run mode: slice `1` passing is `1/N`, never completion. Stopping with unchecked slices requires a real hard stop (`SKILL.md` Autonomy) or three documented dead-end attempts, never convenience.
- Incremental Sprint mode (`active_sprint` / `sme_gate: "required"`): pause ONLY at the explicit sprint/SME feedback checkpoint (`exit 6` or `sme_gate`), and report Sprint `n+1..N` as remaining scope (`scope_complete: false`, never marked done).
- Zero unclassified `"pending"` inventory items may remain when closing; `loop.py manifest` rejects `pending` items and missing proof fields (`representative`, `reason`, `evidence`/`unblock`).
- No `TODO`, `FIXME`, `NotImplementedError`, `todo!()`, or `throw new Error("not implemented")` stubs in delivered code.
- Every slice check with `sprint <= active_sprint` re-runs on later slices so finishing slice `N` cannot silently break slice `1`.
- Passing unit tests never waive the step 5 cold-start end-to-end run on the real artifact.

## Evidence

- The Scope Manifest path and `loop.py manifest <manifest.json>` scoreboard (slice pass ratio, `scope_complete`, `deferred_slices`, and inventory classification counts when used).
- Inner-loop check output (`fast_check`, anti-slop status, and `sme_gate` state).
- Cold-start end-to-end proof artifacts under `.scratch/evidence/<slug>/` (plus `latest-summary.json` resume ledger if paused at a sprint, SME, or quota gate).
- Product decisions made when expanding the prompt, each with how to override it.
