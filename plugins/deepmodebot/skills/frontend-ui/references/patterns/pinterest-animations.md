# Motion techniques & anti-patterns from 193 animated UI pins

Distilled from 193 animated pins grouped by UI role, mapped to `references/playbook/05-motion.md` (§5) and `references/playbook/03-ai-tells.md` (§3). Raw clips live in optional `TimothyVang/frontend:reference/screens/pinterest/`.

## Button and press feedback

- **State-to-state button morphs (§5):** `Submit → loading dots → ✓ Success → reset`, `Refresh pill → circular spinner → pill`, `Download arrow → bend → ✓ Complete`, `Send → plane flies → ✓ Sent`, `+ button → list → sheet → toast`, or small button morphing into a card container. Keep the wipe inside the button's own box; reserve confetti/bursts strictly for rare first-success moments.
- **Reusable hovers (≤200 ms `ease`, transform/opacity-only):** fill slide via `::before` child element, subtle lift, arrow chip nudge, centre-out fill contrast flip, offset shadow slide, caret blink + sliding arrow.
- **Press & toggle feedback:** `scale(0.97)` or subtle 3D card tilt on press; `100–150 ms` checkbox/radio/toggle/heart pop; sliding toggle knob + icon swap (`sun ↔ moon`) with springs for reversible controls; long-press filling radial arc ripple hinting toward the outcome before release.
- **Anti-patterns to avoid (§3/§5):** animating `width` to expand an arrow dot into a pill (use `clip-path`/`transform` instead); slow `600 ms` hover morphs; keyframed gradient sparkles, travelling border lights, or neon/purple glow pulses on idle controls; low-contrast neumorphic inset shadows; playful mascot pop-ups on frequent hovers.

## Loaders and progress

- **Determinate state-to-state loaders (§5):** `'Preparing' dashed card → flip to 'All set'`, liquid fill morphing into brand mark, robot eyes → dot loader → green active state. Show clear state progression rather than endless spinners.
- **Linear constant-motion loaders (keep moving under reduced motion):** thin progress bar, arc spinner, undulating thin line, sequential 3-dot fade or staggered bounce (`30–80 ms` steps), subtle location pulse.
- **Rare-wait delight only:** mascot/character walking a progress bar, liquid slosh, playful icon loops; never pair with full-screen background color cycling or heavy 3D rotating cubes.
- **AI & brand tells (§3):** breathing/wobbling AI orbs and horizon light flares belong *only* while actively generating; glitch scanline intros are brand-only, not product UI.

## Page and screen transitions

- **Product transitions (§5):** short-distance transitions; sequenced whole-view crossfades over changing media with ~`2 px` blur; sheet slide-ups on drawer curve `cubic-bezier(0.32, 0.72, 0, 1)`; spatial origin expansions (`Chats` pill → messages, `Airbnb` search → listing, circular dot reveal → onboarding, swipe-up → full-screen video); state-to-state collapse (card → prompt).
- **Anti-patterns:** 2–4 s full-screen preloaders (`Suit` mask, striped wipes, scatter-then-type) that block time-to-legible; marketing promo-reel hard cuts, kinetic poster type, and 3D tilted hero sequences copied into product UI.

## Cards and lists

- **Shared-element & morph transitions (§5):** list/product card → detail view via Motion `layoutId` or View Transition; card expanding into fanned photo stack or home-screen widget; stacked cards folding as accordions via `interpolate-size` / `::details-content`; sent chat message rising out of composer.
- **Carousels & swipes:** spring physics for draggable carousels (centre card scales up, neighbours dim) and Tinder-style card swipes using momentum projection (`pos + project(v)`).
- **Property decoupling & progressive enhancement:** let background color and foreground object finish on independent curves; gate scroll-driven card rises as progressive enhancement; stagger avatar/step entrances (`30–80 ms`).
- **Anti-patterns:** glass assistant cards drifting over purple gradients (§3); floating orb backgrounds behind scrollable dashboards; copying rotating 3D device mockup reels into app chrome.

## Menus and drawers

- **Spatial origin & morphs (§5):** search icon expanding into input → dropdown → collapsing to origin; avatar/`+` pill or tab-bar dot unfolding into an icon toolbar; two pills merging into an expanding card (Dynamic Island style) with spring physics; timer widget morphing into list → card; chat chips expanding into a list sheet.
- **Navigation & choreography:** active bubble sliding inside a notched tab bar (~`300 ms` `ease-in-out`, on-screen move); radial share icons fanning out on a `30–80 ms` stagger with light spring overshoot; voice-chat avatar grid collapsing into a stacked pill and expanding back; rotary dial menus using draggable springs.

## Data and number animation

- **Digits & live feedback (§5):** roll digits (`NumberFlow`) instead of swapping counters (`8 → 6`, live stats); scrubbers/sliders update color and expression from the first pixel of drag; shuffle dashboard tiles with Motion `layout`, never `width`/`height`; modals enter/exit in `200–300 ms`.
- **Stability rule:** data the user is actively reading (charts, fitness/analytics panels) never re-animates on refresh; keep theme wipes crisp and ambient globes out of Operate surfaces.

## Onboarding and illustrations

- **Where delight fits (§5 rare flows):** mascot/character transitions (blob → welcome screen, habit tick celebration, mood picker), line-art draw-in, staggered pastel sticker pops (`30–80 ms`), step-by-step form choreography, and brand logo squash/stretch morphs.
- **Out of scope for product UI:** fast hard-cut promo reels, ambient particle intros, exploded 3D hardware showcases, and looping 3D scene carousels belong to marketing/video (§5a), not everyday app surfaces.
