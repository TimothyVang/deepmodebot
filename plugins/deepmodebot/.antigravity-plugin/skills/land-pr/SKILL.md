---
name: land-pr
description: "Land a PR with no human: deepmodebot bots review, fix, verify and merge it in the PR thread, on your own subscriptions. Use when invoked via /land-pr."
disable-model-invocation: true
---

# /land-pr

Read `skill://deepmodebot` and then `skill://deepmodebot/references/techniques/pr-conversation.md` (`../../../skills/deepmodebot/references/techniques/pr-conversation.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/references/techniques/pr-conversation.md`) in full, and follow it to land the PR specified by the user.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

When the user invokes `/land-pr`, they are asking to merge it on your own: no owner approval and no human in the loop.
That is their yes for `--admin` when the base branch requires a review, as long as the panel passed at that exact head, every required check reported green, and the repo's local gate passed at that head.
If the base branch's `.deepmodebot.json` sets `"autonomousMerge": false`, stop and ask instead.
Never merge over a failing check or someone else's PR, and never delete the branch.

Run the bots as separate ACP agents through `acpx`, with the agent and model each role names in `~/.config/deepmodebot/bot.json` (omp by default; any ACP agent works).
Each harness uses its own subscription login.
Pass each turn between their sessions yourself and mirror it to the PR thread under the deepmodebot GitHub App when it is configured, or `gh` when it isn't. No API keys, and don't wait for hosted review bots.

Apply this to the PR number or URL the user specified.
