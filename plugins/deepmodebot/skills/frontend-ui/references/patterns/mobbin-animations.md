# Mobile & Web Animation Lessons from Mobbin (86 Mobile Clips + 24 Live Sites)

Distilled on 2026-11-21 from **86 playable mobile animation clips** across Mobbin's `/discover/apps/ios/animations` and 8 unwalled mobile collections (*That was smooth!*, *Micro-interactions*, *Animation*, *Tactile*, *Loading…*, *bottomsheet*, *AI assistant*, *Critical States* — 877 screens total), plus **direct live DOM/CSS inspection of 24 Mobbin-featured Websites & Web Apps** at `1440×900` and `390×844`. Pair with `references/playbook/05-motion.md`.

## 1. Persistent spatial & CTA continuity (Mobile)

- **Sheet CTA → docked floating pill (`DoorDash` Cart & Bag, `3.03 s`):** When dismissing an item sheet after adding to cart, morph or match the full-width bottom `Add to cart · $3.95` button directly into a compact floating `View cart · 2` capsule anchored above the home indicator/tab bar. Shared brand fill and tabular badge count preserve continuity without a blocking confirmation modal.
- **Mini-bar → full-screen sheet (`Spotify`, `MD Vinyl`, `Poolsuite FM`, `Apple Music`):** Keep persistent audio, timer, or active-agent bars (`48–56 px` tall) docked directly above the bottom tab bar; expanding morphs the thumbnail (`40×40 px` → `280–320 px` hero via `layoutId`) while tinting the sheet backdrop from the artwork's dominant OKLCH hue.
- **Color-field & cell expansion (`How We Feel`, `Luma`, `Airbnb`):** Tapping a colored mood/category tile expands that tile's surface and hue into the detail view (`layoutId` / View Transition) instead of cutting hard to white and flashing back.
- **Guest-first onboarding choreography (`DoorDash` `2.37 s`, `OpenTable`):** Fan or stagger 3D/editorial preview cards once (`30–60 ms` steps, `<300 ms` total) above a pinned primary CTA (`Continue`) paired with a quiet secondary escape pill (`Browse first`).

## 2. Bottom sheets, detents & backdrop physics

- **Progressive scrim by detent (`Airbnb`, `Arc Search`, `Grok`, `Any Distance`):**
  - **Peek / half detent (`~38–45%` height):** **zero backdrop scrim** so maps, canvases, and lists underneath stay readable and interactive.
  - **Expanded detent (`~88–94%` height):** fade scrim (`oklch(0 0 0 / 0.35–0.5)`) continuously with drag progress past the midpoint; scale the underlying root screen down (`scale(0.94)`) with `12 px` top corners to signal modal depth.
- **Velocity-projected snap & rubber-band (`Vaul` / native sheet physics):** Project release velocity (`pos + project(v)`) to pick `peek`, `expanded`, or `dismiss`; rubber-band past the top detent rather than hard-clamping.
- **Sheet chrome:** Always pair the `36×4 px` top drag pill with an explicit `30–36 px` circular `×` close button for screen-reader and single-tap dismissal, and lock the primary footer CTA above `env(safe-area-inset-bottom)`.

## 3. Tactile, hardware-inspired micro-interactions

- **Tick-detent ruler scrubbers over mobile number keyboards (`Tonal`, `Ladder`, `Cash App`, `Rise`):** For bounded numeric inputs on mobile (weight, stake, target, duration), use a horizontal momentum-scrolled tick ruler (every 5th tick taller and higher contrast, live rolling readout via `NumberFlow`) instead of popping the OS keyboard.
- **3D card & pass flips (`Revolut`, `Phantom`, `Luma`, `Cash App`):** Reveal card numbers, QR codes, or ticket backs with a perspective `rotateY(180deg)` spring (`backface-visibility: hidden`) and subtle pointer/gyroscope specular highlight—never a separate settings page.
- **Press-and-hold progressive commit (`stoic.`, `Opal`, `Not Boring`):** For reflective or high-intent actions without a confirm dialog, fill a radial ring or background wash continuously from `pointerdown` (`600–900 ms`), canceling cleanly with a quick spring-back if released early.
- **Physical lip & active compression (`Poolsuite FM`, `Once`, `Not Boring Calculator`):** Give primary tactile controls a `1 px` top inner highlight (`inset 0 1px 0 oklch(1 0 0 / 0.18)`) plus a tight bottom shadow, compressing `scale(0.97)` or `translateY(1.5px)` on `:active` within `100–120 ms`.
- **Long-press lift + origin context menu (`Messages`, `Superlist`, `mymind`):** On long-press, lift the target card (`scale(1.03)`) above a `backdrop-filter: blur(16px)` layer and unfold the context menu from the touch corner (`transform-origin`), keeping the acted-on item sharp in view.

