## 5. Motion

**Easing:**

| Motion | Easing |
| --- | --- |
| Enter or exit | `ease-out` (`cubic-bezier(0.23, 1, 0.32, 1)`) |
| Moving or morphing on screen | `ease-in-out` (`cubic-bezier(0.77, 0, 0.175, 1)`) |
| Drawers | `cubic-bezier(0.32, 0.72, 0, 1)` |
| Hover | `ease` (`<= 160 ms` on frequent buttons) |
| Constant motion | `linear` |
| Draggable, throwable or reversible mid-flight | spring (`visualDuration` + `bounce`) |

- Never use `ease-in` for UI. Use strong curves, never improvised approximations.
- **Springs:** specify `{ type: "spring", visualDuration, bounce }` (or CSS `linear()` baked from them), never raw stiffness/damping/mass. `bounce: 0` default, `0.15` brisk, up to `0.3` for momentum gestures, never `> 0.4`. Fire follow-up work (focus, unmount) at perceptual duration, not settle.

**Duration:** Micro-interactions `100–150 ms`; tooltips/dropdowns `150–250 ms`; modals/drawers `200–300 ms`. Keep UI motion `< 300 ms` (frequent buttons `<= 160 ms`); exits ~20% faster than entrances. Choreography: `30–80 ms` steps, `< 300 ms` total, never blocking interaction. Page transitions cap *time to legible* (~360 ms), sequencing whole-view cross-fades over short distances.

**Details:**
- `scale(0.97)` on `:active`; enter from `scale(0.95)` + opacity (never `scale(0)`); origin-aware popovers (`transform-origin: var(--transform-origin)`).
- Only the first tooltip in a group gets a delay; later ones open instantly. Animate a child element to avoid hover flicker.
- Subtle blur (`< 20 px`; `2 px` for crossfades) smooths state changes. Decouple curves when position, scale, and radius finish differently.
- **Interruptible = velocity-preserving:** springs carry velocity mid-flight; never use CSS keyframes for interactive state.
- **Gestures:** track pointer 1:1 keeping grab offset + velocity history; ~10 px drag slop then axis lock; highlight on `pointerdown`, commit on `pointerup` (destructive only on release). Choose release target by **momentum projection**: `project(v) = (v/1000)·0.998/(1−0.998)`. Rubber-band edges; recognize competing gestures in parallel; no double-tap handlers where single taps matter; use Vaul over hand-built sheets.
- **Mobile tactile patterns (`references/patterns/mobbin-animations.md`):** morph dismissed sheet CTAs into docked floating capsules; expand `48–56 px` mini-bars via `layoutId`; keep `0` scrim at `peek`/`half` sheet detents and scale root (`0.94`) continuously past 50%; couple card-swipe `dx` to tilt (`dx * 0.04deg`); `rotateY(180deg)` (`backface-visibility: hidden`) for card flips; `600–900 ms` press-and-hold radial commits; explicit `transition-property` lists (`color, background-color, border-color, transform, opacity`).

**When to animate (frequency gate):**

| Frequency | Motion |
| --- | --- |
| 100+ times/day; keyboard-initiated (Escape-to-close, ⌘K) | None (verify by hand — agents often animate Escape) |
| Tens of times/day | Minimal (`<= 160 ms`) |
| Occasional (dialogs, toasts) | Standard |
| Rare (onboarding, first success) | Delight allowed |

- Animate in response to user actions to show what changed; max one ambient moment. Maintain spatial consistency (popover ↔ trigger, sheet ↔ edge) and match strength to importance.
- **State-to-state:** morph one container while cross-fading with blur; roll digits (`NumberFlow`) rather than swapping; keep each step legible (`button → loading → done`). Spend animation budget where users wait; never re-animate data on refresh.
- **Reduced motion:** gentler, not zero — keep opacity/color, set `--slide-distance: 0` under `prefers-reduced-motion: reduce`. **Exception:** spinners/progress keep moving subtly (decorative shimmer/glows stop). Gate hover effects with `@media (hover: hover) and (pointer: fine)`.
- **Chat & adaptive motion:** sent message rises out of composer (`opacity` + `translateY`); tool-detail panel grows from its trace row; adaptive updates highlight only the changed region.

**Performance & platform first:**
- Animate `transform` and `opacity` only; never `transition: all`. Per-frame values go to `ref.current.style`, not React state. Don't animate inherited CSS variables; add `will-change` only after observing glitch.
- Layout changes (reorder, accordions, expanding trace rows) use Motion `layout`/`layoutId` or View Transitions, never `width`/`height` (scope `layout` narrowly during streaming).
- Prefer CSS first: `@starting-style` + `transition-behavior: allow-discrete` for dialogs/popovers; `interpolate-size: allow-keywords` / `::details-content` for accordions.
- **View Transitions (discrete changes only — non-interruptible):** add `::view-transition { pointer-events: none }` or element-scoped `el.startViewTransition()`; trigger in React only via `startTransition` / `<ViewTransition>` (name persistent chrome so it stays put; use `addTransitionType` for direction); keep `width: fit-content` on named elements; hide stale old snapshots for live/streaming content.
- **Scrolling:** `overscroll-behavior: contain` on nested scrollers; `scroll-behavior: smooth` only under `prefers-reduced-motion: no-preference`; `scrollbar-color` with `light-dark()` (never `thin` on primary scrollers); prefer `scroll-state()` / scroll-driven animations over JS scroll listeners.
- **Feedback & QA:** hover/focus raise contrast; disabled is 50% opacity with no shadow. End every motion pass with a DevTools Animations 10–25% slow-motion scrub and collective full-video playback check.
