# inner-loop

**Use when:** hardening a repo's inner loop so coding agents stop shipping AI code slop; auditing fast local checks before starting an unattended goal loop (`assets/loop/loop.py`), `run-a-goal`, `work-a-queue`, or `/goal`; or converting repeated review findings into deterministic gates.

An outer loop (`loop.py`, `run-a-goal`, `work-a-queue`, `/goal`) multiplies whatever the inner loop permits. When the inner loop accepts untyped shapes, inline suppressions, swallowed exceptions, single-caller wrappers, or unverified behavior, automating the outer loop produces slop faster. Turn the inner loop into a deterministic constraint system before scaling iterations.

1. **Audit the repo's inner loop.** Run `python -B "<this skill>/assets/loop/loop.py" audit <root> --json` (`py -3 -B` on Windows) to inventory four layers and protected configs:
   - Fast static gates (typechecker, linter, custom structural rules).
   - Behavioral test suite.
   - Commit-time hooks.
   - Live verification (`verify-<app>` skill or direct app/CLI execution).
   - Guardrail configs (`tsconfig.json`, `ruff.toml`, `biome.json`, `eslint.config.*`, `pyproject.toml` tool sections, hook configs) that agents must not weaken.
   Done when the audit report is captured and every missing layer or unprotected config is listed.
2. **Push rules down the constraint pyramid.** Enforce invariants at the lowest deterministic layer (`references/principles/encode-lessons-in-structure.md`):
   - Types and narrow boundaries (`references/principles/type-system-discipline.md`, `references/principles/boundary-discipline.md`). Parse untrusted data at entry boundaries and make illegal states unrepresentable instead of scattering defensive checks.
   - Actionable lint and structural checks. Ban error-prone APIs, layer violations, and dead compatibility shims with scripts or lint rules whose failure message names the exact replacement API or fix.
   - Fast behavioral and invariant tests (`references/principles/test-behavior-not-implementation.md`). Assert observable outputs and edge-case invariants rather than mock call counts.
   - Live artifact proof (`references/principles/prove-it-works.md`). Drive the real CLI, service, or UI through its `verify-<app>` skill or entrypoint.
   - Thin prose last (`references/techniques/correct.md`). Keep `AGENTS.md` and `CODING_STANDARDS.md` only for judgment calls no check can express.
   Done when each rule sits at the lowest layer that can check it and every custom check prints how to fix a violation.
3. **Close code-slop escape hatches in checks.** Make the inner loop fail closed on common agent shortcuts. `loop.py`'s `forbid_slop` guard blocks the first three when they are newly added and `protect_configs` blocks the config half of the fifth; encode the rest as the repo's own lint, structural, or hook rules:
   - Inline type or lint suppressions (`# type: ignore`, `# pyright: ignore`, `# noqa`, `# pylint: disable`, `# nosec`, `# pragma: no cover`, `@ts-ignore`, `@ts-expect-error`, `eslint-disable`, `biome-ignore`, `#[allow(`, `#[expect(`, `// nolint`) added instead of fixing the cause (`references/techniques/no-comments.md`).
   - Bare `except:` blocks that do not re-raise, broad `except Exception:` handlers whose body is only `pass`, `continue`, `break`, or `return None`, `contextlib.suppress(Exception)`, and empty `catch {}` blocks that hide faults (`references/principles/fix-root-causes.md`).
   - Deferred `TODO` or `FIXME` markers and `NotImplementedError` or `throw new Error("not implemented")` stubs left in place of working behavior (`references/playbooks/end-to-end.md`).
   - Single-caller pass-through wrappers, speculative options, and dead compatibility shims (`references/principles/minimize-reader-load.md`, `references/principles/outcome-oriented-execution.md`).
   - Weakened linter, typechecker, or hook configs and `--no-verify` commit bypasses (`references/techniques/pre-commit.md`, `references/techniques/git-guardrails.md`).
   Done when a planted suppression or swallowed exception fails the gate and guardrail configs are protected.
4. **Split fast feedback from full acceptance.** Keep `fast_check` (types, lint, structural checks, fast unit tests) under roughly 30 seconds so every edit gets immediate feedback, and wire it into commit hooks with **pre-commit** (`references/techniques/pre-commit.md`). Keep slower integration suites and live runtime checks in `check` so static checks alone never count as done.
   Done when `fast_check` and `check` both run from the project root and fail on a planted fault.
5. **Bind outer goal loops to the hardened inner loop.** Before launching `loop.py`, `run-a-goal` (`references/playbooks/run-a-goal.md`), or `self-authoring` (`references/playbooks/self-authoring.md`):
   - Generate a new goal contract (`python -B "<this skill>/assets/loop/loop.py" audit <root> --write-goal .scratch/goals/<slug>.md`, `py -3 -B` on Windows) with `fast_check`, `check`, and `protect` naming every test, fixture, and check script. (`--write-goal` refuses to overwrite an existing goal file; edit existing goal files directly.)
   - Keep `forbid_slop: true` and `protect_configs: true` enabled (`protect_configs` defaults to `true` except when `protect: none`, where it defaults to `false` unless set explicitly); set `revert_on_fail: true` on a clean tree when failed attempts must reset automatically between iterations.
   - Run `python -B "<this skill>/assets/loop/loop.py" check <goal.md>` once to verify the contract parses, protects configs, and fails on the unfixed state. (`loop.py check` always exits `0` and prints gate pass/fail status to stdout, so inspect its printed output rather than relying on a nonzero exit code.)
   - When an outer loop or review hits the same failure class twice, pause fan-out and encode a permanent check via **correct** (`references/techniques/correct.md`).
   Done when `loop.py check` (or the outer loop's gate) validates the contract and proves a red-to-green path without weakening any check.

**Done when** the repo's inner loop enforces fast static checks, anti-slop guards, behavioral tests, and live artifact proof, and any outer goal loop is wired to fail closed on them.

**Output:** audit summary, checks added or tightened, slop escape hatches closed, red-to-green proof, and goal-loop contract status.
