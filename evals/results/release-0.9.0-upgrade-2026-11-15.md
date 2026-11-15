# Release 0.9.0 upgrade evidence, 2026-11-15

The real omp CLI upgraded an existing isolated user-scoped installation from 0.8.3 to the combined 0.9.0 candidate. No production profile, watcher, credentials, logon task or model session changed.

## Inputs and containment

- Windows x64, Python 3.13.14; verification doctor reported ready.
- Existing isolated installation: candidate `b6476bfe64eeda604d82fa8433990f6dabc12967` at 0.8.3, created by the earlier actual [0.8.3 run](release-0.8.3-upgrade-2026-11-15.md) and reused without reinstalling.
- Combined 0.9.0 candidate source: `20745075e40e531937601419d751cbd0b9900933`.
- The existing 0.8.3 state remains under `.scratch/evidence/release-0.8.3-upgrade/` in the repository reference worktree. This run's raw output and temporary files are under `.scratch/evidence/release-0.9.0-upgrade/` in the combined worktree.
- `PI_CONFIG_DIR` and `PI_CODING_AGENT_DIR` pointed only to that existing isolated state; `TMP`, `TEMP` and `TMPDIR` pointed to this run's `tmp/`. Profile variables were unset only inside the command subshell.

## Actual commands and result

The previous source snapshot was retained; the run extracted the pinned candidate to the existing isolated local marketplace path. The installed cache and registry were never manually edited. These commands exited 0:

```text
omp plugin list --json
omp plugin marketplace update deepmodebot
omp plugin upgrade --dry-run
omp plugin upgrade deepmodebot
omp plugin list --json
omp plugin upgrade --dry-run
```

The before registry recorded 0.8.3. Output included:

```text
[dry-run] Would upgrade deepmodebot@deepmodebot (user): 0.8.3 -> 0.9.0
Upgraded deepmodebot@deepmodebot (user) to 0.9.0
[dry-run] All marketplace plugins are up to date
```

An independent inspector read before/after registries, required the same user-scoped plugin ID and distinct paths within isolated state, resolved the actual `omp/plugins/node_modules/deepmodebot` runtime link to the registered 0.9.0 cache, and compared all candidate plugin files by SHA-256:

```text
PASS: existing isolated user install upgraded 0.8.3 -> 0.9.0; registered runtime link and all 255 plugin files match candidate SHA-256.
```

`payload-inspection.json` retains the file inventory and hashes. Version upgrades may replace installation timestamps; no timestamp-preservation claim is made.

## Limits

This proves local-marketplace version detection and the runtime-linked payload on this Windows omp installation. It does not prove remote GitHub fetching, automatic watcher upgrades, production installation, a running session reload, model inference, native MCP host mounting, or Claude Code/macOS/Linux upgrades. The actual bounded MCP→A2A subscription-agent exchange and Windows cleanup tests are separate evidence described in their feature maps. No private project data, patient data or external deployment was used.
