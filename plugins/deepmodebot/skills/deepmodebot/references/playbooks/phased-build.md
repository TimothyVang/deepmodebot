# Phased build

Use when: work spans phases or PRs. Plan mode writes the plan for a change that spans phases or stacked PRs, after the design is settled. Sprint mode ships a multi-sprint spec one incremental sprint at a time for early customer or SME feedback instead of a Big Bang release. Build mode builds a single-sprint spec's tickets (Spec and Tickets playbooks) onto one integration branch and lands it as one reviewed PR ("implement the spec", "build spec #N", "build all the tickets on one branch").
When each ticket should land on trunk as its own PR, use Work a queue with the board source (`references/playbooks/work-a-queue.md`) instead.

## Pick the mode

| What the user has | Mode |
|---|---|
| A settled design for a change that spans phases or PRs, and nothing built yet | Plan mode. The plan is the deliverable. |
| A spec with `Sprint:` tickets or uncertain domain feedback, shipped one sprint at a time | Sprint mode (Build mode per sprint, with feedback gate) |
| A small or settled spec with tickets, to land as one reviewed change | Build mode |
| A spec with tickets, each to land as its own PR | Work a queue, board source |

## Plan mode

You own the plan, not the code. The plan is a checklist an owner runs box by box and the operator audits from evidence. The plan is the deliverable; do not implement.

### Steps

1. One or two files with an obvious approach → skip the plan; say so and stop.
   Done when you have stopped with the reason stated, or found that the change needs more than one PR.
2. Settle open questions by prototype first (`references/playbooks/prototype.md`); keep branch, SHA, screenshots for Appendix A. Decide product and preference calls no run can settle yourself, and record each choice with its rejected options in Appendix B (SKILL.md Autonomy).
   Done when every open question has a prototype result for Appendix A or a recorded choice for Appendix B.
3. Explore via `scout` tasks (`references/principles/guard-the-context-window.md`); each returns file pointers, conventions, test commands, entry points; no inlined dumps.
   Done when every area the plan touches has a scout report with file pointers, conventions, test commands, and entry points.
4. Write the plan file (default `docs/<program>-plan.md` unless the user names a path) using the structure below; every heading and sub-block, in order. One section per PR; one PR = one change with its own evidence (`references/principles/sequence-verifiable-units.md`).
   Name the execution playbook in How to read this. That is Work a queue (`references/playbooks/work-a-queue.md`) with the PR source in `merge` mode if the run may merge, or in `stack-only` mode if the user lands PRs. For a standing program it is Run a goal at program scale (`references/playbooks/run-a-goal.md`).
   Done when the plan file exists with every heading of the structure, in order, and one section per PR.
5. Write with the **technical-writing** technique (`references/techniques/technical-writing.md`), then **unslop** (`references/techniques/unslop.md`). Body is how-to only; appendices hold explanation and reference. Each heading states a task or finding.
   Done when both passes have run on the file and every heading states a task or finding.
6. Run the Plan checklist below against the file; fix every failure.
   Done when the checklist reports 0 failures.
7. Hand back the plan path and the checklist results, then stop.
   Done when the reply holds the plan path and the checklist results, and no code has changed.

### Plan structure

