import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5] if len(HERE.parents) > 5 else HERE
SPEC = importlib.util.spec_from_file_location("prompt_tools_mod", HERE / "prompt_tools.py")
prompt_tools = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt_tools
SPEC.loader.exec_module(prompt_tools)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class PromptToolsTests(unittest.TestCase):
    def setUp(self):
        base_tmp = ROOT / ".scratch" / "tmp" if (ROOT / "scripts" / "check.py").is_file() else None
        if base_tmp is not None:
            base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="prompt-tools-test-", dir=str(base_tmp) if base_tmp else None)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test User")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# Demo\n\nSimple demo.\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "init")

    def run_cli(self, *args: str, stdin_text: str | None = None) -> tuple[int, str]:
        buf = io.StringIO()
        if stdin_text is not None:
            with contextlib.redirect_stdout(buf), unittest.mock.patch.object(sys, "stdin", io.StringIO(stdin_text)):
                code = prompt_tools.main(list(args))
        else:
            with contextlib.redirect_stdout(buf):
                code = prompt_tools.main(list(args))
        return code, buf.getvalue()

    def test_upgrade_converts_sloppy_compound_prompt_into_full_scope_deepmode_prompt(self):
        raw_prompt = "optimzie auth naetc also add stripe billing also check gaps"
        code, out = self.run_cli("upgrade", "--stdin", "--root", str(self.repo), "--json", stdin_text=raw_prompt)
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertTrue(parsed["needs_upgrade"])
        self.assertIn("multi_part_unnumbered", parsed["weaknesses"])
        self.assertIn("missing_acceptance_oracle", parsed["weaknesses"])
        self.assertIn("contains_typos_or_fragments", parsed["weaknesses"])
        self.assertEqual(len(parsed["decoded_deliverables"]), 3)
        self.assertIn("1. optimzie auth naetc", parsed["upgraded_prompt"])
        self.assertIn("2. add stripe billing", parsed["upgraded_prompt"])
        self.assertIn("3. check gaps", parsed["upgraded_prompt"])
        self.assertIn("Audit for gaps and overclaims", parsed["upgraded_prompt"])
        self.assertIn("self_grill.py check-diff", parsed["upgraded_prompt"])

    def test_suggest_detects_overclaims_broken_links_diff_gaps_and_debt(self):
        (self.repo / "README.md").write_text(
            "# Demo\n\n"
            "This tool is 100% bug-free and never fails.\n"
            "See [missing guide](docs/does-not-exist.md).\n",
            encoding="utf-8",
        )
        (self.repo / "src" / "auth.py").write_text(
            "def login(token):\n"
            "    # TODO: handle expired tokens\n"
            "    return bool(token)\n",
            encoding="utf-8",
        )
        (self.repo / "src" / "ui.tsx").write_text(
            "export function Box(v: unknown) {\n"
            "  setTimeout(() => console.log(v as any), 0);\n"
            "}\n",
            encoding="utf-8",
        )
        (self.repo / "SAMPLE.template.md").write_text(
            "See [Roadmap](../ROADMAP.md) and [Issues]({{REPO_URL}}/issues).\n",
            encoding="utf-8",
        )

        code, out = self.run_cli("suggest", "--root", str(self.repo), "--limit", "10", "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertGreaterEqual(report["overclaim_hits"], 1)
        self.assertGreaterEqual(report["broken_link_hits"], 1)
        self.assertGreaterEqual(report["debt_marker_hits"], 1)

        titles = " ".join(s["title"].lower() for s in report["suggestions"])
        self.assertIn("broken documentation links", titles)
        self.assertIn("overclaims", titles)
        self.assertIn("sensitive paths", titles)
        self.assertIn("comment", titles)
        self.assertIn("workaround", titles)
        for item in report["suggestions"]:
            self.assertTrue(item["prompt"].startswith("/deep "))
            self.assertTrue(len(item["evidence"]) >= 1)
        self.assertTrue(report["hardcore_mode"])
        self.assertIn("hardcore", {s["kind"] for s in report["suggestions"]})

    def test_upgrade_promotes_optional_hardcore_mode_into_mandatory_deliverable(self):
        raw_prompt = (
            "1. Upgrade src/shared/WorldGen.luau to 3D Volumetric Density Field + Hydraulic Erosion\n"
            "2. Add pure-Luau 3D WFC Modular Architecture Solver (src/shared/WFCBuilder.luau)\n"
            "3. (Optional hardcore mode) Replace Roblox Terrain with Surface Nets / Dual Contouring EditableMesh"
        )
        code, out = self.run_cli("upgrade", "--stdin", "--root", str(self.repo), "--json", stdin_text=raw_prompt)
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertTrue(parsed["hardcore_mode"])
        self.assertTrue(parsed["promoted_optional_hardcore"])
        self.assertIn("watered_down_or_optional_hardcore", parsed["weaknesses"])
        self.assertIn("[HARDCORE MODE ON]", parsed["upgraded_prompt"])
        self.assertIn("[Hardcore mandatory] Replace Roblox Terrain with Surface Nets", parsed["upgraded_prompt"])
        self.assertIn("Hardcore Mode by default", parsed["upgraded_prompt"])

    def test_shootout_regressions_negation_optionally_inline_hardcore_and_100_percent(self):
        res_neg = prompt_tools.upgrade_prompt("Build 3D solver; do NOT ship a minimal MVP or quick hack", root=self.repo)
        self.assertTrue(res_neg["hardcore_mode"])

        res_opt = prompt_tools.upgrade_prompt("1. Add login endpoint\n2. Optionally emit debug metrics", root=self.repo)
        self.assertNotIn("[Hardcore mandatory] ly", res_opt["upgraded_prompt"])
        self.assertIn("2. Optionally emit debug metrics", res_opt["upgraded_prompt"])

        res_inline = prompt_tools.upgrade_prompt("Build terrain (Optional hardcore mode: add hydraulic erosion)", root=self.repo)
        self.assertTrue(res_inline["promoted_optional_hardcore"])
        self.assertIn("[Hardcore mandatory: add hydraulic erosion]", res_inline["upgraded_prompt"])

        (self.repo / "README.md").write_text("# Demo\n\nThis engine is 100% reliable.\nSee [artifact](artifact://ok).\n", encoding="utf-8")
        sug = prompt_tools.suggest_prompts(self.repo, limit=10)
        self.assertGreaterEqual(sug["overclaim_hits"], 1)
        self.assertEqual(sug["broken_link_hits"], 0)


    def test_prosecutor_regressions_backticks_plus_untested_stems_and_backend_perf_suggest(self):
        bt = prompt_tools.upgrade_prompt("optimzie `src/auth.py` also add stripe billing also check gaps", root=self.repo)
        self.assertEqual(len(bt["decoded_deliverables"]), 3)
        self.assertIn("multi_part_unnumbered", bt["weaknesses"])

        plus_res = prompt_tools.upgrade_prompt("Add Postgres 18 plus pgvector search in src/db.py", root=self.repo)
        self.assertEqual(len(plus_res["decoded_deliverables"]), 1)
        self.assertIn("high-scale-server-optimization.md", plus_res["upgraded_prompt"])

        (self.repo / "src" / "payments").mkdir(parents=True, exist_ok=True)
        (self.repo / "src" / "payments" / "client.py").write_text(
            "async def charge_all(db, ids):\n"
            "    out = []\n"
            "    for oid in ids:\n"
            "        out.append(await db.fetchrow('SELECT * FROM charges WHERE id = $1', oid))\n"
            "    return out\n",
            encoding="utf-8",
        )
        (self.repo / "tests").mkdir(exist_ok=True)
        (self.repo / "tests" / "test_unrelated.py").write_text(
            "def test_math():\n    client = 123\n    assert client == 123\n",
            encoding="utf-8",
        )
        sug = prompt_tools.suggest_prompts(self.repo, limit=10)
        self.assertGreaterEqual(sug["perf_audit_hits"], 1)
        kinds = {s["kind"] for s in sug["suggestions"]}
        self.assertIn("perf", kinds)
        perf_card = next(s for s in sug["suggestions"] if s["kind"] == "perf")
        self.assertIn("high-scale-server-optimization.md", perf_card["prompt"])
        gap_cards = [s for s in sug["suggestions"] if s["kind"] == "gap"]
        self.assertTrue(any("src/payments" in " ".join(s["evidence"]) for s in gap_cards))

    def test_suggest_surfaces_gap_audit_flag_drift_and_hollow_stubs(self):
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "runner_cli.py").write_text(
            "import argparse\np = argparse.ArgumentParser()\np.add_argument('--root')\n",
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text(
            "# Demo\n\nRun `python scripts/runner_cli.py --root . --missing-opt`.\n",
            encoding="utf-8",
        )
        (self.repo / "src" / "stubbed.py").write_text(
            "def sync_orders():\n    pass\n",
            encoding="utf-8",
        )
        sug = prompt_tools.suggest_prompts(self.repo, limit=10)
        self.assertGreaterEqual(sug["gap_audit_hits"], 2)
        titles = " ".join(s["title"].lower() for s in sug["suggestions"])
        self.assertIn("flag drift", titles)
        self.assertIn("hollow stub", titles)

if __name__ == "__main__":
    unittest.main()
