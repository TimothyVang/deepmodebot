# Release 0.8.3 upgrade evidence, 2026-11-15

The real omp CLI upgraded an existing isolated user-scoped installation from 0.8.2 to 0.8.3. No production profile, watcher, credentials, startup task or model session changed.

## Inputs and containment

- Windows x64, Python 3.13.14; verification doctor reported ready.
- Previous source: `20e13b40ab43add66fa0ee0ac303fe75583552a1` (0.8.2).
- Candidate source: `13af2b4fbb7030f727c5cbeb7833bb600fb71a0d` (0.8.3).
- Isolated state: `.scratch/evidence/release-0.8.3-upgrade-r2/` in the author worktree.
- `PI_CONFIG_DIR=deep-mode/.worktrees/repo-ideas-20261114/.scratch/evidence/release-0.8.3-upgrade-r2/omp` is relative to this host's user home. `PI_CODING_AGENT_DIR` resolved to that directory's `agent/`; `omp config path` confirmed it.
- `TMP`, `TEMP` and `TMPDIR` stayed in the run's `tmp/`; `OMP_PROFILE` and `PI_PROFILE` were unset only inside a subshell. Another host must choose its own fresh contained path.

The earlier successful `b6476bf` upgrade is retained separately. A later integrated gate exposed incoming-base line/core-budget violations and a stale embed. Core prose was compressed without removing hard stops, routes, commands or hooks; long paragraphs were wrapped verbatim and the embed synchronized. R2 verifies that changed candidate, not an unchanged retry; no earlier captures were overwritten.

## Actual commands and observations

The local marketplace first contained a Git archive of the previous source. Commands exited 0:

```text
omp config path
omp plugin marketplace add <run>/marketplace
omp plugin install deepmodebot@deepmodebot
omp plugin list --json
```

`before.json` recorded one user-scoped `deepmodebot@deepmodebot` entry at 0.8.2 in the isolated cache. The run preserved its own source snapshot as `previous-source/`, then extracted the candidate at the same `marketplace/` path. It did not edit or replace the installed cache manually.

```text
omp plugin marketplace update deepmodebot
omp plugin upgrade --dry-run
omp plugin upgrade deepmodebot
omp plugin list --json
omp plugin upgrade --dry-run
```

Observed:

```text
Upgraded deepmodebot@deepmodebot (user) to 0.8.3
[dry-run] All marketplace plugins are up to date
```

All commands exited 0. Raw config/add/install/before/update/availability/upgrade/after/remaining captures are retained in the run directory.

## Runtime-linked payload

An independent Python inspector read both CLI registries, required the same plugin ID and user scope, distinct 0.8.2/0.8.3 paths contained under this run, and the actual `omp/plugins/node_modules/deepmodebot` link resolving to the registered new cache. It read version 0.8.3 from that runtime manifest and compared every candidate plugin file with the runtime-linked file by SHA-256.

```text
PASS: existing isolated user install upgraded 0.8.2 -> 0.8.3; runtime link resolves to registered new cache; all 244 source plugin files match SHA-256.
```

`payload-inspection.json` records the complete file inventory. Installation timestamps are observations, not preservation requirements.

## Separate Windows runtime proof and limits

After the ownership/readiness repair, the seven real process-tree regressions passed in 12.421 seconds. Named events, real processes and held handles exercise virtualenv context, stdin/supervisor/intermediate exit and direct/Bash deadline cleanup; this is not a speed benchmark. The earlier failed three-second readiness observation is retained; its exact original cause remains unestablished. Fixture bootstrap and the cleanup deadline are now coordinated separately rather than retrying the old gate until green.

The upgrade proves real omp local-marketplace version detection and the registered runtime payload. It does not prove remote GitHub publication, automatic watcher upgrade, current-session reload, model inference, provider-side cancellation, OS credential isolation, or Claude Code/macOS/Linux upgrades. Repository gates and independent review are separate evidence.
