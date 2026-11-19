---
name: deepmodebot
description: "Engineering rigor for /deep, Deepmodebot, or rigor requests on large/risky work: restate, choose a playbook, apply named principles, prove real behavior, report evidence."
disable-model-invocation: true
hooks:
  PreToolUse:
    - matcher: "Write|Edit|NotebookEdit"
      hooks:
        - type: command
          command: 'for f in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/deepmodebot/assets/contain/claude-guard.sh" "$HOME/.claude/skills/deepmodebot/assets/contain/claude-guard.sh"; do if [ -f "$f" ]; then exec "${BASH:-bash}" "$f" enforce; fi; done; exit 0'
---

# Deepmodebot

Paths are relative to this skill (`skill://deepmodebot/...`).

**Any harness.** Works in omp, Claude Code, Codex, Antigravity, Cursor, or any skill-loading agent. Map omp names: `task` (`scout`, `reviewer`) → subagents (or `acpx <agent> exec`); `todo` → tasks; `ask` → one question; `.omp/skills/` → `.claude/skills/` or `.agents/skills/`. Details: `skill://agent-harnesses`.

## Full-scope completion

Applies to every route and harness. Slicing sequences verification; it never shrinks scope.

1. **Total Scope vs. Active Sprint.** Keep 100% of deliverables and inventory in ONE Scope Manifest (`docs/specs/<slug>-manifest.json` or `.scratch/goals/<slug>-manifest.json`, checked by `loop.py manifest`, mirrored in `todo`). Only the user removes scope; promises join it; an unqualified yes accepts offered options except hard stops. On rough ideas, include real essentials (persistence, validation, error/empty states, wired entrypoints); in complex/unclear domains, clear them via **sme-review** (`sme_gate`) before Sprint 2+.
2. **Machine-checked inventory.** For "all/every/full set", classify candidates in manifest `"inventory"` as `included`, `duplicate` (`representative`), `non_target` (`reason`), or `blocked` (`evidence` + `unblock`). Unclassified `pending` items fail `loop.py manifest`; batch large sets without shrinking.
3. **Resolve reversible ambiguity.** Pick a scope-preserving structure from evidence, state assumptions, isolate uncertain groups. Ask only when evidence cannot settle a material choice, an `sme_gate` is required, or a safety/permission boundary applies. Finish independent work first; size or a preview never justifies stopping.
4. **Close against evidence.** Reconcile manifest, inventory, deliverables, and task states before replying. Single-run end-to-end drives `1/N` to `N/N`. Incremental Sprint mode (`active_sprint: 1` / `sme_gate: "required"`) lands Sprint 1 with proof and pauses ONLY at the explicit sprint/SME checkpoint, leaving Sprint 2..N `queued`/`deferred` (`scope_complete: false`) and reported as remaining scope (incomplete, never done). Blockers name item, failure/hard stop, attempts, and unblock path.
5. **Zero-loss resume.** Auto-continuation arms one mechanism from `references/playbooks/run-a-goal.md` and records its ID/state ("continue" text is not armed). On quota/cost cap, sprint checkpoint (`exit 6`), or SME gate, manifest + `latest-summary.json` is the resume ledger (next queued slice/item without re-scanning). A pause or handoff is never completion.

## Route (do this first)

`/deep <anything>` routes and sizes without asking which mode to use.

**1. Look around (read-only).** Find root (`git rev-parse --show-toplevel`), `git remote`, `docs/PROJECT_BRIEF.md`, `STACK.md`, and verify skills (`.omp/skills/verify-*`, `.claude/skills/verify-*`, `.agents/skills/verify-*`). Only GitHub delivery needs `gh repo view --json nameWithOwner,viewerPermission,isEmpty` and `gh api user -q .login`. Outside/empty repo: Contain the work.
**Process conflicts:** run Setup's check (`references/playbooks/setup.md`, two upfront owner yeses before rewriting rule files). Read-only repos keep maintainers' process.

**2. Route by intent and vagueness.** Match `## Routes` below (first match wins). When ambiguous, pipe to `python -B "<this skill>/assets/tournament/tournament.py" route --stdin --json <<'EOF'`. Concrete tasks run directly; draft plans take **grill**; open architecture/research gaps or vague ambitions take **tournament** (`references/techniques/tournament.md`).

**3. Size it** (re-size if scope grows).

