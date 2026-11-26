# End-to-end

Use when: building, starting, or finishing a whole app, tool, or broad goal from a prompt or rough idea ("build me <app>", "turn this idea into a working product", "finish the full scope end to end", "don't stop at one slice or MVP").

Slicing sequences verification; it never shrinks Total Scope. On a rough idea, include real product essentials (persistence, boundary validation, error and empty states, wired entrypoints, and cold-start proof); in complex or unclear domains, clear them via **sme-review** (`sme_gate`) before Sprint 2+ so implied essentials never become wasteful scope creep.
Single-run builds drive `1/N` to `N/N` without stopping early. Incremental Sprint mode (`active_sprint: 1` or `sme_gate: "required"`) lands Sprint 1 with proof and pauses ONLY at the explicit sprint/SME checkpoint, reporting Sprint 2..N as remaining scope (incomplete, never done). Never substitute stubs or `TODO` markers; `laziness-protocol` deletes redundant code layers, never requested or implied capabilities.

## Steps

0. **Grill user intent & lock the E2E Rehearsal Standard (mandatory before building/recording E2E workflows).** For any app, tool, UI, or CLI end-to-end workflow, grill the user first on the exact intended user journey: ordered beats, inputs, state transitions, visual/UX bar, and failure criteria so the recorded workflow matches their true intention.
   - Initialize the versioned rehearsal ledger in `.scratch/e2e/<slug>/rehearsal.db` (`REHEARSAL.md`): `python -B "<this skill>/assets/e2e/rehearsal_gate.py" init --root "<root>" --slug "<slug>" --app "<name>" --kind web|cli|desktop|tool|demo --intent "<intent>" --beats b1,b2,... --max-rounds 25` (`py -3 -B` on Windows).
   - Once the user approves the workflow standard, lock it with `rehearsal_gate.py approve --root "<root>" --slug "<slug>" --note "<user approval>"`. Without approval, `rehearsal_gate.py verdict --strict` stays blocked.
   Done when the user-approved workflow intent, ordered beats, and rehearsal standard are locked in `rehearsal.db` (`approved_by_user: true`).
1. **Expand the prompt into a complete Scope Manifest.** Before writing feature code, turn 100% of the request into ONE machine-checked JSON manifest (`docs/specs/<slug>-manifest.json`, or `.scratch/goals/<slug>-manifest.json` for uncommitted local delivery):
   - Cover every capability a finished product needs: all user workflows (full lifecycle or CRUD, not create-only), persistent state across restarts (SQLite, files, or database unless ephemeral is requested), input validation, actionable error states, empty states, and complete CLI/API/UI entrypoints.
   - On greenfield work, run **prior-art** (`references/techniques/prior-art.md`) and `skill://deep-stack` (`references/any-app-stack.md`) to pick the stack, then continue straight into step 2 instead of stopping at `STACK.md`.
   - Format the manifest with `"product"` and `"slices"` (`[{"id", "title", "check", "sprint"?, "sme_gate"?}, ...]`, 3 to 8 vertical slices from core domain/persistence through full workflows and cold-start proof). Tag `"sprint": 1, 2, ...` when running incremental sprints.
   - For "all", "every", or "full set" work, record every candidate in `"inventory"` with `"id"` and `"status"` in `included` (optional `"slice"`), `duplicate` (`"representative"`), `non_target` (`"reason"`), `blocked` (`"evidence"` + `"unblock"`), or `pending`. Unclassified `pending` items fail `loop.py manifest`.
   Done when `python -B "<this skill>/assets/loop/loop.py" manifest <manifest.json> --dry-run` reports `manifest ok` (schema only; slice checks run later).
2. **Initialize the project and harden the inner loop.** Create the repo layout inside the project root (`SKILL.md` Contain the work), install dependencies locally, and set up deterministic local checks per **inner-loop** (`references/techniques/inner-loop.md`):
   - Fast static check (`fast_check`): typecheck, lint, and structural rules that run in seconds.
   - Behavioral test runner (`check`) and anti-slop guard (`forbid_slop: true` in `loop.py`, blocking inline suppressions, swallowed exceptions, `TODO`/`FIXME` comments, and `NotImplementedError` stubs).
   Done when `python -B "<this skill>/assets/loop/loop.py" audit <root>` reports `inner-loop audit (ready)` and `fast_check` passes on the clean skeleton.
3. **Give each slice a real behavioral check.** Write or wire each slice's `check` command so it fails before the slice is built and passes only when observable user behavior and persisted state work (`references/principles/test-behavior-not-implementation.md`, `references/principles/model-the-domain.md`).
   Done when every slice check drives real entrypoints and state rather than mock-only stubs.
