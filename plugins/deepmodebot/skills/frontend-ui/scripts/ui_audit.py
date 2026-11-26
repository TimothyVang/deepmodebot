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

_LAYOUT_PROP = r"(?:width|height|top|left|right|bottom|margin(?:-(?:top|right|bottom|left))?|padding(?:-(?:top|right|bottom|left))?)"
TRANSITION_ALL_RE = re.compile(
    r"\btransition(?:-property)?\s*:\s*(?:['\"][^'\"]*\ball\b[^'\"]*['\"]|[^;{}\"'<>]*\ball\b)",
    re.I,
)
LAYOUT_TRANSITION_RE = re.compile(
    rf"\btransition(?:-property)?\s*:\s*(?:['\"][^'\"]*\b{_LAYOUT_PROP}\b[^'\"]*['\"]|[^;{{}}\"'<>]*\b{_LAYOUT_PROP}\b)",
    re.I,
)
EASE_IN_ONLY_RE = re.compile(r"\bease-in\b(?!-out)", re.I)
SCALE_ZERO_CSS_RE = re.compile(
    r"\btransform\s*:\s*(?:['\"][^'\"]*(?<![a-z0-9_-])scale\(\s*0(?:\.0+)?\s*\)[^'\"]*['\"]|[^;{}\"'<>]*(?<![a-z0-9_-])scale\(\s*0(?:\.0+)?\s*\))",
    re.I,
)
PURE_BLACK_BG_CSS_RE = re.compile(
    r"\bbackground(?:-color)?\s*:\s*(?:['\"][^'\"]*#000(?:000)?\b(?![0-9a-f])[^'\"]*['\"]|[^;{}\"'<>]*#000(?:000)?\b(?![0-9a-f]))",
    re.I,
)
RAW_TW_GRAY_RE = re.compile(r"\b(?:bg|text|border)-(?:zinc|slate|gray|neutral|stone)-\d{2,3}\b")
TW_BG_BLACK_RE = re.compile(r"""(?<=[\s"'`])bg-black(?=[\s"'`])""")
WIDTH_100VW_CSS_RE = re.compile(r"(?:^|[;\s{])width\s*:\s*100vw\b", re.I)
FAKE_LIVE_PULSE_RE = re.compile(
    r"<span\b[^>]*\banimate-pulse\b[^>]*(?:/>|>.*?</span>)\s*(?:LIVE|ONLINE|SYNCED)\b",
    re.I,
)
LIVE_STATUS_A11Y_RE = re.compile(r"\b(?:role\s*=\s*['\"]status['\"]|aria-live\s*=)", re.I)
HEAVY_RGBA_SHADOW_RE = re.compile(r"box-shadow\s*:[^;{}]*rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0?\.[1-9]\d*\s*\)", re.I)
BORDER_DECL_RE = re.compile(r"\bborder(?:-(?:top|right|bottom|left))?\s*:\s*[1-9]\d*px\s+solid\b", re.I)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
ALT_ATTR_RE = re.compile(r"\balt\s*=", re.I)
CIRCULAR_CHECKBOX_TAG_RE = re.compile(
    r"<(?:input\b[^>]*\btype\s*=\s*['\"]checkbox['\"][^>]*|[a-z0-9_-]+\b[^>]*\brole\s*=\s*['\"]checkbox['\"][^>]*)",
    re.I,
)
ROUNDED_FULL_CLASS_RE = re.compile(r"\brounded-full\b|border-radius\s*:\s*(?:50%|9999px)", re.I)
BUTTON_TAG_RE = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<body>(?:(?!</button>).)*)</button>", re.I)
ICON_ELEMENT_RE = re.compile(r"<(?:svg|i)(?=[\s>/])", re.I)
STRIP_ICON_BLOCK_RE = re.compile(r"<(?P<tag>svg|i)\b[^>]*(?:/>|>.*?</(?P=tag)>)", re.I)
STRIP_ANY_TAG_RE = re.compile(r"<[^>]+>")
A11Y_NAME_ATTR_RE = re.compile(
    r"\b(?:aria-label|aria-labelledby|title)\s*=\s*(?:['\"][^'\"]*\S[^'\"]*['\"]|\{\s*(?!['\"]\s*['\"]\s*\})[^}]+\})",
    re.I,
)

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
  const smallTargets = [], unlabeled = [], lowContrast = [], circularCheckboxes = [], pureBlackSurfaces = [], missingTabularNums = [], iconButtonsMissingTooltip = [], centerOriginMenus = [], unprefocusedFilterPopovers = [], trackedCapsEyebrows = [], deadFormsOrHashLinks = [];
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
    if (r.width >= 200 && r.height >= 120 && cs.backgroundColor === "rgb(0, 0, 0)" && pureBlackSurfaces.length < 6) {
      pureBlackSurfaces.push({ tag: el.tagName.toLowerCase(), w: Math.round(r.width), h: Math.round(r.height) });
    }
    if (el.matches("input[type='checkbox'], [role='checkbox']") && r.width > 0 && r.height > 0) {
      const rad = parseFloat(cs.borderTopLeftRadius) || 0;
      if (rad >= Math.min(r.width, r.height) * 0.45 && circularCheckboxes.length < 6) {
        circularCheckboxes.push(el.outerHTML.slice(0, 80));
      }
    }
    if (el.matches("time, [role='timer'], td") && el.children.length === 0 && /\d{2,}/.test(el.textContent || "")) {
      const fvn = cs.fontVariantNumeric || "";
      const ff = (cs.fontFamily || "").toLowerCase();
      if (!fvn.includes("tabular-nums") && !/mono|consolas|menlo|fira code|jetbrains/.test(ff) && missingTabularNums.length < 6) {
        missingTabularNums.push({ tag: el.tagName.toLowerCase(), text: (el.textContent || "").trim().slice(0, 24) });
      }
    }
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
        const visText = (el.textContent || "").trim();
        const name = (el.getAttribute("aria-label") || visText).trim();
        if (!name && !el.getAttribute("aria-labelledby")) unlabeled.push(el.outerHTML.slice(0, 80));
        if (!visText && el.querySelector("svg, img") && iconButtonsMissingTooltip.length < 10) {
          const hasTip = el.hasAttribute("aria-describedby") || el.hasAttribute("data-tooltip") || el.hasAttribute("data-state") || el.hasAttribute("title");
          if (!hasTip) iconButtonsMissingTooltip.push(el.outerHTML.slice(0, 80));
        }
      }
    }
    if (el.matches("[role='menu'], [role='listbox']") && r.width > 0 && r.height > 0) {
      const [ox, oy] = (cs.transformOrigin || "").split(/\s+/).map(parseFloat);
      if (Number.isFinite(ox) && Number.isFinite(oy) && Math.abs(ox - r.width / 2) < 1 && Math.abs(oy - r.height / 2) < 1 && centerOriginMenus.length < 10) {
        centerOriginMenus.push(el.outerHTML.slice(0, 80));
      }
      const filterInput = el.querySelector("input[type='text'], input[type='search'], input:not([type])");
      if (filterInput && document.activeElement !== filterInput && !el.contains(document.activeElement) && unprefocusedFilterPopovers.length < 10) {
        unprefocusedFilterPopovers.push(el.outerHTML.slice(0, 80));
      }
    }
  }
  const brokenImages = [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src);
  for (const h of document.querySelectorAll("h1, h2, h3")) {
    const prev = h.previousElementSibling;
    if (prev && prev.children.length === 0 && trackedCapsEyebrows.length < 6) {
      const pcs = getComputedStyle(prev);
      if (pcs.textTransform === "uppercase" && (parseFloat(pcs.letterSpacing) || 0) >= 1.2 && (prev.textContent || "").trim().length <= 40) {
        trackedCapsEyebrows.push((prev.textContent || "").trim());
      }
    }
  }
  for (const f of document.querySelectorAll("form")) {
    if (!f.getAttribute("action") && !f.onsubmit && deadFormsOrHashLinks.length < 6) deadFormsOrHashLinks.push("<form> missing action/handler");
  }
  for (const a of document.querySelectorAll("a[href='#']")) {
    if (!a.onclick && !a.getAttribute("role") && deadFormsOrHashLinks.length < 6) deadFormsOrHashLinks.push(a.outerHTML.slice(0, 64));
  }
  const h1Rect = h1 ? h1.getBoundingClientRect() : null;
  const heroClippedAboveFold = Boolean(vw >= 1280 && h1Rect && h1Rect.bottom > Math.max(vh, 800));
  const rootOx = getComputedStyle(document.documentElement).overflowX;
  const overflowHiddenBreaksSticky = (rootOx === "hidden" || bodyCs.overflowX === "hidden") && [...document.querySelectorAll("body *")].some(n => getComputedStyle(n).position === "sticky");
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
    circularCheckboxes,
    pureBlackSurfaces,
    missingTabularNums,
    iconButtonsMissingTooltip,
    centerOriginMenus,
    unprefocusedFilterPopovers,
    trackedCapsEyebrows,
    deadFormsOrHashLinks,
    heroClippedAboveFold,
    overflowHiddenBreaksSticky,
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
    scan_text = CSS_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    allows_intrinsic_size = "interpolate-size" in scan_text.lower()

    for idx, line in enumerate(scan_text.splitlines(), 1):
        if TRANSITION_ALL_RE.search(line):
            findings.append({"severity": "P1", "rule": "no-transition-all", "file": rel, "line": idx,
                             "message": "Avoid `transition: all`; animate explicit transform/opacity/color properties."})
        elif LAYOUT_TRANSITION_RE.search(line) and not allows_intrinsic_size:
            findings.append({"severity": "P1", "rule": "no-layout-transition", "file": rel, "line": idx,
                             "message": "Avoid animating layout box properties (width/height/top/left/margin/padding); use transform/opacity or Motion `layout`."})
        if EASE_IN_ONLY_RE.search(line):
            findings.append({"severity": "P2", "rule": "no-ease-in-ui", "file": rel, "line": idx,
                             "message": "Avoid `ease-in` on UI transitions; use `ease-out` (enter/exit) or `ease-in-out` (moves)."})
        if SCALE_ZERO_CSS_RE.search(line):
            findings.append({"severity": "P1", "rule": "no-scale-zero-entry", "file": rel, "line": idx,
                             "message": "Avoid `scale(0)` UI entries; start popovers/menus at `scale(0.95)` with trigger-directional `transform-origin`."})
        if PURE_BLACK_BG_CSS_RE.search(line):
            findings.append({"severity": "P1", "rule": "no-pure-black-surface", "file": rel, "line": idx,
                             "message": "Avoid `#000000` dark surfaces (causes OLED scroll smearing); use brand-tinted dark tokens (`>= #09090b`)."})
        if is_style and WIDTH_100VW_CSS_RE.search(line):
            findings.append({"severity": "P2", "rule": "no-100vw-overflow", "file": rel, "line": idx,
                             "message": "Avoid `width: 100vw` (triggers horizontal scrollbar overflow); use `100%` with `overflow-x: clip`."})
        if is_markup:
            m_tw = RAW_TW_GRAY_RE.search(line)
            if m_tw:
                findings.append({"severity": "P2", "rule": "semantic-color-tokens", "file": rel, "line": idx,
                                 "message": f"Raw gray utility `{m_tw.group(0)}`; map through semantic role tokens."})
            if TW_BG_BLACK_RE.search(line):
                findings.append({"severity": "P1", "rule": "no-pure-black-surface", "file": rel, "line": idx,
                                 "message": "Avoid `bg-black` (`#000000` causes OLED scroll smearing); use a tinted dark surface token."})
            for m_cb in CIRCULAR_CHECKBOX_TAG_RE.finditer(line):
                if ROUNDED_FULL_CLASS_RE.search(m_cb.group(0)):
                    findings.append({"severity": "P1", "rule": "checkbox-not-circular", "file": rel, "line": idx,
                                     "message": "Checkboxes must stay rectangular/squircle (`rounded-sm`/`4–6px`); circles (`rounded-full`/`50%`) signify single-select radios."})
            for m_btn in BUTTON_TAG_RE.finditer(line):
                body = m_btn.group("body")
                if not ICON_ELEMENT_RE.search(body):
                    continue
                visible = STRIP_ANY_TAG_RE.sub("", STRIP_ICON_BLOCK_RE.sub("", body)).strip()
                if not visible and not A11Y_NAME_ATTR_RE.search(m_btn.group("attrs")):
                    findings.append({"severity": "P1", "rule": "icon-button-label", "file": rel, "line": idx,
                                     "message": "Icon-only `<button>` is missing `aria-label`/`aria-labelledby` (and should expose a tooltip + shortcut)."})
            if FAKE_LIVE_PULSE_RE.search(line) and not LIVE_STATUS_A11Y_RE.search(line):
                findings.append({"severity": "P2", "rule": "no-fake-live-pulse", "file": rel, "line": idx,
                                 "message": "Avoid unwired `animate-pulse` decorative `LIVE/ONLINE/SYNCED` dots (`unslop-ui` U10); wire real state with `role='status'`."})
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
