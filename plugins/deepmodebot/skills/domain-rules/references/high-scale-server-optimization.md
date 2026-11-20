# High-scale server & code optimization lessons

Distilled from 96 implementations, infrastructure configs, and benchmarks in the Million Users Challenge (`arjaythedev/million-users-challenge`: 1M-3M concurrent keep-alive connections, ~42k req/s on 2-16 vCPUs + dedicated Postgres 18). Every rule targets measurable CPU, tail-latency, memory-per-connection, packet, or DB-round-trip wins.

## 1. Cost Model & First-Principles Thinking

1. **Budget per idle connection first.** At 1M open keep-alive sockets, 38 KB/conn (Scala/fs2) needs ~38 GB RAM and OOMs; 16-40 byte pointer-free fd-indexed slots use ~16-40 MB total.
2. **Detach buffers from idle connections.** Never hold per-socket 8-16 KB read/write buffers while idle; borrow shared per-thread scratch or provided buffer rings only during active I/O.
3. **Count syscalls, packets, and allocations per request.** Hand-rolled HTTP/1.1 + PG wire loops cut syscalls/req from >2 to ~0.11 via batching.
4. **Raise soft `RLIMIT_NOFILE` before binding.** Default `1024` causes silent `EMFILE` accept sleeps (1 s/accept), slashing throughput 2.5x+ before hitting CPU limits.
5. **Measure with `Accept-Encoding: gzip` enabled.** Compression often dominates 20-40% of server CPU and exposes buffer/stream-closing bugs missed by un-compressed smoke tests.
6. **Avoid cross-core hops on hot paths.** Passing accepted sockets from an acceptor thread to HTTP workers then DB workers via queues stalls throughput well below single-thread-per-core loops.
7. **Eliminate framework object graphs on hot routes.** Stripping Pydantic/DI/middleware in FastAPI (raw Starlette `Route` + `orjson`) yielded 4.2x on 4 cores; dropping frameworks for raw `Protocol`/reactor yielded 8.5x+.
8. **Use `bench` / profiler evidence before tuning.** Checking `perf`, GC logs, and `EXPLAIN ANALYZE` exposed Postgres `ExecMemoize` (24% DB CPU) and .NET `UnfairSemaphoreSpinLimit` (18% CPU).

## 2. Event Loops, Reactors & Kernel I/O (`epoll` / `io_uring`)

9. **Use share-nothing thread- or process-per-core reactors.** Give each worker its own event loop, `SO_REUSEPORT` listeners, and private DB connections to eliminate mutexes and cache-line bouncing.
10. **Prefer `fork` + `unshare(CLONE_FILES)` for GC'd runtimes or fd isolation.** Separate processes isolate stop-the-world GC heaps and split kernel fd-table locks.
11. **Oversubscribe loops on 2-3 vCPUs when the NIC has one RX queue.** Running 4 loops on 2-3 CPUs prevents softirq pinning 1 core at 100% while the other idles.
12. **Cap workers at high core counts when softirq/RPS saturates.** Capping workers at `min(cpus/2, 8)` can leave headroom for `ksoftirqd` and improve DB batch density.
13. **Use full `io_uring` performance flags.** Pair `SINGLE_ISSUER | DEFER_TASKRUN | COOP_TASKRUN | SUBMIT_ALL | NO_SQARRAY` with `IORING_REGISTER_RING_FDS` and `IORING_REGISTER_IOWQ_MAX_WORKERS`.
14. **Use registered direct descriptors + multishot accept/recv.** `IORING_REGISTER_FILES2` + `IORING_FILE_INDEX_ALLOC` + multishot `ACCEPT`/`RECV` + provided buffer rings avoid fd-table growth and `fget`/`fput`.
15. **Handle Ubuntu 6.8 `IORING_REGISTER_PBUF_RING` `EINVAL`.** Try `resv[0] = 0` first; on `EINVAL`, retry with `resv[0] = 1` (or fall back to `IORING_OP_PROVIDE_BUFFERS` / `epoll`).
16. **Re-arm ALL `ENOBUFS`-starved multishot receives when buffers return.** Capping re-arms (e.g., 32/pass) creates multi-second tail-latency spikes under buffer pressure.
17. **Never reuse a direct-descriptor slot before CQEs drain.** Gate slot closure/reuse on `SHUTDOWN` and all pending `RECV`/`SEND` completions plus generation/epoch tags.
18. **Use hybrid `epoll` + `io_uring` syscall batching when `io_uring` isn't the poll source.** Drain `epoll_wait`, then submit all `RECV`s in one `io_uring_enter` and all `SEND`s in a second.
19. **Use one-shot `POLL` SQEs for `libpq` pipeline sockets on `io_uring`.** Edge-triggered multishot poll misses bytes already buffered inside `libpq`'s user-space buffer.
20. **Coalesce loop wakeups with a 1-4 ms cadence when not saturated.** If `epoll_wait` did work without filling its event array, sleep the remaining 1-4 ms; skip sleeping when saturated.
21. **Account for outbound `SEND` CQEs in `io_uring_wait_cqe`.** Use `IORING_FEAT_MIN_TIMEOUT` / `IORING_ENTER_EXT_ARG` so TX completions do not break RX coalescing early.
22. **Set `SCHED_IDLE` (or `SCHED_BATCH`) on busy reactor threads.** Yielding to `ksoftirqd` prevents user polling loops from starving NIC RX softirq processing.
23. **Drain overloaded backlogs newest-first (LIFO) + bound in-flight work.** Serving freshest requests first keeps them inside the 40 ms delayed-ACK window; FIFO lets every request go late and triggers extra bare ACKs.
24. **Be cautious with `SO_INCOMING_CPU` on single-queue NICs.** Pinning connections to incoming RX CPUs can skew load onto one worker when RPS/softirq concentrates on one core.
25. **Use `recvfrom`/`sendto` or `MSG_DONTWAIT` instead of `read`/`write` in raw syscalls.** Bypassing VFS `fdget_pos`/position locks saves ~4% kernel CPU on hot socket loops.

