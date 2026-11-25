## 2. Review rubric & mechanical visual gates

Every UI review checks **mechanical gates** first (run `scripts/ui_audit.py` + live browser inspection) and **design-director criteria** second on real `1440×900` and `390×844` screenshots.

### Mechanical gates (automatic fail if violated)

| Check | Pass bar |
| --- | --- |
| Horizontal overflow | `scrollWidth <= innerWidth` at both `1440 px` and `390 px` |
| Contrast & focus | `lowContrastSamples: []` (WCAG AA `>= 4.5:1` body, `>= 3:1` large) + visible `:focus-visible` ring on every control |
| Type & webfonts | Clear scale ratio (`h1 / body >= 1.4x` Operate, `>= 2.2x` Persuade), intended webfonts present in `loadedWebfonts`, `tabular-nums` on metrics |
| Border budget | `<= 1` nested bordered container depth per region (no bordered cards inside bordered sections inside bordered panels) |
| Token & motion hygiene | `transitionAllCount: 0`, `@media (prefers-reduced-motion: reduce)` present, role tokens over raw hex/Tailwind grays, frequent button hovers `<= 160 ms` |
| Collective video & rehearsal gate | Multi-step/animated flows recorded end-to-end, watched as one continuous video (not single frames), and passing `rehearsal_gate.py verdict --strict` |
| Console & states | Zero console/page errors; loading, empty, error, and primary interactive states exercised live |

### Design-director rubric (inspect actual screenshots & full video)

| Criterion | Weight | Fails when |
| --- | --- | --- |
| Visual identity & craft | High | Sterile grey boxes, flat elevation, near-tangents (`1–3 px`), floating boxed hero shots, unexamined system fonts, or invented logo marks (`06c-product-shots-craft.md`) |
| Focal hierarchy | High | Squinting at the screenshot reveals no clear #1 focal point or primary action within 1 second |
| Originality & restraint | High | Unmodified library defaults, AI tells (§3), or chip/badge/card clutter competing with real content |
| Functionality & a11y | Normal | Unclear primary action, broken keyboard flow, missing accessible names, or broken compact layout |
| Delegation (agent UI) | High | User cannot leave and return, inspect per-task status, steer/stop mid-run, or approve/deny cleanly |

Report findings by severity (`P0` blocks task or severe a11y fail, `P1` likely task failure / broken visual hierarchy / missing state, `P2` friction, `P3` polish). Lead with user impact, location, observed screenshot/DOM evidence, and exact fix.
