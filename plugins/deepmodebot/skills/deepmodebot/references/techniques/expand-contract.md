# expand-contract

**Use when:** renaming, splitting, or dropping a live database column/table, evolving an external API/webhook/queue payload under Hyrum's Law, or sunsetting a production service with zero downtime while old and new app replicas run concurrently.

For single-repo internal callers that deploy atomically, migrate callers and delete the old API in one wave (`references/principles/migrate-callers-then-delete-legacy-apis.md`). Use **expand-contract** whenever rolling deploys, external clients, persisted queue messages, or stateful schemas prevent atomic cutover.

1. **Inventory observable consumers (Hyrum's Law).** Grep callers, SDKs, mobile versions, queued job payloads, analytics pipelines, and DB views; check telemetry for live traffic on the old field/endpoint.
2. **Phase 1 — Expand (additive & backward-compatible).** Add the new nullable column, table, or v2 field/endpoint alongside the old one (`ADD COLUMN ... NULL`, `CREATE INDEX CONCURRENTLY`; never hold long `ACCESS EXCLUSIVE` table locks). Old replicas must keep working against the expanded schema.
3. **Phase 2 — Dual-write & backfill.** Deploy app code that writes both old and new representations transactionally (still reading old), then backfill historical rows in throttled idempotent batches with sleep/jitter.
4. **Phase 3 — Shadow-read parity & switch.** Read from the new path while comparing against the old path in metrics/logs; once mismatch count is `0` across real load, switch primary reads to the new path while keeping rollback safety.
5. **Phase 4 — Deprecate & contract.** Emit `Deprecation` / `Sunset` HTTP headers (`RFC 8594` / `RFC 9745`) or structured telemetry warnings on legacy callers; once legacy read/write rate hits `0` over a full retention window, stop dual-writing and drop the legacy code, column, and feature flag in a dedicated cleanup PR.

**Done when** each deploy step is backward-compatible with its adjacent running version, locks/backfills are non-blocking and idempotent, read-parity check criteria are explicit, and the final contract removal ticket/step is tracked so dual-write shims never become permanent tech debt.
