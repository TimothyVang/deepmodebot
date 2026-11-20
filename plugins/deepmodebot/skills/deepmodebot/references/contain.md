# Contain the work: setup and guards

Mechanics behind `SKILL.md` Contain the work. The rules stay in `SKILL.md`; this file holds the setup snippet, deepmodebot's own outside writes, and the per-harness guards.

## No repo? Make a named one

- **No repo? Make a named one.** Outside a repo, in a folder that isn't a project, or for a new project that isn't the current repo, pick a short kebab-case name from the goal (`sigma-rule-converter`), create `<parent>/<name>/`, and run `git init -b main` in it.
  - `<parent>` is the current folder; the current repo's parent folder when you are inside another project (never nest a repo in a repo); or `~/code/` when the current folder is your home, a drive or filesystem root, a temp dir, or a system folder.
  - Never reuse an existing folder; on a clash add a suffix. Creating and initializing that folder via shell is allowed outside a root; active write guards pin file-edit tools to the session's starting root, so when creating a sibling project from inside another repo, reopen/start a session in the new root before using file-edit tools (use `extraWriteRoots` only when intentionally co-editing both repos). From then on, work only inside it and report its path.

## Set up `.scratch/` and `.worktrees/` once

```bash
ROOT=$(git rev-parse --show-toplevel) && COMMON=$(git rev-parse --path-format=absolute --git-common-dir) &&
case "$COMMON" in */.git) MAIN=${COMMON%/.git} ;; *) MAIN=$ROOT ;; esac &&  # bare repo or submodule: stay in the root
mkdir -p "$ROOT/.scratch/tmp" "$MAIN/.worktrees" &&
for d in "$ROOT/.scratch" "$MAIN/.worktrees"; do [ -f "$d/.gitignore" ] || printf '*\n' > "$d/.gitignore"; done
```

## deepmodebot's own outside writes

- **deepmodebot's own outside writes are the only others.**
  - Transient isolated run dirs created and deleted within one run by `assets/pr-agent/pr_agent_local.py` and `assets/security-audit/audit-pr.sh` (so the target repo's own agent config cannot load).
  - Cross-repo `workspace_map.py --global` index at `~/.cache/deepmodebot/workspace-map.db`.
  - Guard session-activation marks (`CLAUDE_PLUGIN_DATA`, `PLUGIN_DATA`, or Antigravity's fallback `~/.gemini/antigravity/deepmodebot-guard/active-sessions/`) plus Antigravity's `brain/` and `artifactDirectoryPath` state.
  - The optional GitHub App bot the user installed (`~/.config/deepmodebot/` config and `~/.cache/deepmodebot/` clones).

## Guards

- **Guards back file-edit tools; none covers shell commands.**
  - Claude Code: the plugin's `hooks/hooks.json` and `SKILL.md` frontmatter hook deny `Write`, `Edit`, and `NotebookEdit` outside the root.
  - Antigravity: `hooks.json` + `scripts/antigravity-guard.mjs` deny file-edit tools outside the workspace roots (with `brain/` and `artifactDirectoryPath` allowed); combine with `--sandbox` and `allowNonWorkspaceAccess: false` when supported.
  - omp: `assets/contain/omp-contain.ts`, once installed, denies `write`, `edit`, and `ast_edit` outside the root.
  - Codex: its `workspace-write` sandbox (note: allows `/tmp` and `$TMPDIR` by default unless `exclude_slash_tmp = true` and `exclude_tmpdir_env_var = true` are set).
  - The rule still binds shell commands. A denial means move the file into the root; never route around the guard. Setup per harness: `skill://agent-harnesses`.

## Durable notes

- **Durable notes stay in the repo.** Resume notes, trails, and anything later sessions need go under `.scratch/`, or `$(git rev-parse --git-common-dir)/omp-resume/` where the harness can write `.git` (Codex's sandbox cannot), never only in a session store.
