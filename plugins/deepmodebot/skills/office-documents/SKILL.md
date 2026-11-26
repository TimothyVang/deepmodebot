---
name: office-documents
description: "Create, edit, extract, and verify spreadsheets (.xlsx), slide decks (.pptx), Word reports (.docx), and PDFs (.pdf) with deterministic OOXML/PDF formula and layout auditing (doc_audit.py)."
metadata:
  as-of: "2026-11-25"
---

# Office & Document Engineering (`.xlsx`, `.pptx`, `.docx`, `.pdf`)

Use when generating, editing, converting, extracting, or reviewing Excel workbooks (`.xlsx`), PowerPoint decks (`.pptx`), Word documents (`.docx`), or PDFs (`.pdf`).

## Route to the right reference

- Financial/analytical spreadsheets, live formulas, number formats, and LibreOffice recalculation → `references/spreadsheets-xlsx.md`.
- Slide decks, visual hierarchy, slide master geometry, and overflow-free layouts → `references/presentations-pptx.md`.
- Word documents (`.docx`), tracked changes/comments, and fillable/vector PDFs (`.pdf`) → `references/documents-docx-pdf.md`.

## Non-negotiable rules

1. **Run `doc_audit.py` on every produced file before reporting done.** Execute `python -B "<this skill>/scripts/doc_audit.py" <file-or-dir> --json` (`py -3 -B` on Windows; also exposed as `deepmodebot gate docs`). Zero broken OOXML relationships, zero Excel formula error tokens (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!`), zero unclosed PDF trailers, and zero silent text-overflow warnings.
2. **Formulas, never hardcoded derived numbers (`.xlsx`).** Every sum, growth rate, margin, subtotal, and cross-sheet roll-up in `.xlsx` MUST be an Excel formula (`SUM`, `INDEX`/`MATCH`, `XLOOKUP`, `SUMIFS`), never a Python-precomputed float pasted into a value cell. Color-code financial models consistently (blue = hardcoded inputs, black = same-sheet formulas, green = cross-sheet links).
3. **Preserve existing templates & OOXML parts when editing.** When modifying a user-supplied `.docx`, `.pptx`, or `.xlsx`, edit the existing workbook/document structure (styles, masters, media, relationships, tracked changes) rather than regenerating from scratch and stripping corporate branding or comments.
4. **Visually inspect rendered pages, not just XML.** After `doc_audit.py` passes structurally, render multi-page `.docx`/`.pptx`/`.pdf` outputs to page images in `<root>/.scratch/doc-preview/` (via LibreOffice `--headless --convert-to pdf` + `pdftoppm`/`pypdfium2` or Playwright print-to-PDF) when available and inspect every page for clipped text, orphan headings, overlapping shapes, and broken tables.
5. **Keep scratch conversions contained.** Write intermediate XML unpacks, PDFs, and rasterized PNGs strictly inside `<root>/.scratch/docs/`, never `/tmp` or system temp.
