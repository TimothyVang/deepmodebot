"""Unit tests for assets/setup/project_setup.py."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "project_setup.py"
SPEC = importlib.util.spec_from_file_location("project_setup_mod", MOD_PATH)
ps = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ps
SPEC.loader.exec_module(ps)


class ProjectSetupTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
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

    def test_hooks_are_not_written_where_core_hooks_path_makes_git_skip_them(self):
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=self.repo, check=True)
        res = ps.bootstrap_project(self.repo, install_hooks=True)
        note = next(a for a in res["actions"] if "pre-commit" in a)
        self.assertIn("core.hooksPath=.githooks", note)
        self.assertIn("rule_ledger.py check --root . --staged", note)
        self.assertFalse((self.repo / ".git/hooks/pre-commit").exists())

    def test_with_owner_rule_approval_on_managed_rule_files_are_proposed_not_written(self):
        rl = ps._load("dmb_rule_ledger", "rules/rule_ledger.py")
        rl.KDF_ITERATIONS = 1_000
        (self.repo / "AGENTS.md").write_text("# Team rules\n- Small PRs.\n", encoding="utf-8")
        rl.init_ledger(self.repo, "owner passphrase")
        res = ps.bootstrap_project(self.repo)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), "# Team rules\n- Small PRs.\n")
        self.assertFalse((self.repo / ".deepmodebot/policy.xml").exists())
        expected = [".deepmodebot/policy.xml", "AGENTS.md", "CLAUDE.md"]
        proposed = [a for a in res["actions"] if a.startswith("proposed ")]
        self.assertEqual([a.split()[1] for a in proposed], expected)
        self.assertEqual(sorted(p["item"] for p in rl.load_proposals(self.repo)), expected)


if __name__ == "__main__":
    unittest.main()
