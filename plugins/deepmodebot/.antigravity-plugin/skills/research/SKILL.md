---
name: research
description: "Adversarial SOTA & repo gap research (/research): code-over-docs verification, disconfirmation probes, and SOTA-vs-repo Differential Gap Matrix."
---

# /research

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) for **Contain the work** and **Non-negotiables**, then read `skill://deepmodebot/references/techniques/research.md` (and `skill://deepmodebot/references/techniques/prior-art.md` when evaluating repos or orgs) in full.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Run `python -B "<deepmodebot skill dir>/assets/gap-audit/gap_audit.py" init-research --root "<project-root>" --slug "<slug>" --question "<question>" --json` (`py -3 -B` on Windows), verify primary source code and root `LICENSE` files over READMEs, record adversarial disconfirmation probes (`record-claim`) and the SOTA-vs-Repo Differential Gap Matrix (`record-gap`), and pass `gap_audit.py verify-research --dir "<ledger-dir>" --strict --render "<out.md>" --json` before presenting findings.

Apply this to what the user asked for.
