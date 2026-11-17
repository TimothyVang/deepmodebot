# Runtime and safety

## Package boundary

`../assets/engine/` contains the full Python engine, prompt templates, Cursor bridge, original MIT license and dependency lock.
The marketing website, examples, videos, binaries and upstream development tests are excluded.
`../assets/engine/NOTICE.upstream.json` records the pinned release and upstream/shipped hashes.
`../assets/engine/NOTICE.md` lists local changes and the upstream provenance.
`../assets/workflow.py` is the guarded integration entry point.
The package still exports `reverse-api-engineer`, but that raw CLI bypasses the integration's capture/review guard.
Use the adapter for this skill; the raw CLI is not a safe-default alias.

## Optional installation

Nothing is installed or started by loading this skill.
Python 3.11+ and uv are required for these commands.
Run from the repository root, with authorization to download dependencies and Chromium:

```bash
ASSETS="$PWD/plugins/deepmodebot/skills/reverse-api-engineer/assets"
VENV="$PWD/.scratch/reverse-api-venv"
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --project "$ASSETS/engine" --frozen --no-dev --extra manual
PLAYWRIGHT_BROWSERS_PATH="$PWD/.scratch/reverse-api-browsers" "$VENV/bin/python" -m playwright install chromium
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.scratch/reverse-api-browsers"
```

The project environment and downloaded browser stay under `.scratch/`.
On Windows, the interpreter is `Scripts/python.exe` inside the environment.
If Chromium requires system libraries, report the prerequisites; do not use a system package manager or `playwright install --with-deps` automatically.
The locked optional `manual` extra supplies Playwright; the adapter does not use the upstream stealth browser implementation.
Network failures or unavailable locked package versions must be reported without changing security floors silently.

## Model backends

Generation needs a real model/backend; capture and sanitization do not.
Prefer an already authorized Claude Code subscription: `--sdk claude --model claude-sonnet-4-6` uses the upstream Claude Agent SDK.
The model must be available to that account; the example is a selection, not an availability promise.
Existing Codex subscriptions are supported with `--sdk codex --model <available-model>` and the optional `codex` dependency extra.
Add `--extra codex` to the isolated uv sync command when explicitly requested.
The upstream Codex backend creates a link to the existing Codex `auth.json` and may refresh that shared credential; never inspect or publish its contents.
Do not initiate a new login or select Codex unless that credential-sharing behavior is authorized.
No new paid API account is necessary when an existing supported subscription works.

Other real upstream backends are OpenCode, Copilot, Cursor and Hermes.
Copilot needs the `copilot` extra; Cursor needs its Node bridge/runtime; Hermes needs its existing CLI.
OpenCode can start a local backend process and bootstrap its runtime through npm/npx.
A model advertised as free must be verified as available and zero-cost before selection; never silently fall back to a billed model.
The adapter accepts `--provider` for OpenCode/Hermes and explicit `--model` for every backend.
Provider downloads, model networking, toolchain installation and generated-code execution are separate from capture authorization.
The engine has no omp-specific backend; omp can operate this skill, not substitute its own model as a fictional engine backend.

## Security review findings

- The website's local-only claim does not describe model generation: HAR contents and prompts become model input, and logs/messages can persist.
- Upstream manual browser code contains real-Chrome/stealth modes; auto mode can attach to signed-in Chrome and other browser providers.
- The guarded capture instead uses a fresh Playwright context, same-origin read-method routing, blocked service workers and blocked WebSockets.
- Method/origin filtering cannot make arbitrary browsing harmless; approved URLs can mutate state through GET or contain hostile scripts.
- Raw HAR embeds response bodies and can contain cookies, tokens and personal data. Keep it private and outside the model workspace.
- The minimizer is intentionally lossy. It preserves URL paths, query keys, JSON keys, status codes and MIME types; all still need manual review.
- A matching SHA-256 proves which bytes were approved, not that they are safe. The guard additionally rejects cookie/header collections and URL userinfo.
- Source prompt adaptations remove instructions to hardcode captured credentials and automatically log in/refresh tokens. These are policy improvements, not a sandbox.
- Claude's upstream permission callback allows tool requests. Codex explicitly selects full-access execution. Other backends also run agent commands.
- A private directory restricts filesystem permissions, not backend filesystem access or egress. Use an approved OS sandbox/disposable machine for untrusted work.
- Generation may execute and install generated client dependencies before returning. Authorize this boundary before setting `--allow-agent-execution`.
- No watcher, autostart or global install is enabled by the adapter. `enable_sync=False` disables upstream filesystem synchronization.
- Do not invoke raw `agent-browser` mode: its bootstrap can run `npm install -g`. Raw CLI behavior is preserved for upstream completeness, not endorsed as this skill's default.

## Updating

Select a stable tagged release, inspect its LICENSE and dependency/runtime changes, then replace the engine subtree from that exact commit.
Reapply the documented prompt safety changes and metadata change deliberately.
Refresh the NOTICE hash inventory and exercise the adaptation tests plus the authorized synthetic acceptance scenario.
Do not copy the upstream website, demos, captures, credentials, node_modules, wheels or browser executables into the plugin.