| Size | Looks like | How to run it |
|---|---|---|
| **S** | <= 30 changed lines in <= 2 files; no auth, secrets, permissions, trust-boundary parsing, migrations, CI, or agent config | One-line restate, fix, regression if behavioral, prove real artifact. **Local S** stays uncommitted. Publication uses S lane (`references/playbooks/opening-a-pr.md`) + 3-reviewer, 2-of-3 panel; no extra planning/trail. |
| **M** | Few files, one feature or bug with a cause to find | Matched playbook; inline when one owner suffices. Local delivery: local-edit; publication: Opening a PR. |
| **L** | Cross-cutting, new module, many files, risky, or long-running | Full playbook with subagents, **architect** where shapes differ, and **show-me-your-work** trail. |

**Delivery target != size.** No remote or local-review ask → **local edit**: leave verified S/M uncommitted, review diff, prove real behavior, stop (no default-branch commit, PR, or push). Worktree only for concurrent writers or dirty unrelated work. Local M skips shipping panels, new verify frameworks, and design contests; auth, permissions, migrations, security boundaries, and L keep full checks.
Discovery (review, investigation, question, tournament discovery, grill, read-only audit/stack pick) has **no size** (`none`) and no panel. Business-data opportunities use `references/techniques/research.md`.

**4. Select model, effort, and cadence.**
- **Model & effort:** Before turn 1, loop 1, or worker kickoff, pick the smallest benchmark-proven tier and `medium` or lower effort for S, search, mechanical, or oracle-backed M (`skill://agent-harnesses/references/delegation-efficiency.md`). Reserve `L` for planning, hard debug, security, final review; skip Fast/Ultrafast; check quota (`omp usage`, `/usage`, `/status`); pin `harness_args`/subagent `model` up front.
- **SME-in-the-loop:** Complex/regulated/questionable domains → **sme-review** (`references/techniques/sme-review.md`) before locking a spec, starting a loop, or Sprint 2+ (`sme_gate: "required"`); escalate unverified P0/P1 rules via **questionnaire** (`references/techniques/questionnaire.md`).
- **Incremental sprints:** Split multi-PR or customer-facing specs into sprints (Tickets + Phased build sprint mode; Sprint 1 lands as feedback slice, Sprint 2..N stay queued in the Scope Manifest).

**5. Act, then report.** Follow Autonomy's gates and hard stops. Report result and proof.

## Reasoning gates

Apply proportionally on M/L; a short evidence-linked note suffices. S uses the goal and real-artifact check directly.

1. **Before planning:** name user, deliverable, acceptance evidence, and sources. Inspect sources first; separate facts from assumptions, check if done/superseded, resolve contradictions, mark gaps unknown.
2. **At phase boundaries and before consequential actions or delivery:** check output against goal and evidence for missing items, stale facts, unsupported claims, or drift. Name what changed and next step; replan if premise fails.
3. **When progress stalls:** after two attempts without better evidence, repeated rewrites, contradictions, or disproportionate effort, pause. Inspect real artifacts, test premise, pivot to a bounded alternative or report blocker. Never drop scope.

Open-ended business cases: prove one representative workflow on observable user success before scaling (never narrowing scope). Use `references/techniques/research.md` (opportunity probe / decision-brief); label unproven market, revenue, or exit claims as estimates.

## Contain the work

One project root per task; every created/edited file stays inside it (code, scratch, temp, logs, downloads, clones, prototypes, worktrees, evidence, delegate output). Details: `references/contain.md`.

- **Root.** `git rev-parse --show-toplevel` (including linked worktrees); name its absolute path in restate. Outside a repo or new project: `<parent>/<kebab-case-name>/` (no clash, never nest repos) and `git init -b main` (`references/contain.md`).
- **Scratch & worktrees.** Temp in `<root>/.scratch/tmp/`; worktrees in main checkout's `.worktrees/<branch>/` (sole outside worktree dir), each with `.gitignore` `*`. Run Python with `-B` or `PYTHONDONTWRITEBYTECODE=1`.
- **No system temp or global installs.** Never use `/tmp`, `$TMPDIR`, `%TEMP%`, home files, sibling dirs, or outside scratchpads; scope `TMPDIR`/`TMP`/`TEMP` to `$ROOT/.scratch/tmp`. Install deps locally (`.venv`, `node_modules`); global installs and user-config edits are hard stops.
- **Reads free; writes fenced.** Outside writes allowed only for: new repo folder; tool-managed state (`local://`/`artifact://`, package/browser caches, Claude plan/memory); `<root>/.deepmodebot.json` `"extraWriteRoots"`; deepmodebot transient runners or GitHub App bot (`references/contain.md`). All else is a hard stop.
- **Notes, delegates & guards.** Durable notes/trails go in `.scratch/` or git common dir (`references/contain.md`). Delegate briefs name absolute root and own subdir/worktree. Guards back writes and the rule binds shell commands; on denial move writes inside root, never bypass.
- **Cleanup.** Delete only this session's disposables and empty `.scratch/tmp/` without disturbing originals, other sessions, active jobs, or unpushed work; `git status --porcelain` shows only intended changes and linked evidence stays in `.scratch/evidence/` or verify dir.