- `# <Program> plan`, then an intro under 10 non-blank lines: what changes, for whom, the rule enforced, PR ids in order.
- `## How to read this`, containing: "One box is one unit of work", "Every box names the evidence that checks it", "Check a box only when its evidence exists" (a file, log line, screenshot, test run, SHA), the execution playbook path, who merges, and the verification rule verbatim: **"Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked."**
- `## Program checklist` with these `###` in order:
  - `Arm the program`: state protocol + plan, then start once the Plan checklist passes (no user go needed, SKILL.md Autonomy).
     - List `read skill://deepmodebot/references/playbooks/<name>.md` reads of the execution playbook and opening-a-pr, plus `read skill://<verify-skill>` for the repo's verification skill and each leaf skill (skills don't live in the repo; never `git show origin/main:`), re-read every tick.
     - Arm a recurring hourly audit tick (scheduled job or harness loop; never left to memory) with a verbatim tick prompt. The prompt says to re-read the playbook via `skill://deepmodebot/`, audit and fix drift, probe lanes by side effects only, and replace stuck lanes.
     - The prompt also says to post a status message only for tracked changes not yet reported (PR opened, code-ready head, round launched/closed, verdict, merge, stuck agent + action, blocker added/cleared, operator-only decision), else no reply text, and to log a decision-trail row each tick.
     - On hold/stand-down, order every owner to zero writes at once.
  - `Spawn owners`: one owner (`task`) per PR with full lifecycle; dependency graph as nested boxes; file boundaries per PR (exclusive globs); review-gated PR ids.
  - `PR mechanics, for every PR`: `gh` for all PR ops; open ready via **Opening a PR**; lint + typecheck once before the PR-facing push, hooks on; slop review before commit and **no-comments** before review.
     - Triage every automated/security review comment, plus the **pr-review** technique (`references/techniques/pr-review.md`): local mode before the first push, PR mode re-review (steps 6-7) after every push.
     - Rebase onto trunk before code-ready, keep that base in fix rounds, rebase again only at merge prep, on a `git merge-tree` conflict, trunk-caused CI failure, or a known concurrent change to the same files.
  - `Verdict and merge, for every PR`: one full swarm (the **swarm** technique, `references/techniques/swarm.md`) at the code-ready head, paced in rate-limit-safe batches (3-5 lanes per wave by default) and passing file paths rather than large inline dumps: a gates lane, live lanes scaled to the PR's surfaces (up to 10 for full UI apps; fewer for non-UI or smaller PRs), the perf lane, 2+ audit lanes with distinct focus that distrust the PR body.
     - Another full swarm only for new behavior, redesign, or large new diff; rebase/conflict/minor fix → single verifier at new head; wording-only → none.
     - Root audits receipts before the verdict. Clean = no blocking finding. A trunk failure in the regression lane is recorded against trunk and does not block.
     - The verdict is a **panel** at that head (`references/techniques/panel.md`); a new head gets a fresh panel. Merge/handoff rule from the execution playbook.
  - `Boot recipe, for every live lane`: `git fetch origin <head-branch> && git checkout <head SHA>` in the lane's own worktree; start backend + surface, wait for ready.
     - Input only through the project `verify-<app>` skill (else omp `eval` `browser` or bash), naming read-only diagnostics; save screenshots to `<tmp>/swarm-<pr-id>/worker-<n>/<slug>.png` and return paths.
- One `## <Task as verb phrase> (<PR id>)` per PR, with bold sub-blocks in exactly this order: `**Depends on.**` (PR id or None) · `**Files.**` (Edit/Create/Delete `<path>` boxes) · `**Build.**` (one change, symbol + file) · `**You see.**` (exact log line or screen state) · `**Verify, unit.**` (test file + case, `Run <command>`) · `**Verify, live.**` · `**Verify, perf.**` · `**Review gate.**` · `**Merge.**`.
  - The three Verify blocks open with the verification rule verbatim.
  - Verify, live continues "Live lanes (up to ten, scaled to affected surfaces) on `<model>` at the PR head, per the boot recipe, run in waves of 3-5 concurrent lanes per provider rate limits." Boxes `Lane 1.`…`Lane N.`, each with a scenario, ``Save `<slug>.png`.``, and `Pass when <predicate>.`
  - Lane 1 is the "Regression lane against trunk": same load-bearing scenario at trunk and head; if trunk lacks the feature, record that and gate the diff-added behavior plus the end state the user waits for; never invent a trunk result.
  - Verify, perf boxes in order: `Metric.` (measured at trunk and head) · `Probe.` (command, run interleaved at trunk and head, both producing the metric) · `Baseline.` (trunk value first) · `Rule.` (head vs trunk, with the failing number; unlike scenarios → absolute budgets for diff-added work and user-visible end state, no ratio).
  - Review gate: interaction-changing PR → boxes to copy lane screenshots to `<media>/<pr-id>-review-<slug>.png`, record a 30-60 s video `<media>/<pr-id>-review.mp4`, attach both to the PR and give them to the panel's verifiers as receipts. Otherwise exactly `**Review gate.** None. <PR id> is not review-gated.` with no boxes.
  - Merge boxes: a panel pass at the exact head SHA being merged; review-comment triage done; a pr-review round on the merge head with no P0/P1 open and every P2 fixed or dismissed with a reason; `gh pr merge --match-head-commit <that SHA>`; who merges.
- `## Close the program`: every box checked with evidence; reply with the report the execution playbook names, with each PR's review line from the pr-review technique.
- Then only appendices: `## Appendix A. Prototype evidence` (questions answered with branch/SHA/artifacts; what stays unproven), `B. Alternatives rejected`, `C. Risks` (per PR, what the owner watches; any surface with no verification skill), `D. Links and reading list` (docs to read, which PRs get **how** and contested-design review, the **show-me-your-work** trail).

### Gates

