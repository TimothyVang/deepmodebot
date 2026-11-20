---
name: tournament
description: "Run a 12-agent evidence-backed tournament bracket (/tournament) across orthogonal architecture and research lenses, judged with receipt verification and grafting, proposing Champion + Runner-Up before coding. Use when invoked via /tournament, or when hunting architecture/research gaps on an open or vague goal."
---

# /tournament

Read `skill://deepmodebot` (`../../../skills/deepmodebot/SKILL.md` from this skill folder, or `~/.gemini/config/plugins/deepmodebot/skills/deepmodebot/SKILL.md`) for **Contain the work**, **Secrets**, and **Autonomy** subscription rules, then read `skill://deepmodebot/references/techniques/tournament.md` in full and run the **tournament** bracket on the user's goal. Outside a git repo, create a named project root first per **Contain the work** and keep every scratch or temp file inside `<root>/.scratch/`.
In Antigravity, `skill://<name>/<path>` means `<path>` inside `../../../skills/<name>/` (`~/.gemini/config/plugins/deepmodebot/skills/<name>/`).

Initialize `<root>/.scratch/tournaments/<slug>/bracket.json` with `python -B "<deepmodebot skill dir>/assets/tournament/tournament.py" init --root "<root>" --slug "<slug>" --prompt-stdin <<'EOF'` (`py -3 -B` on Windows).
Fan out read-only contenders (`invoke_subagent` with `scout`/`research`, `run_workflow`, or `omp_task`), enforce verified receipts on every pitch and rebuttal, run Round 1 clashes, the semifinals, and the final with an independent read-only judge and optional single-insight grafting, and stop at the **Champion** plus **Runner-Up** proposal gate unless explicitly asked to build the winner too.

Apply this to what the user asked for.
