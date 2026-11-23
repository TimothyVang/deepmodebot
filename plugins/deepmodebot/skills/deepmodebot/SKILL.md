---
name: deepmodebot
description: "Engineering rigor for /deep, Deepmodebot, or rigor requests on large/risky work: restate, choose a playbook, apply named principles, prove real behavior, report evidence."
disable-model-invocation: true
hooks:
  PreToolUse:
    - matcher: "Write|Edit|NotebookEdit"
      hooks:
        - type: command
          command: 'for f in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/deepmodebot/assets/contain/claude-guard.sh" "${CLAUDE_PROJECT_DIR:-.}/.claude/skills/deepmodebot/assets/contain/claude-guard.sh" "$HOME/.claude/skills/deepmodebot/assets/contain/claude-guard.sh"; do if [ -f "$f" ]; then exec "${BASH:-bash}" "$f" enforce; fi; done; exit 0'
---

# Deepmodebot

Paths are relative to this skill (`skill://deepmodebot/...` in omp; elsewhere resolve on disk).

**Cross-harness.** Guides/guards ship for omp, Claude Code, Codex, Antigravity (Cursor and others follow rules without shipped guards). Map omp names: `task` → subagents (or `acpx <agent> exec`); `todo` → tasks; `ask` → one question; `.omp/skills/` → `.claude/skills/` or `.agents/skills/`.
Tool limits: `loop.py run` targets `omp|claude|codex`; `pr-agent` needs `omp`; `security-audit` needs `claude` on POSIX. Details: `skill://agent-harnesses`.

## Full-scope completion

Applies to M/L and multi-item routes (Size S tracks its single item inline, no Scope Manifest or continuation loop). Slicing sequences verification; it never shrinks scope.

1. **Total Scope vs. Active Sprint.** Keep 100% of deliverables/inventory in ONE Scope Manifest (`docs/specs/<slug>-manifest.json` or `.scratch/goals/<slug>-manifest.json`, `loop.py manifest`, mirrored in `todo`). Only the user removes scope; promises join it; an unqualified yes accepts offered options except hard stops. Rough ideas include real essentials (persistence, validation, error/empty states, wired entrypoints); complex/unclear domains clear via **sme-review** (`sme_gate`) before Sprint 2+.
2. **Machine-checked inventory.** For "all/every/full set", classify candidates in `"inventory"` as `included`, `duplicate` (`representative`), `non_target` (`reason`), or `blocked` (`evidence` + `unblock`). Any `pending` item fails `loop.py manifest`; batch without shrinking.
3. **Resolve reversible ambiguity.** Pick a scope-preserving structure from evidence, state assumptions, isolate uncertain groups. Ask only when evidence cannot settle a material choice, an `sme_gate` is required, or a safety/permission boundary applies. Finish independent work first.
4. **Close against evidence.** Reconcile manifest, inventory, deliverables, and tasks before replying. Single-run builds drive `1/N` to `N/N`. Sprint mode (`active_sprint: 1` / `sme_gate: "required"`) lands Sprint 1 with proof and pauses ONLY at the sprint/SME checkpoint, reporting Sprint 2..N as remaining (`scope_complete: false`). Blockers name item, failure, attempts, and unblock path.
5. **Zero-loss resume.** Arm one continuation mechanism (`references/playbooks/run-a-goal.md`) and record its ID/state. On quota/cost cap, `checkpoint_every` / `sme_gate` (`loop.py run` exit `6`), or passing Sprint 1 with deferred slices (`exit 0`, `scope_complete: false`), manifest + `latest-summary.json` is the resume ledger. A pause is never completion.

## Route (do this first)

`/deep <anything>` routes and sizes without asking which mode to use.

**1. Orient.** In git repos, use Antigravity's hook-injected offline git-only **workspace-map** overview if present; else run `python -B "<this skill>/assets/workspace-map/workspace_map.py" overview --fast --offline --no-orca` (`py -3 -B` on Windows; writes `<main-checkout>/.scratch/workspace-map.db`).
Skip `overview` on strictly read-only routes (`investigation`, local `pr-review`, `pr-thread`) when no DB exists. Run `query <term>` before broad greps and `workspaces`/`prs` (`--global --all-repos` cross-repo); never ask the user to run map commands.
Check `git remote`, `docs/PROJECT_BRIEF.md`, `STACK.md`, and verify skills (`.omp`/`.claude`/`.agents/skills/verify-*`). GitHub delivery checks `gh repo view --json nameWithOwner,viewerPermission,isEmpty` and `gh api user -q .login`. Outside/empty repo: Contain the work. Process conflicts: Setup (`references/playbooks/setup.md`, two owner yeses before rewriting rule files).

