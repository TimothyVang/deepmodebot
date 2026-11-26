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
- `scale(0.97)` on `:active`; enter from `scale(0.95)` + opacity (never `scale(0)`). Anchor `transform-origin` and a `4–6 px` entry offset to the menu/popover's actual opening vector (`top left` down-right vs `top right` down-left when collision-flipped, never `50% 50%`), paired with diagonal **aiming-triangle** safe polygons on submenus (`icRjQePEa_A`, 09:00–09:44).
- **Familiarity-tiered roving tooltips (`icRjQePEa_A`, 00:00–00:05, 11:40–12:38):** only the first tooltip in a group gets a delay (`600–800 ms` on daily sidebar chrome, `100–200 ms` on unfamiliar status icons like `[*]`); roving to neighbours opens in `0 ms` with `0` slide motion. Animate a child element to avoid hover flicker.
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

- Animate in response to user actions to show what changed; max one ambient moment. Maintain spatial consistency (popover ↔ trigger, sheet ↔ edge) and match strength to importance. Never build a **"Christmas tree" UI**: keep surrounding chrome still so the one state-confirming target (e.g., a Kanban drop bucket) reads unmistakably; make any workplace Easter egg self-limiting with no `Play again` loop.
- **State-to-state & perceived-speed physics:** morph one container while cross-fading with blur; roll digits (`NumberFlow`) rather than swapping; keep each step legible (`button → loading → done`). Spend animation budget where users wait; never re-animate data on refresh.
  - **High-stakes submit floor vs routine optimism:** routine edits apply in `0 ms` optimistically (backed by retry queue + rollback); irreversible/payment submits enforce a `400–1000 ms` minimum spinner floor so instant completion never looks broken (`XqhduyTnEM8`).
  - **Progress & ETA honesty:** compute transfer ETAs over a **rolling `10 s` sliding window** (never `totalBytes / totalElapsed`), pace progress with goal-gradient acceleration or retrograde-moving ribs (feels ~11% faster), and cap optimistic progress at `<= 95%` until server ACK.
  - **Tap-toggle vs hold-push-to-talk & dictation budget:** tapping a record/capture toggle leaves media paused on stop; **holding** the key (`push-to-talk`) automatically restores the prior playback/view state on key release (`icRjQePEa_A`). For voice dictation, hide noisy partial ASR tokens that cause mid-sentence self-editing behind a minimal live pill + `<= 700 ms` release-to-text budget (`~200 ms` ASR + `200 ms` cleanup + `200 ms` RTT). Text carets blink at idle and stay **solid while typing** (`7DN3Ectm6UY`).
  - **UI sound & volume curves (when audio is present):** map volume sliders logarithmically (`gain = x^3` or dB, never linear amplitude); use ascending harmonious notes for connect/success, low dissonant tones for disconnect/failure, and scale duration inversely to event frequency (`_rFJutK25VU`, `fBdxtU6JN6M`).
- **Reduced motion:** gentler, not zero — keep opacity/color, set `--slide-distance: 0` under `prefers-reduced-motion: reduce`. **Exception:** spinners/progress keep moving subtly (decorative shimmer/glows stop). Gate hover effects with `@media (hover: hover) and (pointer: fine)`.
- **Chat & adaptive motion:** sent message rises out of composer (`opacity` + `translateY`); tool-detail panel grows from its trace row; adaptive updates highlight only the changed region.

**Performance & platform first:**
- Animate `transform` and `opacity` only; never `transition: all`. Per-frame values go to `ref.current.style`, not React state. Don't animate inherited CSS variables; add `will-change` only after observing glitch.
- Layout changes (reorder, accordions, expanding trace rows) use Motion `layout`/`layoutId` or View Transitions, never `width`/`height` (scope `layout` narrowly during streaming).
- Prefer CSS first: `@starting-style` + `transition-behavior: allow-discrete` for dialogs/popovers; `interpolate-size: allow-keywords` / `::details-content` for accordions.
- **View Transitions (discrete changes only — non-interruptible):** add `::view-transition { pointer-events: none }` or element-scoped `el.startViewTransition()`; trigger in React only via `startTransition` / `<ViewTransition>` (name persistent chrome so it stays put; use `addTransitionType` for direction); keep `width: fit-content` on named elements; hide stale old snapshots for live/streaming content.
- **Scrolling:** `overscroll-behavior: contain` on nested scrollers; `scroll-behavior: smooth` only under `prefers-reduced-motion: no-preference`; `scrollbar-color` with `light-dark()` (never `thin` on primary scrollers); prefer `scroll-state()` / scroll-driven animations over JS scroll listeners.
- **Feedback, motion-diff & QA:** hover/focus raise contrast; disabled is 50% opacity with no shadow. End every motion pass with a DevTools Animations 10–25% slow-motion scrub and collective full-video playback check. When rebuilding or matching a reference animation, run `python -B <frontend-ui skill>/scripts/motion_diff.py <ref.mp4> <cand.mp4>` to verify trigger offset `<= 0.08 s`, duration error `<= 0.08 s`, matching easing family, activity-curve `RMSE <= 0.08`, and `<= 0.5%` at-rest jitter.