## 3. TCP, Socket & Kernel/NIC Tuning

26. **Set socket options on the listening fd before `listen()` so `accept4` inherits them.** Zero per-connection `setsockopt` syscalls are needed for `TCP_NODELAY`, `TCP_THIN_LINEAR_TIMEOUTS`, etc.
27. **Enable `TCP_NODELAY = 1` on API listeners.** Small JSON responses must flush immediately without waiting for Nagle's algorithm.
28. **Use `TCP_DEFER_ACCEPT` carefully.** Waking `accept` only when data arrives saves a wakeup on immediate-send clients, but clients that connect and sit idle park in the SYN/accept queue.
29. **Piggyback ACKs with `TCP_QUICKACK = 0`.** Set `TCP_QUICKACK = 0` *after* `listen()` (since `listen()` resets it) and re-clear it when a response takes `>= 25 ms` so ACKs ride on responses.
30. **Set `TCP_THIN_LINEAR_TIMEOUTS = 1` (and `TCP_THIN_DUPACK = 1`).** Avoids exponential RTO doubling on 1-2 packet thin-stream responses when a packet drops.
31. **Disable `TCP_KEEPALIVE` probes for million-connection idle pools.** At 1M sockets, 15-second OS keepalive timers generate constant background packet/CPU churn.
32. **Clamp socket buffers at extreme connection counts.** Setting `SO_RCVBUF`/`SO_SNDBUF = 8192` and `TCP_WINDOW_CLAMP = 4096` halves kernel socket memory at 1.5M+ connections.
33. **Set `TCP_USER_TIMEOUT` on database connections.** Bounds dead-TCP detection (e.g., 15-60 s) instead of waiting 15+ minutes on silent drops.
34. **Use `tc qdisc fq` instead of `fq_codel` on 100k+ concurrent flows.** With massive flow counts behind one TX ring, `fq_codel` drops packets aggressively (causing TCP retransmits); `fq` queues bursts cleanly.
35. **Enable Receive Packet Steering (RPS) on single-queue VM NICs.** Spread `rx-0` softirq across all vCPUs via `rps_cpus` + `rps_sock_flow_entries` so one core doesn't bottleneck RX.
36. **Bind multiple ports (`PORT` + `EXTRA_PORT`) for >64k client connections per IP.** A single `(client_ip, server_ip, server_port)` tuple caps around ~64k ephemeral source ports.
37. **Size `somaxconn`, `tcp_max_syn_backlog`, and `tcp_rmem`/`tcp_wmem` together.** High `65535` listen queues need tight `4096 16384 4194304` buffer floors so 1M idle sockets fit in RAM.

