---
name: reverse-api-engineer
description: Reverse engineer authorized browser traffic or a reviewed HAR into a typed API client. Use for browser request capture, undocumented API discovery, or client generation from captured requests.
metadata:
  as-of: "2026-11-17"
---

# Reverse API engineer

Use the bundled runtime, not a replacement code generator.
It supports Python, JavaScript, TypeScript, Go, Java, C#, PHP, Ruby, C and PowerShell through the engine's language-specific workflows.
Model output still needs review and proof; ten supported languages does not mean ten languages have been exercised in this checkout.

## 1. Establish the boundary

Record the authorized site, allowed read operations, requested client language and selected model backend.
Use synthetic localhost traffic for installation and acceptance checks.
Do not initiate login, use an existing signed-in browser, extract secrets, submit forms or call customer endpoints for a demonstration.
A GET request can still change server state: the method filter is not permission to visit arbitrary URLs.

Read [the runtime and safety guide](references/runtime.md) before installing dependencies or starting capture.
Capture is local; generation can send the reviewed HAR, prompts and model-visible files to the chosen provider.
The upstream agent backends can execute commands with full user privileges.
A private output directory is not an OS sandbox, and prompts are not an enforcement boundary.
Use an approved disposable environment with OS-level containment when processing untrusted captures or executing generated code.
Do not claim that captured data always stays on the machine.

Done when the target, authorization, data-disclosure boundary and execution boundary are explicit.

## 2. Capture and minimize

Run `assets/workflow.py capture` with an explicit URL and `--authorized`.
It opens a fresh Chromium context, records HAR, blocks other origins and non-read methods, blocks service workers and WebSockets, and closes after a bounded duration.
The default capture lasts five seconds; use `--seconds` for a longer authorized manual browsing interval.
The default browser is visible; `--headless` is for the synthetic fixture or another explicitly approved use.
No signed-in profile, global browser state, watcher or autostart is used.

Run `assets/workflow.py sanitize` to make a separate minimized HAR.
Review the result locally: URL paths, field names and MIME types can still identify people or contain secrets or hostile instructions.
The sanitizer drops headers, cookies, metadata and non-JSON bodies, replaces JSON values with type-shaped examples, and replaces query values.
It is not an anonymization guarantee and may remove evidence needed for generation.
Supply safe synthetic examples when values or enums matter; report omissions instead of inventing endpoints.
For a complex authorized capture, use the same review gate on a separately supplied HAR; do not relax capture restrictions silently.

Done when the reviewed HAR contains the required endpoint evidence and no private data or credentials, and its SHA-256 digest is recorded after review.

## 3. Generate using the engine

Use `assets/workflow.py generate` with the reviewed HAR, its exact `--reviewed-sha256`, the requested language, an explicit backend/model and `--allow-agent-execution`.
Only use that execution flag after the user has authorized provider disclosure and the backend's command execution in the selected environment.
The adapter rejects remaining cookies, headers and URL credentials even when the hash matches.
Keep raw HAR files outside the generation workspace.
Synchronization is disabled; generation writes to a new private directory and calls the actual bundled engine.
An unavailable dependency, model, subscription or language toolchain is a blocker to proof, not grounds to substitute canned output.
The guarded path does not invoke the upstream auto-browser mode or install global tools.

Done when a nonempty client exists at the reported path, with its provider/model, input digest and generation logs retained privately.

## 4. Review and prove

Read every generated source file and dependency manifest before executing the client yourself.
Inspect endpoints, methods, request/response types, pagination, error handling, authentication, dependencies and file/network side effects.
Require caller-supplied environment variables for authentication; no captured credentials, automatic login or credential recovery.
Do not publish raw captures, model transcripts, private output or credentials.

Follow [the synthetic acceptance scenario](references/acceptance.md) to prove real Chromium capture, actual model-backed generation and a fresh response from the generated client.
Tests alone are not browser/client proof.
Report the languages actually exercised, provider/network limits and any missing runtime prerequisites.

Done when the reviewed generated client retrieves fresh fixture data, the HAR contains the corresponding browser request, and evidence distinguishes observed results from unsupported capabilities.
