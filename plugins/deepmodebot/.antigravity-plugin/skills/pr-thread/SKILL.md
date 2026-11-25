---
name: pr-thread
description: "Show deepmodebot bot turns on a PR/issue (/pr-thread): text digest, inline 8-bit frames, or live terminal arena."
---

# /pr-thread

Show the bot conversation for the PR, issue URL, or `owner/repo` the user asked for. This command only reads threads: post nothing, edit no repo files (skip creating `.scratch/workspace-map.db` if none exists).

Let `<deepmodebot skill dir>` be the folder `skill://deepmodebot` resolves to on disk (`../../../skills/deepmodebot` relative to this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot` for a global Antigravity install).

- A PR or issue URL alone: run `python -B "<deepmodebot skill dir>/assets/pr-conversation/show_thread.py" <url>` (`py -3 -B` on Windows) and show its output as it is. If the user asks what one bot said in full, run it again with `--full`.
- With `frames`: run `python -B "<deepmodebot skill dir>/assets/pr-conversation/arena.py" <url> --frames` (`py -3 -B` on Windows; `--last N` when given a number, `--repo <owner/repo>` for a repo) and show its output inside a fenced `text` code block so the columns stay aligned. It prints one 8-bit frame per turn (the newest 3 by default) and ends with the newest comment id.
- With `arena`, or an `owner/repo` without `frames`: the 8-bit display runs full screen in a terminal, so give the user the command to run in their own terminal window: `python -B "<deepmodebot skill dir>/assets/pr-conversation/arena.py" <url>` (`py -3 -B` on Windows; or `--repo <owner/repo>`), with the real path filled in.
- If the user asks for `arena` in a browser instead, start it with `--serve --open` as a background service and give them its local URL.

Apply this to what the user asked for.
