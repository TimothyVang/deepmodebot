# Isolate a task

Use a dedicated git worktree and branch for PR/publication work, concurrent writers, or when the starting checkout has dirty unrelated changes so parallel agents never edit the same checkout. (Verified local S/M edits with no remote or PR ask stay uncommitted in the starting working tree per deepmodebot `SKILL.md`.)

## Steps

1. Fetch: `git fetch origin`.
2. Pick a short branch name from the task: `<type>/<slug>`, for example `fix/login-redirect`.
3. Create the worktree inside the repo's self-ignored `.worktrees/` folder, never beside the repo:
   - Bash/POSIX: `mkdir -p .worktrees && { [ -f .worktrees/.gitignore ] || printf '*\n' > .worktrees/.gitignore; } && git worktree add .worktrees/<slug> -b <type>/<slug> origin/main`
   - PowerShell: `New-Item -ItemType Directory -Force .worktrees | Out-Null; if (!(Test-Path .worktrees/.gitignore)) { Set-Content -NoNewline .worktrees/.gitignore "*\`n" }; git worktree add .worktrees/<slug> -b <type>/<slug> origin/main`
4. Work only inside that directory. Install dependencies there; worktrees do not share `node_modules` or virtualenvs.
5. Copy any untracked local config the task needs (for example `.env.local`). Never commit it.
6. When running dev servers across parallel worktrees, avoid `:3000`/`:5173`/`:8787` port, cookie, and OAuth-redirect collisions by wrapping the dev script with [`portless`](https://github.com/vercel-labs/portless) (`portless run <cmd>` routes linked worktrees to `https://<slug>.<app>.localhost` on an assigned free port `4000–4999`; `PORTLESS=0` bypasses) or passing an explicit per-worktree `PORT`.

A worktree already assigned to this task is reused as is. Never build on `main`.

## Done when

`git branch --show-current` inside the worktree prints the task branch, and `git status` shows a clean tree based on `origin/main`.

## Cleanup

After the PR merges or closes: `git worktree remove .worktrees/<slug>`, then delete the branch.
