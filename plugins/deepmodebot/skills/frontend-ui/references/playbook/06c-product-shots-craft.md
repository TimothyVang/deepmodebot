## 6c. Product UI shots, 3-layer composition, optical micro-craft & rehearsal gates

Distilled from MIT-licensed `benjitaylor/skills` (`stageshow` v1.1.1, Copyright (c) 2026 Benji Taylor) and the 3-layer design workflow highlighted by AICodeKing (`https://youtu.be/30Qwke_HGaw`, 2026-11-24). Apply to hero product UI, feature cards, bento tiles, interactive demos, and optical polish on any real app.

### 0. Three-layer non-conflicting frontend stack (never two creative directors)
1. **Page Material Layer (`00-art-direction.md` + `assets/themes/*.css`):** ONE creative director owns ground, typography, OKLCH palette, and browser AI-tell checks (like Hallmark's material themes). Never stack two competing page-taste skills.
2. **Product Moment Layer (`stageshow` 7-step process):** (a) placement + separate `358 px` phone redesign (never a squeeze), (b) read real app tokens (colors, fonts, radii), (c) 3–5 beat story in 10–16 s with zero unexplained cursor moves, (d) start from a real gold exemplar, (e) 3–7 real strings with edge placeholder bars only, (f) cause-driven motion/loops ending where they began, (g) record full continuous video + pass hard `rehearsal_gate.py` before handover (`REHEARSAL.md`). Avoid the 5 AI demo failures: **Too much**, **Wireframe**, **Boxed**, **Flat**, **Bland**.
3. **Motion Polish Pass (`05-motion.md`):** explicit post-build transition audit — `ease-out` on enters/exits (never `ease-in` or plain `ease`), animate `transform`/`opacity` only (never `margin`/`width`/`height`), tighten frequent button hovers (`<= 160 ms`), zero motion on 100+/day controls.
4. **Watch the whole video together, not isolated frames:** a single good still hides digit pop-ins, font-load jumps, mid-flight flicker, bad pacing, and broken loop seams. Always inspect the complete recorded video end-to-end plus keyframes, and enforce `skill://deepmodebot/assets/e2e/rehearsal_gate.py verdict --strict` across rounds `v1..v25` before declaring done.

### 1. Framing product UI shots & heroes (never a boxed screenshot)
- **Bleed deliberately, never float with even margins:** on heroes and feature cards, crop **10–40%** of the hero window or phone off one or two edges so it fills `>= 2/3` of the stage. A whole window shrunk into a card with air on four sides reads as a pasted screenshot, not a product shot.
- **Crop only filler:** real words, active controls, cursors, and payoffs stay whole. A list, diff, or terminal may run one line past a bled bottom edge; remove placeholder buttons a crop would slice rather than slicing them.
- **Full gutter or well past (`>= 24 px`):** pick one gutter measured in the final visible crop and match it on every framed edge; never leave a sliver bleed (`< 24 px`) or stop a few pixels short.
- **The page is the ground:** on a white or dark page, do not wrap a hero window in a tinted backdrop plate; let the window sit directly on the page ground or bleed edge-to-edge.
- **Satellites straddle the edge:** a secondary object (receipt, notification, phone, detail card) straddles the hero's edge about half outside over chrome/margin — never covering key figures, never two twin cards of equal width stacked on one edge.
- **Fade crop over bottom filler only:** when a hard edge cuts awkwardly, dissolve only the window's bottom third via a CSS mask (`mask-image`) over filler — never a color overlay, never on focal content, never on sides.
- **`compact` is a redesigned composition:** at `358–390 px` mobile width, crop closer or drop/stack satellites at readable 1:1 type size — never scale down a desktop layout.
- **No fake headings in demos:** use `div` (never `h1`–`h6`) inside faux product illustrations so they never pollute the host page's document outline.
- **Set the `poster` frame first:** thumbnails, screenshots, and reduced-motion viewers see only the resting frame; compose it with the payoff already legible, never mid-transition.

### 2. Optical micro-craft floors
- **No near-tangents (`1–3 px` gaps):** align edges to the exact pixel or separate by `>= 8 px` / one full gutter.
- **Center labels on letters, not line boxes:** apply `text-box: trim-both cap alphabetic` on pills, badges, buttons with icons, and avatar initials so capitals sit optically centered instead of low.
- **Center currency amounts on digits, not the sign:** `$45` centered as one string pulls optically right; center the digit box and hang the currency symbol at `right: 100%`, rolling only digits.
- **Exact concentric radii & uniform insets:** `outer_radius = inner_radius + padding` with equal padding on all four sides (never `20 px` top / `14 px` sides). Keep `>= 12 px` text inset from container edges, `8–12 px` button clearance from fields above, `8–12 px` row padding, and `4–6 px` ink spacing between title and subtitle.
- **Even icons in even boxes (`14–16 px`):** prevents half-pixel snapping after motion; use **filled** glyphs at `<= 14 px` or inside tinted tiles (thin outlines go wiry); shift play triangles toward their point by `1/6` width; keep emoji in user content, never as UI icons.
- **No invented logos or fake focus rings:** never put a random letter in a colored square as a fake brand mark (use the real mark or plain text wordmark). Never put an accent ring/halo around a hero card just to highlight it — lift with surface step, shadow, and accent label; reserve rings for real focus.
- **No "onion skin" translucent overlap:** stacked cards, chips, and overlapping avatars take opaque fills.

### 3. Relationship choreography & "You see → You do" fault fixes
- **Animate the relationship, not isolated pieces:** hold outer chrome steady while dependent content transitions in overlapping retained tracks masked locally at entry/exit; never abruptly swap values or blur the whole interface.

| You see in a screenshot / capture | Fix immediately |
| --- | --- |
| Empty void under a list or pane (`empty pane`) | Add realistic rows until the list fills/bleeds, or crop the pane; never stretch gaps |
| One-line row `>= 3×` taller than its text (`fat row`) | Set `8–12 px` row padding and tighten pitch |
| Whole window floating with even margins in a hero | Bleed off 1–2 edges with one consistent gutter, or fill the slot |
| Stat value and unit wrapped onto separate lines | `white-space: nowrap` on the pair, resize number, or lead with unit |
| Gray placeholder bars where the eye lands | Put real domain words on the focal subject; keep bars strictly on edge filler |
| Hover/popover shifts position after opening | Anchor to the opening edge and reserve stable layout height |
| Emoji used as a UI icon or clipped SVG stroke | Swap for one icon family (`14–16 px` filled/stroke matched) and verify `viewBox` |
