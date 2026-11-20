# Deepmodebot catalog

On-demand index of deepmodebot's autonomous modes, all 30 playbooks, 52 techniques, 24 principles, and habits. `SKILL.md` holds the binding rules and compact router; read only the section and linked file your task needs. Paths are relative to this skill.

## Running without the human

Pick the row that matches what the user has or wants.

| The user has or wants | Use |
|---|---|
| One goal driven to a checkable end in this session | Run a goal, session scale (`references/playbooks/run-a-goal.md`) |
| A goal run headless or overnight, no session open | `assets/loop/loop.py`, per Self-authoring (`references/playbooks/self-authoring.md`) |
| A multi-day program with many owners | Run a goal, program scale (`references/playbooks/run-a-goal.md`) |
| A whole app or rough idea built across every slice | End-to-end (`references/playbooks/end-to-end.md`) |
| A backlog, or a goal split into many PRs | Work a queue, board source (`references/playbooks/work-a-queue.md`) |
| A queue of independent PRs | Work a queue, PR source (`merge` or `stack-only`) |
| Labeled issues in a repo with `factory.json` | Work a queue, factory source (`references/playbooks/work-a-queue.md`) |
| PRs and issues handled with no session open | GitHub App bot (`references/techniques/github-app.md`) |
| A spec's tickets landed as one PR | Phased build, build mode (`references/playbooks/phased-build.md`) |

## Full playbooks index (30)

Every playbook lives at `references/playbooks/<file>.md`. Open a `todo` list with its steps as `<n>. <short imperative>` before task-specific items; state the reason if a step is skipped.

| Playbook | File | Use for |
|---|---|---|
| Investigation | `investigation` | Read-only question: how does X work, why was Y built this way, are we sure, X or Y? |
| Bug fix | `bug-fix` | A reported defect to reproduce, root-cause, and fix with runtime evidence. |
| Perf issue | `perf-issue` | A measured slowness to trace and improve against a baseline. |
| Hillclimb | `hillclimb` | Sustained improvement of one metric against a target, before/after per hypothesis, one kept change per win. |
| Runtime forensics | `runtime-forensics` | Diagnose a live symptom (leak, idle CPU, glitch) from instrumentation. Deliverable is a diagnosis. |
| Trace forensics | `trace-forensics` | Diagnose a captured artifact (cpuprofile, trace, heap snapshot). Deliverable is a diagnosis. |
| Feature | `feature` | New or changed behavior, built from a named data shape. |
| End-to-end | `end-to-end` | Deliver a whole app, tool, or rough idea across all slices via a machine-checked Scope Manifest (`slices`, `inventory`, `sprint`/`sme_gate`) until finished (or through an explicit sprint/SME checkpoint with remaining scope tracked). |
| Refactoring | `refactoring` | Behavior-preserving structural change (rename, extract, inline, dedupe, move, language ports). |
| Prototype | `prototype` | Throwaway sketch to decide a design, or settle an empirical fork by observing it. |
| Visual parity | `visual-parity` | Pixel-exact UI equivalence between two implementations or styling systems. |
| Reference rebuild | `reference-rebuild` | Rebuild a product UI to the standard of a named app: study reference, design on canvas, build, prove live. |
| Authoring a skill | `authoring-a-skill` | Writing or editing a `SKILL.md` (first step reads `references/techniques/writing-for-agents.md`). |
| Self-authoring | `self-authoring` | Write and prove a reusable prompt, skill, goal, or loop; run goals headless with `assets/loop/loop.py` (`active_sprint`, `inventory`, `sme_gate`, escalation/fallback, `latest-summary.json`). |
| Eval | `eval` | Test how a skill, prompt, or structure change affects agent behavior, blinded, before promoting it. |
| Phased build | `phased-build` | Multi-phase/PR work: Plan mode (verifiable checklist), Sprint mode (incremental sprints + SME feedback gate, remaining sprints tracked), Build mode (one spec to one PR). |
| Wayfinder | `wayfinder` | Effort too big for one session with a foggy route: map decision tickets and resolve them until the way is clear. |
| Babysit | `babysit` | Drive a PR or stack to merge-ready: conflicts, review threads, CI. |
| Shipping | `shipping` | Verify a green stack, then land the contiguous verified run bottom-up, each PR on a panel pass. |
| Run a goal | `run-a-goal` | Drive one goal to a checkable end unattended: session scale (completion predicate) or program scale (multi-day coordinator). |
| Work a queue | `work-a-queue` | Turn a queue of board tasks, independent PRs (`merge`/`stack-only`), or `factory` CLI issues into merged PRs on panel passes. |
| Setup | `setup` | One-time repo setup: tracker (`docs/deepmodebot/tracker.md`), `GLOSSARY.md`, `docs/adr/`, `CODING_STANDARDS.md`, `AGENTS.md` pointer. |
| Spec | `spec` | Turn a settled conversation into `docs/specs/<slug>.md`, a Scope Manifest when multi-slice, and a `spec` issue. No interview. |
| Tickets | `tickets` | Split a spec or plan into tracer-bullet tickets with blocking edges and incremental sprints (preserving 100% of Total Scope), published to the tracker. |
| Triage | `triage` | Move incoming issues and outside PRs through triage states: verify, shape, brief, label, or decline. |
| Session pickup | `session-pickup` | Resume or take over a prior agent's in-flight work. |
| Pause safely | `pause-safely` | Suspend in-flight work so it can be resumed later. |
| Handoff | `handoff` | Compact the session into a portable doc another agent, harness, or colleague can act on; optionally launch a background agent. |
| Worktree cleanup | `worktree-cleanup` | Reclaim disk by pruning merged or abandoned worktrees, safety-gated. |
| Opening a PR | `opening-a-pr` | Run at the end of any playbook that ships code. |

