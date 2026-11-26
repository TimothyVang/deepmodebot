# suggest

**Use when:** the user runs `/deepmodebot:suggest`, `/suggest`, "deepmode suggest", "suggest prompts", "what prompts should I run", or asks to audit the repo for gaps, overclaims, and high-leverage next full-scope prompts.

Every suggested prompt must be **full-scope**, grounded in **real observed repo evidence** (`file:line`, missing test, dirty diff smell, broken link, or unbacked claim), and ready to run as `/deep ...`. Never invent generic advice or fabricate file paths.

## Procedure

1. **Scan the full repository with zero top-N truncation (and emit an interactive A2UI v1.0 cockpit).** Run the deterministic High-Leverage Task Map scanner (`--limit 0` = full un-truncated scope across all subsystems):
   ```bash
   python -B "<this installed skill>/assets/prompt-tools/prompt_tools.py" suggest --root "<project-root>" --limit 0 --ui --json
   ```
   `suggest` maps every subsystem via `git ls-files` + parallel native `dmb-gate` (`perf` + `gap`), combining per-subsystem spec/CLI drift, hollow stubs, swallowed exceptions, hot-path/DB bottlenecks, unchecked roadmap/spec deliverables, LLM/API/UI capability & verification gaps, caller fan-in, git churn, and core architectural ceiling modules (`--ui` writes `<project-root>/.scratch/gen-ui/suggest/index.html`).
   Also inspect `README.md`, `ROADMAP.md`, `docs/PROJECT_BRIEF.md`, open issues, and product routes/workflows to catch domain/SOTA levers static rules cannot see.
   Done when every subsystem and domain workflow has been mapped with concrete `file:line` or command evidence.
2. **Verify candidate gaps and augment with missing domain/SOTA capability levers.** Inspect real handlers, schemas, and user journeys to drop false positives (e.g., intentional contracts or static demo assets) and add any high-leverage product, reliability, DX, observability, or SOTA capability gaps discovered while reading the codebase. Never stop at 1–3 items when the project has more verified high-leverage work.
   Done when every surviving or added task cites exact `file:line` evidence and states why its leverage is high.
3. **Present the complete, un-truncated High-Leverage Task Map grouped into execution waves.** Order by `Wave 1 (P0)` broken seams, spec/CLI drift & trust boundaries → `Wave 2 (P1)` high-leverage product/SOTA capabilities, hollow stubs, hot-path perf & core architectural multipliers → `Wave 3 (P2)` verification, dead seams & codebase gardening. Never cherry-pick 1–3 tasks or hide the best engineering behind "(Optional hardcore mode)". Each numbered task (`1..N`) includes:
   - Wave, Priority (`P0`/`P1`/`P2`), Subsystem, Category (`capability`, `gap`, `overclaim`, `perf`, `hardcore`, `checks`, `verification`, `gardening`), and `leverage_score`
   - Observed evidence (`file:line`, fan-in/churn, or missing capability seam) and concrete user/system impact
   - A copy-paste-ready **Hardcore Mode full-scope `/deep ...` prompt** (plus a final **"Run Wave 1+2 end-to-end"** `/deep` master prompt when multiple tasks compound).
   Done when 100% of verified high-leverage tasks across the project are surfaced, ranked, and ready to execute.

**Done when** the full-scope repo scan ran cleanly, false positives were pruned, domain/SOTA capability gaps were included, and the complete ranked High-Leverage Task Map is presented without arbitrary top-3 truncation.
