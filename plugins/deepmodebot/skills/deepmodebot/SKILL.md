---
name: deepmodebot
description: "Hardcore Mode engineering orchestrator (/deep, Deepmodebot, non-trivial engineering): LLM autoroute, Confession + Adaptive Prosecutor, quota-safe delegation, real-app proof."
hooks:
  PreToolUse:
    - matcher: "Write|Edit|NotebookEdit"
      hooks:
        - type: command
          command: 'for f in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/deepmodebot/assets/contain/claude-guard.sh" "${CLAUDE_PROJECT_DIR:-.}/.claude/skills/deepmodebot/assets/contain/claude-guard.sh" "$HOME/.claude/skills/deepmodebot/assets/contain/claude-guard.sh"; do if [ -f "$f" ]; then exec "${BASH:-bash}" "$f" enforce; fi; done; exit 0'
---

# Deepmodebot

Paths are relative to this skill (`skill://deepmodebot/...` in omp; elsewhere resolve on disk).

**Cross-harness:** Guards ship for omp, Claude Code, Codex, Antigravity (`skill://agent-harnesses`). Map omp tools: `task` → subagents (or `acpx <agent> exec`), `todo` → tasks, `ask` → one question, `.omp/skills/` → `.claude/skills/` or `.agents/skills/`. Tool limits: `loop.py run` targets `omp|claude|codex`; `pr-agent` needs `omp`; `security-audit` needs `claude` on POSIX.

## Full-scope completion

Applies to M/L and multi-item routes (Size **S** tracks its single item inline). Slicing sequences verification; it never shrinks scope. Full manifest, inventory, sprint/SME checkpoint, and zero-loss resume rules: `references/full-scope.md`.
- Keep 100% of deliverables/inventory in ONE Scope Manifest (`loop.py manifest`, mirrored in `todo`); any `pending` inventory item fails `loop.py manifest`. Only the user removes scope.
- Single-run builds drive `1/N` to `N/N`; Sprint mode (`active_sprint: 1` / `sme_gate: "required"`) pauses ONLY at the explicit sprint/SME checkpoint (`scope_complete: false`, never done). A pause is never completion.

## Route (do this first)

`/deep <anything>` is the zero-human-thought autopilot across `agy`, `omp`, Claude Code, and Codex: the user never needs to pick subcommands (`/research`, `/suggest`, `/tournament`, `/grill`) or engineer prompts.

**0. Decode intent & 1-shot pre-flight clarify (`assets/prompt-tools/prompt_tools.py clarify`).** Decode typos, shorthand, URLs/orgs, and compound asks automatically, and look up repo/doc/runtime facts yourself (never ask what tools can answer).
Only when human intent has `2+` materially different product/scope outcomes or hits an irreversible boundary, ask **once upfront** (`1-3` `(Recommended)`-first choices via `ask_question` / `AskUserQuestion` / `ask` / `request_user_input`; pick `(Recommended)` in `-p` mode), then execute 100% end-to-end without mid-run hand-holding.

**1. Orient & auto-bootstrap.** Use Antigravity's hook-injected offline **workspace-map** overview if present; else run `python -B "<this skill>/assets/workspace-map/workspace_map.py" overview --fast --offline --no-orca` (`py -3 -B` on Windows; writes `<main-checkout>/.scratch/workspace-map.db`).
On non-read-only sessions in an uninitialized repo, auto-run `python -B "<this skill>/assets/setup/project_setup.py" --root "<root>"` to create missing `.deepmodebot/ci.yml`, `.deepmodebot/policy.xml`, `.scratch/deepmode-memory.db`, and managed `AGENTS.md`/`CLAUDE.md` blocks (preserves user text; rewriting conflicting rules needs two owner yeses).
Recall top project memories via `project_memory.py recall --root "<root>" --format xml --budget-tokens 600`. Skip `overview` and bootstrap on strictly read-only routes (`investigation`, local `pr-review`, `pr-thread`, `suggest`) when no DB exists. Run `query <term>` before broad greps; check `git remote`, `docs/PROJECT_BRIEF.md`, `STACK.md`, verify skills, and `gh repo view`. Outside/empty repo: Contain the work.