## 4. PostgreSQL Wire Protocol, Pooling & Query Execution

38. **Check `EXPLAIN ANALYZE` for `Memoize` overhead on hot OLTP joins.** In Postgres 18, `ExecMemoize` zero-initialized a `work_mem` hash table every execution (24% DB CPU); `enable_memoize = off` cut query time 3.4x.
39. **Disable `jit` and parallel gather for short OLTP queries.** Set `jit = off`, `max_parallel_workers_per_gather = 0`, `client_min_messages = error`, and `plan_cache_mode = force_generic_plan` per session.
40. **Keep `LIMIT` constants literal in SQL, not `$1` bind params.** Parameterizing `LIMIT $1` can defeat generic-plan caching and trigger per-execution re-planning.
41. **Prefer custom v3 wire (`Parse` once -> `Bind`+`Execute`) without `Describe`.** Skipping per-query `RowDescription` saves ~130 bytes/req and avoids `PGresult` heap allocations.
42. **If using `libpq` pipelines, build `libpq` 17/18+ for `PQsendPipelineSync`.** Older `libpq` 16 `PQpipelineSync` flushes immediately per sync, adding ~7% CPU overhead.
43. **Never send `Prepare` (`Parse+Describe+Flush`) without `Sync`.** Leaving a pooled connection inside an unclosed implicit transaction pins `now()` to startup time and breaks ordering.
44. **Never leave `asyncpg` `statement_cache_size=0` with unnamed `prepare()`.** Unnamed prepared statements re-parse and re-plan every query on Postgres, halving DB capacity.
45. **Eliminate `RESET ALL` / `UNLISTEN *` pool-checkout round trips on read-only/stateless pools.** Use `NoResetOnClose=true` (Npgsql) or lightweight session pools instead of 2 extra RTTs/req.
46. **Request mixed wire column formats (`text` ints, `binary` timestamps).** Decimal text IDs/counts (1-6 bytes) copy straight into JSON without `itoa`; 8-byte binary `timestamptz` avoids 29-byte text parsing.
47. **Format binary `timestamptz` with Hinnant's `civil_from_days` + `DayPrefixCache`.** Caching the `YYYY-MM-DDT` prefix and using a 200-byte two-digit lookup table eliminates `gmtime` and division overhead.
48. **Batch a loop pass's reads onto ONE least-loaded DB connection under one `Sync`.** Funneling 16-64/128 reads into one `Sync` beats spraying across connections, cutting server CPU 25-33% and DB CPU 45-75%.
49. **Right-size read-pool count for fuller TCP packets.** Often 48-96 read connections beat 448 connections because batching produces fuller frames and halves DB TCP retransmits.
50. **Isolate write connections from read connections.** Dedicated write lanes ensure `fsync` stalls on `INSERT`/`COMMIT` never block `SELECT` read latency.
51. **Use group commit answered only at `ReadyForQuery` / `COMMIT`.** Batch queued writes into one explicit or implicit transaction, and reply to clients only after commit completes.
52. **Handle `23503` (FK violation) batch rollbacks explicitly.** If one write in a batched transaction fails (`23503`), Postgres aborts the batch: never answer earlier writes as success; reply error to the bad item and replay the rest individually.
53. **Sort or shard writes by `(user_id, post_id)` inside a batch.** Consistent lock ordering or lane hashing avoids row-lock deadlocks on concurrent duplicate writes.
54. **Bound read batch sizes under packet loss.** Tiny read batches (e.g., 2 feeds / 8 point-reads) limit blast radius when `cwnd=2` drops a packet.
55. **Nudge silent DB connections to trigger TCP fast retransmit.** Sending a lone `Sync` after 3-50 ms of silence (or failing over writes >10 ms) triggers SACK/fast-retransmit instead of waiting for RTO.
56. **Watchdog-close silent DB connections (10 s) and replay idempotent reads.** Close stalled DB sockets, replay in-flight reads up to 3x on healthy lanes, and fail uncertain writes with 500.
57. **Bulk-load seed/migration data BEFORE creating indexes and foreign keys.** Building indexes after `\copy` produces compact B-trees and avoids per-row index maintenance.