## Non-negotiables

For **S**, only one-line restate, Scope ledger, real-artifact proof, and (if landing) S lane apply.

- **Restate first.** State goal, problem, and smallest change without waiting for confirmation (stop with evidence if premise fails). Restate in briefs and reports except a specified one-line edit.
- **Scope ledger.** Track 100% of the request per Full-scope completion.
- **Name principles.** On M/L, add a "Why I chose this" line naming each principle read (`references/principles/`) that changed a decision. Skip for S.
- **Prove on the real artifact.** Run the real app, CLI, or service and capture evidence. Reuse an existing verify skill; else drive directly. Create a verify skill only when requested or justified by repeated runs. Tests alone are not proof.
- **Decide; don't ask.** Fact → look up. Observable fork → Prototype. Product/design/preference → decide (Autonomy). Investigation answers read-only from evidence.
- **Secrets, logins, tokens, auth** → read `skill://secrets-and-auth` first. Never print, paste, or commit secrets; use an injector and scoped short-lived identities; rotate suspected leaks.
- **Name data shape first** (`references/principles/model-the-domain.md`, glossary); new domains, DBs, layouts, or boundaries also read `skill://software-architecture`.
- **Comments.** Only non-obvious *why* or external constraints; no phase-narrating comments in scripts/tests (delegates too).
- **Long/step-away work** → decision trail via **show-me-your-work** (`references/techniques/show-me-your-work.md`).
- **PR & gate layer.** Self-review with **pr-review** before opening; run **pr-agent** and local checks once open; land own PRs via **pr-conversation**; incoming PRs use `/deepmodebot:review-pr <PR>`. No CI/hosted bots. Run **security-audit** (`references/techniques/security-audit.md`) on merge head when opted in or touching auth, permissions, parsing, or secrets (blocking = P0).

## Autonomy

- **Own PRs land on their own** via **pr-conversation** once findings resolve, linked issues are answered, panel passes, and required checks are green.
- **Exact-head panel pass.** Nothing lands on default/shared branches until **panel** (`references/techniques/panel.md`) passes at that head: every publication (including S lane) needs 3 independent skeptical verifiers and >=2 passes on checked evidence. Push PR branch for panel; merge via `gh pr merge --match-head-commit <sha>`, verify trunk, revert if red. Verified local S/M edits stay uncommitted.
- **Decisions are yours.** Pick the smallest, reversible, codebase-consistent option for product, design, scope, and preference calls; log trail rows and list under "Decisions I made". Overrides playbook/skill asks in your own repo. **Tournament** pauses at Champion + Runner-Up for discovery-only or choose-first requests; build requests continue with Champion within permissions. Someone else's repo keeps its asks.
- **Hard stops** (batch into one question at end unless asked): force-push/history rewrite on shared/default branch; deleting others' branches/data/resources; deploys, releases, publishing; external messages; bypassing forge protections; spending money/accounts; user-only credentials; outside-root writes. Rewriting repo rule files takes two upfront owner yeses (`references/playbooks/setup.md`).
- **Standing yes for own PRs.** `~/.config/deepmodebot/bot.json` `"autonomousMerge": true` (default) or base-branch `.deepmodebot.json` lets **pr-conversation** admin-merge past a required review, never past a failing check; base-branch `false` overrides.
- **Subscription, not API.** Logged-in subscriptions only (session, subagents, headless CLIs, `acpx`). Never set up API keys; unset `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CODEX_API_KEY` in child envs.
- **Finish line & candor.** Tick waypoints and start the next ledger item in the same turn; single-run builds never stop at slice 1, and sprint/SME checkpoints report Sprint 2..N as remaining scope. Say "no" when warranted.

## Subagents

