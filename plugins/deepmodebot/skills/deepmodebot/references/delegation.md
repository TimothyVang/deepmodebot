# Subagents, model tiers & quota guard

Read before spawning subagents or running multi-seat reviews/panels.

- **Brief contract:** You run the playbook; delegates own exclusive files. Start every subagent brief with `Read <this installed skill>/worker.md before anything else.` plus goal, absolute root, exact files, acceptance check, root-only writes, and applicable `references/principles/<name>.md` (omp omits `AGENTS.md`). Inspect every delegate's diff yourself.
- **Anti-stacking & quota cap (`assets/quota-guard/quota_guard.py plan`):** Never stack `/teamwork` or `/swarm` on top of multi-seat review/panel waves; if already inside an outer orchestrator or child subagent, run deterministic scripts and 4-lens review inline in 1 pass (`max_subagents=0`).
- **Model & effort tiers (Opus-first, cap `xhigh`; `skill://agent-harnesses/references/delegation-efficiency.md`):**
  - `S` (`low`/`medium`): search, mechanical work, local S.
  - `M` (`medium`): oracle-backed M.
  - `L` (`high`/`xhigh`, never above `xhigh`): planning, hard debug, security, final review.
  - Fable 5.2 outside panels runs only when named or after two `xhigh` failures on the same brief; skip Fast/Ultrafast.
- **Pin low-tier models on ALL scouts, reviewers & verifiers (never `inherit` Carbon/Opus/Pro onto overhead):** Pass `Model: "flash_lite"` / `@smol` / `haiku` / `gpt-6-luna` for `scout`/`Explore`/`explorer`, and `Model: "flash"` / `@smol` / `haiku` (`sonnet` max) / `gpt-6-luna` for `comment-sicko`, mechanical slices, `reviewer`, `security-reviewer`, `self-grill` Prosecutor, and `panel` verifiers (`2–4` batched tool turns max). Reserve `inherit` / `pro` / Opus / Astra strictly for the main agent and hard `L` coding slice authors (or when the user explicitly requests high-tier review).
- **Delegate only when it pays:** Multi-agent runs cost ~15x chat + cold cache. Keep `<=150`-line, 1-file, coupled, and hard reasoning inline; use 1 `prosecutor-bundle.md` `flash`/`@smol` reviewer for `M` (`151–600` lines), delta-only re-review (`git diff <last_sha>..HEAD`), `<=2` parallel worktrees, and `.scratch/quota-guard/` checkpoints to prevent `429` cold respawns.
- **Panel seats & quota hygiene:** Reserve the 3-seat panel strictly for the final green merge SHA, and pin verifiers to fast low-tier models (`Model: "flash"` in Antigravity; `@smol` / `claude-haiku-5-5-high` / `gpt-6-luna` / `gemini-4-flash` across families when available; escalate to `opus`/`fable`/`neon-xhigh` only when explicitly requested by the user). Check quota (`omp usage`/`/usage`/`/status`), `/clear` between tasks, switch models at clean boundaries, reuse warm reviewers, and rotate family on 429s.
