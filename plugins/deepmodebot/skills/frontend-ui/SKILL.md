---
name: frontend-ui
description: "UI and UX rules for building, restyling, or reviewing interfaces: components, layout, typography, color, motion and animation, motion graphics, accessibility, copy, and chat or agent UI, with patterns learned from shipped apps. Use before writing or reviewing UI code."
metadata:
  as-of: "2026-11-12"
---

# Frontend UI/UX rules (bundled)

Distilled from the optional private reference repo `TimothyVang/frontend` (`7c57c43`). The bundled playbook and pattern files under `references/` stand on their own for general UI/UX work; optional deep-dive paths prefixed `TimothyVang/frontend:` below exist only when you have access to that private repo.

Paths written `TimothyVang/frontend:<path>` and bracketed citations like `[youtube/...]` point at that repo's evidence (transcripts, clips, screenshots, vendored skills). If `gh` can read it, shallow-clone it into the project's self-ignored scratch folder (`gh repo clone TimothyVang/frontend .scratch/refs/frontend -- --depth 1`, about 300 MB) and never commit from it: deepmodebot keeps every write inside the project root, and `.scratch/` holds a `.gitignore` of `*`. Otherwise skip the evidence; the rules below stand alone.

## Playbook sections (read the one the task routes to)

- `references/playbook/01-workflow.md`
- `references/playbook/02-review-rubric.md`
- `references/playbook/03-ai-tells.md`
- `references/playbook/04-components.md`
- `references/playbook/04a-agent-ui.md`
- `references/playbook/05-motion.md`
- `references/playbook/05a-motion-graphics.md`
- `references/playbook/06-typography-layout.md`
- `references/playbook/06a-color.md`
- `references/playbook/07-copy.md`
- `references/playbook/08-quality-floor.md`
- `references/playbook/09-steering-agents.md`

## What the images and motion clips taught (text)

- `references/patterns/mobbin-shipped-apps.md`: layout patterns from shipped apps
- `references/patterns/pinterest-patterns.md`: patterns and AI tells from 341 popular UI pins
- `references/patterns/pinterest-animations.md`: 193 animated pins as motion techniques, by type
- `references/patterns/motion-clips.md`: what every reference-talk clip shows, as motion vocabulary
- `references/patterns/live-demos.md`: Sonner, Vaul, cmdk, NumberFlow behaviour
- `references/patterns/motion-graphics.md`: engines, stack, lessons for rendered video

## Playbook intro

General UI/UX rules distilled from shipped-app patterns and design references. Use the bundled `references/` files directly; optional `TimothyVang/frontend:*` citations link deeper evidence when that private repo is available.

Leading idea: **defaults are tells.** Every unexamined default (library styling, stock layout, generic motion) reads as AI-generated. Every visible choice must be one made *for this brief*.

**Bans are defaults, not laws.** The brief's explicit words always win, even when they ask for something listed in §3. [github/INDEX tensions; anthropic frontend-design]

**Decide the surface mode first; ambition follows from it.** [github/pbakaus-impeccable; github/Leonxlnx-taste-skill]

| Mode | Surfaces | How it expresses the brand |
| --- | --- | --- |
| Operate | App UI, dashboards, settings, the agent console | Precision and restraint |
| Persuade | Landing, pricing, onboarding hero | Bold work, including the one standout moment |

Most application and agent-console surfaces are *Operate*.

---

## Rules (always apply)

Every visible UI choice must be made for this brief. Defaults are tells: unmodified library styling, stock layouts and generic motion read as AI-generated.

Prefer retrieval-led reasoning over pretraining for UI work. Explore the project first (`package.json`, existing components, tokens), then load the routed source below.

## Always
- **Pick the surface mode.** Operate surfaces (the app, the agent console, settings) express the brand through precision and restraint. Persuade surfaces (landing, pricing) get the bold work. The brief's explicit words override any rule here.
- **Plan before code.** Write a token plan: OKLCH seed colors with role names, typefaces and their roles, and a layout concept with an ASCII wireframe. Revise any part that would fit any similar page. Where `frontend-design` says hex, `references/playbook/06a-color.md` overrides it.
- **Compose, don't hand-roll.** Use the library already in `package.json` first. For React apps, use shadcn/ui restyled on Base UI or Radix (for SvelteKit — `skill://deep-stack`'s default — use `shadcn-svelte` or equivalent accessible primitives with the same token and quality rules), plus:

  | Need | Library |
  | --- | --- |
  | Toasts | Sonner |
  | Drawers | Vaul |
  | ⌘K | cmdk |
  | Animated numbers | NumberFlow |
  | OTP inputs | input-otp |
  | Long lists | Virtuoso |
  | Drag and drop | dnd kit |
  | Animation | motion |
  | Charts | recharts |
  | State | zustand |
  | Variants | cva + clsx |
  | Theme | next-themes |

