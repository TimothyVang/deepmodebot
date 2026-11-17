# Upstream integration evidence — 2026-11-17

## Scope and sources

Import the current statechart/formal-verification lifecycle and the actual ReverseAPI engine, preserve their licenses, route them through `/deep`, install the reviewed plugin, and submit a draft PR without enabling background bots.

- Statechart/formal source version: `0.15.43`; repository snapshot `536a3352a050e47cb75f86be497ea304ef342301`. Source links, announcements, dates and adaptations are recorded in each imported skill's `NOTICE.md`.
- Reverse API Engineer: stable `v0.16.0`, commit `e3aae749746f076f78f9642d83eeb3c7af9bac44`. See `plugins/deepmodebot/skills/reverse-api-engineer/assets/engine/NOTICE.md` and its original/shipped hash inventory.
- Existing empirical verification skills, bots, release versions and model-provider defaults were not changed.

## Environment

Linux x64; Python 3.12.13; Node 24.22.1; OpenJDK 21.0.13; omp 18.22.0.
Optional dependencies and artifacts stayed under the checkout's ignored `.scratch/`.
TLC 1.7.4 matched SHA-256 `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`.

## Statechart compiler and actual model checker

```sh
node --disable-warning=ExperimentalWarning --test \
  plugins/deepmodebot/skills/statechart/scripts/test/pipeline.test.ts \
  plugins/deepmodebot/skills/statechart/scripts/test/messages.test.ts \
  plugins/deepmodebot/skills/statechart/scripts/test/chart.test.ts
```

Observed: 69 tests passed, zero failed or skipped.

With `TLA2TOOLS` pointing to the verified JAR and `TMPDIR` under `.scratch/`, ran the exact MediaPlayer and MediaPlayerFixed scenarios in `statechart/references/tooling.md`.

- Broken model: exit 1, 12 states and 64 steps; `LoudWhenStopped` failed after one action, increasing volume while stopped.
- Fixed model: exit 0, 11 states and 57 steps; `TypeOK`, `LoudWhenStopped` and `NoDeadlock` held within the model.
- Both produced real `report.md`, `chart.mmd` and `tlc.out` files.
- Rendered both charts with Pele 1.9.0 and inspected them in a managed browser at 1200×1000. Parallel regions and labels were readable; only the broken chart showed violation/path marks. No browser errors were reported.

Logs and screenshots: `.scratch/evidence/statechart-*`; model outputs: `.scratch/statechart/media-broken/` and `media-fixed/`.
These are synthetic model checks and rendering evidence, not proof of production implementation correctness or exhaustive compiler coverage.

## Real skill routing

```sh
python3.12 scripts/eval_routing.py \
  --cases .scratch/integration-routing-cases.json \
  --model openai-codex/gpt-6-astra --jobs 3 --timeout 120 \
  --out .scratch/evidence/integration-routing-results.json
```

Observed: all six routes matched: statechart, formal creation, formal maintenance, two ReverseAPI cases and an unchanged research control.
Five of six size expectations matched. The model classified browser capture as L instead of the fixture's M expectation; the risky data/execution boundary supports that conservative classification. The expectation/result was not rewritten or rerun to force a pass.
This checks actual single-turn model routing, not every downstream authoring or maintenance journey.

## Real browser → engine → generated client

Installed the locked engine with `uv sync --frozen --no-dev --extra manual` into `.scratch/reverse-api-venv/`, using Python 3.12.13.
Installed Playwright 1.64.1's Chromium 156.0.8078.4 under `.scratch/reverse-api-browsers/`.

Executed `assets/fixture_server.py` on `127.0.0.1:8765`, then `assets/workflow.py capture --authorized --headless --seconds 3` and `sanitize` as documented in `references/acceptance.md`.
The reviewed HAR contained actual browser GETs for `/` and `/api/products`, with the expected JSON shape and no headers, cookies or userinfo.
Its reviewed SHA-256 was `9423eba895a830598dd5f676ae12bae8a0e31c302a3987804ce918e415f4b2b1`.

