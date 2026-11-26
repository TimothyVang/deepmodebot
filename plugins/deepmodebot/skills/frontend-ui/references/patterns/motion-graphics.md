# Motion graphics: engines, stack & source tradeoffs

Engine selection matrix and resolved source contradictions backing `references/playbook/05a-motion-graphics.md` (which holds the numbered production rules). Raw repo/channel notes: `TimothyVang/frontend:reference/github/motion-graphics/` and `youtube/channels/`.

## Core thesis

1. **Same machine underneath:** every reliable pipeline renders each frame as a pure function of `t` (`useCurrentFrame()`, `seek(t)`, `render(t)`) in headless Chrome, driven by one timeline file and muxed by ffmpeg at **−14 LUFS**.
2. **Brief beats engine:** quality comes from inputs, numeric specs, a growing **Banned** list, beat grid, and a stills/beat-map gate before full render.
3. **Film ≠ UI motion:** first drafts always run too fast; budget reading holds (`0.3 s/word + 0.5 s`, wordmark ≥ 1 s) and real product UI captures first.

## AI motion-graphics stack

| Need | Tool | Why | Alternative |
| --- | --- | --- | --- |
| Direction (story, spec, shots) | HyperFrames `story.md` + `spec.md`; Lemo-Opuscar `DIRECTOR.md` | 3 storylines → numeric SPEC + BANNED; treatment before code | ClaudeAnimationBase storyboard with *reads* (character pieces) |
| Promo structure & shot vocab | video-shotcraft energy arc + shot cards | Tuned parameters and pitfalls from real rework | HyperFrames registry blocks (~450) |
| Layout + animation engine | **Remotion** (React/TS reusing real components/tokens) | `useCurrentFrame` + `interpolate`, Studio, `@remotion/three` | **HyperFrames** (Apache-2.0, HTML+GSAP) for >3-person teams without Remotion license; plain `render(t)` HTML for one-offs |
| Brand + real UI input | Repo tokens + 2× dev-server screenshots/cutouts | Real UI over mockups is unanimous | MagicPath / Figma styleframes; `npx hyperframes capture <url>` |
| 3D & physics | three.js (R3F) + `@react-three/rapier` **baked per frame** | Deterministic & parallel-safe; Blender MCP for photoreal heroes | Closed-form springs as `f(t)` |
| Post-processing & VFX | `@react-three/postprocessing` (sparingly; DoF/glow as info) | Merged EffectPass + MSAA; pixelfx / p5.brush for stylized looks | ffmpeg grain at mux; Lottie for in-app |
| Music & beat sync | Licensed/user track + `librosa` grid fit (`beat_data.json`, ≤15 ms) | One clock; post-render cut verification ≤3 frames | `npx hyperframes beats`; code-synthesized score only for stylized pieces |
| SFX & voice | Freesound CC0/CC BY (click/whoosh/tick/riser→impact); local Kokoro + Whisper | Cinematic timbres, offline/checkable voice | Procedural `sfx.py`; Fish Audio (hosted, check license) |
| Motion blur, render & master | Remotion `<HtmlInCanvasMotionBlur>` / Playwright subframes + ffmpeg `tmix`; two-pass loudnorm −14 LUFS, ≤−1 dBTP | Deterministic parallel render | HyperFrames `data-motion-blur` + render; Lambda / Cloud Run |
| QA | Contact sheets + 0.2 s strips + 360–480 px crop + beat-error table + clean-context reviewer | Motion cannot be judged from code; maker is biased | HyperFrames `check` / `snapshot --review` |

## Resolved contradictions between sources

| Topic | Side A | Side B | Our call |
| --- | --- | --- | --- |
| Critique loop | Numeric 1–10 score until 7–8+ | HyperFrames: scores find nothing to fix; use timestamped P0–P2 notes | Timestamped `t · where · problem → change` notes (optional score only as stop condition) |
| Music in code | Synthesize original score in code on timeline | HyperFrames: don't burn a run writing music blindly | Licensed/user track by default; code synthesis only for stylized pieces, measured |
| SFX peak | Peak on exact event frame | HyperFrames: peak **+1 frame** after picture | Peak at +1 frame (never perceived as early) |
| Hard cuts | Transitions at every seam | Hard cuts between layout forms / on beat | Hard cuts only on action, beat, or layout-form change (≤1/3 of seams) |
| Overshoot | Critically damped (zero overshoot) | `back.out(1.4–1.7)` (1.04–1.12) by brand | Brand preset decides; product UI stays zero-overshoot |
| Text in video | Character pieces: show, no text | Launch films: titles carry argument (no silent stretch >3 s) | Character pieces: no text; product films: titles per §5a copy/floor rules |

Numbered execution, timing, sound, shot-budget, model-tier, and pipeline-safety rules live in `references/playbook/05a-motion-graphics.md` (not duplicated here). Key extra craft notes: iterate 3+ distinct drafts fixing the worst 3 issues per round, remove ~1/3 of motion when a cut feels busy, and keep two brief silences before the turn.
