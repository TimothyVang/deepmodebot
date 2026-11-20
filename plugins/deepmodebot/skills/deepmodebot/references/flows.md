# Flows

Use when: the user asks which flow fits ("what's the process for X", "how should we approach this", "which flow do I use", "explain the deepmodebot workflow"), or you are choosing between flows for work bigger than one PR. The Route section of SKILL.md still picks the route; this file explains the map so you can show it. Paths are relative to this skill.

## The main line: idea to merged code

| Phase | Flow | Leaves behind |
|---|---|---|
| 1. Sharpen the idea | **grill** technique (`references/techniques/grill.md`), With docs mode in a repo with a glossary | Decision table, `GLOSSARY.md` terms, ADRs |
| 2. Settle a fork by running it | Prototype playbook (`references/playbooks/prototype.md`) | A decision backed by an observation |
| 3. Write it down | Spec playbook (`references/playbooks/spec.md`), plus **sme-review** (`references/techniques/sme-review.md`) for complex domains | `docs/specs/<slug>.md`, SME-cleared assumptions, and a `spec` issue |
| 4. Cut it up | Tickets playbook (`references/playbooks/tickets.md`) | Tracer-bullet tickets grouped into incremental sprints (Sprint 1 = minimum feedback slice) |
| 5. Build it | Phased build in sprint mode (one sprint PR + feedback gate at a time) or build mode (`references/playbooks/phased-build.md`), or Work a queue (`references/playbooks/work-a-queue.md`) | Merged code per sprint or ticket |
| 6. Review and land | **pr-review** (`references/techniques/pr-review.md`), Opening a PR, **panel**, **pr-conversation** | A merged PR with evidence |

Skip phases the work doesn't need. One PR of settled work starts at phase 5 with the Feature or Bug fix playbook. A spec that fits one PR skips phase 4.

## On-ramps

| Situation | Flow |
|---|---|
| Open architecture or research space, blind spots, or a high-vagueness ambition | **tournament** (`references/techniques/tournament.md`), proposing Champion and Runner-Up before phase 1 or 3 |
| First use of the planning flows in a repo | Setup (`references/playbooks/setup.md`) |
| Building a whole app or rough idea end to end across all slices without stopping at an MVP | End-to-end (`references/playbooks/end-to-end.md`) |
| Issues or outside PRs pile up | Triage (`references/playbooks/triage.md`), which feeds phase 5 with `triage:agent-ready` items |
| A defect | Bug fix (`references/playbooks/bug-fix.md`) |
| The route itself is unknown, more than one session of deciding | Wayfinder (`references/playbooks/wayfinder.md`), which hands its decisions to phase 3 |
| A question to answer once | Investigation (`references/playbooks/investigation.md`) |
| A question whose answer should stay in the repo | **research** (`references/techniques/research.md`) |
| Words or decisions need recording | **domain-model** (`references/techniques/domain-model.md`) |
| A queue of labeled issues and the `factory` CLI | Work a queue with the factory source (`references/playbooks/work-a-queue.md`) |
| A multi-day program with many owners | Run a goal at program scale (`references/playbooks/run-a-goal.md`) |
| Hardening fast local checks and anti-slop guards before unattended loops or queues | **inner-loop** (`references/techniques/inner-loop.md`) |
| A workflow done the same way twice, or a goal to run unattended until a check passes | Self-authoring (`references/playbooks/self-authoring.md`), to write and prove a prompt, skill, goal, or loop |
| Choosing a repo layout, data model, database, or backend shape | `skill://software-architecture` |
| Secrets, logins, or agent authentication | `skill://secrets-and-auth` |
| Running in or scripting omp, Claude Code, Codex, or Antigravity; MCP or ACP | `skill://agent-harnesses` |

## Between phases

A phase boundary is where context, model tier, and SME feedback get managed. Mid-phase, keep going or split the rest into subagents. At the boundary, take the first that fits:
1. **Keep going** in this session when the next phase needs this phase's reasoning first hand (a grill straight into its spec) and room remains.
2. **Start fresh** (`/clear` or a new session) when prior turns no longer matter; clearing between unrelated tasks cuts per-turn input tokens and preserves rate-limit headroom.
3. **Switch model tier at clean boundaries** (`skill://agent-harnesses/references/delegation-efficiency.md`): plan or review on flagship `L`, then step down to `M`/`S` for oracle-backed execution or sprint tickets rather than flipping mid-thread and breaking prompt caches.
4. **Pause for SME feedback** after a complex-domain spec or Sprint 1 demo when **sme-review** (`references/techniques/sme-review.md`) flags unverified P0/P1 domain rules; send a **questionnaire** (`references/techniques/questionnaire.md`) before starting Sprint 2+.
5. **Write it down for later.** Same repo, later session → Pause safely (`references/playbooks/pause-safely.md`). Another harness, folder, or person → Handoff (`references/playbooks/handoff.md`).
6. **Hand it to a subagent** when the next phase runs without steering (a review, a research file), pinned to the smallest model tier that fits.
7. **Compact** otherwise. First apply only Handoff step 3's state-preservation checks (`references/playbooks/handoff.md`), without publishing, launching, or pausing. Include the checkpoint path and next phase in the summary; re-read that state and current artifacts before resuming.

Each artifact above (spec, tickets, ADRs, research files) exists so a fresh session can pick up from the file instead of from memory.
