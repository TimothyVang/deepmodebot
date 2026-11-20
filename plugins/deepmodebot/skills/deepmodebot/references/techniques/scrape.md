# scrape

**Use when:** the user asks to scrape, pull, archive, or "get everything" from a web page, video, channel, playlist, or a diagram shown in a video.

1. **Probe media-free, official sources first.** For YouTube, exhaust zero-playback sources via `assets/scrape/yt_enrich.py` before opening a video player or touching `googlevideo.com`: Atom/RSS (`feed`), oEmbed (`oembed`), YouTube Data API v3 (`api-channel`, `api-video --comments --captions-meta`), single-GET watch HTML (`inspect`), and companion repos/slides/canvases/podcasts (`links` — export `docs/images/`, tldraw, Excalidraw, or Figma canvases directly rather than screenshotting video).
   Done when you know what official and companion sources provide and what still requires playback or signed-in access.
2. **Inventory with tab verification before bulk.** Use `yt_enrich.py channel-tabs` (verifies `tab_verified`, handles 2026 `lockupViewModel`, marks `upcoming`, and flags `has_continuation`) or `api-channel` (`uploads` mixes tabs; filter by type). Over ~200 items or any signed-in fetch -> state scope options with time estimates.
   Done when the item count, tab verification, and scope are recorded.
3. **Fix the output layout up front:** `index.md` + `index.csv` (one row per item, newest first, stamped `fetched_at`, unknown dates/counts left blank—never zero), `videos/*.md`, and raw JSONL. `yt_enrich.py render` reduces JSONL to the last `state == "ok"` record per ID and reopens `index.csv` to verify every row matches the header width.
   Done when the folders exist and raw-first rendering passes CSV validation.
4. **Pace from the first request and stop immediately on 403/429.** Run sequentially with >=2 s delay (`>=4 s` signed-in) and verify helpers expose the first denial without automatic retries (`yt_enrich.py` and `yt_meta.py` exit `3` and write `blocked.json`). On HTTP 403/429, login wall, or challenge, halt the entire run, close owned tabs, preserve completed artifacts, and resume only after explicit user clearance. Never switch client, identity, or endpoint to bypass a denial.
   Done when bulk collection runs paced, resumable, and fail-fast on denials.
5. **Tell blocked from absent and check duplicated caption panels.** An empty caption list when `playabilityStatus` is `LOGIN_REQUIRED` is `unknown_player_login_required`, not absent. Check ordered transcript starts for exact repeated panel blocks; retain raw captures and count one block in diagnostics.
   Done when every empty or partial result carries its observed reason.
6. **Signed-in sessions and NotebookLM imports are hard stops.** Ask once with scope, pacing, and anonymous alternatives, then run sequentially at >=4 s per item without exporting cookies. In NotebookLM: check available source slots first (notebooks cap sources, e.g. 300), append each attempt (notebook URL, video ID, time) before clicking Insert, reconcile after any disconnect before submitting again, and reopen each source to confirm its exact embedded YouTube ID and readable transcript text. Keep sharing unchanged.
   Done when user authorization is recorded and every reported import has exact-ID transcript readback.
7. **Prove completeness per item and in total.** Inventory count equals terminal records plus pending records (never report success by subtraction). Compare transcript spans and internal gaps against duration; name every remaining gap (`upcoming`, `unavailable`, `blocked`).

## YouTube facts (2026-11)

- **Official zero-403 sources (`assets/scrape/yt_enrich.py`):** `feed` (Atom XML, latest 15 items, zero auth), `oembed` (title/author/thumbs), `api-video` / `api-channel` (`YOUTUBE_API_KEY`, 50 IDs per 1-unit call, plus pinned/top comments for errata and repo links), and `gemini` (`GEMINI_API_KEY` + `google-genai`, server-side multimodal YouTube URL analysis with `start_offset`/`end_offset`/`fps`, zero local download).
- **Rich single-GET metadata & static stills:** `yt_enrich.py inspect` parses `ytInitialData` even while the player API is walled, returning channel ID + RSS URL, chapters with per-chapter `i.ytimg.com` thumbnails, Most Replayed heatmap peaks, unwrapped `youtube.com/redirect` companion links, caption inventory status, and suggested Gemini windows. `yt_enrich.py thumbs` downloads cover, `hq1`–`hq3` keyframes, and chapter stills with SHA-256 manifests without touching `googlevideo.com`.
- **2026 channel grids:** YouTube channel `/videos` tabs now ship `lockupViewModel` (not only `videoRenderer`); `yt_enrich.py channel-tabs` parses both and rejects silent fallback tabs.
- **Transcripts when walled (last resort):** caption `baseUrl` returns an empty body without a PO token, and in-page `youtubei/v1/get_transcript` POST returns 400. Clicking "Show transcript" and reading the panel works via `assets/scrape/yt_transcript_relay.js` (handles `ytd-transcript-segment-renderer` and `PAmodern_transcript_view`).
- **Unwalled `yt-dlp` path:** `yt-dlp --retries 0 --fragment-retries 0 --skip-download --write-auto-subs --sub-langs "en-orig,en" --sub-format json3 --write-info-json`. Stamp view/like counts with `fetched_at` because counts under ~2 days old lag across endpoints.
- **Frames without downloading:** POSIX `ffmpeg -ss <sec> -i "$(yt-dlp -f 'bv*[height<=1080][ext=mp4]' -g URL)" -frames:v 1 out.png`; Windows PowerShell `$u = yt-dlp -f "bv*[height<=1080][ext=mp4]" -g URL; ffmpeg -ss <sec> -i $u -frames:v 1 out.png`.

## tldraw boards

A shared `tldraw.com/f/<id>` board opens without login, and `window.editor` is exposed. In a managed browser tab (omp `eval` `browser`, Playwright, or CDP): `editor.store.getStoreSnapshot()` saves a `.tldr` (wrap as `{tldrawFileFormatVersion:1, schema, records}`), `editor.getSvgString(ids, {background:true, darkMode:true, padding:32})` gives vector, `editor.toImage(ids, {format:'png', scale:2, ...})` gives PNG. Group shape ids by page-bounds y-range to export each section separately.

**Done when** every inventoried item has a row, every gap carries a reason, CSV row widths are verified, and one rendered file per type was opened and read.
