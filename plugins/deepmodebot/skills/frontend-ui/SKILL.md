---
name: frontend-ui
description: "UI/UX rules before writing or reviewing interfaces: components, layout, typography, OKLCH color, motion, motion graphics, a11y, copy, and agent/chat UI."
metadata:
  as-of: "2026-11-25"
---

# Frontend UI/UX rules

Explore the project first (`package.json`, existing components, tokens), then load the routed `references/` file below. Optional citations prefixed `TimothyVang/frontend:` point at a private archive (skip if inaccessible; if cloning for evidence, shallow-clone into gitignored `.scratch/refs/frontend` and never commit from it).

## Core principles

- **Commit to a positive aesthetic first (`references/playbook/00-art-direction.md`).** Banning clichés without picking an archetype produces sterile grey wireframes. Choose one concrete archetype (Precision Workbench, Warm Editorial, High-Density Swiss, Tactile Consumer, or Spatial Canvas), one non-generic layout composition, and one OKLCH surface/lighting formula before writing CSS.
- **Defaults are tells; bans are defaults, not laws.** Every visible choice serves this brief; explicit brief words override §3 tells.
- **Surface mode first:** **Operate** (app UI, dashboards, settings, agent console — most surfaces) uses precision, hierarchy, and restraint; **Persuade** (landing, pricing, onboarding hero) gets bold display scale and one standout moment.

## Always apply

- **Art-direction & starter CSS kits before code:** Pick an archetype from `00-art-direction.md` and seed tokens from `assets/themes/{workbench,editorial,swiss,tactile,canvas}.css` + `assets/themes/layouts.css` (4 OKLCH surface tiers, 3 text tones, semantic roles, curated font pairing, non-generic layout).
- **Border budget, lighting & optical craft:** Max 1 bordered container depth per region; separate groups with spacing, alignment, or hairline dividers. Dark surfaces get top-edge light (`inset 0 1px 0 oklch(1 0 0 / 0.07)`); light surfaces get layered OKLCH shadows; sticky bars get frosted translucency. Enforce optical micro-craft (no near-tangents, `text-box: trim-both cap alphabetic`, exact concentric radii, deliberate product-shot bleeds) per `06b-media-icons-charts.md` and `06c-product-shots-craft.md`.
- **Specialists:** `Sonner` (toasts), `Vaul` (drawers), `cmdk` (⌘K), `NumberFlow` (animated digits), `input-otp` (OTP), `Virtuoso` (long lists), `dnd kit` (drag/drop), `motion` (animation), `recharts` (charts), `zustand` (state), `cva + clsx` (variants), `next-themes` (theme).
- **Agent UI (shadcn chat contracts):** `MessageScroller` (yields on scroll-up; never hand-roll stick-to-bottom), `Message` + `Bubble`, one `TraceLine` per action inside `Trace` (never hand-roll "Thinking..." collapsibles), state-matched verbs (`Running` → `Ran` / `Failed to run`), risk-tiered approval prompts *outside* the trace (proposal naming target, effect, reversibility; one decision per prompt), persistent `Stop` beside live steering `Send` (disconnect reconnects, never stops), task list for delegated work, streaming Markdown healer (`Streamdown`).
- **OKLCH color & hierarchy:** Tinted brand neutrals, role tokens only (no raw `bg-zinc-*` or hex), equal-lightness/chroma status colors, fill-hue text on colored fills, dark mode as compensated token remap. Three text tones (weight/color before size), one solid primary per view, `@container` over viewport breakpoints, max one standout moment per page.
- **UI motion:** `ease-out` enter/exit, `ease-in-out` on-screen moves, never `ease-in`; springs (`visualDuration` + `bounce`, default `0`, max `0.4`) for reversible controls; View Transitions for discrete changes only; Motion `layout` instead of `width`/`height`; 100–300 ms (exits ~20% faster); `scale(0.97)` press, `scale(0.95)` enter (never `scale(0)`), directional trigger `transform-origin`; diagonal safe-triangle submenus; `transform`/`opacity` only (no `transition: all`); reduced motion = fade; zero animation on ⌘K/Escape/100+/day actions; no "Christmas tree" UI.
- **Motion graphics (rendered video):** Follow `references/playbook/05a-motion-graphics.md` (not UI caps): pure function of `t` + single timeline file, director's brief with Banned list + beat-map/stills gate, holds `0.3 s/word + 0.5 s` (landed text still), beat cuts, −14 LUFS audio, real product UI only, timestamped critique notes.
- **Copy & quality floor:** Sentence case, user vocabulary, result-naming CTAs, `Verb + Noun` destructive actions, actionable errors, `…` in-progress. Responsive (`1440` & `390 px`, zero overflow), `:focus-visible`, WCAG AA, never `#000000`/`bg-black` dark surfaces, non-circular checkboxes, labeled icon buttons with roving tooltips, deferred combobox re-sort, `tabular-nums` on timers/lists/columns, `Intl.Segmenter` + middle-truncation, 44 px touch targets, all reachable states.
- **Audit, capture, motion diff & critique (2-round gate):** Never ship round 1. Run `python -B <this skill>/scripts/ui_audit.py <target>` + `--browser-snippet` at `1440×900` and `390×844` (plus `scripts/motion_diff.py <ref> <cand>` when cloning animations), pass screenshots to a clean-context visual critic against `02-review-rubric.md`, fix top findings, and re-verify.

## Route by task

| Task | Read |
| --- | --- |
| Art direction, archetypes, starter CSS theme/layout kits | `references/playbook/00-art-direction.md`, `assets/themes/layouts.css`, `references/playbook/06-typography-layout.md`, `references/playbook/06a-color.md` |
| Icons, imagery, SVG restraint & data visualization | `references/playbook/06b-media-icons-charts.md` |
| Product UI shots, hero framing, optical micro-craft & visual fault fixes | `references/playbook/06c-product-shots-craft.md` |
| Full workflow, review rubric, AI-tell audit | `references/playbook/01-workflow.md`, `references/playbook/02-review-rubric.md`, `references/playbook/03-ai-tells.md` |
| Component picks, shadcn theming, specialist behavior | `references/playbook/04-components.md`, `references/patterns/live-demos.md` |
| Chat, agent activity, tool calls, A2UI v1.0, approvals | `references/playbook/04a-agent-ui.md`, `skill://deepmodebot/references/techniques/gen-ui.md` |
| Shipped app layouts & component selection matrix | `references/patterns/mobbin-shipped-apps.md`, `references/patterns/pinterest-patterns.md` |
| UI animation, choreography, gestures, perf, motion vocabulary | `references/playbook/05-motion.md`, `references/patterns/mobbin-animations.md`, `references/patterns/pinterest-animations.md`, `references/patterns/motion-clips.md` |
| Motion graphics, launch/promo video, Remotion/HyperFrames | `references/playbook/05a-motion-graphics.md`, `references/patterns/motion-graphics.md`, `skill://deepmodebot/references/techniques/video-forensics.md` |
| Copy, microcopy, CTAs, errors | `references/playbook/07-copy.md` |
| Accessibility, ARIA, forms, mobile baseline, edge cases | `references/playbook/08-quality-floor.md`, `references/playbook/02-review-rubric.md` |
| Steering UI agents and revision passes | `references/playbook/09-steering-agents.md`, `references/playbook/01-workflow.md` |
