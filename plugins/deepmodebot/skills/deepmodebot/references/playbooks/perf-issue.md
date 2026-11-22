# Perf Issue

Use when: something is slow or heavy and needs a one-off fix tied to a measurement. For sustained improvement against a metric use `references/playbooks/hillclimb.md`. You own the measurement story: plan, review, verify the numbers. Measure; don't read source instead of measuring.

## Steps
1. Capture a baseline trace and static hot-path audit on the matching surface:
   - Run `python -B "<this skill>/assets/perf-audit/perf_audit.py" --path "<root>" --json` and check `domain-rules/references/high-scale-server-optimization.md` and `domain-rules/references/data-structures-and-cache-optimization.md`.
   - Measure via the repo's `verify-<app>` skill (in `.omp/skills/`, `.claude/skills/`, or `.agents/skills/`), `python -B "<this skill>/assets/perf-audit/bench_harness.py"` (`http` or `cmd`), DB `EXPLAIN (ANALYZE, BUFFERS)` + query-count assertions, CPU/alloc profilers, omp `eval` `browser`, Playwright/CDP, or bash.
   - Vet it, and every later number, with **benchmark-checklist** (`references/techniques/benchmark-checklist.md`).
   Done when `perf_audit.py` has run and a saved baseline artifact passes every benchmark-checklist item.
2. Ground hypotheses with the **how** technique (`references/techniques/how.md`). Try the performance mantras in order, cheapest first; stop at the first that meets the target:
   1. Don't do it (drop unused fields/serialization, skip gzip before DB waits, cut dead queries).
   2. Do it, but don't do it again (prepared statements, module-level pools, `singleflight` + jittered cache-aside).
   3. Do it less (replace N+1 / `await`-in-loop with `= ANY($1)` batching, `OFFSET` with keyset cursors, composite/FK indexes).
   4. Do it later (transactional outbox / background queue off the request thread).
   5. Do it when they're not looking (precompute rollups, warm pools/JIT before traffic).
   6. Do it concurrently (non-blocking async I/O, semaphore-bounded fan-out `p-limit`/`Semaphore`, SPSC sharding).
   7. Do it cheaper (`orjson`/`msgspec`, flat hash maps, arena/slab buffers, SoA layout, literal SQL `LIMIT`).
   - Done when each tried mantra has a hypothesis tied to the trace, stopping at the first that meets the target.
3. Plan the fix from the trace. Changes a module or public interface with two or more viable shapes → the **architect** technique (`references/techniques/architect.md`) first. Size L → delegate implementation to a default `task` agent (exclusive file ownership, reasoning level per job) and review the diff. Size M → make the change yourself, then run the **pr-review** self-review (`references/techniques/pr-review.md`, local mode).
   Done when the fix is implemented and, for Size M, the self-review has no open P0/P1.
4. Verify each attempt before trying the next (`references/principles/sequence-verifiable-units.md`). Capture a post-fix trace. Done when a post-fix artifact exists for the kept attempt.
5. Parse and compare artifacts (JSON → sqlite, diff). Done when you have a baseline, post-fix, and delta number from the same harness.
6. Cite the measurement in the hand-off (and the commit and PR description). Done when those numbers are in the commit message and drafted for the PR body that step 7 opens.
7. Deliver per SKILL.md's delivery-target rule: for local review or a repo with no remote, leave verified S/M edits uncommitted in the starting working tree with the before/after numbers. For publication, commit and run **Opening a PR** (`references/playbooks/opening-a-pr.md`), which lands a single PR through **pr-conversation** on a panel pass (or a stack through `references/playbooks/shipping.md`).
   Done when the requested delivery target holds (verified uncommitted local fix, merged PR, or stack handed to Shipping).

## Gates
- Every fix tied to a measurement; no perf ceiling claimed without running it.
- Stop at the earliest mantra that meets the target.
- "Inconclusive" or wrong-surface is not a pass. Flag it.

## Evidence
- Baseline number, post-fix number, delta, artifact path(s).
