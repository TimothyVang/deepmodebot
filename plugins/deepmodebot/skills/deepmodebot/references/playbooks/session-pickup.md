# Session pickup

Use when: resuming work a prior agent or session started ("pick up where X left off", "continue that session", a handed-over branch or resume note). You own the resume point: read the prior trail, don't redo it.

## Steps

1. Locate the prior trail and resume ledgers.
   - A prior omp session: consult it with `task`, `agent: "seance"`, `sourceSession: <id/path>` (the consult is the read; don't grep its `.jsonl`), or read an `agent://`/`history://` transcript. On other harnesses (Antigravity, Claude Code, Codex), read the saved conversation transcript file or handoff doc.
   - Check durable resume state on disk: resume note (`$(git rev-parse --git-common-dir)/omp-resume/<slug>.md` or `<root>/.scratch/resume-<slug>.md`, plus any patch beside it), show-me-your-work trail, pushed branch, and any active Scope Manifest (`docs/specs/*-manifest.json` or `.scratch/goals/*-manifest.json`) plus `.scratch/goals/<slug>/latest-summary.json`.
   - When a goal file exists, run `python -B "<deepmodebot skill>/assets/loop/loop.py" status <goal.md> --json` (`py -3 -B` on Windows) to read `active_sprint`, `deferred_slices`, `pending_inventory`, and `sme_gate_blocked`.
   - Stay inside the active project; never read sessions from unrelated projects.
   - Done when every located trail, manifest, and `latest-summary.json` path (or session id) is recorded inside the active project.
2. Read the overview and last messages first, then scan back for decision points. Parse a long transcript in a subagent and keep only the reduced timeline in the main thread (`references/principles/guard-the-context-window.md`).
   Done when a reduced timeline lists the trail's decision points and its last action.
3. Reconstruct operational state: branch and worktree, what already landed (`git log`, `git diff <base>...HEAD`), open todos, decisions made, and manifest/sprint/SME gate state (`active_sprint`, `deferred_slices`, `pending_inventory`, `sme_gate_blocked`). The prior trail and ledgers are authoritative input; resist re-deriving them.
   Done when the branch, worktree, landed commits, open todos, decisions, and any manifest/sprint state are written down.
4. Diff done vs pending against the plan (and Scope Manifest when present) and name the resume point. Do not redo completed work or re-run claims that already have recorded real-artifact receipts; spot-check only unproven prior self-reports on the real artifact (`references/principles/prove-it-works.md`).
   Done when every plan/manifest item is marked done or pending, unproven self-reports are checked on the real artifact, and the resume point is named.
5. Pick the verdict: continue the execution, ship a finished recommendation, ratify or override a prior conclusion, or postmortem a failed run. Done when exactly one verdict is recorded with its reason.
6. Route the remaining work to the matching playbook; pickup ends here and the routed playbook owns the rest. Done when the routed playbook is named and started.

## Gates

- Redoing completed work with recorded real-artifact receipts is a failure of this playbook unless step 4's check shows an unproven inherited claim is false.
- Never cross project boundaries to find a trail.
- Pickup follows SKILL.md Autonomy like any run: commits, pushes, and PRs proceed; merges need a panel pass; hard stops need the user.

## Evidence

- Where the prior agent stopped (with the trail you read).
- What you inherited vs redid (ideally nothing redone, and why if anything was).
- The resume point, the routed playbook, and the verdict.
- The outcome, including the real-artifact check of inherited claims.
