## 0. Art direction, archetypes & visual craft

First-draft AI interfaces look weak for one structural reason: banning clichés without choosing a positive visual system collapses output into sterile grey boxes. Pick **one** concrete archetype, **one** layout composition, and **one** surface/lighting formula before writing CSS.

### 1. Five positive aesthetic archetypes (pick one; adapt hue and type to the brief)

| Archetype | Best for | Surface & OKLCH recipe | Curated typography pairing | Geometry & finish |
| --- | --- | --- | --- | --- |
| **Precision Workbench** | Dev tools, consoles, dashboards, agent ops | Dark: canvas `L 0.14`, surface `0.18`, raised `0.22`, sunken `0.12` (chroma `0.008–0.014` at brand hue). Light: canvas `0.975`, surface `0.995` | `Plus Jakarta Sans` or `Geist` + `JetBrains Mono` / `DM Mono` (`tabular-nums`) | `6–10 px` radius, hairline low-alpha borders, dark top rim `inset 0 1px 0 oklch(1 0 0 / 0.07)`, borderless strips |
| **Warm Editorial** | Docs, reading, brand, launch pages | Deep pine/ink (`oklch(0.20 0.014 165)`) + warm stone (`oklch(0.92 0.010 92)`) + single muted botanical/ochre accent | `Newsreader` / `Instrument Serif` or `Gabarito` display (`-0.03em`) + `Figtree` / `Source Sans 3` + `DM Mono` | Sharp or subtle `4–6 px` radius, inverted contrast bands, asymmetric split grids, minimal shadow |
| **High-Density Swiss** | Fintech, telemetry, dense tables, admin | Paper `oklch(0.985 0.004 95)` or graphite `oklch(0.16 0.006 255)` + crisp semantic accents (equal L/C) | `IBM Plex Sans` + `IBM Plex Mono` (`tabular-nums`, tight leading) | `4–6 px` radius, horizontal `1 px` row rules instead of cards, oversized KPI numerals beside `12 px` muted labels |
| **Tactile Consumer** | Mobile-first apps, media, commerce, social | Warm off-white `0.98` or OLED charcoal (`#000` only on glanceable focal cards) + expressive single brand hue | `DM Sans` or `Outfit` display (`-0.025em`) + clean sans body | Concentric `16–24 px` radii, full-bleed media with `<= 3` text lines/card, `inset 0 1px 0` tactile lip, thumb-zone CTAs |
| **Spatial Canvas** | Creative tools, multiplayer, AI canvas | Quiet neutral ground (`L 0.15` dark / `0.965` light, chroma `<= 0.006`) so user content owns 100% of color | `Geist` / `DM Sans` + `DM Mono` | Floating frosted bars (`backdrop-filter: blur(16px) saturate(1.6)`), origin-aware popovers, quiet chrome |

### 2. Break the centered-card-grid default (pick a real composition)

- **Asymmetric split (`5fr / 7fr` or `4fr / 8fr`):** narrative or controls in a sticky narrow rail; live artifact, table, or canvas in the wider pane.
- **Borderless metric strip:** display 3–5 KPIs in one unified bar separated by `1 px` vertical hairlines and whitespace, never individual bordered tiles stacked above bordered cards.
- **Master-detail workbench:** compact filterable list on the left/top; inline expansion or live side inspector on the right (eliminates modal hopping).
- **Editorial hero + live proof (Persuade):** oversized display headline (`clamp(2.25rem, 5vw, 4.5rem)`, `line-height: 0.98–1.08`, `text-wrap: balance`), one concise value proposition, one solid primary CTA, paired directly with real interactive product UI — never a wall of feature cards.
- **Flat ruled rows (Operate):** operational items separated by subtle bottom hairlines + hover surface lift instead of nested bordered boxes.

### 3. Surface depth, lighting & border budget

- **Border budget (`<= 1` depth):** never nest a bordered card inside a bordered section inside a bordered panel. Separate groups with `24–40 px` spacing, alignment, or a subtle ground shift (`2–3%` L); reserve borders for interactive controls and top-level boundaries.
- **Dark-mode lighting:** top edges catch subtle light (`box-shadow: inset 0 1px 0 oklch(1 0 0 / 0.07)` on surfaces and primary buttons); recessed inputs/code wells sit slightly darker (`--bg-sunken`) than the card holding them.
- **Light-mode elevation:** pair a `1 px` low-alpha border (`oklch(0 0 0 / 0.08)`) with a soft 3-layer OKLCH ambient shadow (`0 1px 2px oklch(0 0 0 / 0.03), 0 4px 12px oklch(0 0 0 / 0.04)`), never harsh `rgba(0,0,0,0.15)` drop shadows.
- **Sticky chrome:** toolbars and action docks use translucent surface fill + `backdrop-filter: blur(14px) saturate(1.5)` so scrolling content remains spatially legible underneath.
- **Desktop vs touch sizing:** on coarse touch pointers keep `44 px` hit targets (`@media (pointer: coarse)` or generous hit-slop); on dense desktop Operate toolbars (`(pointer: fine)`), crisp `32–36 px` buttons and pills read far more refined than inflated `44 px` blocks while maintaining clear focus rings.

### 4. Starter CSS kits (adapt, don't invent from zero)

Start from the matching bundled CSS kit under `assets/themes/` and tune hue/type to the brief: `workbench.css`, `editorial.css`, `swiss.css`, `tactile.css`, `canvas.css`, plus `layouts.css` (`.layout-split`, `.layout-workbench`, `.layout-kpi-strip`, `.ruled-list`, `.frosted-bar`).

### 5. Mandatory 2-round visual polish pass (never ship round 1)

1. **Mechanical audit first:** run `python -B <frontend-ui skill>/scripts/ui_audit.py <target>` (static gate) and execute `--browser-snippet` in Chromium at `1440×900` and `390×844` (real WCAG AA contrast, `document.fonts` fallback check, overflow, border depth).
2. **Clean-context visual critique:** hand *only* the brief, `1440×900` + `390×844` screenshots, and `ui_audit.py` JSON to a fresh-context reviewer subagent (no builder rationale) to score `02-review-rubric.md` and return <= 5 ranked visual fixes (timid hierarchy, border soup, flatness, clutter, icon/chart noise).
3. **Apply Round 2 polish and re-capture** both viewports to prove the visual delta and zero audit regressions.
