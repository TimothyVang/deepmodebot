# Synthetic browser-to-client acceptance

These commands are an opt-in scenario, not a claim that proof has already run.
Use the isolated environment from [runtime setup](runtime.md).
Keep all evidence under `.scratch/` and use a new directory for each attempt.
Only synthetic localhost traffic is authorized here; no existing browser, cookies, live customer endpoint or new account is needed.
Generation still uses the selected model provider and can execute commands with full user privileges; use approved containment.

## 1. Start the fixture explicitly

From the repository root in terminal one:

```bash
ASSETS="$PWD/plugins/deepmodebot/skills/reverse-api-engineer/assets"
python3 "$ASSETS/fixture_server.py" --port 8765
```

It binds only `127.0.0.1`.
`/` makes a real browser fetch to `/api/products`.
Every product response carries a newly generated nonce; `/stats` reports the latest nonce and API hit count.
Stop it with Ctrl-C after proof.
If the port is in use, choose an unused port consistently in every command; do not kill unrelated processes.

## 2. Capture and review

In terminal two, after the dependency installation:

```bash
ASSETS="$PWD/plugins/deepmodebot/skills/reverse-api-engineer/assets"
VENV="$PWD/.scratch/reverse-api-venv"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.scratch/reverse-api-browsers"
PROOF="$PWD/.scratch/reverse-api-proof"
mkdir -m 700 "$PROOF"
"$VENV/bin/python" "$ASSETS/workflow.py" capture --url http://127.0.0.1:8765/ \
  --authorized --headless --seconds 3 --output "$PROOF/capture"
"$VENV/bin/python" "$ASSETS/workflow.py" sanitize --har "$PROOF/capture/recording.har" \
  --output "$PROOF/reviewed.har"
```

Read `reviewed.har` locally.
Confirm that `log.entries` includes the real browser request to `http://127.0.0.1:8765/api/products` and its JSON shape (`items`, `id`, `name`, `nonce`).
Confirm there are no headers, cookies, credentials, sensitive path segments or private fields.
The minimizer replaces example values, including the nonce, and retains only one sample array element.
Compute the digest only after review:

```bash
DIGEST=$(sha256sum "$PROOF/reviewed.har" | cut -d ' ' -f 1)
```

## 3. Generate through the real engine

This step requires explicit approval to send the reviewed synthetic HAR to the selected provider and let its agent execute commands.
The example uses an already-authorized Claude Code subscription; replace the backend/model only with an installed, supported, approved choice.
The generation directory is a sibling of the raw capture, not its parent.

```bash
"$VENV/bin/python" "$ASSETS/workflow.py" generate \
  --har "$PROOF/reviewed.har" --reviewed-sha256 "$DIGEST" --allow-agent-execution \
  --output "$PROOF/generated" --sdk claude --model claude-sonnet-4-6 --language python \
  --prompt 'Generate a typed Python client for the captured localhost products API. Use only http://127.0.0.1:8765/api/products. Use the standard library for HTTP, JSON and typing; no additional dependencies. Its main must fetch the current response and print exactly that response as JSON without labels. Preserve all fields. Do not hardcode response values. No authentication, external APIs, login or unrelated commands. Test only this synthetic endpoint.'
```

Read `generated/result.json` for `script_path` and model usage.
Preserve failed attempt logs; never replace failure evidence with a fabricated client.
An unavailable model, blocked network, missing subscription or Chromium launch failure means that phase is not proven.

## 4. Review output, then prove a fresh fetch

Read the complete generated client and any generated dependency files before running the following verification.
Confirm that the main program only calls the fixture and prints JSON, and that no credentials or unrelated commands were generated.
The backend may already have executed the client during generation; this review controls your subsequent replay, not that earlier authorized agent execution.

```bash
"$VENV/bin/python" - "$PROOF/generated/result.json" "$PROOF/replay-proof.json" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

def stats():
    with urlopen("http://127.0.0.1:8765/stats", timeout=5) as response:
        return json.load(response)

result = json.loads(Path(sys.argv[1]).read_text())
client = Path(result["script_path"]).resolve()
before = stats()
run = subprocess.run([sys.executable, str(client)], cwd=client.parent,
                     capture_output=True, text=True, check=True, timeout=30)
actual = json.loads(run.stdout)
after = stats()
assert actual["items"] == [{"id": 1, "name": "sample product"}]
assert after["api_hits"] > before["api_hits"], "No fresh API request"
assert actual["nonce"] == after["last_nonce"]
assert actual["nonce"] != before["last_nonce"], "Cached or hardcoded response"
evidence = {"client": str(client), "before": before, "after": after, "response": actual}
Path(sys.argv[2]).write_text(json.dumps(evidence, indent=2) + "\n")
print("Real generated client fetched a fresh synthetic response")
PY
```

If the generated program's invocation differs, inspect and document its actual entry point before changing the replay command.
Do not loosen fresh-response assertions or claim a passing run without executing it.
Record the exact language/backend/model, HAR request evidence, generated source path and replay proof.
Other languages require their real toolchains and the corresponding output review and fresh-response replay; this Python scenario does not prove them.

## Adaptation tests

The stdlib suite requires no model, browser or optional engine packages:

```bash
python3 -m unittest discover -s plugins/deepmodebot/skills/reverse-api-engineer/tests -v
```

It checks origin/method restrictions, data minimization, private no-overwrite outputs, exact-byte review, credential rejection, execution consent and the real ten-language prompt inventory.
The parent repository gate discovers these tests separately from optional engine installation.