## 5. HTTP, Auth (JWT), JSON & Compression

58. **Parse HTTP/1.1 in-place on a reusable per-thread scratch buffer.** Reserve 160-256 bytes of headroom before the JSON body so headers and `Content-Length` prepend in place for one `send()`.
59. **Scan delimiters (`\r\n\r\n`, `.` in JWT) with SIMD (`SSE2`/`AVX2`) or `memchr`.** Avoid byte-by-byte scalar loops and regexes for request framing.
60. **Validate auth BEFORE validating path/body parameters when security-ordered.** Check `Authorization` + HS256 signature + `exp` before parsing IDs or touching the DB.
61. **Precompute HMAC-SHA256 `ipad`/`opad` midstates once at startup.** Verify the signature *before* Base64-decoding or JSON-parsing JWT claims; fast-path `{"alg":"HS256","typ":"JWT"}`.
62. **Never accept JWTs missing `exp` or non-HS256 algorithms (`alg=none`).** Always enforce algorithm pinning and expiration checks.
63. **Use optimistic SIMD/SWAR scanning for JSON string escaping.** Scan 8-64 bytes at a time for control chars/quotes/backslashes; copy straight through and branch cold only on hits.
64. **Write compact JSON directly into the response buffer without intermediate DOM/structs.** Stream `DataRow` fields directly into fixed key templates (`DirectBodyWriter` / `Utf8JsonWriter` / `orjson`).
65. **Only gzip bodies `>= 1 KB`.** Small responses (<1 KB) already fit in a single TCP segment with headers and often inflate or waste CPU when compressed.
66. **Never allocate `flate`/gzip writers before waiting on the DB.** Holding ~1 MB `compress/flate` writers across async DB awaits (e.g., `gin-contrib/gzip`) explodes heap by gigabytes; use `gzhttp` or compress at write time.
67. **Always set `leaveOpen = true` on wrapper `GZipStream`s.** Closing a compressing stream without `leaveOpen` disposes the backing `MemoryStream` and causes 500s under `Accept-Encoding: gzip`.
68. **Eliminate `memset` in hot LZ77 gzip hash tables.** Use a rolling `base` cursor on a pre-sized `u32` table (`cand >= base` rejects stale entries) instead of zeroing 8-16 KB per response.
69. **Use a branch-free 64-bit `BitWriter` for deflate.** Accumulate bits in `u64`, store 8 bytes unaligned unconditionally, and advance `ptr += bits >> 3; bits &= 7`.
70. **Retrain ISA-L or dynamic Huffman tables periodically from live bodies.** Updating `isal_hufftables` every ~1 s (or 256 responses) captures repeated JSON key frequencies without per-request tree building.
71. **Offload CRC-32 to hardware `PCLMULQDQ` / `VPCLMULQDQ` or ISA-L.** Scalar CRC-32 loops often consume a surprising fraction of gzip CPU.
72. **Verify compression-vs-bandwidth trade-offs on your target core count.** At 4 cores with fast networks, plain 4-segment TCP writes can beat gzip CPU cost when `GZIP_MIN` is tuned.

## 6. Memory Layout, Allocators & Admission Control

73. **Replace per-connection runtime timers with a hashed timing wheel.** A 512-slot 1 s wheel cut Go timer CPU from 3.4% to 0.2% across 1M idle sockets.
74. **Back large fd/connection arrays with `mmap(MAP_NORESERVE)` + `MADV_HUGEPAGE`.** Untouched slots consume zero RSS while active slots get 2 MiB TLB coverage.
75. **Use thread-local bounded freelists + `mimalloc`/`jemalloc`.** Standard glibc `malloc` arena contention can burn ~28% CPU under multi-core allocation churn; set `mallopt(M_ARENA_MAX, 1)` on single-threaded workers.
76. **Use `MADV_COLLAPSE` on `.text` segments + `SYS_MSEAL` for ultra-hot binaries.** Collapsing hot code onto 2 MiB hugepages cuts iTLB misses; disable ambient heap THP via `PR_SET_THP_DISABLE`.
77. **Acquire response buffers AFTER the DB query returns.** Hold only tiny parsed metadata in admission/DB wait queues so queued requests don't pin KB-sized buffers.
78. **Decouple admission queue budgets from DB pool size.** Coupling a 256-waiter queue with tight 250 ms timeouts triggers cascading 500s during short GC/lock stalls; use larger bounded admission + backpressure (`EPOLLIN` pause).
79. **Reserve top fds + brief `accept` backoff (1-100 ms) to prevent DB reconnect starvation.** Keep ~256 fds reserved below `RLIMIT_NOFILE` so Postgres reconnects never hit `EMFILE`.
80. **Enforce pass time budgets and step-aside stalled work.** Capping loop-pass work (e.g., 12 ms) and parking slow outliers prevents one slow batch from collapsing p95/p99 for everyone.

