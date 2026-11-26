# Backend craft and system design

Read when writing or reviewing backend code, designing an API, choosing or tuning a database, adding a cache or queue, scaling a service, hardening security, or choosing a language. Where a rule matches an existing deepmodebot principle, the principle is named; follow the principle file for detail. Per-language runtime, tooling, and traps are in `language-ecosystems.md`. Source keys are in this skill's `SKILL.md`.

## Coding laws

1. **Main path visible.** Guard conditions first with early returns. No deep if/else nesting. (CODE-LAWS)
2. **Domain names.** `pending_order`, `process_order`, not `data`, `item`, `result`. (CODE-LAWS)
3. **External systems behind a boundary.** Wrap third-party APIs and legacy services in an adapter so their changes stop at the edge. Principle `boundary-discipline`. (CODE-LAWS)
4. **Invalid states unrepresentable.** Types where required fields must exist together; no half-built objects. Principle `type-system-discipline`. (CODE-LAWS)
5. **Decisions apart from side effects.** Pure business rules separate from DB writes, notifications, network calls, so rules test without mocks. Principle `boundary-discipline` (pure core). (CODE-LAWS)
6. **Useful errors.** Machine-readable error code plus a human message. Log diagnostic context, never secrets or customer data. (CODE-LAWS)
7. **Focused changes.** One purpose per PR. Fixes apart from refactors, so each is easy to review and roll back. (CODE-LAWS)

Python additions (PY-LAWS):

- No bare `except:`. It swallows `KeyboardInterrupt` and `SystemExit`. Catch only the exceptions you expect, with narrow `try` blocks.
- Orchestrator functions read as a top-level story and delegate detail to helpers.
- Comments explain *why* only (non-obvious constraint or decision). Same as deepmodebot's Comments rule.

## API design

- URIs are plural nouns (`/orders`); the HTTP verb is the action. Do not mix singular and plural. (API-LAWS)
- GET, PUT, DELETE are idempotent and safe to retry. POST creates. (API-LAWS)
- Identity in the path, filtering, sorting, and paging in the query (`/products?category=shoes&limit=20`). (API-LAWS)
- Evolve by adding optional fields. Create `/v2/` only to change or remove an existing contract. (API-LAWS)
- Never return 200 with an error body. (API-LAWS)

Status codes (HTTP-CODES, API-LAWS):

| Code | Use for |
|---|---|
| 200 | Successful read or update |
| 201 | Resource created |
| 202 | Accepted, processing async |
| 204 | Done, no body (delete) |
| 400 | Malformed request |
| 401 | Missing or invalid authentication |
| 403 | Authenticated but not allowed |
| 404 | Resource does not exist |
| 409 | Conflicts with current state |
| 422 | Well-formed but fails domain validation |
| 429 | Rate limited |
| 500 | Unhandled server crash |
| 502 | Upstream dependency failed |
| 503 | Overloaded or in maintenance |

Choosing an API style (REST-GQL-GRPC, API-TYPES):

| Style | Use for |
|---|---|
| REST over HTTP/JSON | Public web and mobile APIs; best caching and tooling |
| GraphQL | Complex screens that need data from many entities in one round trip, without over- or under-fetching |
| gRPC (Protocol Buffers) | Internal service-to-service calls needing high throughput, low latency, streaming |
| Webhooks | Pushing events to partners instead of making them poll |
| WebSockets | Persistent two-way real time: chat, live tracking, tickers |

Common split: REST or GraphQL at the edge, gRPC inside.

## Databases

- Pick by read and write access patterns, not by the shape of the data. (DB-LAWS)
- Name the **system of record**. Caches and search indexes are disposable copies of it. (DB-LAWS)

| Store | Use for |
|---|---|
| Relational (Postgres, MySQL) | Relationships, joins, transactions |
| Key-value (Redis) | Sessions, carts, fast key lookups |
| Document (MongoDB) | Self-contained records, fast-changing schema |
| Graph (Neo4j) | Multi-hop relationships: social, fraud rings, recommendations |
| Wide-column (Cassandra) | Massive write volume, event logs, ingest |
| Time-series | Metrics, IoT, tickers, with downsampling |
| Search (Elasticsearch) | Full-text, fuzzy autocomplete, log search |
| Blob (S3) | Images, video, backups; keep only metadata and URL in the DB |

(PICK-DB)

### Indexes

