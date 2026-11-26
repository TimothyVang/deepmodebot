# Technical SEO, Core Web Vitals & Schema.org JSON-LD

Checked as of 2026-11-25.

## 1. Crawlability, indexation & canonicals

- **Canonical URL hygiene:** Every indexable page emits `<link rel="canonical" href="https://example.com/exact-path">` using lowercase scheme/host and consistent trailing-slash policy across internal links, `sitemap.xml`, redirects (`301`/`308`, never redirect chains >1 hop), and `og:url`.
- **Meta directives:** Staging/preview deployments emit `X-Robots-Tag: noindex, nofollow` at the HTTP header layer so preview subdomains never leak into search indexes. Never combine `noindex` in `<meta name="robots">` with `Disallow:` in `robots.txt` on a URL you need crawlers to de-index (blocked crawlers never see the `noindex` tag).
- **XML Sitemaps (`sitemap.xml`):** Cap each sitemap file at 50,000 URLs / 50 MB uncompressed; include only `200 OK` canonical indexable URLs (zero `404`, `301`, or `noindex` URLs) and set `<lastmod>` only from real content modification timestamps (search engines ignore `<priority>` and `<changefreq>`, and penalize fake daily `<lastmod>` bumps).
- **Internationalization (`hreflang`):** Multi-locale pages must include reciprocal `hreflang` links (every locale links to all siblings plus itself and `x-default`).

## 2. Core Web Vitals budgets

- **LCP (Largest Contentful Paint `<= 2.5s`):** Never lazy-load (`loading="lazy"`) the above-the-fold hero image; add `fetchpriority="high"`, modern AVIF/WebP `srcset`, and SSR/SSG HTML so the hero element is discoverable in the initial document without waiting on client JS bundles.
- **INP (Interaction to Next Paint `<= 200ms`):** Break long main-thread tasks (`> 50ms`), defer non-critical hydration/analytics, keep event handlers synchronous only for immediate visual feedback, and avoid layout thrashing inside input/click handlers.
- **CLS (Cumulative Layout Shift `<= 0.1`):** Declare explicit `width` and `height` (or CSS `aspect-ratio`) on all images, videos, embeds, and ad/banner slots; use `font-display: swap` or `optional` with metric-matched fallback fonts.

## 3. High-trust Schema.org JSON-LD patterns

- Escape `<` as `\u003c` inside `<script type="application/ld+json">` so injected or user-controlled strings cannot break out of `<script>`.
- Use `@graph` with stable `@id` URIs (`https://example.com/#org`, `https://example.com/docs/#webpage`) when combining `Organization`, `WebSite`, `WebPage`, `BreadcrumbList`, and page-specific entities (`SoftwareApplication`, `TechArticle`, `Product`).
- Include only Google/schema-supported rich-result properties backed by visible page text:
  - `SoftwareApplication`: `name`, `applicationCategory`, `operatingSystem`, `description`, `url`, `offers` (`price`, `priceCurrency`), `softwareVersion`.
  - `TechArticle` / `Article`: `headline`, `author` (`Person` or `Organization` with `url`), `datePublished`, `dateModified` (ISO-8601 with timezone), `image`.
  - `Product`: `name`, `image`, `description`, `sku`, `brand`, `offers` (`price`, `priceCurrency`, `availability` as full `https://schema.org/InStock` URI).
