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

    def test_flags_layout_transition_circular_checkbox_unlabeled_icon_btn_and_pure_black(self):
        bad_tsx = """export function Toolbar() {
  return (
    <div className="bg-black">
      <input type="checkbox" className="w-4 h-4 rounded-full" />
      <button className="icon-btn"><svg viewBox="0 0 16 16"><path d="M0 0h16v16H0z"/></svg></button>
    </div>
  );
}"""
        findings = ui_audit.audit_source(bad_tsx, "Toolbar.tsx", ".tsx")
        by_rule = {f["rule"]: f["severity"] for f in findings}
        self.assertEqual(by_rule.get("no-pure-black-surface"), "P1")
        self.assertEqual(by_rule.get("checkbox-not-circular"), "P1")
        self.assertEqual(by_rule.get("icon-button-label"), "P1")

        bad_css = """.drawer { transition: width 220ms ease-out; background: #000000; transform: scale(0); }
:focus-visible { outline: 2px solid var(--accent); }
@media (prefers-reduced-motion: reduce) { .drawer { transition: none; } }"""
        css_findings = ui_audit.audit_source(bad_css, "drawer.css", ".css")
        css_by_rule = {f["rule"]: f["severity"] for f in css_findings}
        self.assertEqual(css_by_rule.get("no-layout-transition"), "P1")
        self.assertEqual(css_by_rule.get("no-pure-black-surface"), "P1")
        self.assertEqual(css_by_rule.get("no-scale-zero-entry"), "P1")

    def test_legitimate_buttons_styles_and_comments_do_not_false_positive(self):
        legit_tsx = """/* never use transition: width 200ms; background: #000000; transform: scale(0); */
export function SelectRow({ x, y }: { x: number; y: number }) {
  return (
    <div>
      <button type="button"><svg viewBox="0 0 16 16"></svg> English (US) <svg viewBox="0 0 12 12"></svg></button>
      <label><input type="checkbox" className="rounded-sm" /><span className="rounded-full">12</span></label>
      <div style={{ transition: "transform 150ms ease-out", width: 260, top: y, left: x }}>Menu</div>
    </div>
  );
}"""
        self.assertEqual(ui_audit.audit_source(legit_tsx, "SelectRow.tsx", ".tsx"), [])

        legit_css = """.badge-light { background: #ffffff; color: #000000; }
.avatar:hover { filter: grayscale(0); transform: scale(0.98); }
.btn { transition: transform 150ms ease-out } .card { padding: 16px; }
:focus-visible { outline: 2px solid var(--accent); }
@media (prefers-reduced-motion: reduce) { .btn { transition: none; } }"""
        self.assertEqual(ui_audit.audit_source(legit_css, "legit.css", ".css"), [])

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
