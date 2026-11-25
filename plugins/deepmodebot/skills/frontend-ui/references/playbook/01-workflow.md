## 1. Workflow: job → art direction → build → audit & declutter → motion pass → real-browser polish

1. **Start with the job.** Name who acts, the user goal, the primary object, and what changes. List every reachable state (loading, empty, error, populated, destructive) before drawing pixels.
2. **Write a concrete Art Direction Brief (`references/playbook/00-art-direction.md`) before any code:**
   - **Archetype & mood:** pick one positive archetype (Precision Workbench, Warm Editorial, High-Density Swiss, Tactile Consumer, or Spatial Canvas) and name two concrete anti-goals.
   - **Color formula:** 4 OKLCH surface tiers (`canvas`, `surface`, `raised`, `sunken`) tinted with the brand hue, 3 text tones, equal-L/C status tokens, and one primary accent — all named by role (`--bg-surface`, `--fg-muted`), never hex or raw Tailwind grays (`references/playbook/06a-color.md`).
   - **Type pairing:** curated display/body/mono pairing with intentional scale, tight display tracking (`-0.02em` to `-0.03em`), and `tabular-nums` for numbers.
   - **Composition:** pick a non-generic layout (asymmetric split, master-detail workbench, borderless KPI strip + flat ruled rows, or editorial hero + live proof) with an ASCII wireframe.
3. **Diverge deliberately (works in plain code, no external design tool required):**
   - Check shipped references in `references/patterns/mobbin-shipped-apps.md` and `mobbin-animations.md` (or inspect live reference URLs at `1440×900` and `390×844` when browsing).
   - If a working UI feels visually flat, explore 2–3 logic-preserving style directions along clear axes (*Precision Workbench*, *Warm Editorial*, *High-Density Swiss*) before locking global tokens.
   - For agent features, prototype real streaming/approval/error behavior with scripted fixtures before polishing visuals.
4. **Build with real content and surface finish:** Use realistic domain copy and real data shapes — never grey placeholder boxes, lorem ipsum, or invented `99.99%` metrics. Enforce the border budget (`<= 1` bordered container depth), directional dark top-rim lighting or layered light ambient shadows, and frosted sticky chrome.
5. **Separate polish passes (never ship round 1):**
   - **Mechanical audit:** run `python -B <frontend-ui skill>/scripts/ui_audit.py <target>` on CSS/HTML/TSX and run its browser JS audit in the live page to catch overflow, missing fonts, `transition: all`, raw hex/Tailwind grays, border soup, contrast gaps, and missing focus/reduced-motion rules.
   - **Spacing & declutter pass:** strip unrequested chips, redundant badges, nested box borders, and dead chrome; tighten container proportions directly on the rendered DOM.
   - **Motion pass (`references/playbook/05-motion.md`):** add purposeful transform/opacity transitions and springs; verify zero animation on Escape/⌘K/100+/day actions.
6. **Verify live in a real browser at `1440×900` and `390×844` (and record full E2E video for flows/motion):**
   - Capture desktop and mobile screenshots, run a keyboard-only Tab/Escape pass, inspect the accessibility tree, check every reachable state, and read the browser console for zero errors.
   - For any multi-step flow or animated UI, record the **complete continuous video** and watch the entire video together (never judge from isolated single frames alone) to catch digit pop-ins, font-load jumps, awkward pacing, and seam flicker; track versions `v1..v25` via `skill://deepmodebot/assets/e2e/rehearsal_gate.py`.
   - Never claim visual quality from code alone. For agent UI, replay scripted streams (`approve`, `deny`, `error`, `preliminary`, `stopped`) through the real UI before testing a live model.
7. **Clean-context visual critique & Round 2+ polish (`references/playbook/02-review-rubric.md`):**
   - Self-grading anchors on your own draft. Spawn a clean-context visual critic subagent with *only* the brief, the `1440×900` and `390×844` screenshots (plus full recorded video for E2E/motion), and `ui_audit.py` JSON (never your implementation code or excuses), returning <= 5 ranked visual fixes.
   - Fix every P0/P1, contrast, overflow, transition, and visual-flatness finding, then re-record/re-capture until `rehearsal_gate.py verdict --strict` passes.
