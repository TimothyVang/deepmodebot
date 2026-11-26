# suggest

**Use when:** the user runs `/deepmodebot:suggest`, `/suggest`, "deepmode suggest", "suggest prompts", "what prompts should I run", or asks to audit the repo for gaps, overclaims, and high-leverage next full-scope prompts.

Every suggested prompt must be **full-scope**, grounded in **real observed repo evidence** (`file:line`, missing test, dirty diff smell, broken link, or unbacked claim), and ready to run as `/deep ...`. Never invent generic advice or fabricate file paths.

## Procedure

1. **Scan the real repository (and emit an interactive A2UI v1.0 cockpit when visual triage helps).** Run the deterministic repo scanner:
   ```bash
   python -B "<this installed skill>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 8 --ui --json
   ```
   `--ui` compiles a schema-validated **A2UI v1.0 surface** (`surface.a2ui.json`) plus a self-contained OKLCH interactive HTML cockpit (`index.html` inside `<project-root>/.scratch/gen-ui/suggest/`, per `references/techniques/gen-ui.md`) so the human can filter `P0`/`P1`/`P2` gaps, inspect `file:line` receipts, multi-select deliverables, and copy `/deep` prompts or A2UI `action` JSON in 1 click (pass `--open` when the user wants it popped open in the browser). Also inspect recent `git log -n 10 --oneline` and any open verify skill or test failures when relevant.
   Done when every candidate suggestion is backed by concrete `file:line` or command evidence from this repo.
2. **Verify overclaims before flagging them.** For each candidate overclaim in docs, `README.md`, skills, or comments (e.g., "100%", "always", "zero errors", "fully automated", "supports all", stale counts, broken local links), inspect the surrounding context and codebase to distinguish true overclaims/gaps from accurately qualified statements. Drop false positives; keep proven gaps and overclaims with exact evidence.
   Done when every surviving overclaim or gap cites its exact file, line, and what is missing or unproven.
3. **Emit ranked Hardcore Mode full-scope `/deep` prompts.** Order by leverage (`P0` overclaims, trust-boundary gaps, broken checks → `P1` hardcore architectural/systems ceiling upgrades grounded in the repo's core modules, missing verification/tests, lying comments, workaround smells → `P2` gardening, domain architecture, debt). Never suggest watered-down MVPs or hide the best engineering behind "(Optional hardcore mode)". Each suggestion includes:
   - Priority (`P0`/`P1`/`P2`) and category (`overclaim`, `gap`, `hardcore`, `checks`, `verification`, `gardening`)
   - Observed evidence (`file:line` or module line count / diff metric) and why it matters
   - A complete, copy-paste-ready **Hardcore Mode full-scope `/deep ...` prompt** specifying numbered deliverables, first-principles architectural ceiling, gap/overclaim checks, real-artifact verification, and `self-grill` / `no-comments` gates.
   Offer to run any numbered prompt (or all of them) immediately if the user replies with its number.
   Done when every suggestion is evidence-backed, ranked, and ready to execute as a full-scope `/deep` prompt.

**Done when** the repo scan ran cleanly, every gap and overclaim was verified against real files, and ranked full-scope `/deep` prompts are presented with zero fabricated evidence.
