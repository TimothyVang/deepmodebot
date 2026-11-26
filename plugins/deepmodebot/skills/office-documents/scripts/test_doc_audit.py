"""Unit tests for doc_audit.py (.xlsx, .pptx, .docx, .pdf)."""
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("doc_audit", HERE / "doc_audit.py")
da = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = da
spec.loader.exec_module(da)


class DocAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_xlsx_catches_ref_errors_and_hardcoded_totals_and_passes_formulas(self):
        good = self.root / "good.xlsx"
        with zipfile.ZipFile(good, "w") as zf:
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Total</t></is></c>'
                '<c r="B1"><f>SUM(B2:B5)</f><v>100</v></c></row></sheetData></worksheet>',
            )
        rep_good = da.audit_path(good)
        self.assertTrue(rep_good["ok"])
        self.assertEqual(rep_good["warnings"], 0)

        bad = self.root / "bad.xlsx"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Total Revenue</t></is></c>'
                '<c r="B1"><v>500</v></c><c r="C1" t="e"><v>#REF!</v></c></row></sheetData></worksheet>',
            )
        rep_bad = da.audit_path(bad)
        self.assertFalse(rep_bad["ok"])
        rules = {f["rule"] for f in rep_bad["findings"]}
        self.assertIn("xlsx-cell-error", rules)
        self.assertIn("xlsx-hardcoded-total", rules)

    def test_pptx_docx_and_pdf_checks(self):
        pptx = self.root / "deck.pptx"
        with zipfile.ZipFile(pptx, "w") as zf:
            zf.writestr(
                "ppt/slides/slide1.xml",
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                '<p:sp><a:t>Hello {{CLIENT_NAME}}</a:t></p:sp></p:sld>',
            )
        self.assertFalse(da.audit_path(pptx)["ok"])

        pdf_ok = self.root / "ok.pdf"
        pdf_ok.write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Page >> endobj\n%%EOF\n")
        self.assertTrue(da.audit_path(pdf_ok)["ok"])

        pdf_bad = self.root / "bad.pdf"
        pdf_bad.write_bytes(b"%PDF-1.7\ntruncated without eof")
        self.assertFalse(da.audit_path(pdf_bad)["ok"])


if __name__ == "__main__":
    unittest.main()
