## 4. Components: compose, don't hand-roll
Order of preference [youtube/zsCGS-Yzjnw; .claude/skills/pick-ui-library]:
1. **A library already in `package.json`.** Don't churn dependencies unasked.
2. **Foundations, restyled:** shadcn/ui (code copied into the repo) on Base UI or Radix primitives, for dialogs, popovers, menus, selects, tabs and tooltips.
3. **Specialists** for components that are hard to get right:

| Need | Library | What a hand-rolled version gets wrong |
| --- | --- | --- |
| Toasts | Sonner. Error and actionable toasts persist until dismissed and never take focus; others stay at least 5 s, scaled by length, and pause on hover or focus. At most 3–4 visible, and any toast action also exists elsewhere [articles/wai-aria-apg/alert; articles/component-gallery/toast] | Pile up or vanish; no stacking or hover-expand |
| Drawers / bottom sheets | Vaul | No drag; no flick to close |
| ⌘K command menu | cmdk | Breaks with the keyboard |
| Animated numbers | NumberFlow | Digits jump instead of rolling |
| OTP inputs | input-otp | — |
| Long lists (1k+ rows) | Virtuoso | — |
| Drag and drop | dnd kit | — |
| Charts | recharts (Liveline for live streams) | — |
| Animation (springs, layout, exit) | motion | — |
| Shared state / class names / variants / theme | zustand / clsx / cva / next-themes | — |

4. **Design components** (Magic UI, Aceternity, RareUI, 21st.dev) only for the single standout moment. Install through the CLI or registry so the code lives in the repo and can be edited.
5. **AI-product states** come from shadcn's chat components; see §4a. Beautiful UI is the visual reference.
6. **Mobile vs. web component thresholds** (`references/patterns/mobbin-shipped-apps.md`, distilled from 59 Mobbin Glossary guides):
   - **Bottom `Tab Bar` (`3–5` items max):** primary mobile destinations only; `>5` sections → `Drawer` / rail. Never put infrequent settings in a Tab Bar.
   - **`Bottom Sheet` vs. `Action Sheet` vs. `Context Menu`:** `Bottom Sheet` (`Vaul`) for supplementary context/filters (`peek` detent = no scrim; `expanded` = scrim + `scale(0.94)` root recession + explicit `×` button); `Action Sheet` for `3–5` quick mobile choices + separated `Cancel`; long-press `Context Menu` only for secondary item actions (`scale(1.03)` lift + `blur(16px)`).
   - **`Segmented Control` (`2–4` equal views, instant switch)** vs. `Select`/`Combobox` (`5+` choices); **`Stepper` (`1–10`)** vs. **horizontal tick-ruler scrubber** (bounded mobile numeric ranges without popping OS keyboard) vs. numeric `<input>`.
7. **Menus, comboboxes, tooltips & canvas micro-physics** (`TimothyVang/frontend:reference/youtube/icRjQePEa_A/`, `5t8dh3DSdBk`, `b00sgRR_Vc0`, `6DSW1rN-ZV4`, `_RHiFAxISuM`):
   - **Nested submenus:** implement a **diagonal pointer-to-submenu safe triangle** (or hover-intent hysteresis) — never close a submenu on bare `onMouseLeave` while the pointer travels diagonally toward submenu rows. Anchor `transform-origin` to actual opening direction (`top left` down-right, `top right` down-left), autoscroll arrow navigation with top/bottom viewport padding (non-looping bounds), and unwind nested menus one layer per `Escape`.
   - **Multi-select comboboxes / label pickers:** auto-focus the filter input on open and group selected items at the top initially, **freezing row order while open** so accidental clicks undo in place; regroup selected items to the top only after close and reopen.
   - **Universal icon tooltips & delay tiers:** every icon-only button gets an accessible label + tooltip (with shortcut hint). First hover waits (`~500–1000 ms`: shorter on unfamiliar action icons, longer on daily sidebar chrome); roving across neighbors opens in `0 ms` with `0` motion.
   - **Dual-affordance pane splitters (`icRjQePEa_A`, 09:48–10:22):** resizable sidebar/inspector rails expose both drag-to-resize (`ew-resize` / `col-resize`) and click-to-collapse, with a two-line hover tooltip (`Drag to resize` / `Click to collapse [`) and a toggle icon whose geometry morphs to match collapsed vs expanded state.
   - **Rich-text, chat & shortcut disambiguation:** `@`-mention popovers stay open while arrowing inside the query token and close on token exit; `Enter`-to-send composers invert `Enter` to newline inside code blocks and active IME compositions (`isComposing`); pages mixing single-letter shortcuts (`J`/`K`/`L`) with an unfocused primary input buffer non-urgent shortcuts `150 ms` and redirect multi-character bursts into the focused input.
   - **Canvas & spatial editors (Figma patterns):** hit-test active selection bounds before topmost z-order layers on drag start; hide selection outlines during active arrow-key nudging; clamp/re-center out-of-bounds paste to the visible viewport; cap selection/undo history in a bounded ring buffer; never gate primary contextual triggers behind cursor-speed thresholds (use safe-polygon corridors + short overshoot timers).
