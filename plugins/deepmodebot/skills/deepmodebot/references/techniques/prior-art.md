# prior-art

**Use when:** before building any new feature, tool, scanner, integration, CLI, or service, when auditing an external GitHub organization for upgrades, or when asked "is there a library / project / reference for X". Mine proven open-source mechanisms, failure modes, and invariants before writing from scratch.

1. **Name constraints and gap questions** in one line: target job, language/runtime, acceptable permissive licenses (`MIT`, `Apache-2.0`, `BSD-*`, `ISC`), deployment constraints, must-have behavior, and what failure modes would disqualify a candidate.
   When starting from a startup anecdote or video, read [startup references](../startup-ideas.md) first; popularity or revenue claims are never technical validation.
   Done when constraints, license floor, and disqualifiers are explicit.

2. **Sweep across parallel discovery channels** (`researcher` or `scout` low-tier subagents across harnesses; `2-3` max). Always pair popular incumbents with recent breakouts:
   - **Curated + trending catalog:** run `python -B "<this skill>/scripts/trending.py" find <terms> --json` (`py -3 -B` on Windows) against the 340+ repo catalog and [dated reference library](../../assets/repo-references.json).
   - **Organization-wide SOTA sweep:** when mining engineering orgs (e.g. `cloudflare`, `vercel`, `astral-sh`), run `python -B "<this skill>/scripts/trending.py" org <org-or-url> --json` (or `deepmodebot net trending --orgs <orgs> --json`) to surface both flagship and newly pushed repos.
   - **GitHub search & code:** `gh search repos "<terms>" --sort stars --limit 20` plus `--created ">=<90-days-ago>"`, and `gh search code "<symbol>" --limit 30`. For agent/PR orchestration, check `references/factory-landscape.md`.
   - **Papers, registries & bundled docs:** `deepmodebot net fetch-papers --query "<terms>" --json` (extracts linked GitHub `code_urls`), npm/PyPI/crates.io/pkg.go.dev, `node_modules/<pkg>/docs`, and `npx opensrc <package>`.
   - **The active repo itself:** check existing helpers, dependencies, and `gap_audit.py scan --root .` first so you never build a duplicate seam.
   Done when every relevant channel returned candidates or an explicit null result.

3. **Verify license, code truth, and adversarial failure modes** (never judge by stars or README badges):
   - **Root `LICENSE` verification:** read the actual `LICENSE` file for code, docs, assets, and weights. GitHub's SPDX detector frequently labels short Apache-2.0 headers `NOASSERTION`; inspect the file text directly, and reject unlicensed (`NONE`), `CC-BY-*` code, or copyleft/enterprise-restricted files when permissive terms are required (e.g., [OpenMausBot enterprise exception](https://github.com/milind-soni/OpenMausBot/blob/main/enterprise/LICENSE)).
   - **Disconfirmation check:** inspect open bug issues, maintenance pulse, dependency weight, security advisories (`npm audit`, `pip-audit`, GHSA), and source code vs README claims.
   - **Head-to-head runtime fit:** test the shortlisted candidate against the incumbent on a real check (size, latency, edge compatibility, test run in `<root>/.scratch/tmp/`).
   Done when every finalist has verified license text, disconfirmation notes, and runtime-fit evidence.

4. **Choose reuse mode AND mine transferable invariants:**
   - **Depend** on a maintained package when runtime/weight/license fit cleanly.
   - **Copy or adapt** a focused module under permissive terms, preserving copyright/attribution in `NOTICE.md`.
   - **Fork/clone** when most of the project fits, recording upstream URL and exact commit SHA.
   - **Distill invariants & mechanical gates** even when building native code: extract edge-case test vectors, anti-patterns, and static rules into your repo's linters/gates (`gap_audit.py record-gap`) so the codebase permanently learns what upstream solved.
   Done when each component has a reuse mode, attribution plan, and Differential Gap Matrix entry when upgrading an existing repo.

5. **Log the decision trail** (`show-me-your-work`): candidates evaluated, exact license verified, disconfirmations caught, winner chosen, and why alternatives lost.
   Done when the trail records those fields.

## Gates

- Never copy or adapt code/prompts from an unlicensed (`NONE`), unverified, or incompatible-license repository.
- Publishing packages or contacting upstream maintainers remains a hard stop (`SKILL.md` Autonomy).
- Adopted packages and clean-room ports must pass the same behavioral and adversarial tests as first-party code.

**Done when** every piece names its dependency, attributed source, fork SHA, or first-principles build rationale backed by license and disconfirmation receipts.
