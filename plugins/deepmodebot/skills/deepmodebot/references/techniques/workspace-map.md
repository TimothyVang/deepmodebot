# workspace-map

**Use when:** starting Route Step 1 orientation in a repo, locating symbols or headings before reading files, tracking active Orca/git worktrees alongside your own open PRs, or checking Scope Manifest and `loop.py` progress without burning tokens on wide directory walks or broad greps.

`assets/workspace-map/workspace_map.py` builds a zero-bloat, memory-mapped SQLite (`WAL` + `FTS5` + `mmap_size`) pointer index using only the Python 3 standard library. It stores file pointers, short signatures, worktree links, own-PR metadata, and manifest state, never file bodies or embeddings, and runs on demand with no background daemon.

## Storage and anti-bloat design

- **One shared DB per repo:** resolves `git rev-parse --git-common-dir` so linked Orca and git worktrees share one `<main-checkout>/.scratch/workspace-map.db` (with `.scratch/.gitignore` set to `*`), eliminating per-worktree index duplication.
- **Cross-repo view:** pass `--global` to store or query `~/.cache/deepmodebot/workspace-map.db` across repositories for Orca worktrees and open PRs, or override the path with `--db <path>` or `DEEPMODEBOT_MAP_DB`.
- **Pointers and signatures only:** indexes `git ls-files` tracked text files `<= 256 KB`. Extracts symbols via `ast` for `.py` and lightweight extractors for `.ts`/`.tsx`/`.js`/`.jsx`/`.mjs`/`.cjs`, `.rs`, `.go`, `.cs`/`.java`/`.cpp`/`.c`/`.h`, plus `#`/`##` headings in `.md` (signatures capped `<= 120` chars).
- **Strict filtering:** skips binaries (null-byte check), lockfiles (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `uv.lock`), minified files (`*.min.js`, `*.min.css`), media/3D assets, `.scratch/`, and `.worktrees/`.
- **Incremental and self-pruning:** skips unchanged files by `(mtime_ns, size)`, deletes removed files, pruned worktrees, and closed PRs on sync, and reclaims space with `PRAGMA incremental_vacuum`.

## Commands

Run from any checkout or worktree using `python -B "<this skill>/assets/workspace-map/workspace_map.py" <subcommand>` (`py -3 -B` on Windows). Every subcommand supports `--json`, `--db <path>`, and `--global`.

- `overview [path] [--max-bytes 1400] [--offline] [--no-orca]` — incremental sync plus a compact (~300-token) repo map hard-capped to `--max-bytes`: repo identity, entrypoints/docs/verify skills, active Orca/git worktrees, matched open own PRs, active Scope Manifest or `loop.py` state, and DB size in KB.
- `query <term> [path] [--limit 15] [--all-repos]` — FTS5 search over symbol names, signatures, and paths, returning exact `rel_path:line kind signature` pointers so you read only targeted line ranges.
- `workspaces [path] [--all-repos]` — lists git worktrees (`git worktree list --porcelain`) merged with Orca worktrees (`orca worktree list --json` when `orca` is on `PATH`), joined with branch, dirty status, matched PR number, and manifest/loop state.
- `prs [path] [--all-repos]` — lists your open PRs (`gh pr list --author @me --state open`, TTL-cached 180s) joined with local worktree paths and check/merge status; skipped gracefully when `--offline` or `gh`/remote is unavailable.
- `sync [path] [--offline] [--no-orca] [--force-prs]` — refreshes files, symbols, worktrees, PR cache, and project state (`docs/specs/*-manifest.json`, `.scratch/goals/*-manifest.json`, `.scratch/goals/*/latest-summary.json`).
- `prune [--days 30]` — removes missing repos/worktrees and stale rows, runs `VACUUM`, and reports reclaimed bytes.

## Workflow

1. **Orient in ~300 tokens (Route Step 1).** Run `overview` (add `--offline` when GitHub PR state is not needed) instead of running broad `find` or multi-pattern greps. Done when repo root, key docs, verify skills, active worktrees, and manifest/loop state are in hand.
2. **Jump straight to exact lines.** Run `query "<symbol or heading>"` to get `rel_path:line` anchors, then open only the needed line ranges (`references/principles/guard-the-context-window.md`). Done when target definitions and callers are located without dumping whole files.
3. **Track worktrees, PRs, and loop state.** Run `workspaces` or `prs` (add `--global --all-repos` for cross-repo Orca and PR visibility) to see which worktree owns each branch/PR and where `active_sprint`, deferred slices, `pending` inventory, or `sme_gate` stand. Done when active worktrees, PRs, and scope state are reconciled.
4. **Keep the index lean.** Rely on automatic incremental pruning during `sync`/`overview`, and run `prune` after deleting repos or old worktrees. Done when stale repos and worktrees are removed and reclaimed bytes are reported.

**Done when** orientation, symbol lookup, or worktree/PR/manifest tracking succeeded from the memory-mapped index with exact `rel_path:line` pointers, no file bodies loaded into the index, and no tracked `.db` files left in git.
