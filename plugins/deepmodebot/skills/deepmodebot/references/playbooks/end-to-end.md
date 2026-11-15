# End-to-end

Use when: building, starting, or finishing a whole app, tool, or broad goal from a prompt or rough idea ("build me <app>", "turn this idea into a working product", "finish the full scope end to end", "don't stop at one slice or MVP").

Slicing sequences verification; it never shrinks scope. A rough idea from a human asks for a complete, usable product with real persistence, boundary validation, error and empty states, wired entrypoints, and a proven end-to-end user journey. Never stop after slice 1, never substitute stubs or `TODO` markers for working behavior, and never hand back core capabilities as "next steps". `laziness-protocol` deletes redundant code layers, never requested or implied product capabilities.

## Steps

1. **Expand the prompt into a complete Scope Manifest.** Before writing feature code, turn the request or rough idea into an explicit JSON manifest (`docs/specs/<slug>-manifest.json`, or `.scratch/goals/<slug>-manifest.json` for uncommitted local delivery):
   - Cover every capability a finished product needs: all user workflows (full lifecycle or CRUD, not create-only), persistent state across restarts (SQLite, files, or database rather than an ephemeral in-memory list unless requested), input validation, actionable error states, empty states, and complete CLI/API/UI entrypoints.
   - Decide omitted product details yourself and record each decision in a **show-me-your-work** trail (`references/techniques/show-me-your-work.md`).
   - On greenfield work, run **prior-art** (`references/techniques/prior-art.md`) and `skill://deep-stack` (its `references/any-app-stack.md`) to pick the stack, then continue straight into step 2 instead of stopping at `STACK.md`.
   - Format the manifest with `"product"` and `"slices"` (`[{"id", "title", "check"}, ...]`, 3 to 8 vertical slices ordered from core domain and persistence through full user workflows and cold-start end-to-end proof).
   Done when `python <this skill>/assets/loop/loop.py manifest <manifest.json> --dry-run` reports `manifest ok` (schema only; slice checks run later).
2. **Initialize the project and harden the inner loop.** Create the repo layout inside the project root (`SKILL.md` Contain the work), install dependencies locally, and set up deterministic local checks per **inner-loop** (`references/techniques/inner-loop.md`):
   - Fast static check (`fast_check`): typecheck, lint, and structural rules that run in seconds.
   - Behavioral test runner (`check`) and anti-slop guard (`forbid_slop: true` in `loop.py`, blocking inline suppressions, swallowed exceptions, `TODO`/`FIXME` comments, and `NotImplementedError` stubs).
   Done when `python <this skill>/assets/loop/loop.py audit <root>` reports `inner-loop audit (ready)` and `fast_check` passes on the clean skeleton.
3. **Give each slice a real behavioral check.** Write or wire each slice's `check` command so it fails before the slice is built and passes only when observable user behavior and persisted state work (`references/principles/test-behavior-not-implementation.md`, `references/principles/model-the-domain.md`).
   Done when every slice check drives real entrypoints and state rather than mock-only stubs.
4. **Build and verify every slice from `1/N` to `N/N`.** Sequence work one vertical slice at a time (`references/principles/sequence-verifiable-units.md`), driving all slices to completion without stopping early:
   - Write the goal contract once: `.scratch/goals/<slug>.md` with `manifest: <manifest.json>`, `fast_check`, `check` (the cold-start end-to-end check), `protect` (tests, check scripts, and manifest), `forbid_slop: true`, and `protect_configs: true`.
   - In-session when remaining slices fit the context window: implement slice `k`, run `python <this skill>/assets/loop/loop.py check .scratch/goals/<slug>.md` (it runs `fast_check`, the slop guard against `HEAD`, every manifest slice, then `check`), and immediately start slice `k + 1` in the same turn. `loop.py manifest` alone runs only the slice checks.
   - Across fresh context windows or unattended runs: `python <this skill>/assets/loop/loop.py run .scratch/goals/<slug>.md`.
   Done when `loop.py check .scratch/goals/<slug>.md` prints `check exit 0 (pass)`: `N/N` slices green and zero newly added suppressions, swallowed errors, or stub placeholders.
5. **Prove the finished product from a cold start.** Run the built CLI, service, or UI from scratch against fresh persisted state (`references/principles/prove-it-works.md`):
   - Exercise the full primary workflow, restart or re-invoke the process to prove state persisted, trigger invalid-input handling, and check the empty state.
   - Save command transcripts, outputs, or UI captures under `.scratch/evidence/<slug>/`.
   Done when the cold-start end-to-end run passes and its artifacts sit under `.scratch/evidence/<slug>/`.
6. **Self-review against the full manifest and deliver.** Run **no-comments** (`references/techniques/no-comments.md`) and **pr-review** in local mode (`references/techniques/pr-review.md`) with the Scope Manifest as the spec claim so any missing workflow, unwired flag, or stubbed edge case is caught and fixed before delivery. Follow `SKILL.md` for local delivery versus Opening a PR (`references/playbooks/opening-a-pr.md`).
   Done when local `pr-review` has no open P0/P1 findings, all `N/N` slices and the cold-start check pass, and the requested delivery target holds.

## Gates

- Slice `1` passing is `1/N`, never completion. Stopping with unchecked manifest slices requires a real hard stop (`SKILL.md` Autonomy) or three documented dead-end attempts, never convenience.
- No `TODO`, `FIXME`, `NotImplementedError`, `todo!()`, or `throw new Error("not implemented")` stubs in delivered code.
- Every slice check re-runs on later slices so finishing slice `N` cannot silently break slice `1`.
- Passing unit tests never waive the step 5 cold-start end-to-end run on the real artifact.

## Evidence

- The Scope Manifest path and final `N/N` scoreboard (`loop.py manifest <manifest.json>`).
- Inner-loop check output (`fast_check` and anti-slop status).
- Cold-start end-to-end proof artifacts under `.scratch/evidence/<slug>/`.
- Product decisions made when expanding the prompt, each with how to override it.
