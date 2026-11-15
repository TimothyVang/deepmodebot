# Public video source metadata

Read the verification skill and run `control.py doctor` first. Keep fixtures and outputs under `.scratch/evidence/sources/`; never execute source/tutorial code or use a signed-in browser for convenience.

## Author descriptions and identity

Run the actual `plugins/deepmodebot/skills/deepmodebot/assets/scrape/yt_meta.py IDS_JSON OUT_JSONL --workers 1` against one requested public source.
Seed its output with an old metadata row to exercise the real append/resume migration.
Require current-revision matched-player descriptions to preserve complete repository URLs, including `microsoft/TokenEconomizer` rather than the displayed `microsoft/TokenEco...` label.
An empty authoritative description must remain empty, not be replaced with stale displayed text.
A different player video ID must not be attributed to the requested ID.
If only displayed text is available, require `description_complete: false`, its explicit origin and a partial-description count; do not claim full capture.
Legacy/partial rows remain eligible for a later explicit invocation, not an infinite retry loop.

The permanent parser regressions use minimal conflicting-source inputs, not raw transcript/description corpus or test-pinned prose.
A real same-response public fixture independently captured from the native UI supplies the canonical-link counterexample.
Inspect actual CLI output and resulting rows; passing parser tests alone is not live HTTP proof.

## Source coverage and publication

Inventory regular videos, Shorts, live uploads and relevant primary source links separately.
Observe actual continuation exhaustion; an arbitrary scroll cutoff and ranked-search exhaustion are not all-source completeness.
Deduplicate by exact video ID and distinguish original recordings, restreams, commentary and hash-verified transcript reuse.
Record full/partial/unread text ranges and explicit native-caption or login boundaries.
Screenshots must be actual source frames with video/time/URL/hash and visual inspection, not generated substitutes.
Only positive rights-qualified allowlists enter immutable Drive archives; verify downloaded bytes, member hashes/CRC and representative text/images.
Export authored summaries, factual indexes/citations and limited source-frame quotations; full captions and unknown-license copied prose remain analysis-only.
Full third-party code/docs require verified redistribution terms and required notices, not merely public accessibility.
Never publish credential-shaped links, sealed tokens, cookies, headers, signed media URLs or personal/session configs, even when found in a public source.
Private source capture is not public-code adoption, original proprietary implementation proof, a security audit or reproduced performance.
