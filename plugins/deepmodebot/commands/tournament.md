---
description: "Run a 12-agent evidence-backed tournament bracket across architecture and research lenses, proposing Champion, Runner-Up, and the Full Ranked High-Leverage Portfolio"
argument-hint: "<open goal, subsystem, or 'find architecture and research gaps in ...'>"
---

Read `skill://deepmodebot` (**Contain the work**, **Non-negotiables** Secrets, and **Autonomy** subscription rules) and `skill://deepmodebot/references/techniques/tournament.md` in full, then run the **tournament** bracket on $ARGUMENTS. Outside a git repo, create a named project root first per **Contain the work** and keep every scratch or temp file inside `<root>/.scratch/`.

Initialize the bracket with `python -B "<deepmodebot skill dir>/assets/tournament/tournament.py" init --root "<root>" --slug "<slug>" --prompt-stdin <<'EOF'` (`py -3 -B` on Windows). Spawn read-only contenders across architecture and research lenses and require checkable receipts (`<repo-rel-path>:<line>`, public `https://...` URL, or `cmd:<probe> -> <output>`). Run Round 1 clashes, the semifinals, and the final with an independent judge and single-insight grafting. Present Champion, Runner-Up, and the Full Ranked High-Leverage Portfolio (`1..N` across all pitched lenses) before production edits. Discovery-only requests stop for a pick; an original build request continues with Champion unless I asked to choose first.

`<deepmodebot skill dir>` is the folder `skill://deepmodebot` resolves to on disk; python needs that file path, not the `skill://` URL. In Claude Code it is `${CLAUDE_PLUGIN_ROOT}/skills/deepmodebot` for a plugin install, or `~/.claude/skills/deepmodebot` for a manual one.

Goal: $ARGUMENTS
