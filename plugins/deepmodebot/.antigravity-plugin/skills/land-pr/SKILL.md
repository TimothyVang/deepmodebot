---
name: land-pr
description: "Explicit-invocation only (/land-pr): land a PR with no human via deepmodebot bots on your own subscriptions. Never auto-invoke without an explicit /land-pr or user merge request."
disable-model-invocation: true
---

# /land-pr

**Explicit-invocation gate:** Antigravity ignores frontmatter `disable-model-invocation: true`. Proceed with autonomous landing or `--admin` merge ONLY when the user explicitly invoked `/land-pr` or directly asked you to land/merge this PR on your own in their message. If loaded implicitly without that explicit user request, STOP and ask before any merge action.

Read `skill://deepmodebot` and then `skill://deepmodebot/references/techniques/pr-conversation.md` (`../../../skills/deepmodebot/references/techniques/pr-conversation.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/references/techniques/pr-conversation.md`) in full, and follow it to land the PR specified by the user.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Once the explicit-invocation gate above is satisfied, `/land-pr` asks to merge on your own with no owner approval in the loop.
That authorizes `--admin` ONLY to bypass a required review on the user's own PR when the panel passed at that exact head, every check (required or optional) is green with none failing/cancelled, the repo's local gate passed at that head, and `--admin` would not bypass other branch rules (signed commits, linear history, CODEOWNERS, unresolved conversations).
If the base branch's `.deepmodebot.json` sets `"autonomousMerge": false`, stop and ask instead.
Never merge over a failing check or someone else's PR, and never delete the branch.

Run the bots as separate ACP agents through `acpx`, with the agent and model each role names in `~/.config/deepmodebot/bot.json` (`acpx`, `bot.json`, and any harness ACP adapters or `~/.acpx/config.json` registration must be set up first).
Each harness uses its own subscription login.
Pass each turn between their sessions yourself and mirror it to the PR thread under the deepmodebot GitHub App when it is configured, or `gh` when it isn't. No API keys, and don't wait for hosted review bots.

Apply this to the PR number or URL the user specified.
