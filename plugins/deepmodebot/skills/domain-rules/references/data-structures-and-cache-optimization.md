# Data structures & CPU cache optimization

Distilled from `arjaythedev`'s `$12 Server` (1 vCPU / 2 GB RAM, 244 entries), `Multicore` (8 vCPU / 16 GB RAM, 117+ entries), and `Million Users` (2-16 vCPU, 96 entries) challenges. Use when designing or optimizing hot-path data structures, memory layouts, lock-free queues, or tight-RAM runtimes.

## 1. Memory Packing & Pointer-Free Layouts

1. **Pack per-entity/connection slots to 8-64 bytes in flat arrays.** Avoid per-connection heap objects. An 8-12 B or 24-64 B flat `struct` indexed by fd/slot uses ~16-40 MB at 1M entries instead of 10-38 GB.
2. **Keep hot tables pointer-free in GC'd languages (Go, C#, Java, JS/TS, Python).** Store integer indices, generation tags, and `Uint32Array`/`Uint8Array`/primitive arrays instead of object references so the GC never scans millions of idle slots.
3. **Encode operation metadata in 64-bit `user_data` tags.** Pack `(op, ring, gen, aux, slot)` bits into `io_uring` `user_data` or queue tokens to validate completions in O(1) without dereferencing heap structs.
4. **Detach buffers from idle state.** Idle slots hold null/no rx/tx buffers; borrow from shared LIFO buffer pools or provided-buffer rings only while a request is active so LIFO reuse keeps only hot pages resident.
5. **Use inline small-string buffers (`SmallStr`).** A 64-byte stack-inline string avoids heap allocations for keys, usernames, and short tokens on 99% of requests.
6. **Avoid Actor/Graph reference retention leaks.** Never let per-connection actors or handlers hold a reference to a central coordinator that references the entire DB/worker pool; pass only the single assigned slot/handle (e.g., Pony ORCA dropped from 296 KB/conn to 11 KB/conn).

## 2. CPU Cache-Line, L1D & TLB Optimization

7. **Pad cross-thread ring indices and wake flags to 64-byte cache lines.** Put producer `head`, consumer `tail`, and `idle` wake flags on separate `alignas(64)` lines to eliminate false sharing.
8. **Cache peer ring indices locally; publish batches with one atomic store.** On SPSC rings, read the peer's index only when your cached bound looks full/empty, and advance `head`/`tail` once per batch.
9. **Space per-worker wake flags 64 bytes apart (`64 * (w + 1)`).** Prevents cache-line ping-pong when a central planner wakes individual workers.
10. **Avoid L1D 4K-aliasing on multi-lane state arrays.** Pad per-lane structs off exact 4,096 B multiples (e.g., `4,224 B` with `align(64)`) so interleaved SIMD/crypto lanes do not collide on the same L1D sets.
11. **Right-size open-addressed hash tables to fit L1/L2 cache.** Start dynamic lookup tables small (e.g., 4,096 slots) and grow only if needed; fixed 65,536-slot (256 KiB) tables caused 18% CPU cache-miss overhead.
12. **Use L1D-resident bitsets (`[u64; 8]` / `[u64; 32]`) for small membership checks.** Replacing hash sets or branchy loops with bitmasks for per-batch flags keeps lookups in L1D.
13. **Use hardware CRC-32 (`_mm_crc32_*`) for fast integer/short-key hashing.** Cuts hash-map CPU overhead on hot lookup tables.
14. **Pre-fault 2 MB hugepages ONLY for static pools, then disable process-wide THP.** `mmap` + `MADV_HUGEPAGE` + pre-fault static caches (page cache, slot arrays) at startup to cut EPT/TLB walks, then call `prctl(PR_SET_THP_DISABLE, 1)` so dynamic heap allocators do not stall on kernel compaction.
15. **Do not force 64-byte function alignment blindly.** Over-aligning functions can reduce instruction-fetch stalls slightly while tripling branch misses and hurting overall IPC; benchmark with `perf stat`.

## 3. Queues, Timers, Arenas & Page Reclaim

16. **Bypass TCP loopback for intra-process/local IPC.** Use `mmap(MAP_SHARED | MAP_ANONYMOUS)` SPSC rings + `eventfd` (1-3 us) or `AF_UNIX` `socketpair` instead of loopback sockets.
17. **Replace millions of per-item timers with a hashed timing wheel.** A 512-slot 1-second wheel cut Go timer CPU from 3.4% to 0.2% across 1M sockets.
18. **Use 2-12 MiB `mmap` response arenas recycled at `inflight == 0`.** Write JSON bodies with 128-256 B header headroom directly into the arena, prepend headers in-place, and reset the cursor once all `SEND`s complete.
19. **Protect hot `.text` pages on swapless tight-RAM boxes.** Linux MGLRU evicts file-backed code pages first when swap is off; use `mlock`/`MLOCK_ONFAULT` within `RLIMIT_MEMLOCK` (or remap hot code to anon pages) to prevent major-fault stalls.
20. **Control glibc arena fragmentation.** Set `mallopt(M_ARENA_MAX, 1..4)` (or `M_TRIM_THRESHOLD`) on fixed-thread services and call `malloc_trim(0)` after backlog spikes drain so freed buffers return to the kernel.
21. **Avoid `memset` in hot loops via epoch/base-cursor tricks.** Increment a monotonic `base` cursor on pre-sized LZ77/dedup tables instead of zeroing 8-16 KB per call.

## 4. Algorithmic & Storage Access-Pattern Wins

22. **Sort batch lookup keys monotonically before probing B-trees.** Sorting post/author IDs ascending before `TableMoveto` or Postgres `= ANY($1)` walks contiguous leaf pages in L1/cache order instead of random root-to-leaf probes.
23. **Traverse B-tree cursors directly when SQLVM/ORM overhead dominates read-heavy hot paths.** Keeping positioned cursors across read passes and decoding local varint/big-endian payloads off pinned page-cache pointers avoids bytecode VM and `Mem` allocations.
24. **Replace `pcache1` `xTruncate` O(N) scans via `SQLITE_CONFIG_PCACHE2`.** Track `max_key` / park split-swap pages at key `0` so B-tree splits do not trigger full hash-table scans on every commit.
25. **Use LIFO-with-aging on overloaded request queues.** Serve newest requests first to stay inside TCP's 40 ms delayed-ACK window, while reserving a slice (e.g., 50% at 8 s, 100% at 16 s) for aged items to prevent starvation.

## 5. Game Engine, Sim & Real-Time Frame-Budget Layouts

26. **Use Structure-of-Arrays (SoA) over Array-of-Structures (AoS) for hot tick loops.** Storing positions, velocities, and flags in contiguous per-field arrays lets ECS/sim loops stream sequential cache lines and SIMD-vectorize without loading cold fields.
27. **Pre-reserve contiguous arrays and replace `std::unordered_map` on hot paths.** Node-based maps allocate per entry and chase pointers; use flat open-addressed hash maps, dense ID-indexed arrays, or `Reserve()`d vectors.
28. **Use frame-scratch bump allocators reset every tick.** Transient per-frame/per-step scratch data should advance a pointer in a pre-allocated arena and reset in O(1) at frame end instead of calling `malloc`/`new`.
29. **Never flush or heap-allocate inside simulation/render tick loops.** Avoid `std::endl`, string formatting, or dynamic container growth inside 60-120 Hz tick paths; emit diagnostics to lock-free SPSC ring buffers.
30. **Separate sim-thread and render-thread state via double-buffered snapshots or SPSC queues.** Eliminates mutex contention on frame boundaries and keeps frame times deterministic.