**2. Route semantically & chain research/gaps (`references/techniques/autoroute.md`).** Run the 3-stage LLM router (`assets/autoroute/autoroute.py menu` → LLM JSON → `autoroute.py verify --strict`, or `autoroute.py route`) and `prompt_tools.py upgrade` on messy asks. Automatically chain **research** / **prior-art** (`gap_audit.py` + `trending.py` + `dmb-net`) when external SOTA/orgs/APIs apply and `deepmodebot gate gap` for repo drift/stubs; re-route mid-flight via `autoroute.py reroute`.

**3. Size & delivery** (re-size if scope grows; delivery != size).

| Size | Scope | Execution |
|---|---|---|
| **S** | <= 30 lines in <= 2 files; no auth, secrets, permissions, trust-boundary parsing, migrations, CI, or agent config | One-line restate, fix, regression if behavioral, real-artifact proof. Local S stays uncommitted; publishing uses S lane + 3-seat 2-of-3 panel. |
| **M** | Few files, one feature or bug with a cause to find | Matched playbook; inline if one owner suffices. Local: uncommitted; publish: Opening a PR. |
| **L** | Cross-cutting, new module, many files, risky, or long-running | Full playbook + subagents, **architect** if shapes differ, **show-me-your-work** trail. |

No remote, local-review ask, or ordinary local S/M edit → **local edit** (uncommitted + diff review + real proof; skips shipping panels/contests unless touching auth/permissions/migrations/security/L). Explicit PR/ship/land/queue asks publish via Opening a PR + 3-seat panel. Worktree only for concurrent writers or dirty unrelated work. Discovery/read-only = size `none`.

**4. Tier, Prosecutor & SME.** Pick smallest benchmark-proven tier (`references/delegation.md`). Run `self_grill.py init --phase plan` before risky coding and `--phase both --refresh` + `self_grill.py bundle` (**Confession + Adaptive Hotspot Prosecutor + Sieve**, `references/techniques/self-grill.md`) on M/L or sensitive diffs before replying. Complex/unclear domains → **sme-review** (+ **questionnaire**) before specs, loops, or Sprint 2+.

**5. Act, CI gate, clean, report.** Follow Autonomy gates/hard stops. When `.deepmodebot/ci.yml` exists, run `assets/local-ci/local_ci.py run --cached` before reporting done or opening a PR, record durable lessons in `project_memory.py`, and run `assets/cleanup/self_cleanup.py --apply` for disposables. Report result and proof.

## Reasoning gates

1. **Before planning:** name user, deliverable, acceptance evidence, sources; separate facts from assumptions, mark gaps unknown.
2. **At phase boundaries & delivery:** check output against goal/evidence for missing items, stale facts, **gaps, and overclaims** (`self_grill.py check-diff` on M/L or sensitive diffs; `verify_proof.py` on formal/math claims); replan if premise fails.
3. **When stalled:** after two attempts without better evidence, pause, inspect real artifacts, test premise, pivot or report blocker. Never drop scope.

## Contain the work

One project root (`git rev-parse --show-toplevel`) per task; every write stays inside it (`references/contain.md`). Temp in `<root>/.scratch/tmp/` (scope `TMPDIR`/`TMP`/`TEMP` there; never system temp/home/siblings); worktrees in `<main>/.worktrees/<branch>/`; run Python with `-B` / `PYTHONDONTWRITEBYTECODE=1`. Global installs and user-config edits are hard stops.
Outside writes allowed only for new repo folder, tool-managed state (`local://`/`artifact://`, Antigravity `brain/`, caches), `.deepmodebot.json` `"extraWriteRoots"`, and deepmodebot's own outside writes. Guards back file tools (rule still binds shell). Clean session disposables via `assets/cleanup/self_cleanup.py --apply`.
## Non-negotiables