Large cross-cutting work with no clean fit, or step-away work that must be trusted later, routes to `references/techniques/figure-it-out.md` (designs a bespoke rigorous playbook). Standing multi-day programs route to `references/playbooks/run-a-goal.md` at program scale.

## Full technique triggers (52)

Each technique is one file at `references/techniques/<name>.md`. Read only what applies; skip for size **S**. Technique and playbook names mean deepmodebot's files, not same-named global skills (`skill://tdd`, `skill://prototype`, `skill://teach`, `skill://wizard`, `skill://retro`, `skill://handoff`).

- **Fast orientation, Orca/git worktrees, own PRs, or manifest state** → **workspace-map** (`references/techniques/workspace-map.md`): zero-bloat memory-mapped SQLite/FTS5 index (`assets/workspace-map/workspace_map.py` `overview`/`query`/`workspaces`/`prs`/`sync`/`prune`), shared per repo across worktrees (~300-token turn-1 map).

- **Before building anything new** → **prior-art** (`references/techniques/prior-art.md`): check trending first (`python -B "<this skill>/scripts/trending.py" find <terms>`, `py -3 -B` on Windows), then GitHub, registries, and docs; check license before copying or forking.
- **Module/interface with 2+ viable shapes** → **architect** (`references/techniques/architect.md`) before coding; skip for small edits crossing one function boundary.
- **Nontrivial change or "are we sure?"** → **how** (`references/techniques/how.md`). Motivation questions → **why** (`references/techniques/why.md`).
- **Parallel fan-out & sibling coordination** → **swarm** (`references/techniques/swarm.md`) for matrices, races, fuzzing, partitions; **arena** (`references/techniques/arena.md`) for code/design bakeoffs; **agent-collaboration** (`references/techniques/agent-collaboration.md`) for sibling messaging and ACP routing; **coworkers** (`references/techniques/coworkers.md`) for direct peer handoffs.
- **Contested design only** → **interrogate** (`references/techniques/interrogate.md`), keeping only findings a run proves.
- **Open direction, blind spots, or vague ambition** → **tournament** (`references/techniques/tournament.md`) before locking one shape.
- **Draft plan or goal to stress-test** → **grill** (`references/techniques/grill.md`; With docs mode when `GLOSSARY.md`/`docs/adr/` exist); vague goal before looping → **goal-review** (`references/techniques/goal-review.md`) then `self-authoring`.
- **Complex domain or questionable customer spec** → **sme-review** (`references/techniques/sme-review.md`) before locking a spec, starting a loop, or advancing past Sprint 1 (`sme_gate: "required"`); escalate unverified P0/P1 rules via **questionnaire** (`references/techniques/questionnaire.md`).
- **Multi-PR or customer-facing spec** → cut **incremental sprints** (Tickets + Phased build sprint mode; Sprint 1 = verified feedback slice, Sprint 2..N stay queued/deferred in the Scope Manifest as remaining scope, never falsely marked done).
- **Before unattended loops/queues or AI code slop** → **inner-loop** (`references/techniques/inner-loop.md`): harden fast static checks, anti-slop guards, and protected configs before scaling iterations.
- **Tool/skill routing** → **tool-routing** (`references/techniques/tool-routing.md`) for designing automatic tool or skill routers.
- **Visual E2E & design evidence** → **visual-e2e** (`references/techniques/visual-e2e.md`) to record/replay full E2E workflows with 3-agent sampled-frame image review (capped at 24 images, not full-video review); **open-design-evidence** (`references/techniques/open-design-evidence.md`) for portable SVG/Mermaid/HTML workflow diagrams linked to recordings (with a Penpot import/edit check; report raw-SVG or raster limits).
- **Rate limits, 429s, or heavy token burn** → `references/principles/guard-the-context-window.md` + `skill://agent-harnesses/references/delegation-efficiency.md`: pick tiers from LM benchmarks, avoid Fast/Ultrafast, `/clear` between unrelated tasks, plan L / execute S-M, cheap-first with an oracle, batch 3-5 spawns, reuse warm agents, pass file paths, set cost/cooldown caps, and back off or rotate model family on 429s.
- **Measured number** → **benchmark-checklist** (`references/techniques/benchmark-checklist.md`) before reporting or acting.
- **Prose** (reply, docs, PR body, commit) → **unslop** (`references/techniques/unslop.md`); docs and PR/commit text also → **technical-writing** (`references/techniques/technical-writing.md`).
- **Before review** → **no-comments** (`references/techniques/no-comments.md`) on the diff (apply inline for diffs under ~20 lines).
- **Repeated correction & self-prompting loops** → **correct** (`references/techniques/correct.md`) at the highest rung; for prompts, skills, goals, or loops, use Self-authoring (`references/playbooks/self-authoring.md`).
- **Words, durable research, or issues** → **domain-model** (`references/techniques/domain-model.md`), **research** (`references/techniques/research.md`, including opportunity probe and decision-brief), **tracker** (`references/techniques/tracker.md`).
- **PRs, bots, and gates** → **pr-review** (`references/techniques/pr-review.md`), **pr-agent** (`references/techniques/pr-agent.md`), **pr-conversation** (`references/techniques/pr-conversation.md`), **issue-conversation** (`references/techniques/issue-conversation.md`), **github-app** (`references/techniques/github-app.md`), **security-audit** (`references/techniques/security-audit.md`), **panel** (`references/techniques/panel.md`), **show-me-your-work** (`references/techniques/show-me-your-work.md`), **figure-it-out** (`references/techniques/figure-it-out.md`).
- **Tooling & instruction hygiene** → **tdd** (`references/techniques/tdd.md`), **architecture-review** (`references/techniques/architecture-review.md`), **git-guardrails** (`references/techniques/git-guardrails.md`), **pre-commit** (`references/techniques/pre-commit.md`), **scrape** (`references/techniques/scrape.md`), **wizard** (`references/techniques/wizard.md`), **writing-for-agents** (`references/techniques/writing-for-agents.md`; generate/refresh `AGENTS.md` with `assets/agents-md/agents_md.py`).
- **Communication & reflection** → **in-your-own-words** (`references/techniques/in-your-own-words.md`), **sharpen** (`references/techniques/sharpen.md`), **teach** (`references/techniques/teach.md`), **course** (`references/techniques/course.md`), **re-explain** (`references/techniques/re-explain.md`), **recall** (`references/techniques/recall.md`), **blast-radius** (`references/techniques/blast-radius.md`), **reflect** (`references/techniques/reflect.md`), **retro** (`references/techniques/retro.md`).

