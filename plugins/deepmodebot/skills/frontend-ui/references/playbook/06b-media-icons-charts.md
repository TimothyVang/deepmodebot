## 6b. Icons, imagery & data visualization

Poor icon alignment, raw inline SVG blobs, and noisy neon charts are among the fastest tells of generated UI.

### Icons
- **One icon family per product** (`Lucide`, `Phosphor`, or `Tabler`); never mix outline and filled styles or mismatched stroke weights on the same bar.
- **Size & stroke:** `16 px` inside compact controls and tables, `18–20 px` beside body labels (`stroke-width: 1.5–1.75`). Keep icons one tone lighter (`--fg-muted` or `--fg-secondary`) than adjacent primary text so labels win scan order.
- **Optical alignment:** pair icons with `flex-shrink: 0` and `gap: 6–8 px`; mark decorative icons `aria-hidden="true"` and give icon-only buttons a concise `aria-label`.

### Imagery & illustration
- **Never ship AI-drawn inline SVG mascot blobs, wavy abstract dividers, or grey placeholder rectangles.** Use real product screenshots, crisp domain data, real photography, or clean geometric diagrams.
- **Aspect-ratio stability:** lock containers with `aspect-ratio` (`16/9`, `4/3`, `1/1`) + `object-fit: cover` so media never shifts layout on load; match concentric corner radius (`child <= parent - padding`).
- **Text over photography:** never place light text over raw photos; add a subtle bottom scrim (`linear-gradient(to top, oklch(0 0 0 / 0.65), transparent)`) and verify WCAG AA contrast on the brightest underlying area.

### Data visualization & charts
- **Strip chartjunk:** remove vertical gridlines, drop shadows, heavy tick marks, 3D tilts, and neon gradient area fills. Keep subtle `1 px` horizontal reference rules (`--border-subtle`) and direct value labels on hover/end points.
- **Color discipline:** default series use 1–2 muted brand/neutral tones; highlight only the single focal series or anomaly in `--accent` or semantic status color.
- **Numeric alignment:** set `font-variant-numeric: tabular-nums` on every axis tick, KPI tile, tooltip readout, and table column; format units via `Intl.NumberFormat`.
- **Responsive charts:** wrap charts in `@container` or ResizeObserver containers with explicit `min-height`; degrade dense multi-series legends into clean interactive readouts on `390 px` mobile.
