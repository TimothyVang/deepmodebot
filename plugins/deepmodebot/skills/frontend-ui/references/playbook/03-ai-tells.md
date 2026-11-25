## 3. AI tells → concrete replacements

Bans without positive targets yield sterile grey wireframes. Pair every avoided cliché with its concrete replacement (explicit brief requirements always win). Pick your baseline archetype first in `references/playbook/00-art-direction.md`.

| AI tell (avoid by default) | Replace with |
| --- | --- |
| Default shadcn grays, radius, and lone `Inter`/system font | Retheme radius, OKLCH brand-tinted neutrals, and a curated typeface pairing from `00-art-direction.md` |
| Nested bordered cards inside bordered sections (border soup) | Spacing (`24–40 px`), alignment, ground shifts (`2–3%` L), or `1 px` row/column hairlines (`<= 1` bordered depth) |
| Purple/indigo glow washes, glass cards, cursor-following glows, idle AI orbs | Quiet tinted surfaces with subtle directional top-edge light; reserve glow/motion strictly for actively generating state |
| Unrequested chip, badge, eyebrow, and status-pill clutter | Remove non-essential chrome via the removal test below; show plain trace lines for tool calls |
| Template micro-chrome (`ALL-CAPS` eyebrows, `A · B · C` meta strings, `→` on every CTA, `01/02/03` non-sequences, accented italic word in every headline) | Plain sentence-case headings, weight/tone hierarchy, result-naming CTAs |
| Rainbow button clusters or multiple solid primaries per view | One solid primary action per view; outline/soft secondary; text-link tertiary; red primary only inside destructive confirm |
| Color mistakes (grey/opacity-dimmed text on colored fills, white on yellow/green, saturated solid badges, unequal-loudness status colors) | Same-hue text on colored fills, light-tint badges with dark same-hue text, equal-L/C status colors checked in greyscale |
| Fake proof ("Acme", "Sarah Chan", `99.99%`, "Trusted by 10,000+", "Powered by AI") | Real product truth, realistic domain records, or honest empty/placeholder copy |
| Anthropomorphic agent copy ("I thought about…", unlabeled sparkles, "AI can make mistakes" banners) | Plain state verbs (`Running` → `Ran` / `Failed to run`) and actionable work descriptions |
| Heavy `rgba(0,0,0,.15)` shadow on every card; fade-and-slide-up on every section | Layered OKLCH ambient shadows (`0.01–0.04` alpha) on raised layers only; max one standout moment per page |
| Video tells (centered title on gradient, floating tilted 3D UI in dark void, typing prompt opener, breathing landed titles, default crossfades) | Real 2× product UI doing one real task, dead-still landed text, object-carried transitions (`references/playbook/05a-motion-graphics.md`) |

### Removal test (run on every suspect element)

1. Name the element and the exact user job it performs.
2. Mentally delete it from the screenshot. If meaning, state, action, and hierarchy survive (and clarity improves), delete it for real.
3. Never compensate for a deleted gimmick by adding another decoration.
