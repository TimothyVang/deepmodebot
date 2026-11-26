# how

**Use when:** "how does X work", code walkthroughs before changing a subsystem, or placement and ownership questions ("where should this live", "which package owns this"). Motivation questions → **why**. Routine code reads inside a playbook trace directly inline without invoking this technique.

If the scope is ambiguous, state your interpretation and explore.

1. **Explain.** Spawn one read-only explorer (`scout`) that traces the code and explains it in one pass for a senior engineer: overview, key concepts, step-by-step runtime flow naming real files and functions with `file:line`, where things live, and non-obvious gotchas. Split into 2 to 4 parallel angles only for genuinely cross-cutting multi-subsystem overviews.
   Done when the explanation covers the asked scope with `file:line` citations and names any open questions.
2. **Present.** Share the explanation with light edits for clarity or conversation context. Don't pad simple modules or rewrite from scratch.
   Done when every code claim carries a `file:line` citation and open questions are listed.

**Done when** the question is answered with `file:line` citations for every claim about the code and each open question is named.