The Plan checklist. Every item must pass, outside code fences:
- No long dashes (U+2013, U+2014), no curly quotes, no mid-sentence `: ` in prose (code spans and links excepted).
- H1 present; intro under 10 non-blank lines; How to read this contains the four markers above, a `playbooks/` path, and the rule.
- Program checklist has the five `###` in order and contains `skill://deepmodebot/`, the recurring tick, and "status message".
- Program checklist `PR mechanics, for every PR` contains `pr-review` and the technique path `references/techniques/pr-review.md`.
- At least one PR section between Program checklist and Close the program; Close the program exists.
- Each PR section: all nine sub-blocks in exact order; Depends on non-empty; Files, Build, You see, Verify unit, Merge each have ≥1 box; three Verify blocks open with the rule.
  - Live names the lane model and lists Lanes 1..N (up to 10, scaled to affected surfaces), every box a lane with a ``Save `…` `` screenshot and "Pass when".
  - Perf boxes exactly Metric, Probe, Baseline, Rule.
  - Review gate either "None." with no boxes, or boxes mentioning screenshot, video, and attaching both to the PR and the panel.
- Every `##` after Close the program is an Appendix; Appendix A Prototype evidence exists.
- Execution starts once the Plan checklist passes, under the playbook the plan names.
- A surface with no verification skill is a risk in Appendix C; its live block still names how each lane drives it.

### Evidence

- Plan path; PR ids with dependencies and the review-gated set.
- What prototypes proved and what stays unproven.
- Plan checklist results: per PR section, box counts per sub-block; total PR sections; the pr-review PR-mechanics item; every failure fixed (0 remaining).

## Build mode (and Sprint mode)

In **Build mode**, every ticket merges into one **integration branch**, and one PR carries that branch to trunk (`1/N` to `N/N`). In **Sprint mode** (default for multi-sprint specs or complex domains), run steps 1-8 **one sprint at a time** on `spec/<slug>-sprint-<n>` backed by the Scope Manifest (`docs/specs/<slug>-manifest.json`, `active_sprint: <n>` / `loop.py manifest --sprint <n>`).
Sprint `n` verifies every slice with `sprint <= n`, lands with live proof and **sme-review** (`references/techniques/sme-review.md`), and pauses ONLY at the explicit sprint/SME feedback checkpoint (`sme_gate: "required"` or `checkpoint_every` exit 6). Sprint `n+1..N` stay `queued`/`deferred` (`scope_complete: false`) and are reported as remaining scope (incomplete, never done).

You coordinate; ticket owners write the code. The tickets are a graph, not a list. The **frontier** is every open ticket in the active sprint whose blockers are all merged into the integration branch.

### Steps

1. **Load the graph.** Read the spec (issue and `docs/specs/<slug>.md`), its Scope Manifest (`docs/specs/<slug>-manifest.json` when present), and every ticket with its Blocked by lines, per **tracker** (`references/techniques/tracker.md`). Record the graph, manifest path, `active_sprint` (`1` in Sprint mode, or `all` in Build mode), `sme_gate` state, integration branch, `latest-summary.json` resume pointer, and each ticket's owner and state in one notes file a cold start can find (`references/playbooks/run-a-goal.md`).
   Done when the notes file lists the integration branch, manifest/`active_sprint` state, and every ticket with its sprint, blockers, owner, and state.
2. **Explore once** (optional). Tickets that share unknown code → one `scout` pass that returns file pointers, conventions, and test commands. Save its report beside the notes file and give owners the path, not a pasted copy.
   Done when the scout report sits beside the notes file, or no two tickets share unknown code.
3. **Integration branch.** In Build mode, use `spec/<slug>` when the Spec playbook created it; else create it off the default branch. In Sprint mode, cut `spec/<slug>-sprint-<n>` off the default branch once Sprint `n-1` has landed. When the repo has a remote, push it with an explicit refspec. Without a remote, every push and PR step below is skipped. Worktrees share one `.git`, so local branches are enough.
   Done when `git rev-parse --verify <branch>` succeeds and, with a remote, `git ls-remote origin <branch>` lists it.
