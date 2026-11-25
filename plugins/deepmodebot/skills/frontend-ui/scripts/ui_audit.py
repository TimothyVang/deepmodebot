#!/usr/bin/env python3
"""Lightweight UI/CSS/HTML static quality gate + live-browser computed-style audit snippet.

    python -B ui_audit.py <file-or-dir> [--json]
    python -B ui_audit.py --browser-snippet

Catches mechanical UI flaws that make interfaces look generic or broken:
- transition: all and forbidden ease-in UI curves
- raw Tailwind gray/palette utility leaks (bg-zinc-*, text-slate-*)
- missing :focus-visible or prefers-reduced-motion rules
- heavy generic rgba(0,0,0,0.1+) card shadows and excessive border soup
- missing HTML lang, viewport meta, or <img> alt attributes
Stdlib only; never writes bytecode caches.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCAN_EXTS = frozenset({".html", ".htm", ".css", ".scss", ".jsx", ".tsx", ".vue", ".svelte"})
SKIP_DIRS = frozenset({".git", ".scratch", ".worktrees", "node_modules", "__pycache__", "dist", "build", ".next"})

TRANSITION_ALL_RE = re.compile(r"\btransition\s*:\s*[^;{}]*\ball\b", re.I)
EASE_IN_ONLY_RE = re.compile(r"\bease-in\b(?!-out)", re.I)
RAW_TW_GRAY_RE = re.compile(r"\b(?:bg|text|border)-(?:zinc|slate|gray|neutral|stone)-\d{2,3}\b")
HEAVY_RGBA_SHADOW_RE = re.compile(r"box-shadow\s*:[^;{}]*rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0?\.[1-9]\d*\s*\)", re.I)
BORDER_DECL_RE = re.compile(r"\bborder(?:-(?:top|right|bottom|left))?\s*:\s*[1-9]\d*px\s+solid\b", re.I)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
ALT_ATTR_RE = re.compile(r"\balt\s*=", re.I)

BROWSER_AUDIT_SNIPPET = r"""(() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const overflowX = Math.max(0, document.documentElement.scrollWidth - vw);
  const bodyCs = getComputedStyle(document.body);
  const bodySize = parseFloat(bodyCs.fontSize) || 16;
  const h1 = document.querySelector("h1");
  const h1Size = h1 ? parseFloat(getComputedStyle(h1).fontSize) : 0;
  const fonts = new Set();
  const loadedFonts = document.fonts ? [...document.fonts].filter(f => f.status === "loaded").map(f => f.family.replace(/['"]/g, "")) : [];
  const cv = document.createElement("canvas");
  cv.width = 1; cv.height = 1;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  const toRgba = (color) => {
    if (!ctx || !color || color === "transparent") return [0, 0, 0, 0];
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "rgba(0,0,0,0)";
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const blend = (fg, bg) => {
    const a = fg[3];
    return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1];
  };
  const lum = ([r, g, b]) => {
    const f = c => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const contrast = (c1, c2) => {
    const l1 = lum(c1), l2 = lum(c2);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const effectiveBg = (el) => {
    const chain = [];
    for (let n = el; n; n = n.parentElement) {
      const bg = toRgba(getComputedStyle(n).backgroundColor);
      if (bg[3] > 0) chain.push(bg);
      if (bg[3] >= 0.99) break;
    }
    const isDark = /dark/i.test(getComputedStyle(document.documentElement).colorScheme || "") && !/^\s*light\b/i.test(getComputedStyle(document.documentElement).colorScheme || "");
    let acc = isDark ? [18, 18, 18, 1] : [255, 255, 255, 1];
    for (let i = chain.length - 1; i >= 0; i--) acc = blend(chain[i], acc);
    return acc;
  };

  let bordered = 0, maxBorderDepth = 0, transitionAll = 0, foldCoveredArea = 0;
  const smallTargets = [], unlabeled = [], lowContrast = [];
  const depthMap = new WeakMap();

  for (const el of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) continue;
    fonts.add(cs.fontFamily.split(",")[0].replace(/['"]/g, "").trim());
    const hasDur = cs.transitionDuration.split(",").some(d => parseFloat(d) > 0);
    if (hasDur && cs.transitionProperty.split(",").some(p => p.trim() === "all")) transitionAll += 1;
    const hasBorder = ["Top", "Right", "Bottom", "Left"].some(
      s => parseFloat(cs[`border${s}Width`]) > 0 && cs[`border${s}Style`] !== "none" && toRgba(cs[`border${s}Color`])[3] > 0
    );
    const parentDepth = el.parentElement ? (depthMap.get(el.parentElement) || 0) : 0;
    const depth = parentDepth + (hasBorder ? 1 : 0);
    depthMap.set(el, depth);
    if (hasBorder) { bordered += 1; if (depth > maxBorderDepth) maxBorderDepth = depth; }

    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && r.top < vh && r.bottom > 0 && el.children.length === 0) {
      const txt = (el.textContent || "").trim();
      if (txt) {
        const iw = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
        const ih = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
        foldCoveredArea += iw * ih;
        if (lowContrast.length < 10) {
          const bg = effectiveBg(el);
          const fg = blend(toRgba(cs.color), bg);
          const ratio = contrast(fg, bg);
          const fs = parseFloat(cs.fontSize) || 16;
          const bold = parseInt(cs.fontWeight, 10) >= 700;
          const floor = (fs >= 24 || (bold && fs >= 18.66)) ? 3.0 : 4.5;
          if (ratio < floor) {
            lowContrast.push({ tag: el.tagName.toLowerCase(), ratio: Number(ratio.toFixed(2)), floor, text: txt.slice(0, 32) });
          }
        }
      }
    }
    if (el.matches("button, a[href], input, select, textarea, [role='button']")) {
      if (vw <= 500 && r.width > 0 && r.height > 0 && (r.width < 44 || r.height < 44)) {
        smallTargets.push({ tag: el.tagName.toLowerCase(), w: Math.round(r.width), h: Math.round(r.height), text: (el.textContent || "").trim().slice(0, 28) });
      }
      if (el.matches("button, a[href], [role='button']")) {
        const name = (el.getAttribute("aria-label") || el.textContent || "").trim();
        if (!name && !el.getAttribute("aria-labelledby")) unlabeled.push(el.outerHTML.slice(0, 80));
      }
    }
  }
  const brokenImages = [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src);
  return {
    viewport: `${vw}x${vh}`,
    overflowX,
    bodySizePx: bodySize,
    h1SizePx: h1Size,
    h1ToBodyRatio: h1Size ? Number((h1Size / bodySize).toFixed(2)) : null,
    fonts: [...fonts].slice(0, 8),
    loadedWebfonts: [...new Set(loadedFonts)].slice(0, 8),
    aboveFoldTextCoveragePct: Number(Math.min(100, (foldCoveredArea / Math.max(1, vw * vh)) * 100).toFixed(1)),
    borderedElements: bordered,
    maxNestedBorderDepth: maxBorderDepth,
    transitionAllCount: transitionAll,
    lowContrastSamples: lowContrast,
    smallMobileTargets: smallTargets.slice(0, 10),
    unlabeledControls: unlabeled.slice(0, 10),
    brokenImages,
  };
})()"""


def _iter_targets(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    files: list[Path] = []
    for cur_root, dirs, names in os.walk(target):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        base = Path(cur_root)
        for name in sorted(names):
            p = base / name
            if p.suffix.lower() in SCAN_EXTS:
                files.append(p)
    return files


CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def audit_source(text: str, rel: str, suffix: str) -> list[dict]:
    findings: list[dict] = []
    is_html = suffix in {".html", ".htm"}
    is_style = suffix in {".css", ".scss"} or (is_html and "<style" in text.lower())
    is_markup = suffix in {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte"}
    scan_text = CSS_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text) if is_style else text

    for idx, line in enumerate(scan_text.splitlines(), 1):
        if TRANSITION_ALL_RE.search(line):
            findings.append({"severity": "P1", "rule": "no-transition-all", "file": rel, "line": idx,
                             "message": "Avoid `transition: all`; animate explicit transform/opacity/color properties."})
        if EASE_IN_ONLY_RE.search(line):
            findings.append({"severity": "P2", "rule": "no-ease-in-ui", "file": rel, "line": idx,
                             "message": "Avoid `ease-in` on UI transitions; use `ease-out` (enter/exit) or `ease-in-out` (moves)."})
        if is_markup:
            m_tw = RAW_TW_GRAY_RE.search(line)
            if m_tw:
                findings.append({"severity": "P2", "rule": "semantic-color-tokens", "file": rel, "line": idx,
                                 "message": f"Raw gray utility `{m_tw.group(0)}`; map through semantic role tokens."})
            for m_img in IMG_TAG_RE.finditer(line):
                if not ALT_ATTR_RE.search(m_img.group(0)):
                    findings.append({"severity": "P0", "rule": "img-alt", "file": rel, "line": idx,
                                     "message": "<img> is missing an `alt` attribute."})
        if is_style and HEAVY_RGBA_SHADOW_RE.search(line):
            findings.append({"severity": "P2", "rule": "oklch-ambient-shadow", "file": rel, "line": idx,
                             "message": "Heavy generic `rgba(0,0,0,0.1+)` shadow; use layered low-alpha OKLCH ambient shadows."})
    if is_html:
        low = text.lower()
        if "<html" in low and "lang=" not in low:
            findings.append({"severity": "P0", "rule": "html-lang", "file": rel, "line": 1,
                             "message": "Document <html> is missing a `lang` attribute."})
        if "<head" in low and "viewport" not in low:
            findings.append({"severity": "P0", "rule": "meta-viewport", "file": rel, "line": 1,
                             "message": "Document is missing `<meta name=\"viewport\">`."})

    if is_style:
        if ":focus-visible" not in scan_text and ("button" in scan_text or ".btn" in scan_text or "a:" in scan_text or "input" in scan_text):
            findings.append({"severity": "P1", "rule": "focus-visible", "file": rel, "line": 1,
                             "message": "Interactive styles found without a `:focus-visible` rule."})
        if ("transition:" in scan_text or "@keyframes" in scan_text) and "prefers-reduced-motion" not in scan_text:
            findings.append({"severity": "P1", "rule": "reduced-motion", "file": rel, "line": 1,
                             "message": "Transitions/animations found without `@media (prefers-reduced-motion: reduce)`."})
        solid_borders = len(BORDER_DECL_RE.findall(scan_text))
        if solid_borders >= 12:
            findings.append({"severity": "P2", "rule": "border-budget", "file": rel, "line": 1,
                             "message": f"High solid-border count ({solid_borders}); prefer spacing, ground shifts, or hairlines."})
    return findings


def audit_path(target: Path) -> dict:
    files = _iter_targets(target)
    base = target.parent if target.is_file() else target
    findings: list[dict] = []
    for p in files:
        rel = p.relative_to(base).as_posix()
        txt = p.read_text(encoding="utf-8", errors="replace")
        findings.extend(audit_source(txt, rel, p.suffix.lower()))
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {
        "target": str(target),
        "files_scanned": len(files),
        "counts": counts,
        "ok": counts["P0"] == 0 and counts["P1"] == 0,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mechanical UI/CSS/HTML audit gate for frontend-ui.")
    parser.add_argument("target", nargs="?", help="File or directory to audit.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--browser-snippet", action="store_true", help="Print the browser computed-style audit JS IIFE.")
    args = parser.parse_args(argv)

    if args.browser_snippet:
        print(BROWSER_AUDIT_SNIPPET)
        return 0
    if not args.target:
        parser.error("target path is required unless --browser-snippet is passed")

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: target does not exist: {target}", file=sys.stderr)
        return 2

    report = audit_path(target)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        c = report["counts"]
        print(f"ui_audit: {report['files_scanned']} file(s) scanned — P0:{c['P0']} P1:{c['P1']} P2:{c['P2']}")
        for f in report["findings"]:
            print(f"  [{f['severity']}] {f['file']}:{f['line']} ({f['rule']}): {f['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
