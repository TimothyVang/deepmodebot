"""Unit tests for seo_audit.py."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("seo_audit", HERE / "seo_audit.py")
seo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = seo
spec.loader.exec_module(seo)

CLEAN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acme Cloud Backup — Zero-Trust Incremental Snapshots</title>
  <meta name="description" content="Acme Cloud Backup captures encrypted incremental snapshots for Postgres and S3 in under ten seconds with verifiable restore proofs.">
  <link rel="canonical" href="https://acme.example/docs">
  <meta property="og:title" content="Acme Cloud Backup">
  <meta property="og:description" content="Encrypted incremental snapshots with verifiable restore proofs.">
  <meta property="og:image" content="https://acme.example/og.png">
  <script type="application/ld+json">
  {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Acme Cloud Backup"}
  </script>
</head>
<body>
  <h1>Acme Cloud Backup</h1>
  <h2>How incremental snapshots work</h2>
  <img src="/diagram.svg" alt="Snapshot pipeline diagram" width="800" height="450">
  <a href="/docs/quickstart">Read the quickstart guide</a>
  <form>
    <label for="email">Work email</label>
    <input id="email" type="email">
  </form>
</body>
</html>
"""


class SeoAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_clean_site_passes_with_zero_errors_and_warnings(self):
        (self.root / "index.html").write_text(CLEAN_HTML, encoding="utf-8")
        (self.root / "robots.txt").write_text(
            "User-agent: OAI-SearchBot\nAllow: /\nUser-agent: GPTBot\nDisallow: /private/\nSitemap: https://acme.example/sitemap.xml\n",
            encoding="utf-8",
        )
        (self.root / "sitemap.xml").write_text("<urlset></urlset>\n", encoding="utf-8")
        (self.root / "llms.txt").write_text(
            "# Acme Cloud Backup\n\n> Encrypted Postgres and S3 snapshots with restore proofs.\n\n## Docs\n- [Quickstart](https://acme.example/docs): Install in 2 minutes.\n",
            encoding="utf-8",
        )
        rep = seo.audit_target(self.root)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["errors"], 0)
        self.assertEqual(rep["warnings"], 0)

    def test_catches_broken_html_json_ld_and_unlabeled_agentic_forms(self):
        bad = """<!doctype html><html><head><title>Hi</title>
        <script type="application/ld+json">{bad json}</script></head>
        <body><h3>Skipped H1</h3><img src="x.png"><a href="/x">click here</a><input type="text"></body></html>"""
        p = self.root / "bad.html"
        p.write_text(bad, encoding="utf-8")
        rep = seo.audit_target(p)
        self.assertFalse(rep["ok"])
        rules = {f["rule"] for f in rep["findings"]}
        self.assertTrue({"html-lang", "meta-description", "viewport", "h1-missing", "img-alt", "json-ld-parse"} <= rules)
        self.assertIn("agentic-form-labels", rules)
        self.assertIn("anchor-text", rules)


if __name__ == "__main__":
    unittest.main()
