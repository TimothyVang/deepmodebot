# Release 0.8.2 upgrade evidence, 2026-11-14

F1: the real omp and Claude Code CLIs each upgraded an existing user-scoped deepmodebot installation from 0.8.1 to 0.8.2.
No production installation, watcher, credentials, GitHub state or model session was changed.

## Environment and inputs

- Windows 11 x64; omp 18.20.0; Python 3.13.14.
- `python .omp/skills/verify-deepmodebot/control.py doctor` exited 0 with `"ready": true`; Git, Node and omp were available.
- Previous release source: `8ad42b3293a79bd6b6458f6325977ffdb7f918ff` (0.8.1).
- Candidate source: `92c6e8687977106e953014db22c773e51c31dc19` (0.8.2).
- Raw CLI captures and isolated installation remain in `.scratch/evidence/release-0.8.2-upgrade/`.

## Commands and observed output

These commands ran from the repository root in Git Bash with `set -euo pipefail`.
`PI_CONFIG_DIR` is relative to the user's home; `PI_CODING_AGENT_DIR` is absolute.
Both resolved inside this checkout's evidence directory; `omp config path` confirmed the agent directory.
Use a fresh evidence directory and matching config-root path for another run.

```bash
run="$PWD/.scratch/evidence/release-0.8.2-upgrade"
export PI_CONFIG_DIR=".cache/deepmodebot/bot/worktrees/TimothyVang-deepmodebot/pr77-author/.scratch/evidence/release-0.8.2-upgrade/omp"
export PI_CODING_AGENT_DIR="$run/omp/agent"
unset OMP_PROFILE PI_PROFILE
mkdir -p "$run/marketplace"
git archive 8ad42b3293a79bd6b6458f6325977ffdb7f918ff | tar -x -C "$run/marketplace"
omp config path
omp plugin marketplace add "$run/marketplace"
omp plugin install deepmodebot@deepmodebot
omp plugin list --json
```

The add command succeeded. Install output:

```text
✔ Installed deepmodebot from deepmodebot (0.8.1)
```

`before.json` records one user-scoped `deepmodebot@deepmodebot` entry at version `0.8.1`, in the isolated `deepmodebot___deepmodebot___0.8.1` cache.
The source directory below was created by this run and contained only its disposable archive.

```bash
rm -rf "$run/marketplace"
mkdir -p "$run/marketplace"
git archive 92c6e8687977106e953014db22c773e51c31dc19 | tar -x -C "$run/marketplace"
omp plugin marketplace update deepmodebot
omp plugin upgrade --dry-run
omp plugin upgrade deepmodebot
omp plugin list --json
omp plugin upgrade --dry-run
```

Observed output, in order:

```text
✔ Updated marketplace: deepmodebot
[dry-run] Would upgrade deepmodebot@deepmodebot (user): 0.8.1 -> 0.8.2
Upgraded deepmodebot@deepmodebot (user) to 0.8.2
```

`after.json` records the same plugin ID and user scope at version `0.8.2`, in the isolated `deepmodebot___deepmodebot___0.8.2` cache.
The final dry run printed:

```text
[dry-run] All marketplace plugins are up to date
```

All marketplace/install/list/upgrade commands exited 0. Captures: `add.txt`, `install.txt`, `before.json`, `update.txt`, `available.txt`, `upgrade.txt`, `after.json`, `remaining.txt`.

## Runtime-linked payload inspection

A Python inspection read the before/after JSON, checked their versions and distinct cache paths, and required the new cache to stay under the evidence directory.
It resolved `omp/plugins/node_modules/deepmodebot` to that new cache and read its plugin manifest as 0.8.2.
It then compared SHA-256 digests for every file under the candidate's `plugins/deepmodebot/` against the runtime-linked installation.
This inspects installed content, not just the source manifest or a mocked installer.

`payload-inspection.txt` records the successful inspection (exit 0):

```text
PASS: existing user installation upgraded 0.8.1 -> 0.8.2
PASS: runtime node_modules/deepmodebot resolves to the isolated 0.8.2 cache
PASS: all 235 source plugin files match the runtime-linked installation (SHA-256)
deep command SHA-256: d4a4049476469d4cb19f9d9de1cda245f4a5fbaa28d15ad7d479f72682f20652
Note: omp replaced installedAt during upgrade; timestamp preservation is not an acceptance condition.
```

The first inspection failed on an extra, incorrect assumption that omp preserves `installedAt` during upgrade.
The recorded timestamps changed from `2026-11-14T19:18:22.114Z` to `2026-11-14T19:18:42.631Z`.
Only the inspection was corrected and rerun; the installation and upgrade were not rerun or their captures overwritten.

## Limits

The omp run proves version detection and the documented two-command upgrade using the real omp installer and two local, pinned marketplace snapshots.
It does not prove fetching unpublished 0.8.2 from GitHub, automatic watcher updates, an already-running session reload, agent behavior after loading, or upgrades in Codex, macOS or Linux.
Claude Code is verified separately below. Repository checks are separate from runtime proof.

## Repository gate

The first `python scripts/check.py` exited 1 because six Windows Job tests require repo-local temporary directories.
Its output is retained in `check-default-temp-failed.txt`; the failure said `Set TMP/TEMP/TMPDIR to repo-local scratch`.
The corrected invocation used the same code with contained temporary storage:

```bash
mkdir -p .scratch/evidence/release-0.8.2-upgrade/tmp
scratch=$(python -c "from pathlib import Path; print(Path('.scratch/evidence/release-0.8.2-upgrade/tmp').resolve())")
export TMP="$scratch" TEMP="$scratch" TMPDIR="$scratch"
python scripts/check.py
```

It exited 0 and printed `OK`; output is retained in `check-contained-temp.txt`.
No bot or skill behavior changed in this evidence-only follow-up.

## Claude Code follow-up

The real Claude Code 2.1.325 CLI ran on the same Windows host, with a fresh isolated configuration under `.scratch/evidence/claude-release-0.8.2-upgrade/`.
The earlier verification doctor reported `ready: true`.
No model prompt, subscription call, production settings change or watcher launch was needed.

Commands ran from the checkout root in Git Bash with `set -euo pipefail`:

```bash
run="$PWD/.scratch/evidence/claude-release-0.8.2-upgrade"
test ! -e "$run"
mkdir -p "$run/marketplace" "$run/tmp"
export CLAUDE_CONFIG_DIR=$(python -c "from pathlib import Path; print(Path('.scratch/evidence/claude-release-0.8.2-upgrade/claude').resolve())")
export TMP=$(python -c "from pathlib import Path; print(Path('.scratch/evidence/claude-release-0.8.2-upgrade/tmp').resolve())")
export TEMP="$TMP" TMPDIR="$TMP" CLAUDE_CODE_TMPDIR="$TMP" DISABLE_AUTOUPDATER=1
claude --version
git archive 8ad42b3293a79bd6b6458f6325977ffdb7f918ff | tar -x -C "$run/marketplace"
claude plugin marketplace add "$run/marketplace"
claude plugin install deepmodebot@deepmodebot
claude plugin list --json
```

The add and install commands succeeded. `before.json` recorded:

```json
{"id":"deepmodebot@deepmodebot","version":"0.8.1","scope":"user","enabled":true,"folderVersion":"0.8.1","installedAt":"2026-11-14T19:30:19.694Z"}
```

Its `installPath` was under the isolated configuration at `plugins/cache/deepmodebot/deepmodebot/0.8.1`.
Without uninstalling or reinstalling, the same configuration then ran the README's two update commands:

```bash
rm -rf "$run/marketplace"
mkdir -p "$run/marketplace"
git archive 92c6e8687977106e953014db22c773e51c31dc19 | tar -x -C "$run/marketplace"
claude plugin marketplace update deepmodebot
claude plugin update deepmodebot@deepmodebot
claude plugin list --json
```

The removed directory was this invocation's disposable marketplace snapshot, not the installed plugin or its registry.
Observed output:

```text
Updating marketplace: deepmodebot...Validating local marketplace
✔ Successfully updated marketplace: deepmodebot
Checking for updates for plugin "deepmodebot@deepmodebot"…
✔ Plugin "deepmodebot" updated from 0.8.1 to 0.8.2 for scope user. Restart to apply changes.
```

`after.json` recorded:

```json
{"id":"deepmodebot@deepmodebot","version":"0.8.2","scope":"user","enabled":true,"folderVersion":"0.8.2","installedAt":"2026-11-14T19:30:19.694Z","lastUpdated":"2026-11-14T19:30:45.406Z"}
```

Its `installPath` changed to `plugins/cache/deepmodebot/deepmodebot/0.8.2` under the same isolated configuration.
Every command exited 0. Raw captures: `claude-version.txt`, `add.txt`, `install.txt`, `before.json`, `update.txt`, `upgrade.txt`, `after.json`.

A Python inspection required the same plugin ID and user scope, versions 0.8.1 then 0.8.2, enabled state, distinct cache paths and containment under this run directory.
It read version 0.8.2 from the registered installation's manifest and compared every candidate plugin file against that installation by SHA-256.
`payload-inspection.txt` records exit 0 and:

```text
PASS: existing enabled Claude Code user installation upgraded 0.8.1 -> 0.8.2
PASS: registered cache path changed to the isolated 0.8.2 installation
PASS: all 235 source plugin files match the registered installation (SHA-256)
deep command SHA-256: d4a4049476469d4cb19f9d9de1cda245f4a5fbaa28d15ad7d479f72682f20652
Local marketplace readFromFolder: marketplace/plugins/deepmodebot
```

This is an actual Claude Code plugin update, not an omp run or a mocked installer.
The source was a local marketplace: Claude Code also reported `readFromFolder` pointing to its source plugin directory, with `folderVersion` changing from 0.8.1 to 0.8.2.
It proves the CLI update and registered cached payload, not remote GitHub fetching or the distinct behavior of Git-sourced marketplaces.
No interactive Claude session was running or restarted; post-restart skill discovery and agent behavior were not exercised.

The follow-up repository gate also passed:

```bash
scratch=$(python -c "from pathlib import Path; print(Path('.scratch/evidence/claude-release-0.8.2-upgrade/tmp').resolve())")
export TMP="$scratch" TEMP="$scratch" TMPDIR="$scratch"
python scripts/check.py
```

Exit 0; stdout `OK`. Output is retained in `.scratch/evidence/claude-release-0.8.2-upgrade/check.txt`.