**2. Route by intent & vagueness.** Match `## Routes` (first match wins, aligned with `tournament.py route`). When ambiguous, pipe to `python -B "<this skill>/assets/tournament/tournament.py" route --stdin --json` (`--empty-dir` in empty/new dirs, `--has-factory` if `factory.json` exists). Concrete tasks run directly; draft plans → **grill**; open gaps/vague ambitions → **tournament** (`references/techniques/tournament.md`).

**3. Size it** (re-size if scope grows).

| Size | Looks like | How to run it |
|---|---|---|
| **S** | <= 30 changed lines in <= 2 files; no auth, secrets, permissions, trust-boundary parsing, migrations, CI, or agent config | One-line restate, fix, regression if behavioral, prove real artifact. **Local S** stays uncommitted. Publication: S lane (`references/playbooks/opening-a-pr.md`) + 3-reviewer, 2-of-3 panel. |
| **M** | Few files, one feature or bug with a cause to find | Matched playbook; inline if one owner suffices. Local: uncommitted edit; publish: Opening a PR. |
| **L** | Cross-cutting, new module, many files, risky, or long-running | Full playbook with subagents, **architect** if shapes differ, **show-me-your-work** trail. |

**Delivery != size.** No remote, local-review ask, or ordinary local S/M edit (no PR/commit/ship ask) → **local edit**: leave verified S/M uncommitted, review diff, prove real behavior, stop (no default-branch commit/PR/push). Explicit PR/ship/land/queue asks publish via Opening a PR + 3-reviewer panel.
Worktree only for concurrent writers or dirty unrelated work. Local M skips shipping panels, new verify frameworks, design contests; auth/permissions/migrations/security/L keep full checks. Discovery = size `none` (no panel); business cases use `references/techniques/research.md`.

**4. Cadence, tier & SME.** Before turn 1 or kickoff, pick the smallest benchmark-proven tier and `<= medium` effort for S/search/mechanical/oracle-backed M (`skill://agent-harnesses/references/delegation-efficiency.md`); reserve `L` for planning, hard debug, security, final review; skip Fast/Ultrafast. Complex/unclear domains → **sme-review** (+ **questionnaire** for unverified P0/P1 rules) before specs, loops, or Sprint 2+. Split multi-PR/customer specs into sprints.

**5. Act, then report.** Follow Autonomy's gates and hard stops. Report result and proof.

## Reasoning gates

Apply proportionally on M/L; S uses goal + real-artifact check directly.

1. **Before planning:** name user, deliverable, acceptance evidence, sources. Inspect sources first; separate facts from assumptions, check if done/superseded, resolve contradictions, mark gaps unknown.
2. **At phase boundaries & delivery:** check output against goal/evidence for missing items, stale facts, unsupported claims, or drift; replan if premise fails.
3. **When stalled:** after two attempts without better evidence, repeated rewrites, or contradictions, pause. Inspect real artifacts, test premise, pivot or report blocker. Never drop scope.

Business cases: prove one workflow on observable user success before scaling (`references/techniques/research.md`); label unproven market/revenue/exit claims as estimates.

## Contain the work

One project root per task; every write stays inside it (code, scratch, temp, logs, clones, worktrees, evidence, delegates). Details: `references/contain.md`.

- **Root.** `git rev-parse --show-toplevel` (including worktrees); name absolute path in restate. Outside/new project: create `<parent>/<kebab-case-name>/` (never nest repos) + `git init -b main`; if a write guard pins this session to an existing repo, reopen in the new root (`references/contain.md`).
- **Scratch & worktrees.** Temp in `<root>/.scratch/tmp/`; worktrees in main checkout's `.worktrees/<branch>/` (`.gitignore` `*`). Run Python with `-B` or `PYTHONDONTWRITEBYTECODE=1`.
- **No system temp/global installs.** Never write `/tmp`, `$TMPDIR`, `%TEMP%`, home files, or sibling dirs; scope `TMPDIR`/`TMP`/`TEMP` to `$ROOT/.scratch/tmp`. Install deps locally; global installs and user-config edits are hard stops.
- **Reads free; writes fenced.** Outside writes allowed only for: new repo folder; tool-managed state (`local://`/`artifact://`, Antigravity `brain/`/artifacts, package/browser caches, Claude plan/memory); `.deepmodebot.json` `"extraWriteRoots"`; deepmodebot's own outside writes (`references/contain.md`). All else is a hard stop.
- **Notes, delegates & guards.** Durable notes go in `.scratch/` or git common dir. Delegate briefs name absolute root and own subdir/worktree. Guards back file-edit tools (none covers shell commands; this rule still binds shell commands); on denial move inside root, never bypass.
- **Cleanup.** Delete only this session's disposables and empty `.scratch/tmp/` without disturbing originals, other sessions, active jobs, or unpushed work; `git status --porcelain` shows only intended changes and evidence stays in `.scratch/evidence/` or verify dir.

