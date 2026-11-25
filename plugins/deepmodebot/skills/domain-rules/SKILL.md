---
name: domain-rules
description: "Domain engineering rules for design/review: AI agents/LLMs, AWS networking, backend & high-scale perf, cache/data structures, languages, DevOps, debugging."
metadata:
  as-of: "2026-11-11"
---

# Engineering domain rules

Distilled from 102 public 2026 engineering talks (full source key table: `references/sources.md`) and 450+ benchmarked server implementations (`high-scale-server-optimization.md`, `data-structures-and-cache-optimization.md`), current as of 2026-11-20. Read only the file your task touches.

| File | Read when |
|---|---|
| `references/agent-engineering.md` | Building, reviewing, or debugging an AI agent, harness, multi-agent system, MCP/WebMCP integration, or agent instruction file |
| `references/ai-concepts.md` | LLM fundamentals, RAG/retrieval, fine-tuning, inference cost/hardware, local models, model choice |
| `references/aws-networking.md` | AWS/VPC design, cloud connectivity failures, IAM, cloud cost, picking an AWS service |
| `references/backend-system-design.md` | Backend code, API design, database choice/tuning, caching, queues, scaling, resilience, observability, security |
| `references/language-ecosystems.md` | Runtime, memory, concurrency, tooling, and traps for C, C++, Rust, Go, Java, C#, Python, JS/TS, PHP, Ruby, Kotlin, Swift |
| `references/devops-and-fundamentals.md` | Linux, CLI, git, Docker, Kubernetes, Terraform, CI/CD, deploy strategies, secrets, complexity, memory, floats, concurrency, protocols |
| `references/engineering-practice.md` | Unfamiliar codebases, debugging slowness/memory/races, legacy code, PR/commit text, incidents, estimates, pushing back |
| `references/high-scale-server-optimization.md` | High-concurrency server tuning, `epoll`/`io_uring`, TCP/NIC sysctls, Postgres/SQLite batching, co-located DB contention, zero-alloc JSON/gzip, GC/PGO |
| `references/data-structures-and-cache-optimization.md` | Hot-path data structures, pointer-free slot tables, 64 B cache-line alignment, L1D/TLB/hugepages, lock-free SPSC rings, timing wheels, tight-RAM arenas |
| `references/sources.md` | Resolving any `[SOURCE-KEY]` video citation in the files above |

Deepmodebot's principles, gates, and playbooks win any conflict. These files supply domain rules, not process.