## 7. Language & Runtime Playbooks

81. **Rust:** For maximum density, use raw `libc` `epoll`/`io_uring` without an async runtime; if using `tokio`, run `current_thread` per core, keep futures small (box DB states), and use `mimalloc`.
82. **Rust / C / C++ on Cascade Lake / pre-VAES CPUs:** Pass `-C target-feature=-avx512f` or `-mprefer-vector-width=256` to prevent AVX-512 turbo frequency throttling unless `VAES` is present.
83. **Rust / C / C++ / Zig PGO & linker layout:** Two-stage `llvm-profdata` PGO + `-Wl,--call-graph-profile-sort=cdsort` + `-Wl,--icf=safe` + `-enable-ext-tsp-block-placement` + `-split-machine-functions` delivers measurable instruction-cache wins.
84. **C++:** Use `EASTL` / flat hash maps, size-classed thread-local coroutine frame freelists, and `MIMALLOC_ALLOW_LARGE_OS_PAGES=1` (`PURGE_DELAY=-1`) via startup re-exec if needed.
85. **Go:** Use `GOMAXPROCS=1` per forked worker (or `gnet` epoll loops with 8-byte pointer-free `slot`s), `GOGC=400` + `GOMEMLIMIT=70-75% RAM`, `syscall.RawSyscall` on non-blocking fds, `pgx.Batch`, and `gzhttp`.
86. **C# / F# (.NET):** Prefer NativeAOT (`PublishAot=true`, `IlcInstructionSet=x86-64-v3`) + `[SuppressGCTransition]` on non-blocking FFI, `ServerGarbageCollection=false` + `ConcurrentGarbageCollection=false` (per-core) or `DOTNET_GCHeapHardLimitPercent=0x46`, `DOTNET_ThreadPool_UnfairSemaphoreSpinLimit=0` (saved 18% CPU), `UnsafePreferInlineScheduling`, and `Npgsql` `Multiplexing=true;NoResetOnClose=true;MaxAutoPrepare=10`.
87. **Java / Kotlin:** Replace Tomcat/JDBC/G1 with Netty native epoll + pinned per-loop Vert.x reactive `pg-client` (`pipeliningLimit=256`) + `FlushConsolidationHandler` + `thread-selection: MANUAL`; disable Netty idle-timeout `ScheduledFutureTask`s; set `-XX:+UseParallelGC` (or ZGC) + `-XX:+AlwaysPreTouch` + `-XX:+UseCompactObjectHeaders`; keep Tomcat `appReadBufSize=4096` if stuck on Tomcat; use JDK FFM (`captureCallState("errno")`) and verify zero primitive boxing via `javap` in CI.
88. **Python:** Call `gc.freeze()` after startup *and* inside a `gc.callbacks` post-collection hook (cut gen-1 pause 177 ms -> 0.04 ms); replace FastAPI `APIRoute` with Starlette `Route` + `orjson` + ASGI header/body `coalesce`; use `asyncio.Protocol` + `.send(None)` coroutine stepping instead of `asyncio.Task`; offload hot read routes (`GET`) to a C `epoll` + `libpq` extension; slice UTC `timestamptz` strings instead of `datetime.isoformat()`.
89. **JS / TS (Bun / Node):** `Bun.serve` (`reusePort: true`) + `Bun.SQL` + `Bun.gzipSync` beats Node Fastify 3.2x on 4 cores (`<1 KB`/idle conn); in `bun:ffi`, type `ssize_t`/`size_t` returns as `i32` where safe to avoid `BigInt` allocations; in Node, set `--max-old-space-size` per cluster worker (defaults cap at ~4 GB) and raise `node-postgres` `idleTimeoutMillis` to stop SCRAM reconnect storms.
90. **PHP:** Framework DI containers (Laravel Octane) fail under concurrent Swoole coroutine container flushes and cap low; raw `epoll` via PHP FFI + OPcache tracing JIT + persistent `ext-pgsql` hits 7x higher 4-core scale.
91. **Ruby:** Patch/enable per-worker `SO_REUSEPORT` in `iodine` (preventing 2.7x-4.4x kernel accept skew across workers) on Ruby 4.0 + YJIT.
92. **Erlang / Elixir:** Force per-request heap shrink (`erlang:garbage_collect()` / `gc_every_n_keepalive_requests: 1`) so idle connection processes drop back to ~233 words, and pass `+sbwt none` to stop scheduler busy-waiting.
93. **Pony:** Never let per-connection actors hold a reference to a shared coordinator actor that references the whole DB pool (ORCA graph tracing leaked 296 KB/conn vs 11 KB/conn when passing only the single assigned `DbSlot`).
94. **Scala / Cats Effect / ZIO:** Audit per-connection fiber/scope retention (`fs2` + `Ember` held 38.1 KB/idle conn); use generational ZGC for pause control if heap stays large, and pool sessions without `RESET ALL`.
95. **Crystal / Nelua / Common Lisp:** `-Dgc_none -Dwithout_mt` (Crystal) and `pragmas.nogc` (Nelua) eliminate GC pauses; SBCL Common Lisp with forked workers + `VOP` assembly intrinsics competes directly with C/Rust.

