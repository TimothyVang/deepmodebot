"""Unit tests for assets/setup/project_setup.py."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "project_setup.py"
SPEC = importlib.util.spec_from_file_location("project_setup_mod", MOD_PATH)
ps = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ps
SPEC.loader.exec_module(ps)


class ProjectSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dmb-setup-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "demo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        (self.repo / "package.json").write_text(
            json.dumps({"name": "demo", "scripts": {"test": "node -e \"console.log('ok')\""}}),
            encoding="utf-8",
        )

    def test_bootstrap_creates_ci_policy_memory_and_agents_claude_idempotently(self):
        before = ps.check_setup(self.repo)
        self.assertFalse(before["initialized"])
        self.assertIn(".deepmodebot/ci.yml", before["missing"])

        res1 = ps.bootstrap_project(self.repo)
        self.assertTrue(res1["ok"])
        self.assertTrue((self.repo / ".deepmodebot/ci.yml").is_file())
        self.assertTrue((self.repo / ".deepmodebot/policy.xml").is_file())
        self.assertTrue((self.repo / ".scratch/deepmode-memory.db").is_file())
        agents = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        claude = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".deepmodebot/ci.yml", agents)
        self.assertIn(".deepmodebot/policy.xml", agents)
        self.assertIn("deepmode-memory.db", agents)
        self.assertIn("@AGENTS.md", claude)

        after = ps.check_setup(self.repo)
        self.assertTrue(after["initialized"], after)
        res2 = ps.bootstrap_project(self.repo)
        self.assertEqual(res2["actions"], [])

        res3 = ps.bootstrap_project(self.repo, with_dependabot=True)
        self.assertIn("created .github/dependabot.yml", res3["actions"])
        dep = (self.repo / ".github/dependabot.yml").read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "npm"', dep)
        self.assertIn("default-days: 7", dep)

        res4 = ps.bootstrap_project(self.repo, install_hooks=True)
        self.assertIn("installed .git/hooks/pre-commit", res4["actions"])
        hook = (self.repo / ".git/hooks/pre-commit").read_text(encoding="utf-8")
        self.assertIn("deepmodebot:slop-gate", hook)

if __name__ == "__main__":
    unittest.main()
