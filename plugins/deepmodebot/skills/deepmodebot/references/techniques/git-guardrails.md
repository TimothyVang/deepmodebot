# git-guardrails

**Use when:** "block dangerous git commands", "add git safety hooks", "stop the agent from force-pushing / resetting", or a retro found an agent ran or nearly ran a destructive git command. It turns SKILL.md's git hard stops from prose into a hook the harness enforces before the command runs.

Three files in `assets/git-guardrails/` do the work:
- `git-guard-patterns.txt`: the blocked commands, one regular expression per line. Both hooks read it, so the list has one home.
- `git-guard.sh`: Claude Code `PreToolUse` hook for the Bash tool. Exit 2 blocks the call and returns the reason to the agent.
- `git-guard.ts`: omp pre-tool hook. Blocks matching `bash` commands and `eval` cells.

**Blocked by default:** `reset --hard`, `clean -f`, `checkout .` / `restore .` (including `--source <ref>` / `<ref> -- .` forms in current patterns), `stash clear` and `stash drop`, `worktree remove --force`, `branch -D`, `filter-branch`/`filter-repo`, `update-ref -d`, `reflog expire`, `gc --prune=now`, pushes with `--force`, `-f`, `+ref`, `--mirror`, `--delete`, `--prune` or `:ref`, pushes that name `main`, `master`, or `trunk` as the destination, and `push --all`.

**Blocked on the default branch:** while `main`, `master`, or `trunk` is checked out, a push that names no destination (`git push`, `git push origin`) or pushes `HEAD`. These are the `@branch` lines in the pattern file; the hooks check the branch in the command's working directory.

**Allowed:** everything deepmodebot does in normal work: branches, commits, pushes to feature branches, `--force-with-lease` to a feature branch, `gh pr merge`.
Two playbook commands may match the patterns and be blocked too: `git worktree remove --force` (Worktree cleanup) and `git restore ... -- .` (the revert in Work a queue).
Drop `--force` for a clean worktree and use `git revert` for the revert; anything else is the user's to run. **Strict mode** (only the human pushes): uncomment the last line of the pattern file.

1. **Scope.** Default to the project: the hook files are committed, so every agent working in the repo gets them. User scope (every repo on this machine) only when asked. Done when the scope is chosen and its reason logged.
2. **Install for the harnesses in use** (both when unsure):
   - **Claude Code.** Copy `git-guard.sh` and `git-guard-patterns.txt` to `.claude/hooks/` (user scope: `~/.claude/hooks/`). Requires POSIX `bash` (Git Bash/WSL on Windows) with `grep -Eo -f <(...)`. Merge into `.claude/settings.json` (user scope: `~/.claude/settings.json`), appending to `hooks.PreToolUse`:
     ```json
     { "hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/git-guard.sh\"" } ] } ] } }
     ```
   - **omp.** Copy `git-guard.ts` and `git-guard-patterns.txt` to `.omp/hooks/pre/` (user scope: `~/.omp/agent/hooks/pre/`). omp loads hooks only from the `pre/` and `post/` folders, at session start.
   - **Antigravity (`agy`) / native Windows.** Antigravity's `antigravity-guard.mjs` guards file-edit tools, not shell commands; enforce destructive-git blocks with harness command-approval deny rules (or `git-guard.sh --check` via Git Bash/WSL). Other harnesses with a pre-command hook: call `git-guard.sh --check "<command>"` and block on exit code 2.
   - Done when each harness in use has the hook files or deny rules installed at its path.
3. **Tailor the list.** Ask nothing; read the repo. A default branch with another name (`develop`, `production`) gets added to the named-destination push line and to both `@branch` lines. Commands the repo's own scripts legitimately run get removed, with a comment saying why.
   Done when the pattern file names the repo's default branch and each removed line has its comment.
4. **Prove it.**
   - Claude Code script (POSIX / Git Bash): `echo '{"tool_input":{"command":"git reset --hard"}}' | bash .claude/hooks/git-guard.sh; echo $?` prints the block reason and `2`. `--check 'git push --force-with-lease origin feat'` exits `0`.
     On the default branch, `--check 'git push'` exits `2`; on a feature branch it exits `0`.
   - Live, in a new session of each harness: create an isolated scratch repo inside `.scratch/tmp/git-guard-test` (POSIX `mkdir -p .scratch/tmp/git-guard-test && cd .scratch/tmp/git-guard-test && git init -q && git reset --hard`; PowerShell `New-Item -ItemType Directory -Force .scratch/tmp/git-guard-test; Set-Location .scratch/tmp/git-guard-test; git init -q; git reset --hard`) from the project root. It must be blocked before running; remove `.scratch/tmp/git-guard-test` after verifying.
     It is an empty scratch repo of its own inside the self-ignored `.scratch/`, so nothing is lost if the hook fails.
   - Done when every exit code above matches and the live run was blocked in each harness.
5. **Land it** through the Opening a PR playbook (`references/playbooks/opening-a-pr.md`), and add one line to `AGENTS.md` naming the guard and the pattern file, so an agent that gets blocked knows where the rule lives.
   Done when the PR is open and its diff includes that `AGENTS.md` line.

**Limits.** Regex hooks match command text, not a full shell AST: an alias, a script that runs git inside it, non-standard flag/ref quoting, or another tool that shells out can bypass them — verify edge cases (`git checkout <ref> -- .`, `git restore -s <ref> -- .`, quoted refspecs) with live tests.
The `@branch` lines read the branch in the tool call's working directory, so `cd other && git push` or `git -C other push` is judged by the wrong repo, and `push.default=matching` can push the default branch from a feature branch.
Some harmless commands look destructive and are blocked too (`git restore --staged .`); use the safe form (`git reset` to unstage). The guard is a seatbelt; the hard stops in SKILL.md still apply.

**Done when** the hooks block the proof commands in every harness in use and the PR that adds them is open.

**Output:** harnesses and scope installed, any pattern changes and why, the two proof results, and the PR.
