"""Tests for cross-platform static_sec_audit.py."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("static_sec_audit", HERE / "static_sec_audit.py")
ssa = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ssa
spec.loader.exec_module(ssa)


class StaticSecAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_catches_gha_prt_injection_and_unpinned_action(self):
        wf = self.root / ".github" / "workflows" / "pr.yml"
        wf.parent.mkdir(parents=True)
        wf.write_text(
            "on:\n  pull_request_target:\njobs:\n  build:\n    steps:\n"
            "      - uses: some-org/custom-action@v1\n"
            "        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n"
            "      - run: echo \"${{ github.event.pull_request.title }}\"\n",
            encoding="utf-8",
        )
        rep = ssa.scan_repo(self.root)
        self.assertFalse(rep["ok"])
        rules = {f["rule"] for f in rep["findings"]}
        self.assertTrue({"gha-prt-untrusted-checkout", "gha-unpinned-action", "gha-script-injection"} <= rules)

    def test_catches_code_sharp_edges_and_passes_safe_patterns(self):
        app = self.root / "service.py"
        app.write_text(
            "import yaml\n"
            "def bad(raw, expected_hmac, user_sig, cursor, uid):\n"
            "    cfg = yaml.load(raw)\n"
            "    if expected_hmac == user_sig:\n"
            "        cursor.execute(f'SELECT * FROM users WHERE id = {uid}')\n"
            "    return cfg\n",
            encoding="utf-8",
        )
        rep = ssa.scan_repo(self.root)
        self.assertFalse(rep["ok"])
        rules = {f["rule"] for f in rep["findings"]}
        self.assertTrue({"unsafe-yaml-load", "non-constant-time-secret-eq", "sql-fstring-interpolation"} <= rules)

        safe = self.root / "safe.py"
        app.unlink()
        safe.write_text(
            '"""Docstring mentioning yaml.load(raw) should never trigger."""\n'
            "import hmac, yaml\n"
            "def ok(raw, expected_hmac, user_sig, cursor, uid):\n"
            "    cfg = yaml.safe_load(raw)\n"
            "    if hmac.compare_digest(expected_hmac, user_sig):\n"
            "        cursor.execute('SELECT * FROM users WHERE id = ?', (uid,))\n"
            "    return cfg\n",
            encoding="utf-8",
        )
        rep2 = ssa.scan_repo(self.root)
        self.assertTrue(rep2["ok"])
        self.assertEqual(rep2["errors"], 0)


    def test_catches_client_bundle_secrets_browser_llm_keys_and_wrangler_vars(self):
        (self.root / "web.tsx").write_text(
            "const key = process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;\n"
            "const pub = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;\n"
            "const client = new OpenAI({ apiKey: pub, dangerouslyAllowBrowser: true });\n",
            encoding="utf-8",
        )
        (self.root / "wrangler.jsonc").write_text(
            '{\n  // comment\n  "vars": {\n    "API_BASE_URL": "https://api.example.com",\n    "STRIPE_SECRET_KEY": "sk-test-1234567890",\n    "API_KEY_HEADER": "x-api-key",\n    "PASSWORD_POLICY": "strong-12-char"\n  }\n}\n',
            encoding="utf-8",
        )
        rep = ssa.scan_repo(self.root)
        self.assertFalse(rep["ok"])
        by_rule = [(f["rule"], f["line"]) for f in rep["findings"]]
        self.assertIn(("client-bundle-secret-env", 1), by_rule)
        self.assertNotIn(("client-bundle-secret-env", 2), by_rule)
        self.assertIn(("llm-sdk-browser-key-exposure", 3), by_rule)
        self.assertIn(("wrangler-vars-secret", 5), by_rule)
        self.assertNotIn(("wrangler-vars-secret", 6), by_rule)
        self.assertNotIn(("wrangler-vars-secret", 7), by_rule)

if __name__ == "__main__":
    unittest.main()
