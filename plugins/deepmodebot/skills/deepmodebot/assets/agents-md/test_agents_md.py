"""Tests for agents_md.py, run against throwaway git repos.

Run: python -m unittest discover -s <this folder> -p "test_*.py"
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "agents_md.py"
BEGIN = "<!-- deepmodebot:begin"


def remove_tree(path):
    for folder, _, files in os.walk(path):
        for name in files:
            os.chmod(os.path.join(folder, name), stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(path, ignore_errors=True)


class AgentsMdCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agents-md-test-")).resolve()
        self.addCleanup(remove_tree, self.tmp)
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run"}}),
                                                encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def run_tool(self, *args):
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        return subprocess.run([sys.executable, str(TOOL), *args], cwd=self.repo, env=env, capture_output=True, text=True)

    def read(self, name):
        return (self.repo / name).read_text(encoding="utf-8")

    def test_build_creates_both_files_with_the_finish_line_and_the_repos_real_checks(self):
        run = self.run_tool("build", ".")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        agents = self.read("AGENTS.md")
        self.assertIn("## Finish line", agents)
        self.assertIn('"4 of 9 done"', agents)
        self.assertIn("`npm run lint`", agents)
        self.assertIn("`npm test`", agents)
        self.assertIn("@AGENTS.md", self.read("CLAUDE.md"))
        self.assertNotIn("Finish line", self.read("CLAUDE.md"))
        self.assertEqual(self.run_tool("check", ".").returncode, 0)

    def test_a_repo_with_only_a_check_script_is_not_told_it_has_no_tests(self):
        (self.repo / "package.json").unlink()
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")
        self.run_tool("build", ".")
        agents = self.read("AGENTS.md")
        self.assertIn("before calling a part done: `python scripts/check.py`", agents)
        self.assertNotIn("No test command was found", agents)

    def test_build_is_idempotent(self):
        self.run_tool("build", ".")
        first = (self.read("AGENTS.md"), self.read("CLAUDE.md"))
        again = self.run_tool("build", ".")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("up to date", again.stdout)
        self.assertEqual((self.read("AGENTS.md"), self.read("CLAUDE.md")), first)

    def test_existing_text_is_kept_and_a_stale_block_is_refreshed_in_place(self):
        (self.repo / "AGENTS.md").write_text("# Team rules\n\nUse tabs.\n", encoding="utf-8")
        self.run_tool("build", ".")
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"typecheck": "tsc", "test": "vitest"}}),
                                                encoding="utf-8")
        stale = self.run_tool("check", ".")
        self.assertEqual(stale.returncode, 1)
        self.assertIn("AGENTS.md", stale.stdout)
        self.run_tool("build", ".")
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith("# Team rules\n\nUse tabs.\n"))
        self.assertEqual(agents.count(BEGIN), 1)
        self.assertIn("`npm run typecheck`", agents)
        self.assertNotIn("`npm run lint`", agents)

    def test_claude_md_that_already_imports_agents_md_is_left_alone(self):
        original = "# Claude notes\n\n@AGENTS.md\n\nPrefer small diffs.\n"
        (self.repo / "CLAUDE.md").write_text(original, encoding="utf-8")
        self.assertEqual(self.run_tool("build", ".").returncode, 0)
        self.assertEqual(self.read("CLAUDE.md"), original)

    def test_overwrite_replaces_whole_files_after_backing_them_up(self):
        (self.repo / "AGENTS.md").write_text("# Old\n\nUse tabs.\n", encoding="utf-8")
        run = self.run_tool("build", ".", "--overwrite")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("Use tabs.", self.read("AGENTS.md"))
        backups = list((self.repo / ".scratch" / "agents-md-backup").rglob("AGENTS.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "# Old\n\nUse tabs.\n")
        self.assertEqual(subprocess.run(["git", "-C", str(self.repo), "check-ignore", "-q", str(backups[0])]).returncode, 0)

    def test_dry_run_writes_nothing(self):
        run = self.run_tool("build", ".", "--dry-run")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("## Finish line", run.stdout)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / "CLAUDE.md").exists())

    def test_a_begin_marker_without_an_end_marker_is_an_error(self):
        (self.repo / "AGENTS.md").write_text("<!-- deepmodebot:begin -->\nhalf a block\n", encoding="utf-8")
        run = self.run_tool("build", ".")
        self.assertEqual(run.returncode, 1)
        self.assertIn("end marker", run.stderr)

    def test_a_symlinked_instruction_file_is_refused(self):
        target = self.tmp / "elsewhere.md"
        target.write_text("outside\n", encoding="utf-8")
        try:
            os.symlink(target, self.repo / "AGENTS.md")
        except OSError:
            self.skipTest("symlinks need privileges on this machine")
        run = self.run_tool("build", ".")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "outside\n")

    def test_user_previews_by_default_and_writes_only_with_write(self):
        claude_dir = self.home / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Mine\n\nKeep me.\n", encoding="utf-8")
        preview = self.run_tool("user")
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        self.assertIn("## Finish line", preview.stdout)
        self.assertEqual((claude_dir / "CLAUDE.md").read_text(encoding="utf-8"), "# Mine\n\nKeep me.\n")
        wrote = self.run_tool("user", "--write")
        self.assertEqual(wrote.returncode, 0, wrote.stdout + wrote.stderr)
        text = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Mine\n\nKeep me.\n"))
        self.assertIn("## Finish line", text)
        self.assertNotIn("npm", text)

    def test_enforces_local_ci_policy_and_memory_when_deepmodebot_dir_exists(self):
        dm = self.repo / ".deepmodebot"
        dm.mkdir()
        (dm / "ci.yml").write_text("name: test\njobs:\n  ok:\n    steps:\n      - run: echo ok\n", encoding="utf-8")
        (dm / "policy.xml").write_text('<deepmode-policy version="1.0"/>\n', encoding="utf-8")
        run = self.run_tool("build", ".")
        self.assertEqual(run.returncode, 0, run.stderr)
        agents = self.read("AGENTS.md")
        self.assertIn(".deepmodebot/ci.yml", agents)
        self.assertIn(".deepmodebot/policy.xml", agents)
        self.assertIn("deepmode-memory.db", agents)
        self.assertIn("@AGENTS.md", self.read("CLAUDE.md"))


if __name__ == "__main__":
    unittest.main()
