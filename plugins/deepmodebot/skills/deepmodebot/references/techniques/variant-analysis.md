# variant-analysis

**Use when:** a security vulnerability, auth bypass, race, or correctness bug was found once and you must hunt every sibling occurrence across the repo, or check spec-to-code compliance across trust boundaries.

1. **Reduce the seed bug to a 3-part tuple.** Write down `(Source, Missing Guard / Invariant, Sink)` in structural code terms (AST node shape, type, or decorator), stripping away the single file's variable names.
2. **Map the variant neighborhood.** Enumerate every sibling entry point in the same architectural tier (all HTTP/RPC handlers, webhook consumers, CLI subcommands, MCP tools, background jobs, or deserializers) and build a ` Handler | Authz | Validation | Sink ` matrix against the spec's promised invariants.
3. **Encode a deterministic structural query.** Express the generalized pattern in `ast-grep` (`sg`), Semgrep YAML, CodeQL, or a zero-dependency AST/regex script under `<root>/.scratch/variant-hunt/` (and run `assets/security-audit/static_sec_audit.py --root .` for baseline CI/crypto/sink sharp edges). Test the rule against the seed bug first (must match) and its fixed version (must not match).
4. **Triage & prove every hit.** Trace taint from attacker-controlled input to sink for each match; discard unreachable internal-only calls with a 1-line proof and reproduce real variants with an executable test or request.
5. **Turn the query into a permanent gate.** Promote high-signal zero-false-positive rules into `.deepmodebot/ci.yml`, `pre-commit`, or repo lint rules (`references/principles/encode-lessons-in-structure.md`) so the bug class cannot return.

**Done when** the seed bug's `(Source, Missing Guard, Sink)` pattern is encoded as a tested structural query, every sibling entry point is accounted for, all confirmed variants are fixed or filed with reproductions, and the rule is wired into automated checks where zero-FP.
