# Presentations (`.pptx`) — Layout Geometry & Overflow Prevention

Checked as of 2026-11-25.

## 1. Tool choice

- **Python:** `python-pptx` for template-driven and programmatic `.pptx` builds/edits.
- **Node / TypeScript:** `pptxgenjs` for clean declarative widescreen (`16:9`, `13.333" x 7.5"`) decks with shapes, charts, and tables.

## 2. Geometry, density & visual rules

- **Widescreen coordinate discipline (`16:9`):** Treat the slide canvas (`13.333" x 7.5"`) with a strict `0.5"` outer safe margin (`x in [0.5", 12.833"]`, `y in [0.45", 7.05"]`). Compute bounding boxes explicitly so two shapes never collide unless intentionally layered.
- **One takeaway per slide:** Headline states the conclusion ("P99 latency dropped 62% after batching"), never a vague topic label ("Performance Results"). Keep body copy under ~45–65 words per slide; split dense content into two slides instead of shrinking body font below `14pt`.
- **Visual variety over bullet walls:** Convert uniform bullet slides into two-column comparisons, metric callout cards (big stat + 1-line label), architecture/process diagrams, or clean data tables/charts. Pair typography and OKLCH/hex palette choices with `skill://frontend-ui`.
- **Inspect for overflow:** `python-pptx` and `pptxgenjs` do not reflow overflowing text onto new slides—long strings silently spill past the bottom of a shape or overlap the footer. `doc_audit.py` checks character/line density per text frame, and visual PDF/PNG raster inspection catches font-metric clipping.
