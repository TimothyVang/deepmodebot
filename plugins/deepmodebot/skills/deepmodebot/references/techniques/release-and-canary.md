# release-and-canary

**Use when:** preparing a production release, defining pre-ship observability, monitoring a post-deploy canary ("canary check", "monitor after deploy"), or auditing documentation/changelog drift right after code ships ("document release", "update docs after ship").

1. **Instrument before shipping (4 on-call questions).** Before deploy, ensure structured telemetry answers: (a) Is the new path executing? (b) Is it succeeding or failing by error class? (c) Did p50/p95/p99 latency or resource saturation shift? (d) Which tenant/request correlation ID failed? Propagate W3C `traceparent` / `request_id` and redact all PII/secrets.
2. **Define numeric canary rollback triggers.** State exact abort thresholds upfront (e.g., 5xx rate `> +0.5%` over pre-deploy baseline, p99 latency `> 1.5x`, background queue lag monotonic growth over 5m, or any failed synthetic user-journey check).
3. **Run the canary observation window.** Compare canary vs baseline cohorts (or pre- vs post-deploy windows), execute one real synthetic user path (`verify-<app>` doctor + read-safe/sandbox smoke), and inspect live error logs/metrics—never declare healthy from HTTP `200 /healthz` alone. Roll back immediately if any abort threshold trips.
4. **Sync shipped docs & changelogs (`document-release`).** Diff `last_release..HEAD` across routes, CLI flags, config keys, env vars, schemas, and breaking changes against `README.md`, `CHANGELOG.md`, `docs/`, OpenAPI specs, and `llms.txt` / `llms-full.txt`, fixing every stale flag, example, or version string in one clean pass.

**Done when** structured telemetry covers the shipped path, canary metrics and synthetic smoke pass against explicit rollback thresholds (or trigger rollback cleanly), and all user/agent-facing docs match the shipped code byte-for-byte.
