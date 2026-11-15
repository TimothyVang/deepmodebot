# Contain the work: setup and guards

Mechanics behind `SKILL.md` Contain the work. The rules stay in `SKILL.md`; this file holds the setup snippet, deepmodebot's own outside writes, and the per-harness guards.

## No repo? Make a named one

- **No repo? Make a named one.** Outside a repo, in a folder that isn't a project, or for a new project that isn't the current repo, pick a short kebab-case name from the goal (`sigma-rule-converter`), create `<parent>/<name>/`, and run `git init -b main` in it.
  - `<parent>` is the current folder; the current repo's parent folder when you are inside another project (never nest a repo in a repo); or `~/code/` when the current folder is your home, a drive or filesystem root, a temp dir, or a system folder.
  - Never reuse an existing folder; on a clash add a suffix. Creating that folder is the one write allowed outside a root. From then on, work only inside it and report its path.

## Set up `.scratch/` and `.worktrees/` once

```bash
ROOT=$(git rev-parse --show-toplevel) && COMMON=$(git rev-parse --path-format=absolute --git-common-dir) &&
case "$COMMON" in */.git) MAIN=${COMMON%/.git} ;; *) MAIN=$ROOT ;; esac &&  # bare repo or submodule: stay in the root
mkdir -p "$ROOT/.scratch/tmp" "$MAIN/.worktrees" &&
for d in "$ROOT/.scratch" "$MAIN/.worktrees"; do [ -f "$d/.gitignore" ] || printf '*\n' > "$d/.gitignore"; done
```

## deepmodebot's own outside writes

- **deepmodebot's own outside writes are the only others.** Transient files a tool or a deepmodebot helper script creates and deletes within one run: `assets/pr-agent/pr_agent_local.py` and `assets/security-audit/audit-pr.sh` run the model from an empty outside folder so the repo's own agent config can't load. And the GitHub App bot the user installed, which keeps its config in `~/.config/deepmodebot/` and its clones in `~/.cache/deepmodebot/`.

## Guards

- **Guards back the rule; none covers shell commands.** Claude Code: the plugin's hook and this skill's frontmatter hook deny `Write`, `Edit`, and `NotebookEdit` outside the root. omp: `assets/contain/omp-contain.ts`, once installed. Codex: its `workspace-write` sandbox. The rule still binds `bash`. A denial means move the file into the root; never route around the guard. Setup per harness: `skill://agent-harnesses`.