4. **Start the frontier.** One fresh default `task` owner per frontier ticket, each in its own worktree on branch `ticket/<n>-<slug>` cut from the integration branch tip, under Run a goal, Program scale step 3. Pin each owner's model tier and effort up front (`skill://agent-harnesses/references/delegation-efficiency.md`: small/mid for mechanical or oracle-backed tickets; flagship `L` for hard design, security, and closing review), cap concurrent owners to 3-5 per wave (higher only when quota allows), and reuse owners across fix rounds to keep prompt caches warm.
   Each kickoff names the spec path, the ticket, the notes paths, its allowed files, and these duties:
   - Confirm the worktree's base is the current integration tip; reset onto it if not.
   - Build with the Feature or Bug fix playbook's steps (`references/playbooks/feature.md`, `references/playbooks/bug-fix.md`) and commit on the ticket branch, but skip their Opening a PR and Shipping steps. No ticket PR and no push to the default branch. A ticket reaches trunk only through step 5's merge and step 7's single PR.
   - Write the ticket's Done when as failing checks first per the **tdd** technique (`references/techniques/tdd.md`) where a cheap seam exists.
   - Prove each Done when item on the real surface.
   - Run the **pr-review** technique (`references/techniques/pr-review.md`) in local mode against the integration branch and fix, dismiss with a reason, or escalate each finding.
   - Merge the integration tip into the ticket branch, rerun the checks, push (when there is a remote), and report the head SHA with its evidence.
   - Done when every frontier ticket has an owner on its `ticket/<n>-<slug>` worktree, recorded in the notes file, capped to 3-5 concurrent owners per wave (scaling higher only when quota allows).
5. **Merge each finished ticket.** Read the owner's evidence and diff. In a clean worktree of the integration branch, run `git merge --no-ff ticket/<n>-<slug>`, rerun the repo's checks, push when there is a remote. A conflict or red check goes back to the owner with the output.
   No PR exists yet, because Opening a PR hands every PR straight to pr-conversation, which would land a partial build.
   Done when the ticket's merge commit is on the integration branch and the repo's checks pass there.
6. **Move the frontier.** After each merge, comment the merge SHA on the ticket, recompute the frontier, and start owners for newly unblocked tickets. A ticket that grows past one session is split with the Tickets playbook's rules and the graph updated.
   Done when the ticket has its merge-SHA comment and every newly unblocked ticket has an owner.
7. **Close the build (or sprint).** When every ticket in the active sprint (or build) is merged:
   - Run pr-review on the integration branch against the default branch, with the spec as the claim, so its Spec findings check every user story and Done when item in scope. In complex domains, also run the **sme-review** lens (`references/techniques/sme-review.md`).
   - One fresh owner fixes every finding in one pass on the integration branch.
   - Local tracker → set each finished ticket (and the spec, once the final sprint closes) to `Status: closed` on the integration branch, so the close lands with the code.
   - With a remote, open one PR from the integration branch to the default branch through Opening a PR (`references/playbooks/opening-a-pr.md`), with `Closes #<ticket>` per finished ticket (and `Closes #<spec>` only on the final sprint). It lands through the **pr-conversation** technique (`references/techniques/pr-conversation.md`) on a **panel** pass (`references/techniques/panel.md`) at its head.
   - No remote → after a panel pass at the integration tip, run `git merge --no-ff <integration branch>` in a clean worktree of the default branch and rerun the checks there. A red result is undone with `git revert -m 1 <merge sha>`.
   - **Sprint feedback gate (Sprint mode, before Sprint `n+1`):** run `loop.py manifest <manifest.json> --sprint <n>` (when a manifest exists) so slices `<= n` pass with zero `pending` inventory items, report the live proof for landed Sprint `n`, and explicitly list Sprint `n+1..N` as **remaining scope (incomplete, `scope_complete: false`, never marked done)**. Surface unverified domain questions via **questionnaire** (`references/techniques/questionnaire.md`), incorporate SME/customer feedback into Sprint `n+1..N` tickets, and set `"sme_gate": "cleared"` before starting Sprint `n+1`.
   - Done when the sprint or final PR is merged (no remote: local merge on default branch) on a panel pass at its head, trunk checks pass, and in Sprint mode either SME/customer feedback is gathered (with Sprint `n+1..N` explicitly reported as remaining scope) or the final sprint is closed.
8. **Clean up** the ticket worktrees and merged ticket branches you created, per Worktree cleanup (`references/playbooks/worktree-cleanup.md`).
   Done when `git worktree list` and `git branch --list 'ticket/*'` show none of the ones you created.

### Gates

- Only you merge into the integration branch, and only a ticket whose evidence you read.
- The integration branch stays green after every merge. A red merge is reverted on the branch before the next one.
- Sprinting never shrinks Total Scope: Sprint `n` verifies all slices `<= n`, rejects unclassified `pending` inventory items, honors `"sme_gate": "required"`, and reports deferred Sprint `n+1..N` as incomplete remaining scope (`scope_complete: false`).
- The final PR (no remote: the final local merge) lands only on a panel pass at its exact head, with no P0 or P1 review finding open.
- Subagent briefs carry pointers (spec, ticket, notes, commits), not copies of them.

### Evidence

- The final PR link (no remote: none), its merge SHA, and the trunk check after the merge.
- Per ticket: owner, merge SHA into the integration branch, and the Done when evidence.
- The closing review line and panel line.
- Decisions made on the user's behalf, each with how to reverse it.
