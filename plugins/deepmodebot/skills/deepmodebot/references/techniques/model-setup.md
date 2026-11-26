# model-setup

**Use when:** configuring which models and reasoning budgets deepmodebot uses per role across omp, Claude Code, Codex, or Google Antigravity ("configure models", "model budget", "per-role models", or updating role defaults).

1. **Detect entitled models.** Enumerate model slugs actually callable by subagents or CLI (`omp`, `claude`, `codex`, `agy`) in this session, or run `python -B "<this skill>/assets/setup/model_setup.py" inspect --root "<root>"`. Ask the user to paste slugs only when detection is unavailable. Never write an unverified concrete slug; `inherit-parent` and `auto` are always valid aliases.
2. **Load & migrate existing config.** Read `<root>/.deepmodebot/models.json` if present (`defaults_version: 3`), dropping retired roles (`hardest tasks`, `architect runners`, `reflect tooling`, `why investigators`) and upgrading stale legacy defaults while preserving custom user choices:
   - Cap `# budget: unlimited` to `large` (`xhigh`; no role runs above `xhigh`).
   - Upgrade legacy Gemini panel seats (`gemini-4-neon-high` or older non-Neon `gemini-4-*` in `arena_runners`, `arena_cross_judge_pool`, `interrogate_reviewers`) to `gemini-4-neon-xhigh`.
   - Replace single-vendor Claude-only `arena_cross_judge_pool` lists (`claude-fable-*` + `claude-opus-*` share one vendor) with cross-vendor defaults (`claude-opus-5-5-high-fast`, `gemini-4-neon-xhigh`).
3. **Select reasoning budget & map effort.** Choose `large` (`xhigh`, default), `medium` (`high`, -1 step), or `small` (`medium`, -2 steps) on `xhigh > high > medium > low`, shifting real slugs (`claude-opus-5-5-*-fast` keeps `-fast`; `claude-fable-5-2-*` and `gemini-4-neon-*` have no `-fast` or `max` slug; `inherit-parent`/`auto` stay unchanged) via `model_setup.py plan --budget <large|medium|small>`.
4. **Validate & write idempotently.** Confirm every concrete slug is in the detected set at `<=xhigh` (`arena_cross_judge_pool` excludes `inherit-parent`/`auto` and orders cross-vendor judges by preference), then write `<root>/.deepmodebot/models.json` via `model_setup.py write` (read automatically by `autoroute.py`).
5. **Offer verification skills once (optional).** If the repo has no `verify-*` app harness skill, offer `skill://create-verification-skill` once; if it has no formal model/prover skill, offer `skill://create-formal-verification-skill` once.

**Done when** `.deepmodebot/models.json` is validated and written idempotently with `defaults_version: 3` and `<=xhigh` verified slugs, migrated entries are reported, and optional verification-skill offers are handled without nagging.