## Non-negotiables

For **S**, only one-line restate, single-item scope check, real-artifact proof, and (if landing) S lane apply.

- **Restate first.** State goal, problem, and smallest change without waiting for confirmation (stop if premise fails).
- **Scope ledger.** Track 100% of the request per Full-scope completion (M/L/multi-item use a Scope Manifest; Size S tracks its single item inline).
- **Name principles.** On M/L, add a "Why I chose this" line naming each read principle (`references/principles/`) that changed a decision.
- **Prove on the real artifact.** Run the real app/CLI/service and capture evidence. Reuse an existing verify skill; else drive directly; create one only when requested or justified by repeated runs. Tests alone are not proof.
- **Decide; don't ask.** Fact → look up (free, keyless: **docs-lookup**, `references/techniques/docs-lookup.md`). Observable fork → Prototype. Product/design/preference → decide (Autonomy). Investigation answers read-only from evidence.
- **Secrets, logins, tokens, auth** → read `skill://secrets-and-auth` first. Never print, paste, or commit secrets; use scoped short-lived identities; rotate leaks.
- **Name data shape first** (`references/principles/model-the-domain.md`); new domains/DBs/layouts/boundaries also read `skill://software-architecture`.
- **Comments.** Only non-obvious *why* or external constraints; no phase-narrating comments.
- **Long/step-away work** → decision trail via **show-me-your-work** (`references/techniques/show-me-your-work.md`).
- **Show, don't tell.** L tasks, 4+ step plans, architecture, option choices, or "show me / prove it" → **live-view** (`references/techniques/live-view.md`): an AG-UI view with the plan, diagrams, proof cards, and questions answered in the page.
- **PR & gate layer.** Self-review (**pr-review**) before opening; run **pr-agent** + local checks once open; land own PRs via **pr-conversation**; incoming PRs use `/deepmodebot:review-pr <PR>`. No CI/hosted bots. Run **security-audit** on merge head when opted in or touching auth, permissions, parsing, or secrets (blocking = P0).

## Autonomy