Claude CLI had no logged-in subscription. Selected the real OpenCode backend, pinned its server to `opencode-ai@1.18.4`, and explicitly selected `opencode/big-pickle` after its live catalog and official pricing documentation showed zero-cost input/output.
No paid fallback, login, user credential copy or Codex auth link was used.

Ran generation with the exact reviewed digest, `--allow-agent-execution`, language `python`, and a prompt restricted to the synthetic endpoint and standard library.
The generation process ran under Bubblewrap with cleared environment, hidden user home and raw capture, read-only repository/system mounts, a dedicated writable scratch subtree and an isolated PID namespace. Network access remained available for the model provider and localhost fixture; this was not an egress allowlist.

The unmodified upstream runtime called the actual model, generated `api_client.py`, exercised the endpoint, and returned a nonempty client path. Reported model cost: zero.
After reading the generated client, replayed it independently and asserted the exact fixture items plus a newly generated nonce:

- Fixture API hit count advanced from 5 to 6.
- The returned nonce matched the latest fixture nonce and differed from the pre-replay nonce.
- Thus the replay fetched a fresh response rather than echoing the HAR or hardcoding output.

Evidence: `.scratch/evidence/reverse-api-generation.log`, `.scratch/reverse-api-proof/replay-proof.json`, and the generated source under `.scratch/reverse-api-proof/sandbox/generated/`.
Only Python/OpenCode was exercised. Other language workflows and backends are included, not claimed tested.
Both owned HTTP fixture servers and the managed chart browser tab were stopped; no watcher or autostart was installed.

## Repository gate and security limits

`python3.12 scripts/check.py` ran once. The full gate did **not** pass:

- `evals/outcome/test_run.py`: two existing Windows-path containment expectations failed on Linux.
- `assets/github-app/test_bot.py`: four errors and one failure because installed Git 2.34.1 rejects `git worktree list --porcelain -z`; one test was skipped.
- The existing loop suite reported eight skipped tests.

No structural, link, branding, syntax or new ReverseAPI adaptation-test failure was reported. No checker exemption, disabled test, unrelated fix or compatibility shim was added. The submission remains a draft, not merge-ready.

The whole-plugin static scan timed out. Separate scans of the five instruction entrypoints completed: the four new skills scored zero; the core skill's two warnings were its existing automatic route choice and creation of a new named repository, not an installed scheduler.
The full ReverseAPI subtree scan completed with a composite **CRITICAL / DO_NOT_INSTALL** score. It flags subprocess execution, credential/environment access, automatic agent tool approval and generic syntax patterns. This is not represented as a clean security audit.
Manual inspection distinguished actual execution/auth capabilities from matches such as `--use-mock-keychain`, a missing-Hermes installer help string, `OPENCODE_DEBUG`, MIT license prose and rejected `file:///etc/passwd` test inputs.

Real residual risk remains: raw upstream CLI modes bypass adapter guards; model backends can execute commands, read files and disclose input to providers. Generation requires explicit data/execution consent and approved containment for untrusted work. Credential-hardcoding/automatic-login prompt instructions were replaced at their source, not merely contradicted by an appended prompt.

## Local installation

The npm-style local-directory install was rejected because this is a marketplace plugin, not a package.json package. Used the supported marketplace flow instead:

```sh
omp plugin marketplace add /home/assessor/Desktop/github-projects/deepmodebot
omp plugin install deepmodebot@deepmodebot --scope user
omp plugin list --json
```

Observed installed identity: `deepmodebot@deepmodebot`, version `0.8.3`, user scope.
The cached payload matched the checkout byte-for-byte for all four new SKILL entrypoints, the core router, compiler entrypoint, guarded workflow and engine dispatcher.
The installed `/deepmodebot:deep` command points to the router. Installed hooks are the existing prompt-activated containment guard, not a background bot.
This installation uses the local integration checkout; it does not imply that the draft PR is merged or that GitHub main contains these additions.
