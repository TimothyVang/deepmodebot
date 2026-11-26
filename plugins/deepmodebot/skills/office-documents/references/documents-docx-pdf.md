# Word Documents (`.docx`) & PDFs (`.pdf`)

Checked as of 2026-11-25.

## 1. Word Documents (`.docx`)

- **Tool choice:** `python-docx` (Python) or `docx` npm package (TypeScript/Node) for generating clean structured `.docx` files; direct OOXML (`zipfile` + `lxml`/`ElementTree` on `word/document.xml`) when inserting OOXML `<w:ins>` / `<w:del>` tracked redlines or preserving complex custom elements `python-docx` does not wrap.
- **Semantic styles over inline font hacks:** Use built-in/template paragraph styles (`Heading 1`, `Heading 2`, `Normal`, `List Bullet`) so Word's Navigation Pane and Table of Contents (`TOC`) work natively. Never build tables with space-padded plain text or fake headings by bolding `Normal` paragraphs.
- **Tables & page breaks:** Set explicit column widths on every cell (`w:tcW`), repeat table header rows across page breaks (`w:tblHeader`), and set `keep_with_next = True` on all headings so a heading is never stranded at the bottom of a page.

## 2. PDFs (`.pdf`)

- **Reading & extraction:** `pypdf` / `pypdfium2` / `pdfplumber` (tables & bounding boxes); use OCR (`pytesseract` / vision) only on scanned image-only pages where extracted text is empty.
- **Generating new PDFs:** Prefer HTML+CSS `@page` rendered via Playwright/Chromium `page.pdf()` (or Typst / WeasyPrint / ReportLab `platypus`) over low-level manual `(x, y)` canvas drawing, which frequently overlaps lines on variable-length text.
- **Merging, splitting & AcroForm filling:** Use `pypdf` (`PdfReader` / `PdfWriter`) to inspect form fields (`get_fields()`), populate AcroForm widgets (`update_page_form_field_values`), set `/NeedAppearances` or flatten cleanly, and verify page count and extracted text on the output PDF with `doc_audit.py`.
