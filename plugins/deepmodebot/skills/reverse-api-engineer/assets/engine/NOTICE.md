# Reverse API Engineer attribution

Vendored from https://github.com/kalil0321/reverse-api-engineer.
Product website inspected: https://reverseapi.dev/.
Release: `v0.16.0`, published 2026-11-15.
Source commit: `e3aae749746f076f78f9642d83eeb3c7af9bac44`.
Source package version: `0.16.0`.
Inspected on 2026-11-17.
License: MIT, Copyright (c) 2025 kalil0321; the original license is preserved verbatim in `LICENSE`.
The main repository NOTICE must retain this attribution when redistributing this subtree.

## Included boundary

The complete upstream `src/reverse_api/` runtime is included, including all six model backends, browser capture, ten language prompt partials and the Cursor JavaScript bridge.
The original `pyproject.toml` and `uv.lock` isolate the dependency stack from the host plugin's standard-library runtime.
The original `LICENSE` and lock are unmodified.
All upstream Python and JavaScript runtime files are unmodified.
The marketing website, binary assets, examples, upstream tests and development scripts are not included.
No upstream README is copied, because the local skill documents its own guarded workflow and the upstream README includes website/media references and unsafe privacy claims.

## Local changes

- `pyproject.toml`: remove the README metadata field, because the upstream marketing README is not vendored. Dependency requirements, extras, version and build backend are unchanged.
- `src/reverse_api/prompts/engineer/system.md`: replace captured-secret hardcoding and auto-login instructions with environment-supplied credentials, explicit authorization and no credential recovery. Add project-local dependency and execution-boundary guidance.
- `src/reverse_api/prompts/auto/system.md`: the same credential policy and explicit fresh-context/network/dependency boundaries.
- `src/reverse_api/prompts/auto/user_chrome_mcp.md`: replace the instruction to leverage existing browser authentication with an authorized fresh-context requirement.
- Every `src/reverse_api/prompts/partials/_language_<language>.md`, for `python`, `javascript`, `typescript`, `go`, `java`, `csharp`, `php`, `ruby`, `c` and `powershell`: replace authentication sections that instructed embedding captured cookies/tokens and automatic credential refresh. Keep actual language generation, typing, toolchain and verification workflows.
- `_language_php.md`: report a missing system curl extension instead of instructing a system package installation.
- `_language_c.md`: wrap one long cJSON ownership paragraph without changing its content to satisfy the host repository's Markdown line limit.

`NOTICE.upstream.json` lists SHA-256 hashes of every original file included in this distribution and its shipped bytes, including these explicitly modified files.
This is an attribution/change inventory, not a claim of an independent security audit or successful execution.

## Integration boundary

The sibling `../workflow.py`, `../fixture_server.py`, skill/reference files and adaptation tests are local integration code, not upstream files.
The adapter uses fresh-profile capture, lossy HAR minimization, a required reviewed-byte digest and explicit model-agent execution consent.
It never enables filesystem synchronization or invokes the upstream auto-browser bootstrap.
The immutable runtime still contains powerful raw CLI modes; installing the package does not turn those modes into a sandbox.
Model generation can disclose HAR content to a provider and execute commands with user privileges.
No claim that all traffic remains local is carried forward.
