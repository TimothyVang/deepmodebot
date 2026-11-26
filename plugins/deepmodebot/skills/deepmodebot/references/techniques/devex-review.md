# devex-review

**Use when:** auditing developer experience ("DX review", "developer onboarding audit", "CLI/SDK ergonomics review"), designing a CLI, SDK, or MCP tool surface, or checking whether a newcomer or coding agent can go from cold clone to first working run without friction.

1. **Cold-start onboarding stopwatch.** Walk the documented setup from a clean directory/env (`README.md` / `CONTRIBUTING.md`): count required manual steps, undocumented system prerequisites, missing `.env.example` keys, broken scripts, and time-to-first-green-test. Aim for one deterministic bootstrap command (`make dev`, `npm test`, `uv sync && pytest`).
2. **CLI ergonomics for humans & agents.** Audit every command against dual human/agent usability:
   - Machine-readable `--json` output on stdout, progress/diagnostics on stderr;
   - Non-interactive flags (`--yes`, `--dry-run`) that never hang waiting on stdin when `!isatty`;
   - Complete `--help` with real examples, `NO_COLOR` support, and distinct non-zero exit codes (`0` ok, `1` check/finding failed, `2` usage/setup error).
3. **Actionable error messages.** Trigger 3–5 common failure modes (missing env var, occupied port, bad config, expired auth, wrong argument type). Every error must state **what failed, where, and the exact command or edit to fix it**—never raw stack traces or opaque `"Invalid input"`.
4. **SDK & API surface audit.** Check pit-of-success defaults (safe timeouts, retries on idempotent calls, typed errors, zero required boilerplate for the 80% case, and progressive disclosure of advanced knobs).

**Done when** cold-start setup friction is reproduced or verified clean, CLI/SDK interfaces satisfy `--json`/`--dry-run`/non-TTY/exit-code contracts, and unhelpful errors are replaced with actionable fix hints.
