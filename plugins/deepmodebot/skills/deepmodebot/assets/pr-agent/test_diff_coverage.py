"""Unit tests for diff_coverage.py."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "diff_coverage.py"


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True, text=True,
    )
    return res.stdout


def remove_tree(path: Path) -> None:
    for folder, _, files in os.walk(path):
        for name in files:
            os.chmod(os.path.join(folder, name), stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(path, ignore_errors=True)


class DiffCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="diff-cov-")).resolve()
        self.addCleanup(remove_tree, self.tmp)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "src").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / "src" / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
        (self.repo / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "package-lock.json").write_text("{}", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(TOOL), *args],
            cwd=self.repo, capture_output=True, text=True,
        )

    def test_plan_excludes_deleted_lockfile_and_groups_by_rule(self) -> None:
        (self.repo / "src" / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        (self.repo / "src" / "auth.py").write_text("def verify(tok):\n    return bool(tok)\n", encoding="utf-8")
        (self.repo / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        (self.repo / "package-lock.json").write_text('{"v": 2}', encoding="utf-8")
        (self.repo / "src" / "old.py").unlink()
        git(self.repo, "add", "src/app.py", "src/old.py", "package-lock.json")

        plan_file = self.tmp / "plan.json"
        run = self.run_tool("plan", str(self.repo), "--include-untracked", "--out", str(plan_file), "--json")
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(run.stdout)
        self.assertEqual(data["reviewable_count"], 3)
        self.assertEqual(data["excluded_count"], 2)
        excluded_reasons = {x["path"]: x["reason"] for x in data["excluded"]}
        self.assertEqual(excluded_reasons["package-lock.json"], "lockfile")
        self.assertEqual(excluded_reasons["src/old.py"], "deleted")
        groups = {b["rule_group"] for b in data["batches"]}
        self.assertEqual(groups, {"auth_security", "backend_core", "tests"})

    def test_verify_fails_on_missing_file_or_out_of_range_line(self) -> None:
        (self.repo / "src" / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        (self.repo / "src" / "auth.py").write_text("def verify(tok):\n    return bool(tok)\n", encoding="utf-8")
        plan_file = self.tmp / "plan.json"
        self.run_tool("plan", str(self.repo), "--include-untracked", "--out", str(plan_file))

        bad_cov = self.run_tool("verify", str(plan_file), "--reviewed", "src/app.py", "--json")
        self.assertEqual(bad_cov.returncode, 1)
        self.assertEqual(json.loads(bad_cov.stdout)["missing_files"], ["src/auth.py"])

        findings = self.tmp / "findings.json"
        findings.write_text(json.dumps([{"path": "src/app.py", "line": 99}]), encoding="utf-8")
        bad_pos = self.run_tool("verify", str(plan_file), "--all-reviewed", "--findings", str(findings), "--json")
        self.assertEqual(bad_pos.returncode, 1)
        self.assertIn("out of range", bad_pos.stdout)

        findings.write_text(json.dumps([{"path": "src/app.py", "start_line": 1, "end_line": 2}]), encoding="utf-8")
        good = self.run_tool("verify", str(plan_file), "--all-reviewed", "--findings", str(findings), "--json")
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(json.loads(good.stdout)["coverage_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