4. **Build and verify every slice from `1/N` to `N/N` (or through the active sprint gate).** Sequence work one vertical slice at a time (`references/principles/sequence-verifiable-units.md`):
   - Pick model tier and effort up front (`skill://agent-harnesses/references/delegation-efficiency.md`): small tier for `scout` searches/summaries, mid (`medium`) for oracle-backed slice builds, flagship `L` only for planning, hard debugging, security, and final review.
   - Write the goal contract once: `.scratch/goals/<slug>.md` with `manifest: <manifest.json>`, `fast_check`, `check` (cold-start end-to-end check), `protect` (tests, check scripts, and manifest), `forbid_slop: true`, and `protect_configs: true`. Omit `active_sprint` for single-run full delivery (`1/N` to `N/N`); set `active_sprint: 1` (and optional `checkpoint_every`) only for incremental Sprint mode.
   - In-session when remaining slices fit the context window: implement slice `k`, run `python -B "<this skill>/assets/loop/loop.py" check .scratch/goals/<slug>.md` (runs `fast_check`, slop guard against `HEAD`, all active manifest slices with `sprint <= active_sprint` plus inventory/SME status, then `check`), and immediately start slice `k + 1` in the same turn.
   - Across fresh context windows or unattended runs (`omp|claude|codex`): `python -B "<this skill>/assets/loop/loop.py" run .scratch/goals/<slug>.md`. On quota/cost cap, `checkpoint_every` / `sme_gate: "required"` (exit `6`), or passing Sprint 1 with deferred slices (exit `0`, `scope_complete: false`), the Scope Manifest + `latest-summary.json` form the exact zero-loss resume ledger.
   Done when `python -B "<this skill>/assets/loop/loop.py" check .scratch/goals/<slug>.md` (`py -3 -B` on Windows) prints `check exit 0 (pass)` with zero `pending` inventory items, zero slop findings, and either `N/N` slices green (`scope_complete: true`) or the active sprint gate cleanly met with Sprint `n+1..N` recorded as deferred remaining scope (`scope_complete: false`).
5. **Rehearse, record full video, watch collectively, and pass hard gates (`v1..v25`).** Prove the finished app/tool/UI from a cold start against fresh persisted state (`references/principles/prove-it-works.md`):
   - Exercise EVERY approved beat from start to settled payoff, restart/re-invoke to confirm persistence, test invalid input and empty states, and record a **complete continuous end-to-end video** (`.mp4`/`.webm` via `assets/e2e/record.py`, browser/terminal recorder, or ffmpeg) — isolated still frames alone fail the gate.
   - **Watch the entire video together** (not just single keyframes): inspect continuity, transitions between beats, pacing, flicker, layout jumps, digit rolls, and reset seams end-to-end, plus keyframes at desktop (`1440×900`) and mobile (`390×844`) for UI apps.
   - Log each iteration `v1..vN` in `rehearsal_gate.py record-run` and run a fresh-eye critic against the full video and approved intent. Iterate internally (`v1..v25`) until `python -B "<this skill>/assets/e2e/rehearsal_gate.py" verdict --root "<root>" --slug "<slug>" --strict` exits `0` (`REHEARSAL_PASSED`). Never report an E2E workflow done while any gate is red.
   Done when `rehearsal_gate.py verdict --strict` returns `REHEARSAL_PASSED` (exit 0) and the verified video + `REHEARSAL.md` sit under `.scratch/e2e/<slug>/`.
6. **Self-review against the full manifest and deliver.** Run **no-comments** (`references/techniques/no-comments.md`) and **pr-review** in local mode (`references/techniques/pr-review.md`) with the Scope Manifest as the spec claim so any missing workflow, unwired flag, unclassified inventory item, or stubbed edge case is caught before delivery. Follow `SKILL.md` for local delivery versus Opening a PR (`references/playbooks/opening-a-pr.md`).
   Done when local `pr-review` has no open P0/P1 findings, active/all slices and `rehearsal_gate.py verdict --strict` pass, any deferred sprints are explicitly reported as remaining scope (incomplete), and the requested delivery target holds.
## Gates

- Single-run mode: slice `1` passing is `1/N`, never completion. Stopping with unchecked slices requires a real hard stop (`SKILL.md` Autonomy) or three documented dead-end attempts, never convenience.
- Incremental Sprint mode (`active_sprint` / `sme_gate: "required"`): pause ONLY at the explicit sprint/SME feedback checkpoint (`exit 6` or `sme_gate`), and report Sprint `n+1..N` as remaining scope (`scope_complete: false`, never marked done).
- Zero unclassified `"pending"` inventory items may remain when closing; `loop.py manifest` rejects `pending` items and missing proof fields (`representative`, `reason`, `evidence`/`unblock`).
- No `TODO`, `FIXME`, `NotImplementedError`, `todo!()`, or `throw new Error("not implemented")` stubs in delivered code.
- Every slice check with `sprint <= active_sprint` re-runs on later slices so finishing slice `N` cannot silently break slice `1`.
- Passing unit tests or cherry-picked single screenshots never waive the Step 5 full-video E2E rehearsal gate (`rehearsal_gate.py verdict --strict`).

## Evidence

- The Scope Manifest path and `python -B "<this skill>/assets/loop/loop.py" manifest <manifest.json>` (`py -3 -B` on Windows) scoreboard (slice pass ratio, `scope_complete`, `deferred_slices`, and inventory classification counts when used).
- Inner-loop check output (`fast_check`, anti-slop status, and `sme_gate` state).
- Rehearsal gate verdict (`rehearsal_gate.py verdict --strict` -> `REHEARSAL_PASSED`), `.scratch/e2e/<slug>/REHEARSAL.md`, full recorded video path + SHA-256, and cold-start proof artifacts.
- Product decisions made when expanding the prompt, each with how to override it.
