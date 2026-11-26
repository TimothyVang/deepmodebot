---
description: "Run adversarial SOTA & repo gap research: verify code over docs, run disconfirmation probes, and build a SOTA-vs-repo Differential Gap Matrix"
argument-hint: "<question, repo, GitHub org URL, paper, or subsystem to gap-audit>"
---

Read `skill://deepmodebot` (**Contain the work** and **Non-negotiables**) and `skill://deepmodebot/references/techniques/research.md` (plus `skill://deepmodebot/references/techniques/prior-art.md` when evaluating external repos or orgs) in full.

Initialize `<project-root>/.scratch/research/<slug>/ledger.json` with `python -B "<deepmodebot skill dir>/assets/gap-audit/gap_audit.py" init-research --root "<project-root>" --slug "<slug>" --question "<question>" --json` (`py -3 -B` on Windows), inspect primary source code, specs, papers (`dmb-net fetch-papers`), and repos (`trending.py find` / `trending.py org`), run mandatory disconfirmation probes (`record-claim`), populate the SOTA-vs-Repo Differential Gap Matrix (`record-gap`), and enforce `gap_audit.py verify-research --dir "<ledger-dir>" --strict --render "<out.md>" --json` before reporting.
