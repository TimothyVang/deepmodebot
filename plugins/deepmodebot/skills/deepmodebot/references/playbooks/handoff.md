# Handoff

Use when: the work should continue in a fresh context: "hand this off", "write a handoff", "summarize this for another agent", "continue this in a new session", "start a background agent on the rest", or the context is crowded and the next phase is cleanly separable (then start a background agent on the rest: a handoff you start yourself keeps every ledger item open).
Stopping for later in this same repo is Pause safely (`references/playbooks/pause-safely.md`); picking up someone else's handoff is Session pickup (`references/playbooks/session-pickup.md`); parallel work while this session continues is a `task` subagent. You own a document a cold agent, another harness, or a colleague can act on without this conversation.

## Steps

1. Set the focus. The user's words after "handoff" say what the next session is for; tailor the document to that. No focus given → the next unfinished unit of the current goal.
   Done when the focus is one sentence with a done-when check (a command and its expected result).
2. Make the work reachable: for remote/branch work, commit finished units on a non-default working branch (never commit or push directly to the default branch) and push it so the next agent reads the branch instead of a description of it. Half-done edits get a `wip:` commit (say so in the document). For local uncommitted S/M delivery or repos with no remote, skip pushing and leave verified S/M edits uncommitted (or note the exact tree/branch state in the document).
   Done when the working tree and branch state match the delivery mode (clean and pushed on a non-default branch, or local-only state recorded).
3. Prepare `docs/handoffs/<YYYY-MM-DD>-<slug>.md` (outside a repo: the current folder) with the sections below. Apply step 4's redaction and key-shaped-string scan to its contents before writing this document or any compaction checkpoint.
   - **Goal:** the user's goal and the problem, in your own words (**in-your-own-words**, `references/techniques/in-your-own-words.md`).
   - **Next session's focus:** from step 1, with its done-when check (a command and its expected result).
   - **State:** repo, branch, head SHA, open PRs and their status, what is verified and how, what is not, plus Scope Manifest (`docs/specs/<slug>-manifest.json` or `.scratch/goals/<slug>-manifest.json`) and `latest-summary.json` (`active_sprint`, `deferred_slices`, `inventory_counts`, `sme_gate_blocked`) when present so remaining scope carries across pauses, sprint checkpoints (`exit 6`), SME gates, or quota stops.
   - **Decisions:** each choice made and why, or a pointer to the decision trail that holds them.
   - **Open questions and risks.**
   - **Next steps:** ordered, the first one concrete enough to start without reading anything else (naming the next queued slice or inventory item from the Scope Manifest when active).
   - **Pointers:** paths and URLs to specs, Scope Manifest, `latest-summary.json`, ADRs, issues, PRs, logs, and trails. Link artifacts; never paste their contents.
   - **Start with:** the deepmodebot route the next agent should take (playbook or technique names and paths), and the skills it should load.
   - Done when the file exists with all eight sections filled.
   Before compaction or session replacement, persist pending actions, active child/process identifiers, remaining task budget, permission limits, and evidence paths alongside this state.
   Re-read that state and the current artifact before resuming; resolve uncertain side effects from their actual status instead of blindly replaying a tool call.
   Done when the next session can distinguish completed, pending, failed, and unknown work without the old conversation; serialized context alone is not durable execution.
4. Redact before saving: API keys, tokens, passwords, connection strings, private hostnames that matter for security, personal data about anyone. Replace each with `<redacted: what it was>` and say where the real value lives (`.env`, a secret manager). Scan the file for key-shaped strings (`sk-`, `ghp_`, `AKIA`, `-----BEGIN`, `password=`) before going on.
   Done when every match of that scan is a `<redacted: ...>` placeholder.
5. Decide where it lives. Next agent on this machine → leave the file untracked. Next agent elsewhere or a colleague → commit it to the working branch and push. Print its absolute path.
   Done when the absolute path is printed and, for a remote reader, the pushed branch contains the file.
6. Launch, only when asked for a background or new agent. Unset API-key and cloud-billing env vars first (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`, per `SKILL.md`) so the child uses subscription logins. Pass the file, not pasted text, so the shell never expands `$` or backticks:
   - omp, attended: `omp @<file>` in a new terminal (the `@` prefix reads the file as the first message).
   - omp, unattended: POSIX `nohup omp -p @<file> > <file>.log 2>&1 &`; Windows PowerShell `Start-Process omp -ArgumentList '-p','@<file>' -RedirectStandardOutput <file>.log -RedirectStandardError <file>.err.log`. Saved runs show in `omp -r`.
   - Claude Code: POSIX `claude --bg -n "<short task name>" -- "$(cat <file>)"`; Windows PowerShell `claude --bg -n "<short task name>" -- (Get-Content -Raw <file>)` (or pass a short prompt pointing at `<file>` to avoid command-line length limits); `claude agents` lists it.
   - Antigravity (`agy`): `agy -p "Follow the handoff in <file>" --output-format json > <file>.log 2>&1` (resume with `agy -c` or `agy --conversation <id>`). Note: in headless `-p` mode, actions matching `Ask` rules are silently soft-denied even when `agy -p` exits `0`, so pre-allow required tools in `permissions.allow` first.
   - Codex: POSIX `codex exec -s workspace-write --json - < <file> > <file>.log 2>&1`; Windows PowerShell `Get-Content -Raw <file> | codex exec -s workspace-write --json - > <file>.log 2>&1` (resume with `codex exec resume --last`).
   - Other harnesses: their headless or background flag with the same file. None → give the user the command to start it themselves.
   Done when the launched name or log path is reported, or no launch was asked for.

## Gates

- Nothing lives only in this context: every fact the next agent needs is in the document, the branch, or a linked artifact.
- No secrets or personal data in the document (step 4 scan done).
- A launched agent follows SKILL.md Autonomy on its own; its hard stops still need the user.

## Evidence

- The handoff path, and whether it is committed.
- Branch and head SHA it describes.
- The launch command and the agent's name or log path, if one was launched.
- What was redacted (kinds, not values).

Context-lifecycle evidence: the [session/compaction discussion](https://www.youtube.com/watch?v=zOiFHo2KVgc&t=1097s) distinguishes harness state from the small agent loop.
These handoff checks are synthesis, not proof that a resumed process or external side effect runs exactly once.
