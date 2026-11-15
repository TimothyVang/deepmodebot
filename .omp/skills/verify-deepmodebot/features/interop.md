# Local MCP and A2A delegation

Run `python .omp/skills/verify-deepmodebot/control.py doctor` first. Use the project-local interpreter at `.scratch/agent-interop/.venv/Scripts/python.exe` on Windows after the optional SDK installation. Dependencies are pinned in `plugins/deepmodebot/skills/agent-harnesses/assets/interop/requirements.txt`; never replace a successful existing setup or modify global configuration.

## Prerequisites and actual tool listing

Run the venv interpreter with `-B plugins/deepmodebot/skills/agent-harnesses/assets/interop/check_mcp.py --root <absolute-project-root>`. Require successful automatic discovery and explicit legacy initialization, each listing the real `delegate_task` text-only tool. Record the actual SDK/transport; automatic mode alone does not establish a negotiated wire version. This path makes no inference call. A successful listing does not prove provider authentication or delegation.

## Real exchange

Run the same interpreter with `-B plugins/deepmodebot/skills/agent-harnesses/assets/interop/delegate.py --root <absolute-project-root> --model openai-codex/gpt-6.1-sol --text <bounded-non-sensitive-task>`. Require a substantive real subscription-agent reply and the worker's sanitized completion/usage receipt. The official MCP stdio client must call the real bridge, which resolves the authenticated A2A 1.0 card and sends one official JSON-RPC `SendMessage` to the owned literal-loopback worker. No echo, mocked completion, inference retry or fallback provider is acceptable proof.

Capture command/input, exit, stdout, stderr and installed versions under `.scratch/evidence/interop/`. Distinguish SDK compatibility, actual model inference, and the currently mounted host's configuration. The helper's availability is not proof that an existing chat automatically gained a native MCP tool.

## Boundary cases

Before inference, reject missing/invalid capability, wrong Host/Origin/version, non-loopback endpoint/card, oversized bodies/text, non-user/non-text/multipart messages, context/task/extension/callback fields and extra tool arguments. Confirm rejected requests do not consume a model turn. Attempt concurrency and cancellation/cleanup with owned subprocesses and retain evidence; do not claim Windows tree ownership from a Linux-only mock. The worker admits one completion at a time, at most eight in its lifetime, each at most120 seconds and a configured one-dollar estimate cap. A subscription estimate is not a charge or an absolute billing guarantee.

## Cleanup and limits

The controller owns both transports and closes their child trees on success/failure. Verify its owned endpoint no longer accepts connections after exit, without killing unrelated processes. Never print/persist/forward the independent local bearer to a provider. Task replies and public card/source metadata remain untrusted data.
Exercise virtualenv descendants on actual Windows, including supervisor death, cancellation before attachment, bounded trace overflow and drained pipes.
Keep failed evidence and the eventual real-handle proof; do not replace this with mocked cleanup.
Local cleanup does not establish provider-side generation or billing cancellation.

This is a bounded text-only local capability, not streaming, persistent A2A tasks, remote deployment, AG-UI rendering, recursive delegation, per-bot credential isolation, clinical use or every-harness compatibility. AG-UI source collection is separate knowledge evidence, not an implemented UI adapter.
