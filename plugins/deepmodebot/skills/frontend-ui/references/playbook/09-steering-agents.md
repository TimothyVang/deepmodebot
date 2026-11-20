## 9. Steering agents (meta)
[articles/vercel-agents-design-guidance; articles/anthropic-harness-*]
- Always-loaded `AGENTS.md` rules trigger more reliably than optional skills (one Vercel write-up cited 100% vs 53–79% [unverified: no primary eval URL archived]). Still keep `AGENTS.md` short (~200 lines max per `skill://agent-harnesses/references/delegation-efficiency.md`): inline only universal invariants and route detailed workflows to skills.
- "Explore the project first, then load the skill" works better than "MUST invoke the skill first".
- Write observable rules ("Destructive CTAs use Verb + Noun"), not adjectives ("clean", "polished").
- Criteria wording steers the look: words like "museum quality" pull every design toward one style.
- When a rule is mechanically checkable, make it a lint rule rather than more prose.
- **Prompt with vocabulary:** name effects (pop-in, stagger, morph, rubber-band, origin-aware) and moves (bolder, quieter, distill, polish). Narrow each request to one section and add a feel constraint ("count up, fast and professional"). [.claude/skills/animation-vocabulary; youtube/vjP8bNs8aok; youtube/r2P1v64pM28]
- Package house effects as parameterized skills (effect, intensity, personality) and improve them after each use. [youtube/TbZjOrrZIVk]
- If a project defines heavy explicit-only UI skills (for example animation review, library selection, or UI prototyping in its own `.claude/skills/` or `.agents/skills/` — not bundled in deepmodebot), load them by path so names like `prototype` do not collide with user-level skills.
- **Steer design revisions with named verbs** that have project-specific meanings (bolder = hierarchy, scale and type, never gradients, glass or neon; harden = devices, edge cases, performance). No auto mode: a human chooses each steer. [youtube/v42opQpCy60]
- **Use shapeof.ai pattern names as shared vocabulary** in prompts ("Action Plan", "Stream of Thought: plan / execution / evidence", "Sample response before Auto-fill"). [articles/ai-ux/shapeof-ai-pattern-library]
- **One flat accent means "agent acting now"** (§6a): never a gradient, never on idle UI. Brand color only on the primary CTA and badges; status colors only for operational status. [articles/ai-ux/atlassian-rovo-ai-guidelines; articles/ai-ux/openai-apps-sdk-ui-guidelines]
