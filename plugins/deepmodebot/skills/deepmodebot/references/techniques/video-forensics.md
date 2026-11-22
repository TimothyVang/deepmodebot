# video-forensics

**Use when:** the user asks to reverse-engineer, break down, audit, or remake a video ("how was this video made", "is this AI or real footage", "break down this video", "extract VIDEO.md", "remake/recreate this video", "separate vocals/music/SFX stems", "how did this transition or magic trick work").

Built around [JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) (Apache-2.0) and the open [VIDEO.md](https://videomd.github.io/videomd/) layered breakdown format: work backward from observed frames and audio stems to how each shot was produced, separate observed facts from inference, and verify remakes by frame-diff measurement.

## Procedure

1. **Check tools and contain all outputs.** Verify `ffmpeg -version`, Python >= 3.10, and `rea-video --help`.
   - If missing, install inside a contained `.venv` (`git clone https://github.com/JuneYaooo/rea-video .scratch/tools/rea-video` and `pip install -e ".scratch/tools/rea-video[ocr]"`, keeping model caches in `REA_VIDEO_HOME` / `REA_VIDEO_MODELS` when needed).
   - Write every breakdown under `<project-root>/.scratch/video-forensics/<slug>/` (`references/contain.md`).
   - Never hardcode VLM keys (`skill://secrets-and-auth`); pass `--env-file` if configured, and check `rea-video summary`'s `VLM:` line (`failed` or `not_configured` means offline mode—state that plainly).
   Done when `rea-video --help` works and the contained output directory is set.

2. **Survey and decompose shot-by-shot (CV + Multimodal Agent review).**
   - When running as a multimodal agent without an external VLM endpoint, run the two-pass agent-as-VLM loop:
     ```bash
     rea-video survey "<video-path>" -o "<out-dir>"
     rea-video decompose "<video-path>" -o "<out-dir>"
     rea-video review "<out-dir>"
     ```
     Inspect the generated contact sheets, strip frames, and low-confidence shots yourself, fill the review template, and merge verdicts with `rea-video apply-review "<out-dir>" --by agent`.
   - When an external VLM is configured and verified active, run `rea-video decompose "<video-path>" -o "<out-dir>" --vlm`, then still eyeball flagged/uncertain shots.
   - For audio-only stem isolation (`vocals.wav` via UVR MDX-Net, speaker tracks `voice_S1.wav`, `music.wav`, `effects.wav` via BandIt v2), run `rea-video stems "<video-path>" -o "<out-dir>"`.
   Done when `breakdown.json`, `report.html`, and `VIDEO.md` exist and `rea-video videomd "<out-dir>" --check` exits 0.

3. **Classify with strict evidence rules (zero visual-style guessing).** Answer six questions backed by frame/audio timestamps:
   - **Base visual provenance (11 classes):** `live_footage`, `film_clip`, `ai_video`, `avatar`, `render_3d`, `anim_2d`, `stop_motion`, `code_render`, `screen_capture`, `still_motion` (Ken Burns), or `still_frame`, plus `ai_edits` on live footage (face-swap, lip-sync, stylization, outfit/background swap). Never judge by art style alone (3D cartoon can be Blender or AI—check temporal geometry stability, text/hand drift, and flicker). Never treat stripped metadata after platform transcoding as proof of live footage.
   - **Packaging overlays vs scene content:** word-timed captions, kinetic titles, stickers/GIFs, and PiP vs typography rendered inside `code_render` scenes (which is the scene itself, not a post-overlay).
   - **User real assets vs reference assets:** real embedded pixels (footage, photos, UI recordings) that must be supplied verbatim vs reference images needed to prompt AI/3D shots.
   - **Audio provenance & beat sync:** human voice vs TTS, library BGM vs AI-generated music (e.g., Suno—mark uncertain BGM `"unconfirmed"` with verification steps), SFX-to-visual hit sync, and cut-on-beat alignment (`video/sound.md`, `video/rhythm.md`).
   - **Live-action cinematography & special moments:** framing, camera rig/moves, 12-setup lighting + color grade (`video/look.md`), and frame-by-frame reveals/twists/continuity goofs (`video/moments.md`).
   - **Calibrated uncertainty:** when evidence is mixed, report probabilities and missing proof (e.g., `"undecided, ~70% AI due to scroll glyph drift at shot_004"`) rather than fabricating certainty.
   Done when every shot verdict separates observed evidence from `~` inference in `video/timeline.md`.

4. **Read `VIDEO.md` layer-by-layer (`references/principles/guard-the-context-window.md`).** Never dump 190k-token `breakdown.json` into context: read `VIDEO.md` frontmatter card (~300 tokens) -> `VIDEO.md` overview & file map (~1.5k tokens) -> `video/timeline.md` -> specific `video/shots/<NNN>.md` files only for shots under question.
   Done when downstream reasoning or Q&A cites layered `VIDEO.md` artifacts cleanly.

5. **Plan, reconstruct, and diff-verify remakes (`fidelity` vs `adapt`).** When asked to remake or adapt the video:
   - Choose `fidelity` (match structure, cut timing, camera grammar, layout) or `adapt` (keep hook/pacing/reveal grammar, swap subject/brand/copy) per layer in `<out-dir>/remake/intent.yaml`, then run `rea-video plan "<out-dir>"`.
   - **Code-rendered / motion-graphics shots (`code_render`):** load `skill://frontend-ui` (`references/playbook/05a-motion-graphics.md`), extract layers via `rea-video code-remake "<out-dir>"`, rebuild in Remotion / HyperFrames / Three.js as a pure function of time `t` driven by `video/rhythm.md`, and verify pixel/layout/timing alignment with `rea-video compare "<ref-mp4>" "<remake-mp4>" -o "<out-dir>/compare"` (`compare.json` + `compare_worst.jpg`).
   - **Motion-driven / dance shots:** extract clean beat-aligned driving segments with `rea-video drive "<out-dir>"`.
   - **Paid AI video generation (`capsule-cinema` / `remake-run`):** **hard stop**—run `rea-video remake-run --dry-run` and get explicit user approval on shot count, model, and cost before spending paid generation credits. Never reuse third-party copyrighted footage, music, or likenesses.
   Done when the breakdown report (`VIDEO.md` + `report.html`) or verified remake (`compare.json` + assembled MP4) is proven on disk.

**Done when** `rea-video videomd "<out-dir>" --check` passes, uncertain shots were visually reviewed with honest confidence bounds, and any requested remake was verified against the reference timeline or frame diff.