## 8. Benchmarking & Correctness Harnesses

96. **Use `SO_REUSEPORT` in multi-worker servers** so the kernel distributes accepts evenly instead of LIFO-starving most workers.
97. **Subtract TCP `connect()` dial time from request latency** in custom load generators so SYN-queue wait doesn't distort app latency.
98. **Pool `gzip.Reader`s (`sync.Pool`) in load generators.** Unpooled 32 KB `gzip.Reader`s across 250k simulated users waste >8 GB RAM on the load box.
99. **Snapshot benchmark counters BEFORE closing `stop` channels.** Stopping workers concurrently with stat reads injects artificial teardown errors and map races.
100. **Retry idempotent `GET`s once on `status == 0` stale keep-alive EOFs** while failing non-idempotent writes cleanly.
101. **Coordinate distributed load generators with shared `-start` unix-ms and disjoint `-offset` auth slices** + log-bucket histograms (`1.01^b`) that merge by exact array addition.
102. **Test golden-byte exactness (key order, UTC ms truncation without rounding), auth-before-validation ordering, AND `Accept-Encoding: gzip` in CI.**
103. **Reset DB caches (`sync; echo 3 > /proc/sys/vm/drop_caches`) and clone from `TEMPLATE` DB between runs** so warm-cache runs don't mask cold-start or index-fit bugs.
104. **Keep `mload`/client GC behavior in mind when tuning compression.** Generating unusually sized bursts can shift client-side GC mark pauses and distort p99.
105. **Coalesce HTTP headers and body in ASGI/middleware** (`coalesce.py`) to turn 2 `send()` syscalls into 1 TCP write.
106. **Always coalesce or disable `FlushConsolidationHandler` / idle-timeout `ScheduledFutureTask`s in Netty** — 1M connections x 2 idle tasks = 2M timer heap entries.
107. **Verify zero primitive boxing in JVM FFM call sites via `javap` in `build.sh`** so JIT regressions fail the build.
108. **Use `ABBABAB` online tuning only under healthy headroom (`p99 < 100 ms`, `busy < 60%`)** with an >=8% CPU/req win threshold.
109. **Co-locate `ksoftirqd` awareness with loop sizing:** on small VMs (2-4 vCPUs), kernel RX/TX softirq share is a first-class competitor for CPU cycles.
110. **Treat architecture beats micro-tuning as a strict hierarchy:** Share-nothing per-core + zero-idle-buffer + DB pipelining/batching gives 5x-10x; SIMD/gzip/PGO gives the final 10-30%.
