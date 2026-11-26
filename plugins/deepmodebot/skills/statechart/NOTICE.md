# Upstream attribution

This directory adapts `pstack/skills/statechart/` from Lauren Tan's pstack in `cursor/plugins`.
Copyright (c) 2026 Lauren Tan. Licensed under MIT; the full license is in `LICENSE` beside this notice.

- Canonical source: https://github.com/cursor/plugins/tree/main/pstack
- Imported repository snapshot: `b1fbf4b60ac6813b4583ccc356850dafcf492665` (2026-11-25).
- Latest pstack commit in that snapshot: `9e278fe4d4ec` (2026-11-24), including native Windows & `\r\n` TLC fixes (`0b46ec399d55`, 2026-11-19).
- Plugin version: `0.15.48`, from the pinned `pstack/plugin.json`.
- Pinned source: https://github.com/cursor/plugins/tree/b1fbf4b60ac6813b4583ccc356850dafcf492665/pstack/skills/statechart

## Integration changes

Adapted skill discovery and cross-links for deepmodebot on omp, Claude Code, Codex, and Google Antigravity.
Documented repository-local scratch work, isolated mutations, native Windows Node TypeScript execution, optional tools, and evidence limits.
No upstream automation, model-provider routing, or bots are installed by these skills.

The TypeScript compiler, janitor/kill helpers, launcher, test suite, and synthetic corpus are vendored from that snapshot.
Compiler behavior is unchanged. Package identity is `@deepmodebot/statechart`.
Recorded upstream fixture paths under `/agent/repos/plugins/pstack/` are normalized to `/source/plugins/deepmodebot/`; they are parser fixtures, not new run evidence.
Pele, TLC, Java, and optional test packages are not vendored; their licenses remain with their respective distributions.