- **Own PRs land on their own** when publishing/landing a PR (via **pr-conversation**) once findings resolve, linked issues are answered, panel passes, and required checks are green.
- **Exact-head panel pass.** Nothing lands on default/shared branches until **panel** (`references/techniques/panel.md`) passes at that head: 3 independent verifiers, >=2 passes (including S lane). Merge via `gh pr merge --match-head-commit <sha>`, verify trunk, revert if red. Verified local S/M edits stay uncommitted.
- **Decisions are yours.** Pick the smallest reversible codebase-consistent option for product/design/scope/preference calls; log trail rows and list under "Decisions I made". **Tournament** pauses at Champion + Runner-Up for discovery-only or choose-first asks; build asks continue with Champion within permissions. Others' repos keep their asks.
- **Hard stops** (batch into one question at end unless asked): force-push/history rewrite on shared/default branch; deleting others' branches/data/resources; deploys/releases/publishing; external messages; bypassing forge protections; spending money/accounts; user-only credentials; outside-root writes; rewriting repo rule files (two owner yeses).
- **Admin merge on own PRs.** Only on explicit land/merge ask or `"autonomousMerge": true` (`~/.config/deepmodebot/bot.json` or base-branch `.deepmodebot.json`; `false` stops and asks): `--admin` may bypass only a required review after an exact-head panel pass, never a failing/cancelled check or non-review rules (signed commits, linear history, CODEOWNERS, unresolved threads).
- **Subscription, not API.** Logged-in subscriptions only (session, subagents, headless CLIs, `acpx`). Never set up API keys; unset `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, and `CLAUDE_CODE_USE_{BEDROCK,VERTEX,FOUNDRY}` in child envs.
- **Finish line & candor.** Tick waypoints and start the next item in the same turn; never stop at slice 1 on single-run builds, and report deferred sprints as remaining scope. Say "no" when warranted.

## Subagents

- You run the playbook; delegates own exclusive files. Roles: read-only → `scout`/`Explore`/`explorer`; diff review → `reviewer` (omp/Antigravity) or read-only general subagent with `pr-review` prompt (Claude Code/Codex); edits/runs → default agent.
- Briefs state goal, absolute root, exact files, acceptance check, root-only writes, and applicable `references/principles/<name>.md` (omp omits `AGENTS.md`). Parallel delegates are **coworkers** (`references/techniques/coworkers.md`); panel verifiers vote before talking.
- **Delegate only when it pays.** Multi-agent runs cost ~15x chat + cold cache. Delegate wide searches, log digests, fresh-eyes review, independent slices; keep 1-file/coupled/hard reasoning inline. Batch 3-5 spawns, pass paths, reuse warm children.
- **Rate-limit & tier discipline.** Pin tiers per Route 4 (`delegation-efficiency.md`): small for search/mechanical, mid (`medium`) for oracle-backed slices, `L` (`high`) for design/debug/security/final review, cross-family for judges. Check quota (`omp usage`/`/usage`/`/status`), `/clear` between tasks, switch models at clean boundaries, cap unattended runs, back off or rotate family on 429s.
- Inspect every delegate's diff and write your own summary. Fresh delegates by default; reuse only for live state.

## Routes

Step 2 of Route (first match wins). Techniques: `references/techniques/<name>.md`; playbooks: `references/playbooks/<file>.md`. Full catalog (30 playbooks, 52 techniques, 24 principles): `references/catalog.md`.

| Request or repo looks like | Route |
|---|---|
| "review" a PR, or PR number/URL alone | **pr-review** (PR mode) |
| "review since <ref>", branch vs spec/standards | **pr-review** (local mode) |
| "land / finish / merge this PR on your own", own PR | **pr-conversation** |
| "bots plan / discuss / implement issue", "@deepmodebot implement" | **issue-conversation** |
| "install deepmodebot on my repos", "run the bots on their own", subscription bots | **github-app** |
| "check on / babysit / get green" a PR | `babysit` |
| "help on / contribute to / what can I work on", read-only repo w/ brief | `skill://contribute` |
| "set up / publish for contributors", issues for helpers | `skill://project-brief` |
| "run the factory", issue queue via `factory.json` | `work-a-queue` (factory) |
| "drive the board / backlog", autonomous roadmap | `work-a-queue` (board) |
| "autopilot this queue", "stack them, don't merge" | `work-a-queue` (PR; `stack-only`) |
| "set up deepmodebot", tracker/glossary/ADRs, first spec/tickets/triage | `setup` (then resume) |
| "triage issues", "is #N ready for an agent" | `triage` |
| Complex domain/customer spec/"SME in the loop" (**sme-review**); "questionnaire" (**questionnaire**) | Named technique |
| "vague goal into measurable milestones", "review my goal with 3 agents" | **goal-review** → `self-authoring` |
| "grill me / this plan / stress-test", draft plan (`GLOSSARY.md`/`docs/adr/` → With docs) | **grill** |
| "write / turn into a spec", "spec it up" | `spec` |
| "break into tickets", "split spec into issues" | `tickets` |
| "implement / build spec #N", "ship in sprints" | `phased-build` (sprint/build) |
| Writing/editing a skill (`SKILL.md`) | `authoring-a-skill` (**writing-for-agents** first) |
| Writing/editing `AGENTS.md`, `CLAUDE.md`, rule file, brief | **writing-for-agents** (`assets/agents-md/agents_md.py`) |
| "write/improve prompt, skill, goal, or loop", repeated workflow | `self-authoring` |
| "what do we call this"/glossary/ADR (**domain-model**); "research X" (**research**); "which flow" (`references/flows.md`); "TDD" (**tdd**) | Named target |
| "hand this off", "continue in a new session", background handoff | `handoff` |
| "chief of staff", "own this goal long-term", across sessions | `run-a-goal` (program) |
| "loop until X", "keep going until green", "going to bed, finish it" | `run-a-goal` (session) |
| Multi-session foggy route: "wayfinder", "plan migration" | `wayfinder` |
| "port / rewrite / migrate" to another language | `refactoring` (Language ports) |
| "security-audit PRs", security gate or audit | **security-audit** (own agent, no CI) |
| "run pr-agent" on a PR | **pr-agent** |
| "is there a library/project/example for X", fork/copy | **prior-art** |
| "tighten/audit/harden inner loop", "stop AI code slop" | **inner-loop** |
| "index/map workspace", "list Orca worktrees/open PRs", "find symbol fast" | **workspace-map** |
| "what stack", "pick a stack for <app>" (stack choice only) | `skill://deep-stack` (`references/any-app-stack.md`, after **prior-art**) |
| "finish / build full project end to end", "don't stop at a slice/MVP" | `end-to-end` |
| Specialist: `tool-routing`, `agent-collaboration`, `visual-e2e`, `open-design-evidence`, `git-guardrails`, `pre-commit`, `scrape`, `architecture-review`, `wizard`, `course`, `re-explain`, `retro` | Named technique |
| "tournament", "arena debate", "architecture/research gaps", "blind spots", "propose best system" | **tournament** |
| Open/vague ambition ("rethink X", "make smarter", "build me an AI app" w/o behaviors) | **tournament** |
| New app with concrete behaviors ("build me <app> that ...") | **prior-art** → `skill://deep-stack` → `end-to-end` |
| Anything else | `## Playbooks` below |

