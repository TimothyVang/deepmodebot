# Rule approval: owner-signed agent rules

Mechanics behind the `SKILL.md` rule approval rule. Code: `assets/rules/rule_ledger.py`. Tracked paths: `assets/rules/rule-paths.json`.

## What counts as a rule

- Files coding agents load as instructions or permissions, at any depth: `AGENTS.md` (plus `.override`/`.local`), `AGENT.md`, `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.roorules`, `.rules`.
- Everything under rule, skill, agent and command folders: `.claude/{rules,skills,agents,commands}`, `.omp/{rules,skills,agents,commands}`, `.agents/{rules,skills,workflows}`, `.cursor/rules`, `.windsurf/rules`, `.devin/{rules,skills}`, `.roo/rules`, `.kiro/steering`, `.continue/rules`, `.amazonq/rules`, `.github/instructions`, `.codex/{rules,agents}`.
- Settings that grant agents permissions or pick their rule files: `.claude/settings.json`, `.claude/settings.local.json`, `.codex/config.toml`, `.gemini/settings.json`, `.github/copilot-instructions.md`, `.omp/RULES.md`, `.omp/SYSTEM.md`, `.deepmodebot.json`, `.deepmodebot/policy.xml`.
- `convention` records in the project memory (`.scratch/deepmode-memory.db`).
- Gitignored rule files (`CLAUDE.local.md`, `.claude/settings.local.json`) are personal: the hooks block agent writes to them, but the ledger never stores them, so their text never lands in git. Paths under `.git`, `node_modules`, `.scratch` or `.worktrees` never count, so drafts in `.scratch/` are free.
- A rule path may be a symlink only to another rule path (`CLAUDE.md -> AGENTS.md`). A link to anything else is refused at `init` and fails the gate, because its target could change unseen.

## Owner workflow

1. `deepmodebot rules init` lists every rule present, asks you to approve them as the baseline, and sets your passphrase (8+ characters). Commit `.deepmodebot/rules/` so clones and CI enforce it.
2. `deepmodebot rules status` shows each rule as approved, changed, new or removed, plus waiting proposals. `review` prints every pending change with its id and diff. `log` prints the signed decision history. Agent text is shown with control characters escaped.
3. `deepmodebot rules approve <id>...` or `reject <id>...` (`--all` for everything) asks for the passphrase. Rejecting puts the approved text back, deletes an unapproved new rule file or memory convention, or restores a deleted rule. Commit `.deepmodebot/rules/` with the rule files.
4. `deepmodebot rules rotate` changes the passphrase; the old key signs the new one. A lost passphrase means `rule_ledger.py init --reset`, which keeps the history but changes the key. The gate flags that change until you commit it yourself with `git commit --no-verify` and merge it into the default branch.

Never type the passphrase into an agent chat or an agent-run terminal.

## Agent workflow

- Never edit a rule file in a repo with `.deepmodebot/rules/ledger.json`. Draft the full new file under `.scratch/`, then run `python -B <skill>/assets/rules/rule_ledger.py propose --item AGENTS.md --file .scratch/AGENTS.draft.md --reason "<why>" --by <harness>`. The rule file stays unchanged until the owner approves.
- Tell the owner the proposal id and to run `deepmodebot rules review`. Never run `init`, `approve`, `reject` or `rotate`, never skip git hooks, and never ask for the passphrase.
- Memory conventions you record stay hidden from `project_memory.py recall` until approved; recall reports how many with `unapproved-conventions-hidden`.
- `deepmodebot init` (`assets/setup/project_setup.py`) follows the same path: it proposes `.deepmodebot/policy.xml` and its managed-block refresh for `AGENTS.md` and `CLAUDE.md` instead of writing them.

## Enforcement layers

| Layer | What it stops |
|---|---|
| Hooks: Claude Code `hooks/hooks.json`, omp `assets/contain/omp-contain.ts`, Antigravity `scripts/antigravity-guard.mjs` | In every session of a ledger repo, active or not: file-tool writes to rule files and the ledger (also through symlinked folders or aliases); shell commands that write, move or delete them (redirects, `tee`, `sed -i`, `cp`/`mv`/`rm`/`ln`, globs, `cd` chains, `find -delete`, `curl -o`, `bash -c`, inline interpreter code, heredocs); writers fed by `xargs` or `$(...)`; `git commit --no-verify`/`-n` and `core.hooksPath` changes. Owner-only commands are blocked in any repo. |
| Ledger signature | Ed25519 over the canonical ledger with a key derived from the passphrase (PBKDF2-SHA256, 600k rounds). Any edit without the passphrase breaks the signature. |
| Gate: `rule_ledger.py check` inside `slop_gate.py`, the `project_setup.py --install-hooks` pre-commit hook, and `deepmodebot gate rules` | P1 per unapproved change and per symlinked rule whose target is not a rule path. P0 for a forged ledger, a ledger rolled back to an older version, an owner key swapped without a rotation signed by the old key, a deleted ledger, a symlinked store, or a missing approved copy. The ledger must extend the committed one at HEAD and at the merge-base with `origin`'s default branch, so a bad ledger committed with hooks skipped still fails against the default branch. `--staged` checks the commit; CI passes `--base origin/main`, which must resolve. |
| Memory recall | Unapproved conventions never reach the agent. |

## Storage

- `.deepmodebot/rules/ledger.json`: owner key (public key, salt, rounds), approved item to SHA-256 map, approved symlinks, decision history, signature.
- `.deepmodebot/rules/approved/<sha256>`: the approved bytes, used for diffs and rejects.
- `.deepmodebot/rules/proposals/<id>.json`: agent proposals waiting for the owner.

## Limits

- Codex has no deepmodebot hook; the gate catches its rule edits at commit time.
- Shell parsing is best effort. A script written to a file and then run, `git apply`, or a path held in a shell variable can still change a rule in the working tree, and harnesses may load that text until the owner rejects it. The signed ledger keeps it from being approved, and the gate blocks the commit.
- An agent with full shell access can remove hooks or the plugin and commit with hooks skipped. The check against the default branch catches that commit; keep the default branch protected and merge only PRs whose rule gate passes.
- A repo with no `origin` default branch anchors trust on HEAD only.
- Trust starts at `init`: whoever runs it first sets the owner key, which is why `init` is blocked for agents everywhere.
