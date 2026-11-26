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


if __name__ == "__main__":
    unittest.main()
