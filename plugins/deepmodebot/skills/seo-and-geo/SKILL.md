---
name: seo-and-geo
description: "Technical SEO, Schema.org JSON-LD, Generative/Answer Engine Optimization (GEO/AEO), llms.txt, AI crawler policy, and Agentic Browsing readiness with deterministic auditing (seo_audit.py)."
metadata:
  as-of: "2026-11-25"
---

# Technical SEO, GEO & Agentic Web Readiness

Use when building, auditing, or shipping public web pages, documentation sites, landing pages, SaaS marketing routes, `robots.txt`, `sitemap.xml`, Schema.org JSON-LD, `llms.txt`, or browser-agent-accessible forms.

## Route to the right reference

- Crawlability, canonicals, Core Web Vitals (`LCP`/`INP`/`CLS`), OpenGraph, and Schema.org JSON-LD → `references/technical-and-schema.md`.
- Generative/Answer Engine Optimization (GEO/AEO), `llms.txt` / `llms-full.txt`, AI crawler `robots.txt` rules, and Agentic Browsing readiness → `references/geo-and-agentic-web.md`.
- Visual layout, typography, color, and UI craft → pair with `skill://frontend-ui`.

## Core rules (apply on every public web surface)

1. **Run the deterministic auditor before declaring done.** Execute `python -B "<this skill>/scripts/seo_audit.py" <dir-or-html-path> --json` (`py -3 -B` on Windows; also exposed as `deepmodebot gate seo`). Fix every `error` and review every `warning` on the real built HTML, not just JSX templates.
2. **Every indexable route needs one canonical identity.** Ship a unique `<title>` (30–60 chars), one `<meta name="description">` (70–160 chars), `<link rel="canonical" href="https://...">` with an absolute HTTPS URL, `<html lang="...">`, `<meta name="viewport">`, and matching `og:title`, `og:description`, `og:url`, `og:image`, and `twitter:card`.
3. **One `<h1>` and semantic landmarks.** Keep exactly one `<h1>` per document, non-skipping heading levels (`h1 -> h2 -> h3`), descriptive anchor text (never bare "click here" or "read more"), and `alt` attributes plus intrinsic `width`/`height` on every `<img>` to prevent layout shift (`CLS`).
4. **Validated JSON-LD only.** Every `<script type="application/ld+json">` block must parse as strict JSON (`<` escaped as `\u003c`), declare `"@context": "https://schema.org"` and a concrete `"@type"` (`SoftwareApplication`, `Article`, `FAQPage`, `Product`, `Organization`, `BreadcrumbList`), and reflect visible page facts (never hidden spam claims).
5. **Explicit AI-crawler & discovery policy.** Ship `robots.txt` naming a `Sitemap:` URL and explicit allow/disallow decisions for search vs training crawlers (`OAI-SearchBot`, `ChatGPT-User`, `Claude-SearchBot`, `PerplexityBot` vs `GPTBot`, `ClaudeBot`, `Google-Extended`, `CCBot`), plus a concise root `/llms.txt` (and optional `/llms-full.txt`) with quotable facts, canonical docs links, and install/API quickstarts.
6. **Agentic Browsing readiness = semantic HTML + fast deterministic actions.** Browser agents (Chrome Gemini, ChatGPT Atlas/Operator, Claude computer/browser use) rely on the accessibility tree, stable ARIA roles/labels, URL-addressable state, and explicit form validation errors—treat WebMCP (`navigator.modelContext`) only as a progressive enhancement on transactional forms, never a substitute for accessible HTML.

## Verification

Run `seo_audit.py` against the rendered/built output directory (e.g., `dist/`, `out/`, `docs/`, or captured SSR HTML) and inspect any JSON-LD, `robots.txt`, `sitemap.xml`, and `llms.txt` files directly.