- B-tree indexes are shallow and wide, one node per disk block. About 3 reads find a row among 10 million. (CS-4H)
- Each index costs storage and slows INSERT, UPDATE, DELETE. Index only columns in WHERE, JOIN, ORDER BY that filter out most rows. (CS-4H)
- A function on the column (`WHERE LOWER(email) = ...`) defeats a plain B-tree index. (CS-4H)
- Composite indexes work left to right. `(last_name, first_name)` serves `last_name` alone or both, never `first_name` alone. (CS-4H)
- Partial indexes (`WHERE status = 'pending'`) speed queries on a small hot subset of a big table. (SQL-10)
- Run `EXPLAIN` or `EXPLAIN ANALYZE` before shipping a query to confirm the index is used. (CS-4H)
- Postgres auto-indexes `PRIMARY KEY` and `UNIQUE`, never `REFERENCES` foreign keys: index every child FK column (`orders(customer_id)`) or parent `DELETE`/`UPDATE` locks and sequential-scans the child table, and lead composite indexes with `tenant_id` on pooled RLS tables.

### Transactions and IDs

- Group dependent writes in one transaction for atomicity, consistency, isolation, durability. (DB-10MIN)
- Prevent lost updates with transactions, row locks, or atomic operations, never read-modify-write in app code. (CS-4H)
- Keep transactions short. Never hold one open across a slow external API call; it pins pool connections and row locks. (JAVA-INT)
- One database: sequential integer IDs (4–8 bytes, small indexes). Distributed key generation: UUIDs (16 bytes), preferably time-ordered UUIDv7. (UUID)

### Query patterns, pagination & async hot paths

- Eliminate N+1 queries (`SELECT` or ORM `.findUnique`/`.get` inside `for`/`while` loops): batch IDs with `WHERE id = ANY($1)`, `JOIN`, or DataLoader, and assert bounded SQL query counts in integration tests.
- Replace `OFFSET` pagination with keyset/cursor pagination (`WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 50`) so deep pages stay O(log N) instead of scanning skipped rows.
- Never block an `async` event loop (FastAPI, Node, Tokio) with synchronous I/O (`requests.*`, `time.sleep`, `fs.readFileSync`, `bcrypt.hashSync`), and cap fan-out with `asyncio.Semaphore` / `p-limit` / `errgroup.SetLimit` instead of unbounded `Promise.all(items.map(...))` or serial `await`-in-loop waterfalls.
- Reuse one process-level connection pool (`replicas * pool_size <= max_connections` or PgBouncer) and set explicit connect + read timeouts on every outbound HTTP/DB client.

## Caching

- Cache-aside: read the cache; on a miss, read the DB, return, and fill the cache. (BACKEND-ECO)
- A cache is never durable. A missing key must repopulate cleanly from the system of record. (DB-LAWS)
- Every cache has a hard memory cap and an eviction policy. An unbounded cache is a slow memory leak. (CS-4H)
- LRU is a hashmap (O(1) lookup) plus a doubly linked list (O(1) move-to-front and tail evict). (CS-4H)
- Prevent cache stampede (thundering herd) on hot-key expiry with `singleflight` request coalescing, short lease locks, jittered TTLs (`ttl * (0.9 + 0.2 * rand)`), or `stale-while-revalidate`.

## Partitioning and sharding

- Partitioning splits a table inside one DB server. Sharding splits data across separate servers. (PART-SHARD)
- Shard last. First exhaust query tuning, indexes, caching, read replicas, and bigger hardware. (PART-SHARD)
- Choose a shard key that spreads both data and live traffic evenly, or one node becomes the hotspot. (PART-SHARD)
- Cross-shard queries and transactions are slow and operationally expensive. Design so common queries hit one shard. (PART-SHARD)

## Queues and events

- Move slow work (notifications, fulfillment, reports) off the request thread into a queue. (BACKEND-INT)
- Task queue (RabbitMQ, SQS): competing consumers; a message is gone once acknowledged. Event log (Kafka): durable, partitioned, replayable. (DEVOPS)
- Publish domain events (`OrderPlaced`) to a bus so other services react without coupling. (PATTERNS)
- Bound every queue or apply backpressure, so a surge cannot exhaust memory. (CS-4H)
- **Outbound notifications & OS AI summarizers:** schedule engagement notifications relative to the user's last active session (`~23.5 h` offset) with a local quiet-hours ceiling (`<= 22:00`), suppress mobile push while the user is active on desktop, rank by multi-signal context rather than `{name}` templates, and front-load unambiguous factual claims + structured priority metadata so OS-level LLM notification summarizers cannot invert meaning.

## Local-first sync, collaborative state & product surfaces

