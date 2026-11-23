---
description: "Open deepmodebot's live view: an AG-UI page that shows the plan, progress, diagrams, screenshots and proof, and lets you answer the agent's questions in the browser"
argument-hint: "[what to show or explain] | stop"
---

Show me $ARGUMENTS in the live view, following the **live-view** technique (`references/techniques/live-view.md` in `skill://deepmodebot`).

- With `stop`: run `node "<deepmodebot skill dir>/assets/live-view/agui.mjs" stop` from the project root and tell me it stopped.
- Otherwise start `node "<deepmodebot skill dir>/assets/live-view/agui.mjs" serve --open` from the project root as a background service (reuse a running one: `.scratch/live-view/session.json` exists and its `/health` answers), give me the printed URL, then:
  1. Set the goal and plan for what I asked (`plan --goal …`), or for the current task when I named nothing.
  2. Explain it with visuals (`visual mermaid|table|image|code|markdown`) and short `say` messages, not long prose.
  3. Ask me in the page (`ask … --choices …`) only for real choices; decide everything else and say what you chose.
  4. Back every "works" or "fixed" claim with `proof … --evidence <screenshot or log>`, then `done`.

Keep the full report in your reply too. Leave the view running until I say `stop` or the session ends.

`<deepmodebot skill dir>` is the folder `skill://deepmodebot` resolves to on disk: `${CLAUDE_PLUGIN_ROOT}/skills/deepmodebot` for a Claude Code plugin install, `${CLAUDE_PROJECT_DIR:-.}/.claude/skills/deepmodebot` project-local, or `~/.claude/skills/deepmodebot` for a manual one.

Arguments: $ARGUMENTS
