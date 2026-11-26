"""Behavioral red-to-green tests for assets/local-ci/slop_gate.py."""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "slop_gate.py"
SPEC = importlib.util.spec_from_file_location("slop_gate_mod", MOD_PATH)
sg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sg
SPEC.loader.exec_module(sg)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=30)


class SlopGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="slop-gate-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test")
        (self.repo / ".deepmodebot").mkdir()
        (self.repo / ".deepmodebot/ci.yml").write_text("name: demo\njobs:\n  ok:\n    steps:\n      - run: echo ok\n", encoding="utf-8")
        (self.repo / ".deepmodebot/policy.xml").write_text(
            '<deepmode-policy version="1.0">\n'
            '  <boundaries><forbid from="ui/*" to="db/*" reason="UI must not import DB directly"/></boundaries>\n'
            '  <budgets><file path="AGENTS.md" max-lines="10"/></budgets>\n'
            '</deepmode-policy>\n',
            encoding="utf-8",
        )
        (self.repo / "AGENTS.md").write_text("# Rules\nKeep clean.\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "init")

    def test_blocks_secrets_slop_test_theater_unsafe_casts_boundaries_budgets_and_config_tamper(self):
        fake_aws = "AKIA" + "1234567890ABCDEF"
        (self.repo / "ui").mkdir(exist_ok=True)
        (self.repo / "ui/view.py").write_text(
            "import db.store\n"
            f"TOKEN = '{fake_aws}'\n"
            "def run():\n"
            "    try:\n"
            "        subprocess.run(['echo', 'hi'])\n"
            "    except Exception:\n"
            "        pass\n"
            "    x = 1  # noqa\n",
            encoding="utf-8",
        )
        (self.repo / "ui/widget.ts").write_text(
            "export const x = (v: unknown) => (v as any).foo;\n"
            "export const leaked = process.env.NEXT_PUBLIC_STRIPE_SECRET_KEY;\n"
            "export const llm = { dangerouslyAllowBrowser: true };\n"
            "export class Counter implements DurableObject {}\n"
            "export function handle(ctx: any) { const { waitUntil } = ctx; return waitUntil; }\n",
            encoding="utf-8",
        )
        (self.repo / "test_fake.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_empty(self):\n"
            "        pass\n"
            "    def test_tautology(self):\n"
            "        assert True\n"
            "        self.assertEqual(1, 1)\n"
            "    def test_no_assert(self):\n"
            "        x = 2 + 2\n",
            encoding="utf-8",
        )
        (self.repo / "AGENTS.md").write_text("\n".join(f"line {i}" for i in range(15)) + "\n", encoding="utf-8")
        (self.repo / ".deepmodebot/ci.yml").write_text("name: weakened\n", encoding="utf-8")

        res = sg.run_slop_gate(self.repo, run_linters=False, record_memory=True)
        self.assertFalse(res["ok"])
        rules = {f["rule"] for f in res["findings"]}
        self.assertIn("config-tamper-lock", rules)
        self.assertIn("secret-aws-key", rules)
        self.assertIn("suppression-comment", rules)
        self.assertIn("swallowed-exception", rules)
        self.assertIn("safety-subprocess-timeout", rules)
        self.assertIn("ts-unsafe-cast", rules)
        self.assertIn("client-env-secret", rules)
        self.assertIn("llm-browser-key-exposure", rules)
        self.assertIn("workers-legacy-implements-do", rules)
        self.assertIn("workers-ctx-destructure", rules)
        self.assertIn("test-theater-empty", rules)
        self.assertIn("test-theater-tautology", rules)
        self.assertIn("test-theater-no-assert", rules)
        self.assertIn("boundary-violation", rules)
        self.assertIn("budget-max-lines", rules)
        self.assertTrue((self.repo / ".scratch/deepmode-memory.db").is_file())

    def test_clean_change_passes_and_ruff_catches_unused_import_when_installed(self):
        (self.repo / "app.py").write_text("import json\n\ndef fmt(x):\n    return str(x)\n", encoding="utf-8")
        if shutil.which("ruff"):
            bad = sg.run_slop_gate(self.repo, run_linters=True)
            self.assertFalse(bad["ok"], bad)
            self.assertIn("ruff-F401", {f["rule"] for f in bad["findings"]})

        (self.repo / "app.py").write_text("def fmt(x):\n    return str(x)\n", encoding="utf-8")
        good = sg.run_slop_gate(self.repo, run_linters=True)
        self.assertTrue(good["ok"], good)
        self.assertEqual(good["findings"], [])


if __name__ == "__main__":
    unittest.main()