- **Local workspace replica for daily-use tools (Linear pattern):** request-wait-render navigation feels laggy on 8-hour/day tools; keep a normalized local client replica (IndexedDB/SQLite) for `0 ms` reads, apply mutations optimistically, and sync diffs asynchronously via dual persistence/retry queues (fast metadata separate from heavy media blobs) with explicit rollback/retry banners on failure.
- **Property-granularity sync & actor-scoped undo (Figma/Notion pattern):** resolve concurrent collaborative edits at **property/field granularity** (LWW or CRDT/OT) rather than whole-object locks, preserve all edits in version history, and implement **per-actor `Ctrl/Cmd+Z` undo** (including non-destructive selection state, capped in a bounded ring buffer).
- **Collapse overlapping flags into one orthogonal primitive:** before adding `pinned`, `starred`, `flagged`, `important`, and `folder` booleans, unify them into one composable tag/label/block primitive plus saved view queries; keep privacy/read-receipt toggles reciprocally symmetric.
- **End-to-end latency budgets & perceptual algorithms:** decompose interactive AI/voice SLAs into hard per-stage budgets (e.g., `<= 700 ms` release-to-render = `200 ms` ASR + `200 ms` cleanup + `200 ms` RTT + `100 ms` buffer); use perceptual spread shuffling (grouped per-category spacing + `20–30%` jitter + random offset) when uniform Fisher-Yates clumping feels broken to humans.
- **Tri-modal surface parity:** pair direct-manipulation GUIs (`<= 3` taps) and schema-validated GenUI widgets (for fuzzy middle-complexity queries) with **headless CLI/API/MCP parity** for bulk, administrative, and agentic operations.

## Scaling

- Keep app servers stateless (sessions and files in a DB or cache) so any instance can serve any request behind a load balancer. (SCALING)
- Scale vertically first to buy time before distributing. (SYS-4MIN)
- Reverse proxy (NGINX): TLS termination and caching. Load balancer (ALB): spread requests across instances. API gateway (Kong): central routing, rate limits, client auth. (CONFUSING-3)
- Do the minimum synchronously in the request. Push heavy work to background workers. (X-DESIGN)
- For high-concurrency server, reactor (`epoll`/`io_uring`), TCP/NIC, Postgres/SQLite, and per-runtime optimization rules, read `high-scale-server-optimization.md`.
- For hot-path data structures, pointer-free slot tables, cache-line alignment, hugepages, and tight-RAM arenas, read `data-structures-and-cache-optimization.md`.

## Resilience

- Set connect + request timeouts on every outbound call and retry at one layer only with full jitter plus a retry-budget token bucket; add a circuit breaker (Resilience4j — closed, open, half-open) around third-party calls when a degraded fallback exists. (PATTERNS)
- Idempotency keys on payments and other mutations. A duplicate retry returns the original response. Principle `make-operations-idempotent`. (BACKEND-INT)
- Degrade gracefully: serve cached or partial data rather than failing the whole app. (SYS-FINALLY)

## Observability

- Three signals: metrics (health, throughput), structured logs (event context), distributed traces (a request across services). (DEVOPS)
- Propagate trace and span IDs in HTTP headers with OpenTelemetry. (DEVOPS)
- Separate liveness (process is up) from readiness (dependencies connected, safe to receive traffic). (JAVA-INT)
- Alert on what users feel (error rate, p99 latency), not noisy host stats that teach people to ignore alerts. (DEV-LIFE)

## Security

- Never trust the client. Every permission, rule, and validation runs on the server. (SECURE-API)
- Object-level authorization (prevents BOLA): check the caller may access *this* resource ID, not just that they are logged in. (SECURE-API)
- SSRF: validate and allow-list user-supplied URLs so the server cannot be pointed at internal admin endpoints or the cloud metadata service. (SECURE-API)
- Parameterized queries or an ORM. Never concatenate input into SQL. (DEV-LIFE)
- Short-lived access tokens (minutes) plus securely stored refresh tokens. (API-AUTH)
- Logs never contain passwords, tokens, or customer PII. (CODE-LAWS)

## Choosing a language

| Domain | Pick | Why |
|---|---|---|
| Kernels, firmware, microcontrollers | C | No runtime, direct memory (C-ECO) |
| Game engines, browsers, ML runtimes | C++ | Zero-cost abstractions, peak performance (CPP-ECO) |
| Network infrastructure, security-critical tools, concurrent CLIs | Rust | Memory safety checked at compile time, no GC (RUST-ECO) |
| Microservices, cloud tooling (Docker, Kubernetes), networking | Go | Fast builds, goroutines, single static binary (LANGS-2026) |
| Enterprise and banking backends | Java (Spring Boot) | Stability, deep ecosystem, JVM with JIT (JAVA-ECO) |
| Enterprise APIs, Windows, Unity games | C# (.NET 10) | Managed runtime, cross-platform (CSHARP) |
| ML, AI agents, data, quick APIs | Python (PyTorch, Pandas, FastAPI) | Ecosystem and speed of iteration (LANGS-2026) |
| Large web front ends and Node backends | TypeScript | Types catch bugs at build time (LANGS-2026) |
| CMS, storefronts, fast web delivery | PHP (Laravel) | Rapid feature delivery (LANGS-2026) |
| Native Android, modern JVM backends | Kotlin | Java interop, null safety, coroutines (LANGS-2026) |
| Apple platform apps | Swift | Native speed, ARC memory safety (LANGS-2026) |

Pick by domain constraint, not popularity rankings.