For **S**, only one-line restate, single-item scope check, real-artifact proof, and (if landing) S lane apply.
- **Restate first** (goal, problem, smallest change) without waiting; track 100% scope (`references/full-scope.md`).
- **Hardcore mode by default (`references/principles/hardcore-mode.md`):** build the first-principles architectural ceiling (real algorithms, solvers, parallelism, full integration) rather than stubs/toy MVPs unless asked.
- **Name principles:** on M/L, add "Why I chose this" naming each read principle (`references/principles/`) that changed a decision.
- **Prove on the real artifact (E2E Rehearsal Gate):** run the real app/CLI/service; tests alone are not proof. For E2E workflows (any app/tool/UI), grill & lock user intent first (`assets/e2e/rehearsal_gate.py init` + `approve`), record the full continuous video, watch the entire video together (never isolated frames alone), and iterate `v1..v25` until `rehearsal_gate.py verdict --strict` returns `REHEARSAL_PASSED`.
- **Clarify once upfront, then decide autonomously:** repo/doc/code fact → look up yourself; empirical engineering fork → Prototype; genuine human-intent ambiguity (`2+` distinct user outcomes) → ask `1-3` `(Recommended)`-first choices once before coding, then drive to 100% completion with zero interruptions.
- **Secrets/logins/auth** → read `skill://secrets-and-auth` first; never print/paste/commit secrets.
- **Name data shape first** (`references/principles/model-the-domain.md`; new domains/DBs/layouts → `skill://software-architecture`).
- **No lying comments:** zero narration/banner/workaround comments; run **no-comments** before review. Long work → **show-me-your-work**.
- **UI & Operate craft (`skill://frontend-ui`):** enforce 2-round `ui_audit.py` + clean-context critique, 3-seed OKLCH themes (`Accent`, `Background`, `Contrast`), directional trigger origins + submenu safe polygons, roving tiered tooltips, frozen-order multi-select pickers, anti-Christmas-tree stillness, and zero-spinner local state on daily Operate views.
- **PR & gate layer:** **pr-review** before opening (with **Intent-First Diff Guides** + **Meaningful-LOC** breakdown); **pr-agent** + local checks once open; land own PRs via **pr-conversation**; incoming PRs via `/deepmodebot:review-pr <PR>`; **security-audit** on auth/permissions/parsing/secrets (blocking = P0). No hosted review bots.

## Autonomy & Subagents

- **Own PRs land on their own** via **pr-conversation** once findings resolve, linked issues are answered, exact-head **panel** (`references/techniques/panel.md`: 3 verifiers, >=2 passes, including S lane) passes, and checks are green. Merge via `gh pr merge --match-head-commit <sha>`, verify trunk, revert if red.
- **Admin merge:** only on explicit land/merge ask or `"autonomousMerge": true`; `--admin` may bypass only a required review after exact-head panel pass, never failing checks or non-review rules.
- **Decisions & hard stops:** pick smallest reversible codebase-consistent choice and log under "Decisions I made". Hard stops (batch once at end): force-push/history rewrite on shared/default branch; deleting others' branches/data; deploys/releases/publishing; external messages; bypassing forge protections; spending money; user-only credentials; outside-root writes; rewriting repo rule files (two owner yeses).
- **Subscription, not API:** logged-in subscriptions only; unset all provider API key env vars in child processes. Tick waypoints and keep moving; say "no" when warranted.
- **Subagents & quota (`references/delegation.md`, `assets/quota-guard/quota_guard.py`):** delegates own exclusive files and start briefs with `Read <this installed skill>/worker.md before anything else.`; never stack `/teamwork`/`/swarm` with multi-seat waves (`max_subagents=0` when nested); pin low-tier models (`flash`/`flash_lite`, `@smol`, `haiku`/`sonnet`, `gpt-6-luna`) for scouts, helpers, `reviewer`, `security-reviewer`, and `panel` verifiers (`2-4` turns, never `inherit` Carbon/Opus/Pro); keep `<=150`-line work inline; run 3-seat panel only at final merge SHA.

## Routes

Techniques: `references/techniques/<name>.md`; playbooks: `references/playbooks/<file>.md`. Full 30-playbook / 70-technique / 25-principle catalog: `references/catalog.md`.

