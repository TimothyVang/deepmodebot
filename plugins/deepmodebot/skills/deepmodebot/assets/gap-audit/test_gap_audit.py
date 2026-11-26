import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5] if len(HERE.parents) > 5 else HERE
SPEC = importlib.util.spec_from_file_location("gap_audit_mod", HERE / "gap_audit.py")
gap_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gap_audit
SPEC.loader.exec_module(gap_audit)


class GapAuditTests(unittest.TestCase):
    def setUp(self):
        base_tmp = ROOT / ".scratch" / "tmp" if (ROOT / "scripts" / "check.py").is_file() else None
        if base_tmp is not None:
            base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="gap-audit-test-", dir=str(base_tmp) if base_tmp else None)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()

    def run_cli(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gap_audit.main(list(args))
        return code, buf.getvalue()

    def test_scan_catches_flag_drift_stubs_swallowed_errors_replaces_and_unwired_assets(self):
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "tool_cli.py").write_text(
            "import argparse\n"
            "def main():\n"
            "    p = argparse.ArgumentParser()\n"
            "    p.add_argument('--root', required=True)\n"
            "    p.add_argument('--json', action='store_true')\n"
            "    return p.parse_args()\n",
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text(
            "# Demo\n\n"
            "Run `python scripts/tool_cli.py --root . --bogus-flag`.\n"
            "Subshell `TOKEN=$(python scripts/tool_cli.py --root .) gh pr comment --body-file x` is fine.\n",
            encoding="utf-8",
        )
        (self.repo / "src").mkdir()
        (self.repo / "src" / "handlers.py").write_text(
            "from abc import ABC, abstractmethod\n\n"
            "class Base(ABC):\n"
            "    @abstractmethod\n"
            "    def allowed_contract(self):\n"
            "        pass\n\n"
            "def unbuilt_webhook(payload):\n"
            "    pass\n\n"
            "def silent_sync(items):\n"
            "    try:\n"
            "        return len(items)\n"
            "    except Exception:\n"
            "        pass\n",
            encoding="utf-8",
        )
        (self.repo / "src" / "client.ts").write_text(
            "// replaces scripts/tool_cli.py\n"
            "export function send(p: Promise<void>) {\n"
            "  p.catch(() => {});\n"
            "}\n"
            "export function futureWork() {\n"
            "  throw new Error('Not implemented yet');\n"
            "}\n",
            encoding="utf-8",
        )
        orphan = self.repo / "plugins" / "demo" / "skills" / "demo" / "assets" / "x" / "orphan_tool.py"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("def helper():\n    return 42\n", encoding="utf-8")

        code, out = self.run_cli("scan", "--root", str(self.repo), "--json")
        self.assertEqual(code, 1)
        res = json.loads(out)
        rules = [f["rule"] for f in res["findings"]]
        self.assertIn("doc-script-flag-drift", rules)
        self.assertIn("stale-replaces-claim", rules)
        self.assertIn("hollow-stub-body", rules)
        self.assertIn("swallowed-exception", rules)
        self.assertIn("unwired-script-asset", rules)

        flag_hits = [f for f in res["findings"] if f["rule"] == "doc-script-flag-drift"]
        self.assertEqual(len(flag_hits), 1)
        self.assertIn("--bogus-flag", flag_hits[0]["message"])

        stub_msgs = " ".join(f["message"] for f in res["findings"] if f["rule"] == "hollow-stub-body")
        self.assertIn("unbuilt_webhook", stub_msgs)
        self.assertNotIn("allowed_contract", stub_msgs)

    def test_research_ledger_enforces_disconfirmation_evidence_tiers_and_gap_matrix(self):
        (self.repo / "src").mkdir()
        (self.repo / "src" / "engine.py").write_text("def run():\n    return True\n", encoding="utf-8")

        code, raw = self.run_cli(
            "init-research",
            "--root", str(self.repo),
            "--slug", "edge-rpc",
            "--question", "Should we adopt Cap'n Web capability RPC?",
            "--sources", "https://github.com/cloudflare/capnweb",
            "--json",
        )
        self.assertEqual(code, 0)
        init_res = json.loads(raw)
        ledger_dir = init_res["dir"]

        code_fail, raw_fail = self.run_cli("verify-research", "--dir", ledger_dir, "--strict", "--json")
        self.assertEqual(code_fail, 1)
        self.assertEqual(json.loads(raw_fail)["status"], "NEEDS_WORK")

        self.run_cli(
            "record-claim",
            "--dir", ledger_dir,
            "--id", "C1",
            "--claim", "Cap'n Web pipelines dependent RPC calls in a single round-trip under 16 kB.",
            "--evidence-tier", "code-verified",
            "--primary-receipt", "cloudflare/capnweb@main:src/rpc.ts:1",
            "--disconfirmation-probe", "Checked open GitHub issues and bundle size build output for browser transport limits.",
            "--disconfirmation-result", "qualified",
            "--caveat", "Requires explicit RpcTarget disposal over WebSocket sessions to avoid capability retention.",
            "--json",
        )

        code_nogap, raw_nogap = self.run_cli("verify-research", "--dir", ledger_dir, "--strict", "--json")
        self.assertEqual(code_nogap, 1)
        self.assertIn("Differential Gap Matrix", " ".join(json.loads(raw_nogap)["violations"]))

        self.run_cli(
            "record-gap",
            "--dir", ledger_dir,
            "--id", "G1",
            "--capability", "Promise-pipelined capability RPC with automatic stub disposal",
            "--source-ref", "https://github.com/cloudflare/capnweb",
            "--repo-state", "missing",
            "--repo-evidence", "src/engine.py:1",
            "--priority", "P1",
            "--leverage", "Eliminates N-round-trip sequential fetch waterfalls across edge workers.",
            "--json",
        )

        brief_md = self.repo / "docs" / "research" / "edge-rpc.md"
        code_ok, raw_ok = self.run_cli(
            "verify-research",
            "--dir", ledger_dir,
            "--strict",
            "--render", str(brief_md),
            "--json",
        )
        self.assertEqual(code_ok, 0)
        ver = json.loads(raw_ok)
        self.assertEqual(ver["status"], "PASS")
        self.assertTrue(brief_md.is_file())
        rendered = brief_md.read_text(encoding="utf-8")
        self.assertIn("SOTA vs Target-Repo Differential Gap Matrix", rendered)
        self.assertIn("Promise-pipelined capability RPC", rendered)

    def test_docs_only_universal_overclaim_is_rejected(self):
        (self.repo / "README.md").write_text("# Notes\n", encoding="utf-8")
        _, raw = self.run_cli(
            "init-research",
            "--root", str(self.repo),
            "--slug", "bad-claim",
            "--question", "Does library X fail?",
            "--json",
        )
        ledger_dir = json.loads(raw)["dir"]
        self.run_cli(
            "record-claim",
            "--dir", ledger_dir,
            "--id", "C1",
            "--claim", "Library X is 100% bug-free and never fails under load.",
            "--evidence-tier", "docs-only",
            "--primary-receipt", "https://example.com/docs",
            "--disconfirmation-probe", "Checked GitHub issues and found 12 open crash bugs under concurrency.",
            "--disconfirmation-result", "survived",
            "--json",
        )
        code, ver_raw = self.run_cli("verify-research", "--dir", ledger_dir, "--json")
        self.assertEqual(code, 1)
        self.assertIn("universal guarantee", " ".join(json.loads(ver_raw)["violations"]))


if __name__ == "__main__":
    unittest.main()
