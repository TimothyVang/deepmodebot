# Local MCP → A2A delegation

Checked 2026-11-14 on Windows, Python 3.13.14, a2a-sdk 1.3.0, mcp 2.3.0 and uvicorn 0.54.0.
This optional kit makes a real text-only subscription-agent call; it is not a second implementation of either protocol.

## Choose the seam

- **MCP** exposes the typed `delegate_task(text) -> text` tool to a caller.
- **A2A** carries its one standalone user message to a separate worker, using an authenticated Agent Card and the official JSON-RPC `SendMessage` client/server.
- **AG-UI** streams agent events/state to a user-facing application. It complements the first two protocols; this kit does not implement an AG-UI renderer or adapter.
- A headless harness call alone needs none of these protocols. Use this kit when the actual client/server interoperability seam is wanted, not to wrap every local function in a service.

## Install once in the project

Resolve `assets/interop/` relative to this installed agent-harnesses skill. Keep the full plugin layout: the worker reuses its sibling deepmodebot sealed runner and Windows Job helper. Never copy individual scripts or edit a managed plugin cache by hand.

From an existing absolute Git project root whose `.scratch/` is already ignored:

```text
python -B <kit>/setup_workspace.py --root <absolute-project-root>
```

Use Python 3.13.
The setup creates only `.scratch/agent-interop/.venv/`, pins the reviewed dependencies and refuses any existing/partial workspace rather than clearing or silently repairing it.
Reuse a successful environment.
It does not install a system package, change a global harness configuration or provide authentication.

## Run the actual path

Use the venv interpreter (`Scripts/python.exe` on Windows, `bin/python` elsewhere), not an arbitrary Python:

```text
<venv-python> -B <kit>/check_mcp.py --root <absolute-project-root>
<venv-python> -B <kit>/delegate.py --root <absolute-project-root> --model openai-codex/gpt-6.1-sol --text <non-sensitive-task>
```

The check performs automatic MCP discovery and explicit legacy initialization, listing the real tool without inference. Listing is not proof of A2A execution or provider authentication.

The controller mints an independent random local capability, starts an owned literal `127.0.0.1` worker on an ephemeral port, waits for actual readiness, calls the real MCP tool, returns its real A2A reply and closes the owned children.
It never writes the local bearer to config, a prompt or a receipt.
`--mcp-mode legacy` selects explicit legacy MCP initialization.
Do not claim an already-running chat gained a native MCP tool: this controller uses the official MCP client; mounting the stdio server in another host is a separate host configuration and verification step.

The fixed model is the operator-approved `openai-codex/gpt-6.1-sol`. The sealed headless runner checks existing subscription/OAuth eligibility, disables tools/context/skills/extensions/discovery and verifies the actual response provider/credential identity. It fails closed on mixed/API billing, routing or fallback. Never add an API key to make a failed run pass.

A 2026-11-14 actual exchange after the Windows virtualenv cleanup fix distinguished all three protocols and rejected shared-cookie roles as independent security boundaries.
The worker recorded one valid provider completion, 370 input and 263 output tokens.
That is substantive inference proof, not an accuracy benchmark, all-harness compatibility claim or evidence that an AG-UI application was built.

## Boundary and lifecycle

- Caller text and remote replies are data, not new system instructions or permissions.
- Exactly one nonempty text part, no NUL, at most 16 KiB UTF-8; encoded HTTP body at most 32 KiB. Both limits apply, including JSON escaping overhead.
- The worker supports only A2A 1.0, literal-loopback authenticated card/RPC routes and one final agent Message. No stream, persistent task, context, extensions, callbacks, attachments or recursive tools.
- Host/Origin/version, raw JSON fields/duplicate members and body limits are enforced before SDK dispatch. The client refuses redirects, environment proxies and card-selected alternate destinations before sending the bearer.
- One worker completion may be in flight, at most eight per worker lifetime.
- Each completion has a 120-second process deadline and a configured one-dollar estimate cap.
- This is not a monetary charge or absolute billing guarantee; the owning task must still track its shared usage/time/depth budget.
- The MCP bridge rejects extra/ill-typed arguments and concurrent admission. No inference retry, fallback provider, echo or fabricated success is used.
- Cancellation of a thread await is not process cancellation.
- The sealed runner owns/reaps its subprocess tree; the worker retains admission until real cleanup completes.
- The controller closes the owned worker/bridge on success or failure.
- Seven real Windows process tests and a separate handle-based cancellation probe passed, including virtualenv descendants and drained pipes.
- Local process cleanup does not prove provider-side generation or billing stopped. Windows Job ownership is cleanup, not an OS security sandbox.
- The processes still run as the user's account. No-tools inference is not per-agent OS/credential isolation. Do not send patient data, production secrets or another project's private context through this demonstration boundary.

## Source and verification pointers

Official libraries: [A2A Python SDK v1.3.0](https://github.com/a2aproject/a2a-python/tree/v1.3.0), [MCP Python SDK v2.3.0](https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0).
A2A spec 1.0.0 uses wire version `1.0`; the kit disables 0.3 compatibility.
MCP 2.3's APIs are not interchangeable with old 1.x FastMCP examples.

Read the repo verification feature `features/interop.md` before driving this surface. Record dependency versions, actual commands and non-sensitive input/output, negative-boundary cases and owned cleanup. A successful static check or synthetic policy test is not a live agent exchange.
