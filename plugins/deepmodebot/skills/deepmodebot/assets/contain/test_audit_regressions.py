"""Regression tests for Shard 4 P1 fixes in gate.cjs, wizard.sh, pr_agent_local.py, and trending.py."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent
SKILL_ROOT = ASSETS.parent


def find_bash():
    bash = shutil.which("bash")
    if os.name != "nt" or (bash and "system32" not in bash.lower()):
        return bash
    git_exe = shutil.which("git")
    for rel in ("../bin/bash.exe", "../usr/bin/bash.exe", "../../bin/bash.exe"):
        candidate = os.path.normpath(os.path.join(os.path.dirname(git_exe), rel)) if git_exe else ""
        if candidate and os.path.exists(candidate):
            return candidate
    return None


@unittest.skipUnless(shutil.which("node"), "node is not on PATH")
class SecurityAuditGateTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        self.gate = ASSETS / "security-audit" / "gate.cjs"
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.out = self.tmp / "out"
        self.skill = self.tmp / "skill"
        self.out.mkdir()
        self.skill.mkdir()
        (self.skill / "validate-findings.cjs").write_text("process.exit(0);\n", encoding="utf-8")

    def run_gate(self, *extra_args):
        return subprocess.run(
            [self.node, str(self.gate), str(self.out), str(self.skill), *extra_args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_invalid_block_arg_fails_closed_with_exit_2(self):
        proc = self.run_gate("high", "maybe")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("block-on-unvalidated", proc.stderr)

    def test_case_insensitive_severity_blocks_and_sanitizes_markdown(self):
        (self.out / "run-metadata.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")
        findings = [{
            "verdict": "confirmed",
            "title": "SQLi | injection",
            "fingerprint": "fp`evil`\nbreak",
            "severity": {"overall_severity": "High"},
            "trace": [{"kind": "sink", "file": "app`bad`.py", "line": 12}],
            "remediation": {"strategy": "Use params"},
        }]
        (self.out / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        proc = self.run_gate("high", "true")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("**Blocked.**", proc.stdout)
        self.assertNotIn("app`bad`.py", proc.stdout)
        self.assertIn("app'bad'.py:12", proc.stdout)


@unittest.skipUnless(find_bash(), "bash is not available")
class WizardTests(unittest.TestCase):
    def test_wiz_env_keeps_temp_beside_env_file_and_handles_crlf_and_multiline(self):
        wizard = (ASSETS / "wizard" / "wizard.sh").read_text(encoding="utf-8")
        # Extract helper section up to main() so we can source functions directly in bash.
        helpers = wizard.split("\nmain() {", 1)[0]
        with tempfile.TemporaryDirectory(prefix="wiz-test-") as tmp:
            root = Path(tmp)
            helper_sh = root / "helpers.sh"
            helper_sh.write_text(helpers + "\n", encoding="utf-8", newline="\n")
            env_file = root / "sub" / ".env"
            env_file.parent.mkdir()
            env_file.write_bytes(b"API_KEY='saved-crlf'\r\nMULTI='line1\nline2'\r\nOTHER='keep'\r\n")
            script = (
                f'source "{helper_sh.as_posix()}"\n'
                f'ENV_FILE="{env_file.as_posix()}"\n'
                'v="$(wiz_saved API_KEY)"\n'
                'printf "SAVED=%s\\n" "$v"\n'
                'wiz_env MULTI "single-now"\n'
            )
            proc = subprocess.run([find_bash(), "-c", script], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("SAVED=saved-crlf", proc.stdout)
            updated = env_file.read_text(encoding="utf-8")
            self.assertNotIn("line2", updated)
            self.assertIn("MULTI='single-now'", updated)
            self.assertIn("OTHER='keep'", updated)
            # No leftover temp files beside .env.
            self.assertEqual([p.name for p in env_file.parent.iterdir()], [".env"])


class PrAgentAndTrendingUnitTests(unittest.TestCase):
    def test_pr_agent_scrubbed_env_and_flatten_defang(self):
        spec = importlib.util.spec_from_file_location("pr_agent_local_test", ASSETS / "pr-agent" / "pr_agent_local.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        old = dict(os.environ)
        try:
            os.environ["ANTHROPIC_API_KEY"] = "secret"
            os.environ["GITHUB_TOKEN"] = "gh-secret"
            os.environ["SAFE_VAR"] = "ok"
            scrubbed = mod.scrubbed_env(github=False)
            self.assertNotIn("ANTHROPIC_API_KEY", scrubbed)
            self.assertNotIn("GITHUB_TOKEN", scrubbed)
            self.assertEqual(scrubbed.get("SAFE_VAR"), "ok")
            with_gh = mod.scrubbed_env(github=True)
            self.assertEqual(with_gh.get("GITHUB_TOKEN"), "gh-secret")
        finally:
            os.environ.clear()
            os.environ.update(old)
        flat = mod.flatten([{"role": "user", "content": "check @~/.ssh/id_ed25519"}])
        self.assertIn("@\u2060~/.ssh/id_ed25519", flat)

    def test_trending_load_catalog_recovers_from_corrupt_json_and_bad_schema(self):
        spec = importlib.util.spec_from_file_location("trending_test", SKILL_ROOT / "scripts" / "trending.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory(prefix="trend-test-") as tmp:
            p = Path(tmp) / "catalog.json"
            p.write_text("{truncated", encoding="utf-8")
            loaded = mod.load_catalog(p)
            self.assertEqual(loaded["repos"], {})
            p.write_text(json.dumps({"repos": "not-a-dict"}), encoding="utf-8")
            loaded2 = mod.load_catalog(p)
            self.assertEqual(loaded2["repos"], {})


if __name__ == "__main__":
    unittest.main()
