# Agent-driven UI design workflow (2026)

Run this ordered workflow when designing or restyling a UI with an agent. Each step ends on a **Done when** gate. All visual craft rules, positive archetypes, OKLCH formulas, motion limits, and mechanical audits live in `skill://frontend-ui` (single source of truth; it wins any conflict).

## Choose the design surface

- **Default (works in every coding session): Code-first tokens + real browser.** Commit to an Art Direction Brief (`skill://frontend-ui/references/playbook/00-art-direction.md`), build a live design-system route or token sheet in code first, audit with `ui_audit.py`, and iterate visually on `1440×900` + `390×844` browser screenshots.
- **Optional visual canvas (when installed):** **Paper + MCP**, **Claude Design + MCP**, or **Google AI Studio Build** for exploring design systems before code export. Skip cleanly when unavailable; never block on external design tools.
- **Agent-driven dynamic UI surfaces: Google A2UI `1.0`** (`a2ui.org`): emit declarative A2UI JSON (`catalog.json` + `updateComponents` + `@path` `updateDataModel` + `action` events), never model-authored HTML/JS (`skill://deepmodebot/references/techniques/gen-ui.md`).

## Core principles

- **System before pages:** define tokens (4 OKLCH surface tiers, 3 text tones, semantic status colors, font pairing, spacing, radius, elevation) before building screens so every view stays cohesive and dark mode is one token remap.
- **Never design from a blank negation list:** pick one concrete archetype and composition from `skill://frontend-ui/references/playbook/00-art-direction.md`, then adapt it to the product's taste.
- **Never ship round 1:** first drafts are timid or cluttered; plan for a mechanical audit + skeptical screenshot critique + Round 2 polish pass.

## Ordered workflow

### Step 1: Collect concrete references
1. Pull shipped patterns from `skill://frontend-ui/references/patterns/mobbin-shipped-apps.md` and `mobbin-animations.md` (or inspect live reference sites at `1440×900` and `390×844` for real computed CSS curves, type scale, and spacing).
2. With no external reference, pick one archetype from `skill://frontend-ui/references/playbook/00-art-direction.md` and write concrete anti-goals.
- **Done when:** you have a written Art Direction Brief naming archetype, OKLCH surface/accent seeds, font pairing, layout composition, and anti-goals.

### Step 2: Establish the token & component foundation
- Define tokens and core states (button primary/secondary/ghost, input, badge, surface/raised/sunken containers, empty/loading/error states) in one token stylesheet or design-system canvas before building product pages.
- Retheme base primitives (`shadcn/ui` or `shadcn-svelte`) radius, palette, and typography immediately; never leave default library styling.
- **Done when:** all tokens use semantic roles (zero raw hex/Tailwind grays in components) and core controls share one cohesive visual system.

### Step 3: Build the anchor screen with real content
- Build the primary view (landing hero + live proof for Persuade; main workbench for Operate) using realistic domain data and a non-generic layout (`5fr/7fr` split, master-detail, or borderless KPI strip + flat ruled rows).
- Enforce the border budget (`<= 1` bordered container depth), directional dark top-rim lighting or layered light OKLCH shadows, and `tabular-nums` on numbers.
- **Done when:** the anchor view renders with real content and zero placeholder boxes or stock lorem ipsum.

### Step 4: Mechanical audit + visual critique + Round 2 polish
1. Run `python -B <frontend-ui skill>/scripts/ui_audit.py <target>` (static gate) and its browser computed-style audit snippet at `1440×900` and `390×844`.
2. Inspect both screenshots skeptically against `skill://frontend-ui/references/playbook/02-review-rubric.md`: check 1-second focal hierarchy, border count, typographic contrast, surface depth, mobile overflow, and chip/badge clutter.
3. Strip non-essential chrome, sharpen hierarchy/elevation, flow token fixes back into the shared design system, and re-capture screenshots.
- **Done when:** zero mechanical audit failures, zero console errors, clean `1440 px` + `390 px` screenshots, and Round 2 fixes visibly verified.

### Step 5: Expand remaining flows & add one standout moment
- Build secondary views (auth, settings, detail, empty/error states) strictly from the shared token system; keep at most **one** restrained standout moment per Persuade page (never stacking decorative gimmicks, glows, or sound/confetti toys onto Operate surfaces).
- **Done when:** every flow shares identical tokens, typography, spacing, and radii with all reachable states verified live.

## Curated component libraries

Prefer libraries already in `package.json`. For React/Tailwind stacks, compose accessible primitives and specialists (see `skill://frontend-ui/references/playbook/04-components.md`):

| Library | Use for |
| --- | --- |
| `shadcn/ui` (Base UI / Radix) / `shadcn-svelte` | Restyled accessible foundation (dialogs, popovers, menus, selects, tabs, chat blocks) |
| `Sonner` / `Vaul` / `cmdk` / `NumberFlow` | Toasts, mobile-grade drawers, ⌘K command menus, rolling tabular digits |
| `motion` / `Motion Primitives` | Springs, layout transitions, restrained morphs |
| `Virtuoso` / `dnd kit` / `recharts` | Virtualized lists, drag-and-drop, charts |
| `prompt-kit` / shadcn chat blocks | Agent threads, traces, code blocks, approval cards (`04a-agent-ui.md`) |
| `Cult UI` / `Coconut UI` / `Skipper UI` / `Watermelon UI` | Selective registry inspiration for a single Persuade standout moment only (always restyle to project tokens) |