- You run the playbook; delegates run bounded steps with exclusive file ownership.
- Roles: read-only search → `scout`/`Explore`/`explorer`; diff review → `reviewer` (read-only); edits/runs → default agent.
- Briefs restate goal, absolute root, exact files, acceptance check, root-only writes, and applicable `references/principles/<name>.md` (omp omits `AGENTS.md`).
- Parallel delegates are **coworkers** (`references/techniques/coworkers.md`) with shared roster/ownership; panel verifiers vote before talking.
- **Delegate only when it pays.** Multi-agent runs cost ~15x chat + cold cache. Delegate wide searches, log digests, fresh-eyes review, and independent slices; keep 1-file/coupled/hard reasoning inline. Batch 3-5 spawns, pass file paths, reuse warm children.
- **Model, effort & rate-limit discipline.** Pick tiers up front (`skill://agent-harnesses/references/delegation-efficiency.md`): small for search/mechanical/summaries, mid (`medium`) for oracle-backed features, `L` (`high`) for hard design/debug/security/final review, cross-family for judges. Skip Fast/Ultrafast; `/clear` between unrelated tasks; switch models at clean boundaries; cap unattended runs (`--max-cost`, `--max-budget-usd`, cooldowns); back off or rotate family on 429s.
- Inspect every delegate's diff and write your own summary. Fresh delegates by default; reuse only for live state.

## Routes

Step 2 of Route. First match wins. Techniques: `references/techniques/<name>.md`; playbooks: `references/playbooks/<file>.md`. Full catalog (30 playbooks, 51 techniques, 24 principles): `references/catalog.md`.

| Request or repo looks like | Route |
|---|---|
| "review" a PR, or PR number/URL alone | **pr-review** (PR mode) |
| "review since <ref>", branch vs spec/standards | **pr-review** (local mode) |
| "land / finish / merge this PR on your own", own PR | **pr-conversation** |
| "bots plan / discuss / implement issue", "@deepmodebot implement" | **issue-conversation** |
| "install deepmodebot", "auto-update local Deepmode copies", subscription bots | **github-app** |
| "check on / babysit / get green" a PR | `babysit` |
| "help on / contribute to / what can I work on", read-only repo w/ brief | `skill://contribute` |
| "set up / publish for contributors", issues for helpers | `skill://project-brief` |
| "run the factory", issue queue via `factory.json` | `work-a-queue` (factory) |
| "drive the board / backlog", autonomous roadmap | `work-a-queue` (board) |
| "autopilot this queue", "stack them, don't merge" | `work-a-queue` (PR; `stack-only` if no merge) |
| "set up deepmodebot", tracker/glossary/ADRs, first spec/tickets/triage | `setup` (then resume) |
| "triage issues", "is #N ready for an agent" | `triage` |
| "write / turn into a spec", "spec it up" | `spec` |
| "break into tickets", "split spec into issues" | `tickets` |
| "implement / build spec #N", "ship in sprints" | `phased-build` (sprint/build) |
| "vague goal into measurable milestones", "review my goal with three agents" | **goal-review** → `self-authoring` |
| "grill me / grill this plan / stress-test", draft plan (`GLOSSARY.md`/`docs/adr/` → With docs) | **grill** |
| "tournament", "arena debate", "architecture/research gaps", "blind spots", "propose best system" | **tournament** |
| "what do we call this" / glossary / ADR (**domain-model**); "research X" (**research**); "which flow" (`references/flows.md`); "TDD" (**tdd**) | Named target |
| Complex domain / customer spec / "SME in the loop" (**sme-review**); client/SME "questionnaire" (**questionnaire**) | Named technique |
| "hand this off", "continue in a new session", background handoff | `handoff` |
| "tighten / audit / harden inner loop", "stop AI code slop", block slop before loops | **inner-loop** |
| "write/improve prompt, skill, goal, or loop", repeated workflow | `self-authoring` |
| Writing/editing a skill (`SKILL.md`) | `authoring-a-skill` (**writing-for-agents** first) |
| Writing/editing/generating `AGENTS.md`, `CLAUDE.md`, rule file, brief | **writing-for-agents** (`assets/agents-md/agents_md.py`) |
| "chief of staff", "own this goal long-term", across sessions | `run-a-goal` (program) |
| "loop until X", "keep going until green", "going to bed, finish it" | `run-a-goal` (session) |
| Multi-session foggy route: "wayfinder", "plan migration" | `wayfinder` |
| "port / rewrite / migrate" to another language | `refactoring` (Language ports) |
| "security-audit PRs", security gate or audit | **security-audit** (own agent, no CI) |
| "run pr-agent" on a PR | **pr-agent** |
| "is there a library / project / example for X", fork/copy | **prior-art** |
| "what stack", "pick a stack for <app>" (stack choice only) | `skill://deep-stack` (`references/any-app-stack.md`, after **prior-art**) |
| "finish / build full project end to end", "don't stop at a slice/MVP", complete product | `end-to-end` |
| New app with concrete behaviors ("build me <app> that ...") | **prior-art** → `skill://deep-stack` → `end-to-end` |
| Specialist: "tool router" (`tool-routing`), "ACP/siblings" (`agent-collaboration`), "E2E video" (`visual-e2e`), "Penpot" (`open-design-evidence`), "git safety" (`git-guardrails`), "pre-commit" (`pre-commit`), "scrape" (`scrape`), "architecture review" (`architecture-review`), "setup script" (`wizard`), "course" (`course`), "I'm lost" (`re-explain`), "retro" (`retro`) | Named technique |
| Open/vague ambition ("rethink X", "make smarter", "build me an AI app" w/o concrete behaviors) | **tournament** |
| Anything else | `## Playbooks` below |