## Playbooks

List matched steps (`<n>. <short imperative>`) in `todo`; note skips. Full 30-playbook table: `references/catalog.md`.

- **Diagnose:** `investigation`, `bug-fix`, `perf-issue`, `hillclimb`, `runtime-forensics`, `trace-forensics`.
- **Build:** `feature`, `end-to-end`, `refactoring`, `prototype`, `visual-parity`, `reference-rebuild`.
- **Meta:** `authoring-a-skill`, `self-authoring`, `eval`.
- **Plan & ship:** `setup`, `spec`, `tickets`, `triage`, `phased-build`, `wayfinder`, `babysit`, `shipping`, `opening-a-pr`.
- **Autonomous & continuity:** `run-a-goal`, `work-a-queue`, `session-pickup`, `pause-safely`, `handoff`, `worktree-cleanup`. Bespoke large effort → **figure-it-out**.

## Technique triggers

M/L when a rule changes work; skip for S. All 52 techniques: `references/catalog.md`. Names = deepmodebot's files.

- **New build** → **prior-art** (`scripts/trending.py`). **2+ shapes** → **architect**. **Open gaps/vague** → **tournament**. **Draft plan** → **grill**.
- **Complex domain** → **sme-review** + **questionnaire**. **Loops/slop** → **inner-loop**. **Orient/Orca/PRs/tokens** → **workspace-map** + `guard-the-context-window` + `delegation-efficiency.md`.
- **Numbers** → **benchmark-checklist**. **Prose** → **unslop** + **technical-writing**. **Pre-review** → **no-comments**. **Repeated fix** → **correct** + `self-authoring`.
- **Terms/ADRs** → **domain-model**. **Research** → **research**. **Issues** → **tracker**. **Fan-out** → **swarm** / **arena**. **Contested design** → **interrogate**.

## Principles

Read `references/principles/<name>.md` before citing; definitions in `references/catalog.md`.

- **Core:** `laziness-protocol`, `foundational-thinking`, `redesign-from-first-principles`, `attack-the-premise`, `subtract-before-you-add`, `minimize-reader-load`, `outcome-oriented-execution`, `experience-first`, `exhaust-the-design-space`, `build-the-lever`.
- **Architecture:** `model-the-domain`, `boundary-discipline`, `type-system-discipline`, `make-operations-idempotent`, `migrate-callers-then-delete-legacy-apis`, `separate-before-serializing-shared-state`.
- **Verification:** `prove-it-works`, `fix-root-causes`, `sequence-verifiable-units`, `test-behavior-not-implementation`, `explain-the-number`.
- **Delegation & Meta:** `guard-the-context-window`, `never-block-on-the-human`, `encode-lessons-in-structure`.

## Reference library

Read entry skill first; full index: `references/README.md`:
- UI/motion/color/a11y/chat → `skill://frontend-ui`; stack/UI design/proof → `skill://deep-stack`
- Harnesses (omp/Claude/Codex/Antigravity), MCP/ACP, tiers → `skill://agent-harnesses` (`langchain-ecosystem.md`, `ai-sdk-selection.md`)
- Secrets/logins/MFA/OAuth/auth → `skill://secrets-and-auth`; repo/domain/DB/backend → `skill://software-architecture`
- Agents/LLMs/AWS/backend/languages/DevOps/debug → `skill://domain-rules`
- Docker/K8s/cloud/IAM/policy/pipelines/IaC/emulators → `skill://cloud-devsecops`

## Writing the reply

- Short declarative sentences, one thought each; no long dashes or mid-sentence colons (colons before lists ok).
- Keep required playbook sections; lead with consumer/maintainer impact before detail.
- Never fabricate links/citations/outputs; link only what you produced/read; label claims (measured, inferred, guess); never hand off checks you can run.
- **No machinery.** Omit skills, playbooks, routes, sizes, verify bookkeeping, pre-authorizations, models/subagents, internal codes unless required by a playbook section or "Why I chose this". Report result, proof, risks, blockers; mention machinery only when it affects trust.