- **Agent UI uses shadcn's chat components:**
  - Threads: `MessageScroller`, which follows the reply but yields when the user scrolls up.
  - Turns: `Message` + `Bubble`.
  - Agent activity: one `TraceLine` per action inside a `Trace`.
  - Status words match the state (Running → Ran / Failed to run).
  - Tool approvals: a prompt *outside* the trace, tiered by risk (read-only tools run unprompted), phrased as a proposal stating target, effect and reversibility. One decision per prompt.
  - Stop stays visible for the whole run, beside a working Send (messages sent mid-run steer the agent). A dropped connection reconnects; it never acts as a stop.
  - Delegated work gets a task list with per-task status and a jump to whatever is awaiting the user.
  - Streaming Markdown goes through a renderer that heals unterminated syntax (Streamdown).
  - Never hand-roll "Thinking..." collapsibles or a stick-to-bottom div.

- **Retheme shadcn.** Change radius, palette and type before shipping anything.
- **Color through tokens:**
  - Author in OKLCH. Components use only role tokens (`--bg-subtle`, `--fg-muted`, `--border-strong`); no raw `bg-zinc-*` or hex.
  - Neutrals are tinted with the brand hue.
  - Status colors share lightness and chroma.
  - Text on a colored fill uses that fill's hue.
  - Dark mode is a token remap.
- **Hierarchy:**
  - Three text tones; weight and color before size.
  - One solid primary per view.
  - Separate things with spacing before borders.
  - Lay components out with `@container`, not viewport breakpoints.
- **One standout moment per page.** Keep everything around it quiet.
- **Motion:**
  - Easing: ease-out to enter or exit; ease-in-out to move on screen; never ease-in. Anything draggable or reversible uses a spring (duration + bounce; bounce 0 by default, never above 0.4).
  - View Transitions only for discrete changes (routes, filters, add/remove), because they can't be interrupted. Animate layout with Motion `layout`, never `width`/`height`.
  - Duration: 100–300 ms by size. Exits run about 20% faster.
  - Press: `scale(0.97)`. Enter from `scale(0.95)`. Origin-aware popovers.
  - Animate `transform` and `opacity` only, with no `transition: all`. Reduced motion means a fade, not nothing.
  - Gate motion by frequency. Anything keyboard-initiated (⌘K, shortcuts, Escape-to-close) or used 100+ times a day gets no animation.
- **Motion graphics (anything rendered to video)** follow `references/playbook/05a-motion-graphics.md`, not §5's UI timings:
  - Every frame is a pure function of `t`, with one timeline file.
  - Write a director's brief with a Banned list, and gate on a beat map plus stills before the full render.
  - Text holds 0.3 s/word + 0.5 s; landed titles stay still.
  - Cuts land on the beat; sound is mastered to −14 LUFS.
  - Show real product UI only.
  - Critique with timestamped notes, not scores.
- **Copy:**
  - Sentence case, the user's vocabulary.
  - A CTA names its result. Destructive actions use Verb + Noun.
  - Errors say what happened and how to fix it. In-progress labels end in `…`.
- **Quality floor:**
  - Responsive to mobile; visible focus; WCAG AA contrast.
  - Accessible names; 44 px hit areas.
  - Every reachable state: loading, empty, error, permission, disabled, optimistic, destructive.
- **Verify in a real browser.** Screenshots at compact and wide widths, a keyboard pass, every changed state. Never claim visual quality from code alone. Then run a skeptical critique against the `references/playbook/02-review-rubric.md` rubric (design quality, originality, craft, functionality).

## Route by task
Read the bundled `references/` file first. Paths prefixed `TimothyVang/frontend:` are optional private-repo deep dives available only if you have access to that repo.

| Task | Read (bundled first; optional private-repo deep dive) |
| --- | --- |
| Full workflow, AI-tell list, review rubric | `references/playbook/01-workflow.md`, `references/playbook/02-review-rubric.md`, `references/playbook/03-ai-tells.md` |
| New page, visual direction, color, typography | `references/playbook/06-typography-layout.md`, `references/playbook/06a-color.md`, `references/playbook/03-ai-tells.md` |
| Picking a component library or shadcn theming | `references/playbook/04-components.md`, `references/patterns/live-demos.md` (optional: `TimothyVang/frontend:.claude/skills/shadcn/SKILL.md`) |
| Chat, agent activity, tool calls, approvals, AI UX | `references/playbook/04a-agent-ui.md` (optional: `TimothyVang/frontend:reference/articles/ai-ux/_batch-ai-ux-guidelines.md`) |
| Seeing shipped layouts or motion vocabulary | `references/patterns/mobbin-shipped-apps.md`, `references/patterns/pinterest-patterns.md`, `references/patterns/pinterest-animations.md`, `references/patterns/motion-clips.md` |
| Building UI animation, choreography, gestures, perf | `references/playbook/05-motion.md`, `references/patterns/motion-clips.md` |
| Motion graphics, launch/promo videos, Remotion/HyperFrames | `references/playbook/05a-motion-graphics.md`, `references/patterns/motion-graphics.md` |
| Copy, microcopy, CTAs, error messages | `references/playbook/07-copy.md` |
| Reviewing UI, accessibility, keyboard, ARIA, mobile, edge cases | `references/playbook/02-review-rubric.md`, `references/playbook/08-quality-floor.md`, `references/playbook/03-ai-tells.md` |
| Steering UI agents and revision passes | `references/playbook/09-steering-agents.md`, `references/playbook/01-workflow.md` |
| Optional private evidence archive (if accessible) | `TimothyVang/frontend:reference/INDEX.md` (vendored skills, WAI-ARIA APG notes, Mobbin screenshots, channel transcripts) |
