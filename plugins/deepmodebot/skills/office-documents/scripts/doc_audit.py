#!/usr/bin/env python3
"""Deterministic zero-dependency auditor for .xlsx, .pptx, .docx, and .pdf artifacts.

    python -B doc_audit.py <file-or-dir> [--json] [--strict]
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

EXCEL_ERRORS = frozenset({"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"})
SUMMARY_LABELS_RE = re.compile(r"^\s*(?:total|subtotal|grand\s+total|net\s+income|ebitda|gross\s+profit)\b", re.I)
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def _check_ooxml_rels(zf: zipfile.ZipFile, rel_file: str, findings: list[dict]) -> None:
    names = set(zf.namelist())
    for item in names:
        if not item.endswith(".rels"):
            continue
        try:
            root = ET.fromstring(zf.read(item))
        except ET.ParseError as err:
            findings.append({"file": rel_file, "severity": "error", "rule": "ooxml-xml-parse", "message": f"{item}: {err}"})
            continue
        base_dir = posixpath.dirname(posixpath.dirname(item))
        for rel in root.findall(REL_NS):
            if rel.attrib.get("TargetMode", "").lower() == "external":
                continue
            target = rel.attrib.get("Target", "")
            if not target or target.startswith("#"):
                continue
            resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base_dir, target))
            if resolved not in names:
                findings.append({
                    "file": rel_file,
                    "severity": "error",
                    "rule": "ooxml-broken-rel",
                    "message": f"{item} references missing archive member {resolved!r}",
                })


def audit_xlsx(path: Path, rel_file: str) -> dict:
    findings: list[dict] = []
    stats = {"sheets": 0, "formulas": 0, "error_cells": 0}
    with zipfile.ZipFile(path, "r") as zf:
        _check_ooxml_rels(zf, rel_file, findings)
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sroot.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))

        sheet_files = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        stats["sheets"] = len(sheet_files)
        if not sheet_files:
            findings.append({"file": rel_file, "severity": "error", "rule": "xlsx-empty", "message": "Workbook has no worksheets"})

        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        for sf in sheet_files:
            wroot = ET.fromstring(zf.read(sf))
            for row in wroot.iter(f"{ns}row"):
                cells = list(row.findall(f"{ns}c"))
                first_text = ""
                for idx, c in enumerate(cells):
                    ref = c.attrib.get("r", "?")
                    ctype = c.attrib.get("t", "")
                    f_el = c.find(f"{ns}f")
                    v_el = c.find(f"{ns}v")
                    is_el = c.find(f"{ns}is")
                    val = (v_el.text or "").strip() if v_el is not None else ""
                    if ctype == "s" and val.isdigit() and int(val) < len(shared):
                        text_val = shared[int(val)]
                    elif ctype == "inlineStr" and is_el is not None:
                        text_val = "".join(t.text or "" for t in is_el.iter(f"{ns}t"))
                    else:
                        text_val = val
                    if idx == 0:
                        first_text = text_val
                    if f_el is not None:
                        stats["formulas"] += 1
                        ftxt = (f_el.text or "").strip()
                        if any(err in ftxt for err in EXCEL_ERRORS):
                            stats["error_cells"] += 1
                            findings.append({"file": rel_file, "severity": "error", "rule": "xlsx-formula-error", "message": f"{sf}:{ref} formula contains error literal ({ftxt})"})
                    if ctype == "e" or text_val in EXCEL_ERRORS:
                        stats["error_cells"] += 1
                        findings.append({"file": rel_file, "severity": "error", "rule": "xlsx-cell-error", "message": f"{sf}:{ref} evaluates to error {text_val!r}"})
                    if idx > 0 and SUMMARY_LABELS_RE.search(first_text) and f_el is None and val and re.fullmatch(r"-?\d+(?:\.\d+)?", val):
                        findings.append({
                            "file": rel_file,
                            "severity": "warning",
                            "rule": "xlsx-hardcoded-total",
                            "message": f"{sf}:{ref} on summary row {first_text!r} has hardcoded number {val} instead of a formula",
                        })
    return {"kind": "xlsx", "stats": stats, "findings": findings}


def audit_pptx(path: Path, rel_file: str) -> dict:
    findings: list[dict] = []
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    p_ns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    with zipfile.ZipFile(path, "r") as zf:
        _check_ooxml_rels(zf, rel_file, findings)
        slides = sorted(n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        if not slides:
            findings.append({"file": rel_file, "severity": "error", "rule": "pptx-no-slides", "message": "Presentation contains 0 slides"})
        for sl in slides:
            sroot = ET.fromstring(zf.read(sl))
            total_words = 0
            for sp in sroot.iter(f"{p_ns}sp"):
                texts = [t.text or "" for t in sp.iter(f"{a_ns}t")]
                joined = " ".join("".join(texts).split())
                words = len(joined.split())
                total_words += words
                if "{{" in joined and "}}" in joined:
                    findings.append({"file": rel_file, "severity": "error", "rule": "pptx-unfilled-placeholder", "message": f"{sl} still contains template token in {joined[:60]!r}"})
            if total_words == 0:
                findings.append({"file": rel_file, "severity": "warning", "rule": "pptx-blank-slide", "message": f"{sl} has zero text words"})
            elif total_words > 140:
                findings.append({"file": rel_file, "severity": "warning", "rule": "pptx-dense-slide", "message": f"{sl} has {total_words} words (>140 risk text overflow)"})
    return {"kind": "pptx", "stats": {"slides": len(slides)}, "findings": findings}


def audit_docx(path: Path, rel_file: str) -> dict:
    findings: list[dict] = []
    w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = 0
    with zipfile.ZipFile(path, "r") as zf:
        _check_ooxml_rels(zf, rel_file, findings)
        if "word/document.xml" not in zf.namelist():
            findings.append({"file": rel_file, "severity": "error", "rule": "docx-missing-body", "message": "Missing word/document.xml"})
        else:
            droot = ET.fromstring(zf.read("word/document.xml"))
            paragraphs = len(list(droot.iter(f"{w_ns}p")))
            body_txt = " ".join((t.text or "") for t in droot.iter(f"{w_ns}t"))
            if "{{" in body_txt and "}}" in body_txt:
                findings.append({"file": rel_file, "severity": "error", "rule": "docx-unfilled-placeholder", "message": "Document contains unfilled {{...}} placeholder tokens"})
            if not body_txt.strip():
                findings.append({"file": rel_file, "severity": "warning", "rule": "docx-empty-text", "message": "Document contains zero visible text characters"})
    return {"kind": "docx", "stats": {"paragraphs": paragraphs}, "findings": findings}


def audit_pdf(path: Path, rel_file: str) -> dict:
    findings: list[dict] = []
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        findings.append({"file": rel_file, "severity": "error", "rule": "pdf-header", "message": "File does not start with %PDF- header"})
    if b"%%EOF" not in data[-2048:]:
        findings.append({"file": rel_file, "severity": "error", "rule": "pdf-eof", "message": "PDF is truncated or missing trailing %%EOF marker"})
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", data))
    if pages == 0 and b"/Count" not in data:
        findings.append({"file": rel_file, "severity": "error", "rule": "pdf-no-pages", "message": "No PDF Page objects detected"})
    return {"kind": "pdf", "stats": {"approx_pages": pages, "bytes": len(data)}, "findings": findings}


SUPPORTED_EXTS = {".xlsx": audit_xlsx, ".pptx": audit_pptx, ".docx": audit_docx, ".pdf": audit_pdf}


def audit_path(target: Path) -> dict:
    if target.is_file():
        files = [target]
        base = target.parent
    elif target.is_dir():
        skip = {".git", "node_modules", ".scratch", ".worktrees", "__pycache__"}
        files = [
            p for p in sorted(target.rglob("*"))
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS and not (skip & set(p.relative_to(target).parts))
        ]
        base = target
    else:
        raise ValueError(f"target does not exist: {target}")

    all_findings: list[dict] = []
    checked: list[dict] = []
    for f in files:
        rel = f.name if target.is_file() else f.relative_to(base).as_posix()
        ext = f.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            raise ValueError(f"unsupported document extension {ext!r} (expected .xlsx, .pptx, .docx, .pdf)")
        try:
            res = SUPPORTED_EXTS[ext](f, rel)
            checked.append({"file": rel, "kind": res["kind"], "stats": res["stats"]})
            all_findings.extend(res["findings"])
        except (zipfile.BadZipFile, ET.ParseError, OSError) as err:
            all_findings.append({"file": rel, "severity": "error", "rule": "corrupt-container", "message": str(err)})

    errors = sum(1 for item in all_findings if item["severity"] == "error")
    warnings = sum(1 for item in all_findings if item["severity"] == "warning")
    return {
        "ok": errors == 0,
        "files_checked": len(checked),
        "errors": errors,
        "warnings": warnings,
        "documents": checked,
        "findings": all_findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        rep = audit_path(Path(args.target).resolve())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        status = "OK" if rep["ok"] and not (args.strict and rep["warnings"]) else "FAIL"
        print(f"doc-audit [{status}]: {rep['files_checked']} file(s), {rep['errors']} error(s), {rep['warnings']} warning(s)")
        for item in rep["findings"]:
            print(f"  [{item['severity'].upper()}] {item['file']} ({item['rule']}): {item['message']}")
    return 1 if (not rep["ok"] or (args.strict and rep["warnings"])) else 0


if __name__ == "__main__":
    sys.exit(main())
