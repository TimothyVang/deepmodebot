# Measurement and repository-discovery learning

Source research captured 2026-11-14. This is authored synthesis, not reproduced benchmark evidence or permission to execute tutorial code.

## Coverage, not a claim every video was watched

| Collection | Capture | Substantive review and limits |
| --- | --- | --- |
| [Arjay McCandless](https://www.youtube.com/watch?v=TIyvOtGjnzc) | 432 unique items, 431 returned native-caption texts, 17 technical frames | 16 full available-text reviews; other texts unread. One unavailable caption path and alternate-language gaps remain. No continuous audio/video review. |
| [Better Stack](https://www.youtube.com/watch?v=qy4ajsBbOKw) | 1,477 items; 1,474 complete default transcript panels and three documented exceptions | 11 full returned-text reviews; 1,466 items not substantively reviewed. All 107 additional original tracks across 67 videos were selected natively, but the UI retained baseline English and exposed no alternate transcript selector: zero full alternate-panel captures. |

The [rights-qualified Better Stack archive](https://drive.google.com/drive/folders/1nzQmn_7ncIHzP8x_JGNVZSY-ExZCgJNN) contains authored findings, factual indexes, 19 limited source-frame quotations and sanitized repository metadata, not full copied captions/descriptions or an unrestricted source mirror. Downloaded ZIP SHA, CRC and every indexed member were independently checked. Its namespace diagram is an actual source frame, not a reconstructed original.

## Accepted refinements

The existing [benchmark checklist](../../../plugins/deepmodebot/skills/deepmodebot/references/techniques/benchmark-checklist.md) remains the single measurement procedure. These sources refine it rather than introduce another benchmark convention:

- Preserve equivalent observable responses, authentication and durability before comparing throughput.
- Budget database connections across all workers/processes and reserve operational headroom; a per-process pool size is not the aggregate.
- Keep failed builds, timeouts, unsupported and not-scored cases visible rather than reducing the denominator.
- Merge samples/histograms before computing aggregate percentiles; averaging worker percentiles is not equivalent.
- State arrival/session model and generator saturation. Closed-loop concurrency is not a fixed open-loop request rate.
- Separate process/container lifecycle latency from application readiness and useful completed work.

Primary evidence: Arjay's [specification](https://github.com/arjaythedev/multicore-server-challenge/blob/6145e7291a3625c184a58b63b86ed9d1f7304700/SPEC.md), [workload](https://github.com/arjaythedev/multicore-server-challenge/blob/6145e7291a3625c184a58b63b86ed9d1f7304700/WORKLOAD.md) and [histogram merge](https://github.com/arjaythedev/multicore-server-challenge/blob/6145e7291a3625c184a58b63b86ed9d1f7304700/bench/cmd/loadgen/merge.go); Kiri's [dated methodology](https://github.com/libracoder/kiri-bench/blob/a4e471cfe584f8aaaf5ba0166d7a00c21835a12a/docs/benchmarks/2026-11-02/HOW-WE-TESTED.md).

The Arjay challenge's connection limits and worker counts are workload parameters, not tuning defaults for another service. Its ranked Zig entry and off-leaderboard comparison are different submissions; no correctness disqualification was established by the reviewed public evidence. The collection ran neither submissions nor the load generator.

## Kiri: evidence against a universal winner

The seed's headline concerns a warm, pre-pulled short-lived Alpine container running `true` and immediate teardown. It does not establish a general application-startup or throughput improvement. The original methodology records failed build/network cases and page-cache rather than disk throughput; original per-sample outputs were not published. A current source pin is not proof it equals the historical abbreviated harness commit.

A Docker-compatible client/API surface does not prove namespace, seccomp, networking, volume, BuildKit or host-observability parity. Static review found required host namespace/security settings in the [collector configuration](https://github.com/BetterStackHQ/collector/blob/f9115bc81a8594c6573918f8bc54aa6b305582be/docker-compose.yml); unchanged deployment on another runtime was not verified. No daemon, container, trust certificate, public tunnel or benchmark was started for this research.

## Reference-only findings and rejected shortcuts

Other reviewed videos provide source-linked context, not newly enforced defaults: retained allocation/layout costs, OTel context and sampling loss, parser/wire-contract migration, held-out evaluator integrity, and provenance/invalidation for learned shortcuts. Tool-specific security/prover claims and historical SDK configurations were not independently reproduced.

Do not copy the unsafe recipes: adding swap without OOM/pressure diagnosis, force-pushing all branches for an ordinary revert, deleting a leaked secret without revocation/coordination, swallowing promise errors, or calling minimal image size a security guarantee. A policy description, a screenshot or several agreeing models is not an authorization mechanism.

## Additional repository choices

The [candidate index](../../../plugins/deepmodebot/skills/deepmodebot/assets/repo-candidates.json) contains 391 unique channel-linked, organization-discovered or primary-document-linked records. It is separate from the curated reference library. Most implementations are unread; some routes and metadata are unavailable. An observed SPDX identifier or captured license file is not a component-wide reuse grant.

Use `scripts/trending.py candidates <project terms>` for offline name/short-description/language matching. Results preserve snapshot revision, review state, unknown liveness/license data and adoption limits. The actual CLI was exercised for runtime discovery, an unavailable repository and an archived fork; it supplies no invented star counts or network enrichment. Read pinned primary implementation/license evidence before selecting a dependency or copying code.

Credential-shaped originals and encrypted credential links were quarantined, not followed, decrypted or exported. Narrow pattern scans are not a secret-free or security-audit guarantee.
