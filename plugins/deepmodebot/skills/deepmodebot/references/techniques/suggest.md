# suggest

**Use when:** the user runs `/deepmodebot:suggest`, `/suggest`, "deepmode suggest", "suggest prompts", "what prompts should I run", or asks to audit the repo for gaps, overclaims, and high-leverage next full-scope prompts.

Every suggested prompt must be **full-scope**, grounded in **real observed repo evidence** (`file:line`, missing test, dirty diff smell, broken link, or unbacked claim), and ready to run as `/deep ...`. Never invent generic advice or fabricate file paths.

## Procedure

1. **Scan the real repository (and emit an interactive A2UI v1.0 cockpit when visual triage helps).** Run the deterministic repo scanner:
   ```bash
   python -B "<this installed skill>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 8 --ui --json
   ```
   `suggest` combines `gap_audit.py scan` (doc-to-CLI flag/subcommand drift, stale replacement claims, Python-vs-Rust gate drift, hollow stubs, swallowed exceptions, unwired script assets), `perf_audit.py`, doc overclaims/links, and diff hygiene, and `--ui` compiles a validated **A2UI v1.0** cockpit (`index.html` inside `<project-root>/.scratch/gen-ui/suggest/`). Also inspect `git log -n 10 --oneline` and any open verify skill or test failures when relevant.
   Done when every candidate suggestion is backed by concrete `file:line` or command evidence from this repo.
2. **Verify candidate gaps and overclaims before flagging them.** Inspect surrounding context and real handlers/parsers to distinguish true spec-to-code drift, hollow stubs, silent error black-holes, or overclaims from accurately bounded contracts. Drop false positives; keep proven gaps and overclaims with exact evidence.
   Done when every surviving overclaim or gap cites its exact file, line, and what is missing or unproven.
3. **Emit ranked Hardcore Mode full-scope `/deep` prompts.** Order by leverage (`P0` doc-to-CLI/gate drift, overclaims, trust-boundary gaps, broken checks → `P1` hollow stubs/swallowed errors, perf bottlenecks, hardcore architectural ceiling upgrades, missing tests, lying comments, workaround smells → `P2` unwired assets, gardening, domain architecture). Never suggest watered-down MVPs or hide the best engineering behind "(Optional hardcore mode)". Each suggestion includes:
   - Priority (`P0`/`P1`/`P2`) and category (`gap`, `overclaim`, `perf`, `hardcore`, `checks`, `verification`, `gardening`)
   - Observed evidence (`file:line` or module line count / diff metric) and why it matters
   - A complete, copy-paste-ready **Hardcore Mode full-scope `/deep ...` prompt** specifying numbered deliverables, first-principles architectural ceiling, gap/overclaim checks, real-artifact verification, and `self-grill` / `no-comments` gates.
   Offer to run any numbered prompt (or all of them) immediately if the user replies with its number.
   Done when every suggestion is evidence-backed, ranked, and ready to execute as a full-scope `/deep` prompt.

**Done when** the repo scan ran cleanly, every gap and overclaim was verified against real files, and ranked full-scope `/deep` prompts are presented with zero fabricated evidence.
