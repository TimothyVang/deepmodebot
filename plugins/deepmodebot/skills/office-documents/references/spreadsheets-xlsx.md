# Spreadsheets (`.xlsx`) — Formulas, Modeling & Recalculation

Checked as of 2026-11-25.

## 1. Tool choice

- **Authoring & editing `.xlsx` in Python:** `openpyxl` (preserves existing styles, formulas, named ranges, and sheets; load with `load_workbook(path, data_only=False)` when editing so formulas are never overwritten with cached values!). For write-only multi-sheet reports from scratch with rich conditional formatting and charts, `xlsxwriter` is fast and clean.
- **Data analysis / bulk tabular IO:** `polars` or `pandas` + `fastexcel`/`calamine` for reading; never write analytical models back with plain `df.to_excel()` when formulas, column widths, frozen headers, or number formats are needed.

## 2. Dynamic formulas & financial conventions

- **Never hardcode calculated outputs:** Any total, subtotal, variance, CAGR, ratio, or cross-sheet reference must be written as a string starting with `=` (`ws["B12"] = "=SUM(B4:B11)"`). `doc_audit.py` flags summary rows (`Total`, `Subtotal`, `Net`, `EBITDA`, `Margin`) that contain raw numeric literals instead of `<f>` formula elements.
- **Explicit number formatting:** Apply Excel number format codes to every numeric cell: currency `#,##0;(#,##0);"-"`, percentages `0.0%`, multiples `0.0"x"`, dates `yyyy-mm-dd`, integers `#,##0`.
- **Column widths & layout:** Auto-fit every column width (`max_chars + 4`, minimum `10`), freeze header panes (`ws.freeze_panes = "B2"`), disable gridlines on executive summary tabs when appropriate (`ws.views.sheetView[0].showGridLines = True/False`), and keep one table/grain per worksheet.
- **Recalculation proof:** `openpyxl` writes `<f>` tags without evaluating cached `<v>` values. Whenever LibreOffice (`soffice --headless --convert-to xlsx` or `pdf`) is installed, recalculate in `.scratch/` and re-run `doc_audit.py` so cached `<v>` cells exist and zero `#REF!`/`#DIV/0!`/`#NAME?` errors appear.
