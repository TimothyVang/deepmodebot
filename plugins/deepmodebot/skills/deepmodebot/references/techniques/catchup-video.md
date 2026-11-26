# catchup-video

**Use when:** "catch me up with a video", "video recap", "subtitled slide video of what happened", or visual catch-up since the user's last message.

Follow **recall** (`references/techniques/recall.md`), replacing its prose/static visuals with a short silent subtitled landscape MP4 slide deck plus waiting user calls underneath. Scope starts at the user's last message before this request. Rendering the MP4 inside `<root>/.scratch/catchup-video/` is the one write exception to `recall`'s read-only rule.

1. **Plan from real artifacts.** Use captured screenshots, recordings, diffs, and measured outputs rather than chat prose. Draft one takeaway sentence and one point per slide (`<=10` slides; drop any slide that changes nothing the user knows; omit planning notes from the reply).
2. **Compose evolving visual slides.** Build on one visual model and evolve it across slides with arrows, highlights, and motion (system flow, PR stack states, before/after fix, or side-by-side decision options using consistent color/shape meanings). Never render bullet lists, status tables, or unconnected boxes; never invent numbers or draw uncaptured screens (if a UI change lacks a screenshot, state that on the slide and name what changed). Never mark work done if it still waits on the user.
3. **Burn readable subtitles.** Place one plain ~10-word subtitle per slide inside a fixed-height strip below the slide frame so it never overlaps slide content and stays legible at chat width. State what the picture means rather than reading labels aloud, without repeating facts across slides or reply text.
4. **Render & verify hold timing.** Render a silent landscape MP4 from generated slide frames (never screen-recording) with burnt-in subtitles held for the full slide duration (excluding transitions) at `>=1s` per 3 newly added words (subtitle + new/changed slide labels; words inside embedded screenshots excluded). Inspect one rendered frame per slide at chat size and measure frame-matched holds (not still-frame detectors on fades); re-render any cramped or unreadable slide.
5. **Reply.** Output the opening recap sentence, the embedded/linked MP4 path, one line naming remaining work you can finish yourself, and waiting user calls using the exact option names shown in the video (or a one-line render-failure note plus the waiting calls).

**Done when** the verified MP4 in `.scratch/catchup-video/` passes per-slide readability and word-hold checks (or reports render failure cleanly) and the reply lists only real waiting calls and remaining agent work.
