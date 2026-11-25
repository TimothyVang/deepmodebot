"""Unit tests for plugins/deepmodebot/skills/frontend-ui/scripts/ui_audit.py."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT / "plugins/deepmodebot/skills/frontend-ui/scripts/ui_audit.py"
SPEC = importlib.util.spec_from_file_location("ui_audit_mod", AUDIT_PATH)
ui_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ui_audit
SPEC.loader.exec_module(ui_audit)


class UiAuditTests(unittest.TestCase):
    def test_flags_transition_all_missing_focus_reduced_motion_and_alt(self):
        bad_html = """<!doctype html>
<html>
<head><style>
.btn { transition: all 200ms ease-in; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); }
</style></head>
<body><button class="btn bg-zinc-900">Go</button><img src="a.png"></body>
</html>"""
        findings = ui_audit.audit_source(bad_html, "index.html", ".html")
        rules = {f["rule"] for f in findings}
        self.assertIn("no-transition-all", rules)
        self.assertIn("no-ease-in-ui", rules)
        self.assertIn("semantic-color-tokens", rules)
        self.assertIn("img-alt", rules)
        self.assertIn("html-lang", rules)
        self.assertIn("meta-viewport", rules)
        self.assertIn("focus-visible", rules)
        self.assertIn("reduced-motion", rules)
        self.assertIn("oklch-ambient-shadow", rules)

    def test_clean_oklch_document_passes(self):
        good_html = """<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
.btn { transition: transform 120ms ease-out; box-shadow: 0 1px 2px oklch(0 0 0 / 0.04); }
:focus-visible { outline: 2px solid var(--accent); }
@media (prefers-reduced-motion: reduce) { .btn { transition: none; } }
</style></head>
<body><button class="btn">Save changes</button><img src="a.png" alt="Preview"></body>
</html>"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clean.html"
            p.write_text(good_html, encoding="utf-8")
            report = ui_audit.audit_path(p)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["findings"], [])


if __name__ == "__main__":
    unittest.main()
