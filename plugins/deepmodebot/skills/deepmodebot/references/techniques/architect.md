# architect

**Use when:** "architect/design this", or a non-trivial interface/module change where jumping straight to code would lock in the wrong shape. For a large or contested design, run **arena** (`references/techniques/arena.md`) instead of sketching alone.

1. **Ground.** Trace every system the change touches directly (or run **why** when ownership or layering history constrains it); skip only for true greenfield. For system design, state critical user journeys, non-goals, expected traffic, operating constraints, existing API/data contracts, and trace one representative request through validation, authority, durable writes, async execution, and failure/replay behavior.
   Done when touched systems and the source of truth at every boundary hop are written down.
2. **Sketch and compare.** Sketch at least two structurally distinct shapes with caller usage and types first (`references/principles/exhaust-the-design-space.md`). Pick the shape with one owner per piece of state, one way to do each task, deep interfaces (more complexity hidden behind a smaller public surface), and the least for callers to know. Screen every candidate against the red flags below.
   Done when at least two shapes are compared against the red flags and one base is chosen.
3. **Implement or scrap.** Build against the sketch as the contract; surface deviations with their cause. If workarounds repeat (same workaround across unrelated code, type escape hatches, lock reflexes for unshared state, or >=2 same-shape deviations), stop patching, re-ground, and redesign smaller from day one.
   Done when the code matches the chosen shape (or deviations are listed) with no repeating friction pattern.

**Red flags:** shallow module · information leakage (re-exported wire types) · temporal decomposition · pass-through method · split ownership · two ways to do one task · importable internals · hand-synced lists.

**Output:** caller usage and type sketch, shapes considered, red-flag screen, and chosen design rationale.

**Done when** the implemented code matches the chosen shape (or every deviation names its cause) and at least two shapes were screened against the red flags.

System-design evidence: [requirements and request trace](https://www.youtube.com/watch?v=5nM5sB_kqYI&t=133s), [operating constraints](https://www.youtube.com/watch?v=hOYzvUQKq8s&t=632s).
