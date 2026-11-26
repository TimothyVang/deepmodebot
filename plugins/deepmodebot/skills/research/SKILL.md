---
name: research
description: "Adversarial SOTA & repo gap research (/research): primary-source code verification, mandatory disconfirmation probes, and SOTA-vs-repo Differential Gap Matrix across agy, omp, Claude Code, and Codex."
---

# /research

Read `skill://deepmodebot` (`../deepmodebot/SKILL.md` from this folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md` in Antigravity) for **Contain the work** and **Non-negotiables**, then read `skill://deepmodebot/references/techniques/research.md` (plus `skill://deepmodebot/references/techniques/prior-art.md` when evaluating repos, packages, or GitHub orgs) in full.

Execute the identical 4-stage machine-checked workflow in every harness (`agy`, `omp`, `Claude Code`, `Codex`):

1. Initialize the ledger and baseline repo gap scan:
   `python -B "<deepmodebot skill dir>/assets/gap-audit/gap_audit.py" init-research --root "<project-root>" --slug "<slug>" --question "<question>" --json` (`py -3 -B` on Windows).
2. Harvest primary code, specs, papers (`dmb-net fetch-papers`), and repo/org SOTA (`trending.py find` / `trending.py org`), inspecting root `LICENSE` text directly whenever SPDX is `NOASSERTION` or `NONE`.
3. Run adversarial disconfirmation probes (open GitHub bug issues, changelogs, CVEs, code-vs-README contradictions, and small-$n$ boundary checks) and record every claim via `gap_audit.py record-claim`.
4. Map upstream SOTA capabilities and invariants against the active repository (`missing`, `partial`, `stubbed`, `divergent`, `parity`) via `gap_audit.py record-gap`, then enforce `gap_audit.py verify-research --dir "<ledger-dir>" --strict --render "<out.md>" --json` (`PASS`, exit 0) before replying.

Apply this to what the user asked for.
