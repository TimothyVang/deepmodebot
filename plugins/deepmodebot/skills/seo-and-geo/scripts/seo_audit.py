#!/usr/bin/env python3
"""Deterministic Technical SEO, Schema.org JSON-LD, llms.txt & Agentic Readiness auditor.

    python -B seo_audit.py <dir-or-html-file> [--json] [--strict]
"""
from __future__ import annotations

import argparse
import html.parser
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

VAGUE_LINK_TEXT = frozenset({"click here", "here", "read more", "learn more", "more", "link"})
AI_BOTS = ("OAI-SearchBot", "GPTBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended")


class _HTMLInspector(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_lang = False
        self.in_title = False
        self.titles: list[str] = []
        self._cur_title: list[str] = []
        self.metas: list[dict[str, str]] = []
        self.canonicals: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self._cur_heading_level: int | None = None
        self._cur_heading_text: list[str] = []
        self.in_ld_json = False
        self._cur_ld: list[str] = []
        self.ld_blocks: list[str] = []
        self.imgs_missing_alt = 0
        self.imgs_missing_dims = 0
        self.vague_links = 0
        self._in_a = False
        self._cur_a_text: list[str] = []
        self._cur_a_aria = ""
        self.unlabeled_inputs = 0
        self.label_fors: set[str] = set()
        self.inputs_needing_label: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        if t == "html" and ad.get("lang", "").strip():
            self.has_lang = True
        elif t == "title":
            self.in_title = True
            self._cur_title = []
        elif t == "meta":
            self.metas.append(ad)
        elif t == "link":
            rels = {r.lower() for r in ad.get("rel", "").split()}
            if "canonical" in rels:
                self.canonicals.append(ad.get("href", "").strip())
        elif t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._cur_heading_level = int(t[1])
            self._cur_heading_text = []
        elif t == "script" and ad.get("type", "").lower().strip() == "application/ld+json":
            self.in_ld_json = True
            self._cur_ld = []
        elif t == "img":
            if "alt" not in ad:
                self.imgs_missing_alt += 1
            if not (ad.get("width") and ad.get("height")):
                self.imgs_missing_dims += 1
        elif t == "a":
            self._in_a = True
            self._cur_a_text = []
            self._cur_a_aria = ad.get("aria-label", "").strip()
        elif t == "label" and ad.get("for", "").strip():
            self.label_fors.add(ad["for"].strip())
        elif t in ("input", "select", "textarea"):
            itype = ad.get("type", "text").lower()
            if itype not in ("hidden", "submit", "reset", "button", "image"):
                has_inline = bool(ad.get("aria-label", "").strip() or ad.get("aria-labelledby", "").strip())
                self.inputs_needing_label.append((ad.get("id", "").strip(), has_inline))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title" and self.in_title:
            self.in_title = False
            self.titles.append("".join(self._cur_title).strip())
        elif t in ("h1", "h2", "h3", "h4", "h5", "h6") and self._cur_heading_level is not None:
            self.headings.append((self._cur_heading_level, " ".join("".join(self._cur_heading_text).split())))
            self._cur_heading_level = None
        elif t == "script" and self.in_ld_json:
            self.in_ld_json = False
            self.ld_blocks.append("".join(self._cur_ld))
        elif t == "a" and self._in_a:
            self._in_a = False
            txt = (self._cur_a_aria or " ".join("".join(self._cur_a_text).split())).lower().strip(" .!?:;")
            if txt in VAGUE_LINK_TEXT:
                self.vague_links += 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self._cur_title.append(data)
        if self._cur_heading_level is not None:
            self._cur_heading_text.append(data)
        if self.in_ld_json:
            self._cur_ld.append(data)
        if self._in_a:
            self._cur_a_text.append(data)


def audit_html_file(path: Path, rel: str) -> list[dict]:
    findings: list[dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    parser = _HTMLInspector()
    parser.feed(text)

    def add(severity: str, rule: str, message: str) -> None:
        findings.append({"file": rel, "severity": severity, "rule": rule, "message": message})

    if not parser.has_lang:
        add("error", "html-lang", "<html> is missing a non-empty lang attribute")
    if not parser.titles or not parser.titles[0]:
        add("error", "title-missing", "Missing or empty <title>")
    elif not (15 <= len(parser.titles[0]) <= 70):
        add("warning", "title-length", f"<title> length is {len(parser.titles[0])} chars (aim for 30-60)")

    desc = [m.get("content", "").strip() for m in parser.metas if m.get("name", "").lower() == "description"]
    if not desc or not desc[0]:
        add("error", "meta-description", "Missing or empty <meta name='description'>")
    elif not (50 <= len(desc[0]) <= 170):
        add("warning", "meta-description-length", f"Meta description is {len(desc[0])} chars (aim for 70-160)")

    viewport = [m for m in parser.metas if m.get("name", "").lower() == "viewport"]
    if not viewport:
        add("error", "viewport", "Missing <meta name='viewport'>")

    if not parser.canonicals:
        add("warning", "canonical-missing", "Missing <link rel='canonical'>")
    elif len(parser.canonicals) > 1 or not parser.canonicals[0].startswith(("https://", "http://")):
        add("error", "canonical-invalid", f"Invalid or duplicate canonical URL(s): {parser.canonicals}")

    og_props = {m.get("property", "").lower(): m.get("content", "").strip() for m in parser.metas if m.get("property")}
    for req_og in ("og:title", "og:description", "og:image"):
        if not og_props.get(req_og):
            add("warning", "opengraph", f"Missing OpenGraph tag {req_og}")

    h1s = [h for lvl, h in parser.headings if lvl == 1]
    if len(h1s) == 0:
        add("error", "h1-missing", "No <h1> heading found")
    elif len(h1s) > 1:
        add("warning", "h1-multiple", f"Found {len(h1s)} <h1> headings; keep exactly one primary <h1>")

    prev_lvl = 0
    for lvl, _ in parser.headings:
        if prev_lvl and lvl > prev_lvl + 1:
            add("warning", "heading-skip", f"Heading hierarchy skips from h{prev_lvl} to h{lvl}")
            break
        prev_lvl = lvl

    if parser.imgs_missing_alt:
        add("error", "img-alt", f"{parser.imgs_missing_alt} <img> element(s) missing alt attribute")
    if parser.imgs_missing_dims:
        add("warning", "img-cls-dims", f"{parser.imgs_missing_dims} <img> element(s) missing explicit width/height (CLS risk)")
    if parser.vague_links:
        add("warning", "anchor-text", f"{parser.vague_links} link(s) use non-descriptive anchor text (e.g. 'click here')")

    unlabeled = sum(1 for fid, has_aria in parser.inputs_needing_label if not has_aria and (not fid or fid not in parser.label_fors))
    if unlabeled:
        add("warning", "agentic-form-labels", f"{unlabeled} form control(s) lack an associated <label for> or aria-label (breaks Agentic Browsing)")

    for idx, raw_ld in enumerate(parser.ld_blocks, 1):
        try:
            parsed = json.loads(raw_ld)
        except ValueError as err:
            add("error", "json-ld-parse", f"JSON-LD block #{idx} failed to parse: {err}")
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for obj in items:
            if not isinstance(obj, dict):
                add("error", "json-ld-shape", f"JSON-LD block #{idx} item must be an object")
                continue
            ctx = str(obj.get("@context", ""))
            if "schema.org" not in ctx:
                add("error", "json-ld-context", f"JSON-LD block #{idx} missing https://schema.org @context")
            if not obj.get("@type") and not obj.get("@graph"):
                add("error", "json-ld-type", f"JSON-LD block #{idx} missing @type or @graph")

    return findings


def audit_site_files(root: Path, findings: list[dict]) -> dict:
    meta = {"has_robots_txt": False, "has_sitemap_xml": False, "has_llms_txt": False}
    robots = root / "robots.txt"
    if robots.is_file():
        meta["has_robots_txt"] = True
        rtxt = robots.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^Sitemap:\s*https?://", rtxt, re.I | re.M):
            findings.append({"file": "robots.txt", "severity": "warning", "rule": "robots-sitemap", "message": "robots.txt does not declare a Sitemap: URL"})
        if not any(b.lower() in rtxt.lower() for b in AI_BOTS):
            findings.append({"file": "robots.txt", "severity": "warning", "rule": "robots-ai-policy", "message": "robots.txt sets no explicit AI search/training crawler rules (e.g. OAI-SearchBot, GPTBot, ClaudeBot)"})

    sitemap = root / "sitemap.xml"
    if sitemap.is_file():
        meta["has_sitemap_xml"] = True

    llms = root / "llms.txt"
    if llms.is_file():
        meta["has_llms_txt"] = True
        ltxt = llms.read_text(encoding="utf-8", errors="replace").strip()
        if not ltxt.startswith("# "):
            findings.append({"file": "llms.txt", "severity": "error", "rule": "llms-txt-h1", "message": "llms.txt must open with a top-level '# Project Name' heading"})
        if not re.search(r"^>\s+\S", ltxt, re.M):
            findings.append({"file": "llms.txt", "severity": "warning", "rule": "llms-txt-summary", "message": "llms.txt should include a '> one-line summary' blockquote"})
        if len(ltxt.encode("utf-8")) > 25_000:
            findings.append({"file": "llms.txt", "severity": "warning", "rule": "llms-txt-size", "message": "llms.txt exceeds 25 KB; keep /llms.txt concise and put full text in /llms-full.txt"})
    return meta


def audit_target(target: Path) -> dict:
    findings: list[dict] = []
    if target.is_file():
        html_files = [target]
        base = target.parent
        site_meta = {}
    elif target.is_dir():
        skip = {".git", "node_modules", ".scratch", ".worktrees", "__pycache__"}
        html_files = []
        for p in sorted(target.rglob("*.html")):
            if skip & set(p.relative_to(target).parts):
                continue
            if p.name.lower().endswith(("fragment.html", "partial.html")):
                continue
            head_snip = p.read_text(encoding="utf-8", errors="replace")[:1024].lower()
            if "<!doctype" not in head_snip and "<html" not in head_snip:
                continue
            html_files.append(p)
        base = target
        site_meta = audit_site_files(target, findings)
    else:
        raise ValueError(f"target does not exist: {target}")

    for hf in html_files:
        rel = hf.name if target.is_file() else hf.relative_to(base).as_posix()
        findings.extend(audit_html_file(hf, rel))

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "ok": errors == 0,
        "html_files_checked": len(html_files),
        "errors": errors,
        "warnings": warnings,
        "site_files": site_meta,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors")
    args = parser.parse_args(argv)
    try:
        report = audit_target(Path(args.target).resolve())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "OK" if report["ok"] and not (args.strict and report["warnings"]) else "FAIL"
        print(f"seo-audit [{status}]: {report['html_files_checked']} HTML file(s), {report['errors']} error(s), {report['warnings']} warning(s)")
        for f in report["findings"]:
            print(f"  [{f['severity'].upper()}] {f['file']} ({f['rule']}): {f['message']}")
    if not report["ok"] or (args.strict and report["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
