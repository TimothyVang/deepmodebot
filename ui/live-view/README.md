# Live view UI (source)

The deepmodebot live view page, built with React and shadcn/ui's agent components: `Trace`, `Message`, `Bubble`, `CodeBlock`, `MessageScroller` and `Marker`, on Base UI.

The build writes one self-contained file, `plugins/deepmodebot/skills/deepmodebot/assets/live-view/viewer.html`, which `agui.mjs` serves. Scripts, styles and the Geist font are all inlined. Users install nothing, and the deepmodebot package keeps zero runtime dependencies. This folder is not shipped in the npm package.

```sh
cd ui/live-view
npm ci
npm run build      # type-checks, then rebuilds viewer.html
```

Commit the rebuilt `viewer.html` together with any source change.

- **AG-UI client:** `src/lib/agui.ts` folds AG-UI 1.0 events into one snapshot and answers interrupts with `resume`.
- **Page:** `src/App.tsx`.
- **Dark mode:** the default. The light/dark toggle is remembered per browser.
- **Mermaid:** loads on demand from a pinned CDN build, the only remote fetch, and runs with `securityLevel: 'strict'`.
- **Agent text:** rendered as React elements and never as HTML (`src/lib/markdown.tsx`).
