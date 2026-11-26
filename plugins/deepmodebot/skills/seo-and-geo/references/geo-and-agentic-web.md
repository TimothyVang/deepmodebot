# GEO/AEO, `llms.txt`, AI Crawlers & Agentic Browsing

Checked as of 2026-11-25.

## 1. Generative & Answer Engine Optimization (GEO / AEO)

AI answer engines and coding-agent research tools extract self-contained factual passages rather than keyword-stuffed marketing copy:
- **Lead with a quotable 1–2 sentence definition** immediately under `<h1>` stating what the product/concept is, who it is for, its license/pricing model, and its measurable scope or limits.
- **Pair claims with primary evidence:** Concrete numbers, benchmark dates, exact CLI commands, version numbers, and explicit "Fits when / Does not fit when" tables outperform vague adjectives in RAG/citation ranking and reduce model hallucination when citing your docs.
- **Question-shaped `<h2>`/`<h3>` headings** followed by a direct 40–80 word answer paragraph allow passage chunkers to retrieve complete answers without losing context across headings.

## 2. `llms.txt` and Markdown content negotiation

- **`/llms.txt` (concise index, `< 15 KB`):** Markdown file at the site root starting with `# <Project Name>`, `> <1-line summary>`, a brief factual overview ("Fits when / Does not fit when", install one-liners), and H2-grouped markdown links (`- [Title](https://.../path): 1-line description of what is inside`).
- **`/llms-full.txt` (optional bundle):** Concatenated primary docs with explicit `Source: <canonical-url>` delimiters regenerated deterministically in CI so it never drifts from the real docs.
- **Clean Markdown mirror / `Accept: text/markdown`:** Where practical on docs sites, serve clean `.md` URLs (`https://example.com/docs/page.md`) or content-negotiate `Accept: text/markdown` without navigation chrome, cookie banners, or client-only JS rendering.

## 3. Separate AI search crawlers from training crawlers in `robots.txt`

Blocking all AI user-agents blindly removes a site from live AI search citations. Separate **retrieval/grounding bots** from **corpus-training crawlers**:
- **Search / live citation bots (allow on public docs/marketing):** `OAI-SearchBot`, `ChatGPT-User`, `Claude-SearchBot`, `Claude-User`, `PerplexityBot`, `Perplexity-User`, `Googlebot`, `Bingbot`.
- **Model-training crawlers (explicit owner policy — allow for open-source/AI-SEO visibility, or disallow for proprietary content):** `GPTBot`, `ClaudeBot`, `Google-Extended`, `CCBot`, `Bytespider`, `Meta-ExternalAgent`.

## 4. Agentic Browsing readiness (Lighthouse Agentic Browsing & browser agents)

Sites operated by browser agents fail on custom `<div>` controls, hover-only menus, canvas-trapped text, and ephemeral toasts:
- **Accessibility tree completeness:** Every interactive element uses native `<button>`, `<a href>`, `<input>`, `<select>`, or explicit ARIA role + accessible name (`<label for>`, `aria-label`), `aria-expanded`, and `aria-invalid` + `aria-describedby` pointing to persistent inline error text.
- **URL-addressable state:** Filters, tabs, pagination, and steps reflect in URL query/path parameters so an agent (or human) can navigate directly, refresh, or bookmark without replaying fragile multi-click sequences.
- **Idempotent & confirmable mutations:** Destructive or paid actions expose a clear review/summary screen with explicit totals before final submission, and never fire irreversible side effects on `GET` or focus/blur.
- **WebMCP (`navigator.modelContext`) as optional progressive enhancement:** Expose structured client tools only when a site has complex multi-field forms or client workflows, keeping standard HTML forms 100% functional because non-Chromium engines and many headless harnesses do not execute WebMCP.