## 4. Lists, swipe gestures & mobile AI composers

- **Velocity-coupled card swipe (`Doji`, `Feeld`, `Spark Mail`):** Couple horizontal drag `dx` to subtle Z-rotation (`dx * 0.04deg`) and progressive action-icon reveal; commit only when projected momentum crosses threshold.
- **Inline completion without blocking multi-tap (`Superlist`, `Amie`, `Brilliant`):** Strike through text immediately (`120 ms`), collapse row height smoothly (`interpolate-size` / `layout`), and keep celebration particles strictly local and non-blocking so users can check off 5 items in a row at full speed.
- **Skeleton → content handoff (`mymind`, `Cosmos`, `Uber`, `Particle News`):** Match skeleton block geometry 1:1 to real cards; crossfade opacity (`150–200 ms`) when data lands and never re-animate rows during pull-to-refresh updates.
- **Mobile AI voice & chat choreography (`ChatGPT`, `Claude`, `Gemini`, `Perplexity` iOS):**
  - Pin the pill composer directly above `visualViewport` keyboard height; collapse horizontal starter-prompt chips on the first keystroke.
  - Voice mode transitions into a calm full-screen surface with **one reactive center waveform/orb** and oversized `56 px` bottom circular controls (`Mute`, `End`)—strip transcripts and tool chrome until the user exits or taps to inspect.

## 5. Production CSS motion & surface telemetry (24 live Mobbin sites/webapps)

Measured live across **Mercury, Ramp, Superpower, Linear, Stripe, Vercel, Raycast, Clerk, Resend, Attio, Luma, Contra, Monarch, VEED, Mintlify, Dovetail, Cosmos, Sana, Braintrust, n8n, Uniswap, Voicenotes, Ghost, and Antimetal**:

| Pattern observed live | Measured values | Shipped examples |
| --- | --- | --- |
| **Strong exponential `ease-out`** (entrances, sheets, morphs) | `cubic-bezier(0.16, 1, 0.3, 1)`, `cubic-bezier(0.22, 1, 0.36, 1)`, `cubic-bezier(0.23, 1, 0.32, 1)`, `cubic-bezier(0.19, 1, 0.22, 1)` at `200–300 ms` | Superpower, Sana, Mintlify, Antimetal, Contra |
| **Fast micro-state curve** (color, border, pill hover) | `cubic-bezier(0.2, 0, 0, 1)` or `cubic-bezier(0.4, 0, 0.2, 1)` at `150–200 ms` (`100 ms` press) | Attio, Ramp, Linear, Clerk, Monarch |
| **Controlled spring overshoot** (swaps, active pills) | `cubic-bezier(0.34, 1.56, 0.64, 1)` or spring `bounce: 0.15–0.25` | Uniswap |
| **Explicit `transition-property` list** (no `transition: all`) | `color, background-color, border-color, transform, opacity` | Ramp, Attio, Contra, Superpower, Monarch |
| **Frosted sticky chrome** | `backdrop-filter: blur(12px–24px) saturate(1.6–1.8)` over semi-transparent surface | Superpower, Monarch, Ramp, Attio, Luma |
| **Multi-layer OKLCH ambient shadow** | `oklch(0 0 0 / 0.01) 0 1px 2px, oklch(0 0 0 / 0.02) 0 2px 4px -1px, oklch(0 0 0 / 0.03) 0 4px 8px -2px` | Attio (11/24 sites ship `oklch`/`lab` CSS) |
| **`prefers-reduced-motion` rules** | Dedicated `@media (prefers-reduced-motion: reduce)` blocks (up to 17 rules/site) | Ramp (17), Superpower (10), Monarch (8), Attio (6), Mercury (4) |