## Full principles directory (24)

One file per principle in `references/principles/<name>.md`. Read the file before applying or citing it.

- **Core (design):** `laziness-protocol` (bias to deletion, smallest change), `foundational-thinking` (types, data structures, shared state before logic), `redesign-from-first-principles` (integrate a requirement as if there from day one), `subtract-before-you-add` (remove complexity first), `experience-first` (design from user experience).
- **Core (execution):** `attack-the-premise` (two fixes sharing a premise failed the same gate, so test it), `minimize-reader-load` (count layers/hidden state; collapse one-caller wrappers), `outcome-oriented-execution` (converge on target architecture, no throwaway compat), `exhaust-the-design-space` (2-3 prototypes for novel decisions), `build-the-lever` (build the script/checker reviewers rerun).
- **Architecture:** `model-the-domain`, `boundary-discipline` (guards at boundaries, trust internal types, pure core), `type-system-discipline` (illegal states unrepresentable, brand primitives, parse at boundaries), `make-operations-idempotent`, `migrate-callers-then-delete-legacy-apis`, `separate-before-serializing-shared-state`.
- **Verification:** `prove-it-works`, `fix-root-causes` (a guard fixes only legitimate states), `sequence-verifiable-units`, `test-behavior-not-implementation`, `explain-the-number`.
- **Delegation:** `guard-the-context-window`, `never-block-on-the-human` (proceed on reversible work, present results, let the human correct).
- **Meta:** `encode-lessons-in-structure` (repeated instruction becomes a lint, check, or script).

## Habits worth keeping

- Restate-in-your-own-words is the highest-leverage first move on any fuzzy ask, report, or thread.
- Prototypes beat abstract plans; empirical runs catch real risks without inventing imaginary ones.
- Your codebase is the memory: turn repeated agent nits into types, lints, tests, or structure.
- Artifacts beat explanations: show failing/passing tests, before/after screenshots, logs, or traces.
- Every stage can stop the line: "not a bug", "can't reproduce", and "too risky" protect downstream work.
