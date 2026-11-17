# Upstream attribution

This directory adapts `pstack/skills/statechart/` from Lauren Tan’s pstack in `cursor/plugins`.
Copyright (c) 2026 Lauren Tan. Licensed under MIT; the full license is in `LICENSE` beside this notice.

- Canonical source: https://github.com/cursor/plugins/tree/main/pstack
- Imported repository snapshot: `536a3352a050e47cb75f86be497ea304ef342301` (2026-11-17).
- Latest pstack commit in that snapshot: `2f87c854fe3e2fcda44ca86b46ede35aad3c46b7` (2026-11-16).
- Plugin version: `0.15.43`, from the pinned `pstack/plugin.json`.
- Pinned source: https://github.com/cursor/plugins/tree/536a3352a050e47cb75f86be497ea304ef342301/pstack/skills/statechart

## Integration changes

Adapted skill discovery and cross-links for deepmodebot on omp, Claude Code, and Codex.
Documented repository-local scratch work, isolated mutations, optional tools, and evidence limits.
No upstream automation, model-provider routing, or bots are installed by these skills.

The TypeScript compiler, launcher, test suite, and synthetic corpus are vendored from that snapshot.
Compiler behavior is unchanged. Package identity is `@deepmodebot/statechart`.
Recorded upstream fixture paths under `/agent/repos/plugins/pstack/` are normalized to `/source/plugins/deepmodebot/`; they are parser fixtures, not new run evidence.
The corpus reports are historical expected outputs, not proof that this integration has been executed.
Pele, TLC, Java, and optional test packages are not vendored; their licenses remain with their respective distributions.

The November 15 source change includes improved SANY line/column diagnostics and parent-state border entry rendering:
https://github.com/cursor/plugins/commit/bf0c7cd80abdbf7fe47b634978a7d1b4071f71a7
The November 16 release metadata and changelog are at:
https://github.com/cursor/plugins/commit/2f87c854fe3e2fcda44ca86b46ede35aad3c46b7

## Primary announcement trail

- Stable statechart v0.15.36, mini TLC compiler and formal-verification pairing: https://x.com/poteto/status/2115880102601101414
- Pele diagram rendering: https://x.com/poteto/status/2113398433977659654
- Later usage example, one verification skill per subsystem: https://x.com/poteto/status/2119521036660314339
- Later explanation of project-local verify skills: https://x.com/poteto/status/2119606119559782488

Announcements identify capabilities, not the pinned release. Version and dates above come from GitHub source and commit metadata, not search-snippet relative timestamps.