- **PRs, releases & migrations:** review PR / "review since <ref>" → **pr-review**; land own PR → **pr-conversation**; aging/stale PR → **modernize-pr**; bot issue work → **issue-conversation**; bots on own sub → **github-app**; get green → `babysit`; security gate → **security-audit** (`static_sec_audit.py` + **variant-analysis**); run pr-agent → **pr-agent**; zero-downtime DB/API cutover → **expand-contract**; post-deploy canary & release docs → **release-and-canary**.
- **Contributing & repos:** read-only repo → `skill://contribute`; publish for helpers → `skill://project-brief`; repo setup → `setup`; DX/CLI onboarding audit → **devex-review**; triage → `triage`; spec → `spec`; tickets → `tickets`; implement spec/sprints → `phased-build`; full project → `end-to-end`.
- **Queues, goals & orientation:** `factory.json`/board/PR queue → `work-a-queue`; session/program goal → `run-a-goal`; vague goal → **goal-review** → `self-authoring`; harden checks/anti-slop → **inner-loop**; index repo/worktrees/PRs/symbols → **workspace-map**; foggy multi-session → `wayfinder`; handoff → `handoff`.
- **Prompts, audits & checks:** LLM router → **autoroute**; upgrade prompt → **prompt-upgrade**; expert words / problem disambiguation → **reframe**; founder/ambition check → **product-lens**; scan repo gaps/overclaims → **suggest**; grill plan → **grill**; "are you sure" / gaps / overclaims → **self-grill** (`bundle` Prosecutor); kill weak tests / fuzz → **mutation-testing**; stuck → `bug-fix` + **self-grill**; blast radius → **blast-radius**; deepen → **sharpen**.
- **Formal proofs & statecharts:** Lean/Rocq/TLA+/SMT/Claim-DAGs → **formal-verification** (`verify_proof.py`); TLA+ model + Mermaid statechart → `skill://statechart`; author/maintain project formal verify skill → `skill://create-formal-verification-skill` / `skill://maintain-formal-verification-skill`.
- **Design, stack, SEO & Office docs:** open gaps/vague ambition → **tournament**; 2+ shapes → **architect**; contested design → **interrogate**; new app → **prior-art** (`scripts/trending.py`) → `skill://deep-stack` → `end-to-end`; SEO/GEO/`llms.txt`/Schema.org/Agentic Browsing → `skill://seo-and-geo` (`seo_audit.py`); `.xlsx`/`.pptx`/`.docx`/`.pdf` → `skill://office-documents` (`doc_audit.py`); catch up → **recall** (video → **catchup-video**); glossary/ADR → **domain-model**; research → `skill://research` (**research**); SME → **sme-review** / **questionnaire**.
- **UI, E2E, perf & media:** A2UI (`a2ui.org`) / cockpit → **gen-ui**; webhook/Tailscale bot UI → **webhook-ui**; E2E full-video rehearsal gate (`v1..v25`, `REHEARSAL.md`) → `assets/e2e/rehearsal_gate.py` + **visual-e2e**; Penpot/editable design → **open-design-evidence**; backend/DB/API slowness, N+1, pools, hot loops → `perf-issue` (`assets/perf-audit/perf_audit.py` + **benchmark-checklist** + `skill://domain-rules`); video breakdown (`rea-video`/`VIDEO.md`) → **video-forensics**.
- **Build, CI, slop & memory:** parallel gates (`deepmodebot gate slop|ci|perf|ui|seo|docs|sec|cleanup|agents|skill-check|map|guard|gap`; `native/dmb-net`: `trending|pr-overlap|fetch-papers|webhook`) with Python fallbacks (`local_ci.py`, `slop_gate.py`, `gap_audit.py`, `project_memory.py`, `project_setup.py --install-hooks`); per-role model & budget setup → **model-setup** (`model_setup.py`); TDD → **tdd**; comments → **no-comments**; prose → **unslop** + **technical-writing**; garden → **correct**; fan-out → **swarm**/**arena**; port → `refactoring`.
- **Skills, rules & meta:** edit `SKILL.md` → `authoring-a-skill` (**writing-for-agents** first); edit `AGENTS.md`/`CLAUDE.md`/brief → **writing-for-agents** (`assets/agents-md/agents_md.py`); prompt/loop → `self-authoring`; specialist (`tool-routing`, `git-guardrails`, `pre-commit`, `scrape`, `architecture-review`, `wizard`, `course`, `re-explain`, `reflect`, `retro`, `tracker`, `agent-collaboration`) → named technique.
## Playbooks & Principles

List matched playbook steps (`<n>. <short imperative>`) in `todo`; note skips. Read `references/principles/<name>.md` before citing. Full tables: `references/catalog.md`.

- **Diagnose:** `investigation`, `bug-fix`, `perf-issue`, `hillclimb`, `runtime-forensics`, `trace-forensics`.
- **Build & Meta:** `feature`, `end-to-end`, `refactoring`, `prototype`, `visual-parity`, `reference-rebuild`, `authoring-a-skill`, `self-authoring`, `eval`.
- **Plan, Ship & Continuity:** `setup`, `spec`, `tickets`, `triage`, `phased-build`, `wayfinder`, `babysit`, `shipping`, `opening-a-pr`, `run-a-goal`, `work-a-queue`, `session-pickup`, `pause-safely`, `handoff`, `worktree-cleanup`. Bespoke large effort → **figure-it-out**.
- **Principles (Core & Architecture):** `hardcore-mode`, `laziness-protocol`, `foundational-thinking`, `redesign-from-first-principles`, `attack-the-premise`, `subtract-before-you-add`, `minimize-reader-load`, `outcome-oriented-execution`, `experience-first`, `exhaust-the-design-space`, `build-the-lever`; `model-the-domain`, `boundary-discipline`, `type-system-discipline`, `make-operations-idempotent`, `migrate-callers-then-delete-legacy-apis`, `separate-before-serializing-shared-state`.
- **Principles (Verification, Delegation & Meta):** `prove-it-works`, `fix-root-causes`, `sequence-verifiable-units`, `test-behavior-not-implementation`, `explain-the-number`; `guard-the-context-window`, `never-block-on-the-human`, `encode-lessons-in-structure`.

## Reference library

Read entry skill first; full index: `references/README.md`:
- UI/motion/color/a11y/chat/A2UI → `skill://frontend-ui`; stack/UI design/proof → `skill://deep-stack`; SEO/GEO/Schema.org/`llms.txt`/Agentic Browsing → `skill://seo-and-geo`
- Spreadsheets (`.xlsx`), slide decks (`.pptx`), Word docs (`.docx`), and PDFs (`.pdf`) → `skill://office-documents`
- Harnesses (omp/Claude/Codex/Antigravity), MCP/ACP, tiers → `skill://agent-harnesses` (`langchain-ecosystem.md`, `ai-sdk-selection.md`)
- Secrets/logins/MFA/OAuth/auth → `skill://secrets-and-auth`; repo/domain/DB/pools/backend → `skill://software-architecture`
- Agents/LLMs/AWS/high-scale backend/cache/languages/DevOps/debug → `skill://domain-rules`
- Docker/K8s/cloud/IAM/policy/pipelines/IaC/emulators → `skill://cloud-devsecops`
- Deep learning, RL, neural nets, world models, geometric/SciML & weight-space programming (`wsp.py`) → `skill://deep-learning`
- Build an agent control adapter for a desktop, terminal, mobile or headless app → `skill://app-automation-relay`
- TLA+ statechart compiler & formal verification lifecycle → `skill://statechart`, `skill://create-formal-verification-skill`, `skill://maintain-formal-verification-skill`

## Writing the reply

- Short declarative sentences, one thought each; no long dashes or mid-sentence colons (colons before lists ok).
- Keep required playbook sections; lead with consumer/maintainer impact before detail.
- Never fabricate links/citations/outputs; link only what you produced/read; never overclaim (counts/guarantees must match fresh observed runs); label claims (measured, inferred, guess); never hand off checks you can run.
- **No machinery.** Omit skills, playbooks, routes, sizes, verify bookkeeping, pre-authorizations, models/subagents, internal codes unless required by a playbook section or "Why I chose this". Report result, proof, risks, blockers; mention machinery only when it affects trust.