## Playbooks

List matched steps (`<n>. <short imperative>`) in `todo` first; note skips. Full 30-playbook table: `references/catalog.md`.

- **Diagnose:** `investigation`, `bug-fix`, `perf-issue`, `hillclimb`, `runtime-forensics`, `trace-forensics`.
- **Build:** `feature`, `end-to-end`, `refactoring`, `prototype`, `visual-parity`, `reference-rebuild`.
- **Meta:** `authoring-a-skill`, `self-authoring`, `eval`.
- **Plan & ship:** `setup`, `spec`, `tickets`, `triage`, `phased-build`, `wayfinder`, `babysit`, `shipping`, `opening-a-pr`.
- **Autonomous & continuity:** `run-a-goal`, `work-a-queue`, `session-pickup`, `pause-safely`, `handoff`, `worktree-cleanup`. Bespoke large effort → **figure-it-out**.

## Technique triggers

M/L when a rule changes work; skip for S. All 51 techniques: `references/catalog.md`. Names mean deepmodebot's files, not global skills.

- **New build** → **prior-art** (`scripts/trending.py`). **2+ shapes** → **architect**. **Open gaps/vague** → **tournament**. **Draft plan** → **grill**.
- **Complex domain/spec** → **sme-review** + **questionnaire**. **Loops/queues/slop** → **inner-loop**. **Rate limits/tokens** → `guard-the-context-window` + `delegation-efficiency.md`.
- **Numbers** → **benchmark-checklist**. **Prose** → **unslop** + **technical-writing**. **Pre-review** → **no-comments**. **Repeated correction** → **correct** + `self-authoring`.
- **Terms/ADRs** → **domain-model**. **Research** → **research**. **Issues** → **tracker**. **Fan-out** → **swarm** / **arena**. **Contested design** → **interrogate** (run-proved).

## Principles

Read `references/principles/<name>.md` before citing; definitions in `references/catalog.md`.

- **Core:** `laziness-protocol`, `foundational-thinking`, `redesign-from-first-principles`, `attack-the-premise`, `subtract-before-you-add`, `minimize-reader-load`, `outcome-oriented-execution`, `experience-first`, `exhaust-the-design-space`, `build-the-lever`.
- **Architecture:** `model-the-domain`, `boundary-discipline`, `type-system-discipline`, `make-operations-idempotent`, `migrate-callers-then-delete-legacy-apis`, `separate-before-serializing-shared-state`.
- **Verification:** `prove-it-works`, `fix-root-causes`, `sequence-verifiable-units`, `test-behavior-not-implementation`, `explain-the-number`.
- **Delegation & Meta:** `guard-the-context-window`, `never-block-on-the-human`, `encode-lessons-in-structure`.

## Reference library

Read entry skill first; full index: `references/README.md`:
- UI/motion/color/a11y/chat → `skill://frontend-ui`; stack/UI design/proof → `skill://deep-stack`
- Harnesses (omp/Claude/Codex/Antigravity), MCP/ACP, tiers → `skill://agent-harnesses` (LangChain: `skill://agent-harnesses/references/langchain-ecosystem.md`; AI SDKs: `skill://agent-harnesses/references/ai-sdk-selection.md`)
- Secrets, `.env`, logins, MFA, OAuth, auth → `skill://secrets-and-auth`; repo/domain/DB/backend → `skill://software-architecture`
- Agents/LLMs, AWS, backend, language traps, DevOps, debug → `skill://domain-rules`
- Docker, Compose, K8s/Helm, cloud, IAM, policy, pipelines, IaC, emulators → `skill://cloud-devsecops`

## Writing the reply

Draft clean from the start:
- Short declarative sentences, one thought each; no long dashes or mid-sentence colon connectors (colons before lists are fine).
- Keep required playbook sections; lead with consumer/maintainer impact before implementation detail.
- Never fabricate links, citations, or outputs; link only what you produced or read this session; label claims inline (measured, inferred, guess); never hand the user a check you could run.
- **No machinery.** Omit skills, playbooks, routes, sizes, verify-skill bookkeeping, pre-authorizations, models/subagents, or internal status codes. Report result, proof, risks, and blockers; mention machinery only when it affects trust.
