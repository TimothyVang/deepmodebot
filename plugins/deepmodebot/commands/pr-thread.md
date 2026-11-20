---
description: "Show what the deepmodebot bots said on a PR or issue: a short text digest, 8-bit frames of the turns right here, or the live 8-bit battle screen in your terminal"
argument-hint: "<PR or issue URL | owner/repo> [frames [N] | arena]"
---

Show me the bot conversation for $ARGUMENTS. This command only reads threads: post nothing, edit no repo files (skip creating `.scratch/workspace-map.db` if none exists).

- A PR or issue URL alone: run `python -B "<deepmodebot skill dir>/assets/pr-conversation/show_thread.py" <url>` (`py -3 -B` on Windows) and show me its output as it is. If I ask what one bot said in full, run it again with `--full`.
- With `frames`: run `python -B "<deepmodebot skill dir>/assets/pr-conversation/arena.py" <url> --frames` (`py -3 -B` on Windows; `--last N` when I give a number, `--repo <owner/repo>` for a repo) and show me its output as it is, inside a fenced `text` code block so the columns stay aligned. It prints one 8-bit frame per turn (the newest 3 by default) and ends with the newest comment id.
- With `arena`, or an `owner/repo` without `frames`: the 8-bit display runs full screen in a terminal, so give me the command to run in my own terminal window: `python -B "<deepmodebot skill dir>/assets/pr-conversation/arena.py" <url>` (`py -3 -B` on Windows; or `--repo <owner/repo>`), with the real path filled in. If I ask for it in a browser instead, start it with `--serve --open` as a background service and give me its local URL.

`<deepmodebot skill dir>` is the folder `skill://deepmodebot` resolves to on disk; python needs that file path, not the `skill://` URL. In Claude Code it is `${CLAUDE_PLUGIN_ROOT}/skills/deepmodebot` for a plugin install, `${CLAUDE_PROJECT_DIR:-.}/.claude/skills/deepmodebot` project-local, or `~/.claude/skills/deepmodebot` for a manual one.

Arguments: $ARGUMENTS
