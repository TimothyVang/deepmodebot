# Contain the work: disposable setup

Mechanics for `SKILL.md` Contain the work; its Disposable lifecycle is authoritative.

## Allocate only what the task needs

Follow `SKILL.md`'s Disposable lifecycle. For temporary files, run this once when first needed, retaining the returned absolute path for this session:

```bash
ROOT=$(git rev-parse --show-toplevel) &&
mkdir -p "$ROOT/.scratch/tmp" &&
{ [ -f "$ROOT/.scratch/.gitignore" ] || printf '*\n' > "$ROOT/.scratch/.gitignore"; } &&
SESSION_SCRATCH=$(mktemp -d "$ROOT/.scratch/tmp/session.XXXXXX")
```

Use `mktemp -p "$SESSION_SCRATCH"` or Python `tempfile.TemporaryDirectory(dir=session_scratch)`. For a command needing temp files, prefix only that invocation with `TMPDIR="$SESSION_SCRATCH" TMP="$SESSION_SCRATCH" TEMP="$SESSION_SCRATCH"`; Python invocations also use `-B`. Invoke helpers by their quoted installed paths. Pass explicit output/cache/profile directories under this session directory rather than accepting shared defaults.

Only when a worktree is needed, allocate its separate session container:

```bash
ROOT=$(git rev-parse --show-toplevel) && COMMON=$(git rev-parse --path-format=absolute --git-common-dir) &&
case "$COMMON" in */.git) MAIN=${COMMON%/.git} ;; *) MAIN=$ROOT ;; esac &&
mkdir -p "$MAIN/.worktrees" &&
{ [ -f "$MAIN/.worktrees/.gitignore" ] || printf '*\n' > "$MAIN/.worktrees/.gitignore"; } &&
SESSION_WORKTREES=$(mktemp -d "$MAIN/.worktrees/session.XXXXXX")
```

Create the requested worktree beneath `$SESSION_WORKTREES`; no scratch allocation is needed merely to create a worktree. Give delegates distinct owned subdirectories. Record exact owned paths in session state, or the resume ledger when interrupted. For cleanup, check ownership and resolved containment first, retain required outputs outside disposable directories, and remove eligible worktrees with `git worktree remove` on the exact quoted path, never `--force`. Remove only empty owned worktree containers afterward; shared parents remain. Report cleanup failures instead of broadening deletion.
