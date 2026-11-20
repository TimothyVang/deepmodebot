# Spec

Use when: the conversation has settled what to build and it should be written down before anyone builds it ("write the spec", "turn this into a spec", "spec it up", "make this an issue an agent can build"), or the Wayfinder playbook's route is clear and its destination is a feature. Synthesis, not interview: everything needed is already in the conversation, the code, and the decisions made so far. An open question → the **grill** technique (`references/techniques/grill.md`) first, then come back.

The spec is the contract a build is judged against: the **pr-review** technique's spec findings and the panel's Done when both read it. It lives in `docs/specs/<slug>.md` and one tracker issue labeled `spec`; for multi-slice or sprint builds, pair it with a machine-checked Scope Manifest (`docs/specs/<slug>-manifest.json`, validated with `python -B "<this skill>/assets/loop/loop.py" manifest <file> --dry-run`, `py -3 -B` on Windows) holding 100% of Total Scope (all stories, slices, and `"inventory"` candidates) so slicing never drops scope.

## Steps

1. **Gather.** Collect the decisions from the conversation and its show-me-your-work trail. Read `GLOSSARY.md` and the ADRs in the area (`docs/adr/`) so the spec uses the project's words and does not contradict a recorded decision. Unknown code → `scout` tasks for entry points, the modules involved, and existing tests near them.
   Done when every decision, glossary term, and ADR in the area that bears on the spec is listed in your notes.
2. **Pick the test seams.** A seam is the boundary a test drives (an HTTP route, a CLI command, a public function, the UI). Prefer the highest seam that already exists; add a new one only when no existing seam can observe the behavior, and as high as possible. Fewer seams is better; one is ideal. Record the choice as a trail row.
   Done when the trail has a row naming each seam and why it was chosen.
3. **Write `docs/specs/<slug>.md`** with the template below, with the **technical-writing** technique (`references/techniques/technical-writing.md`), then **unslop** (`references/techniques/unslop.md`).
   Done when the file exists with every template section filled.
4. **Check it (including SME sanity in complex domains).** Every user story maps to at least one Done when item; every Done when item can be checked by a command, a test at a named seam, or an observation on the real surface; no file paths or line numbers (they rot), except a short snippet a prototype produced that states a decision better than prose.
   If the domain is complex or requirements carry unverified domain rules (or rough-idea essentials that could become scope creep), run **sme-review** (`references/techniques/sme-review.md`) on the draft spec. When P0/P1 domain questions cannot be settled from the repo or a prototype, set `"sme_gate": "required"` in the Scope Manifest (or on Sprint 2+ slices) and pause via **questionnaire** (`references/techniques/questionnaire.md`) until the human SME verifies the rules and marks `"sme_gate": "cleared"`.
   Done when every story maps to a real-surface check and any complex-domain `sme_gate` is either cleared or explicitly recorded.
5. **Commit** the file on branch `spec/<slug>` off the default branch. Push it when the repo has a remote; with no remote, the local branch is enough. That branch becomes the integration branch of the Phased build playbook (`references/playbooks/phased-build.md`), so the spec lands with its code. When the user wants the spec on trunk before any build, open a docs PR for it through Opening a PR (`references/playbooks/opening-a-pr.md`) instead (no remote: merge it into the default branch locally after a panel pass).
   Done when `git log -1 spec/<slug>` shows the commit (pushed when a remote exists), or the docs PR is open.
6. **Publish** per the **tracker** technique (`references/techniques/tracker.md`): one issue, title `Spec: <name>`, labels `spec`, the category role, and `triage:agent-ready`. Body: a link to the file on its branch (no remote: its path and branch name), then the file's full text.
   Done when the issue exists with those labels and the full text.
7. **Next.** Hand off to the Tickets playbook (`references/playbooks/tickets.md`) unless the spec fits one PR, in which case the spec issue is itself the ticket. For multi-ticket or uncertain-domain specs, tell Tickets to cut **Sprint 1** as the smallest end-to-end feedback slice while keeping Sprint 2..N explicitly `queued`/`deferred` in the Scope Manifest (`active_sprint: 1`, `scope_complete: false`) so incremental delivery never shrinks Total Scope.
   Done when the Tickets playbook has started, or the spec issue is named as the ticket in your report.

## Spec template

```markdown
# <Name>

## Problem
<Who hits it, what they try to do, and what goes wrong today. Their view, not the code's.>

## Outcome
<What is true for them when this ships.>

## User stories
1. As a <role>, I can <action>, so that <benefit>.
<As many as it takes to cover every role, path, error, and empty state. A missing story is a missing feature.>

## Decisions
- <Module, interface, data shape, contract, or behavior decided, and why. Link the ADR when there is one.>

## Test seams
- <Seam>: <what it observes>. Nearby tests to copy: <test name or folder>.

## Done when
- [ ] <Observable result, with the command, test, or surface that shows it.>

## Out of scope
- <What this does not do, so the build doesn't grow into it.>

## Notes
- <Prototype evidence, research files, open risks.>
```

## Gates

- No interview for facts you can look up or calls you can make yourself (SKILL.md Autonomy); in a complex domain, **sme-review** sets `"sme_gate": "required"` and pauses for a human SME when customer-spec assumptions cannot be proved from the repo.
- Total Scope lives in the spec and Scope Manifest (`docs/specs/<slug>-manifest.json`); only the user removes scope, and sprinting never drops later stories.
- The spec never contradicts an accepted ADR. A spec that needs to → write the superseding ADR first (domain-model technique, `references/techniques/domain-model.md`).
- Done when items are behavior on a real surface, never "tests pass".

## Evidence

- The spec file path and branch, and the spec issue link.
- The chosen test seams and why.
- Decisions made while writing, each with how to reverse it.
