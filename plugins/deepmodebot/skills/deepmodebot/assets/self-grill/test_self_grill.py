import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5] if len(HERE.parents) > 5 else HERE
SPEC = importlib.util.spec_from_file_location("self_grill_mod", HERE / "self_grill.py")
self_grill = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = self_grill
SPEC.loader.exec_module(self_grill)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class SelfGrillTests(unittest.TestCase):
    def setUp(self):
        base_tmp = ROOT / ".scratch" / "tmp" if (ROOT / "scripts" / "check.py").is_file() else None
        if base_tmp is not None:
            base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="self-grill-test-", dir=str(base_tmp) if base_tmp else None)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test User")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "init")

    def run_cli(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self_grill.main(list(args))
        return code, buf.getvalue()

    def test_check_diff_classifies_size_and_flags_missing_tests(self):
        (self.repo / "src" / "app.py").write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertEqual(report["measured_size"], "S")
        self.assertFalse(report["recommend_cross_family_skeptic"])
        qids = {q["id"] for q in report["questions"]}
        self.assertIn("real-artifact-proof", qids)
        self.assertIn("missing-regression-test", qids)
        self.assertIn("gaps-and-overclaims", qids)

    def test_sensitive_path_escalates_out_of_s_and_requests_cross_family_skeptic(self):
        (self.repo / "src" / "auth.py").write_text("def verify_token(tok):\n    return bool(tok)\n", encoding="utf-8")
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertEqual(report["measured_size"], "M")
        self.assertTrue(report["recommend_cross_family_skeptic"])
        self.assertIn("src/auth.py", report["sensitive_paths"])
        qids = {q["id"] for q in report["questions"]}
        self.assertIn("trust-boundary-fail-closed", qids)

    def test_skill_file_triggers_skill_validation_question(self):
        skill_dir = self.repo / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        qids = {q["id"] for q in report["questions"]}
        self.assertIn("skill-and-link-validation", qids)

    def test_init_answer_receipt_enforcement_and_strict_verdict(self):
        (self.repo / "src" / "app.py").write_text("def add(a, b):\n    return int(a) + int(b)\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_app.py").write_text("assert True\n", encoding="utf-8")

        code, raw = self.run_cli("init", "--root", str(self.repo), "--slug", "check-run", "--phase", "both", "--json")
        self.assertEqual(code, 0)
        init_out = json.loads(raw)
        gdir = init_out["dir"]
        self.assertTrue((self.repo / ".scratch" / ".gitignore").is_file())

        code, raw = self.run_cli("verdict", "--dir", gdir, "--strict", "--json")
        self.assertEqual(code, 2)
        verdict = json.loads(raw)
        self.assertEqual(verdict["verdict"], "NEEDS_WORK")
        self.assertGreater(len(verdict["open_critical"]), 0)

        with self.assertRaises(SystemExit):
            self.run_cli(
                "answer", "--dir", gdir, "--id", "real-artifact-proof",
                "--status", "proven", "--answer", "Looks good to me",
            )

        for q in init_out["questions"]:
            if q["severity"] == "critical":
                code, _ = self.run_cli(
                    "answer", "--dir", gdir, "--id", q["id"],
                    "--status", "proven",
                    "--answer", f"Verified {q['id']} against current tree.",
                    "--receipt", "cmd:py -3 -B -m unittest -> exit 0 (src/app.py:1)",
                )
                self.assertEqual(code, 0)

        code, raw = self.run_cli("verdict", "--dir", gdir, "--strict", "--json")
        self.assertEqual(code, 0)
        verdict = json.loads(raw)
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertEqual(verdict["open_critical"], [])

        code, _ = self.run_cli(
            "answer", "--dir", gdir, "--id", "deletion-test",
            "--status", "blocked", "--answer", "Waiting on external fixture access.",
        )
        self.assertEqual(code, 0)
        code, raw = self.run_cli("verdict", "--dir", gdir, "--strict", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(raw)["verdict"], "BLOCKED")

    def test_detects_added_code_comments_and_escalates_high_scent_suppressions(self):
        (self.repo / "src" / "app.py").write_text(
            "def add(a, b):\n"
            "    # IMPORTANT: do not remove this workaround\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertEqual(report["added_comment_count"], 1)
        self.assertTrue(report["added_comments"][0]["high_scent"])
        qmap = {q["id"]: q for q in report["questions"]}
        self.assertIn("no-lying-comments", qmap)
        self.assertEqual(qmap["no-lying-comments"]["severity"], "critical")

    def test_detects_imperative_timers_and_unsafe_type_escapes(self):
        (self.repo / "src" / "ui.tsx").write_text(
            "export function Widget(x: unknown) {\n"
            "  setTimeout(() => console.log(x as any), 0);\n"
            "}\n",
            encoding="utf-8",
        )
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertEqual(report["workaround_smell_count"], 2)
        qmap = {q["id"]: q for q in report["questions"]}
        self.assertIn("no-workaround-smells", qmap)
        self.assertEqual(qmap["no-workaround-smells"]["severity"], "critical")


    def test_detects_toy_shortcuts_and_luau_comments_for_hardcore_craft_depth(self):
        (self.repo / "src" / "WorldGen.luau").write_text(
            "-- placeholder flat heightmap until later\n"
            "local function build()\n"
            "  local mode = 'simplified fallback'\n"
            "  return mode\n"
            "end\n",
            encoding="utf-8",
        )
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertEqual(report["added_comment_count"], 1)
        self.assertGreaterEqual(report["toy_shortcut_count"], 1)
        qmap = {q["id"]: q for q in report["questions"]}
        self.assertIn("hardcore-craft-depth", qmap)
        self.assertEqual(qmap["hardcore-craft-depth"]["severity"], "critical")

    def test_detects_reward_hacking_threshold_zeroing_and_primitive_standins(self):
        (self.repo / "src" / "gen_mesh.py").write_text(
            "import bpy\n"
            "bpy.ops.mesh.primitive_cone_add(radius1=1)\n"
            "cmd = ['gate.py', '--min-iou', '0.0']\n",
            encoding="utf-8",
        )
        code, raw = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(code, 0)
        report = json.loads(raw)
        self.assertGreaterEqual(report["reward_hack_count"], 2)
        qmap = {q["id"]: q for q in report["questions"]}
        self.assertIn("no-reward-hacking", qmap)
        self.assertEqual(qmap["no-reward-hacking"]["severity"], "critical")

    def test_shootout_regressions_init_shortcuts_sensitive_paths_inline_comments_and_bundle(self):
        self.assertIsNotNone(self_grill.SENSITIVE_PATH_RE.search("src/user_auth.py"))
        self.assertIsNotNone(self_grill.SENSITIVE_PATH_RE.search("config/prod.env"))
        self.assertIsNone(self_grill.SENSITIVE_PATH_RE.search("src/container/Box.tsx"))
        self.assertIsNone(self_grill.SENSITIVE_PATH_RE.search("src/signals/store.ts"))
        self.assertEqual(self_grill._comment_body("a.py", "x = 1  # noqa"), "noqa")
        self.assertIsNone(self_grill._comment_body("a.luau", "--!strict"))

        (self.repo / "src" / "Form.tsx").write_text(
            'export const F = () => <input placeholder="Search" />;\n', encoding="utf-8"
        )
        _, raw_ui = self.run_cli("check-diff", "--root", str(self.repo), "--json")
        self.assertEqual(json.loads(raw_ui)["toy_shortcut_count"], 0)

        (self.repo / "src" / "Stub.py").write_text("def run():\n    raise NotImplementedError\n", encoding="utf-8")
        code, raw_init = self.run_cli("init", "--root", str(self.repo), "--slug", "stub-check", "--phase", "checks", "--json")
        self.assertEqual(code, 0)
        init_data = json.loads(raw_init)
        self.assertIn("hardcore-craft-depth", {q["id"] for q in init_data["questions"]})

        with self.assertRaises(SystemExit):
            self.run_cli(
                "answer", "--dir", init_data["dir"], "--id", "real-artifact-proof",
                "--status", "proven", "--answer", "Checked", "--receipt", "took",
            )

        code_b, raw_b = self.run_cli(
            "bundle", "--root", str(self.repo), "--slug", "pros-test",
            "--confession", "Stub.py raises NotImplementedError", "--json",
        )
        self.assertEqual(code_b, 0)
        bdata = json.loads(raw_b)
        self.assertTrue(Path(bdata["bundle_path"]).is_file())
        self.assertIn("Adaptive Hotspot Map", bdata["prosecutor_prompt"])
    def test_rejects_home_or_temp_root(self):
        with self.assertRaises(SystemExit):
            self_grill.reject_unsafe_root(Path.home())

    def test_prosecutor_regressions_multiline_regex_bundle_ranking_untracked_window_and_backend_perf(self):
        (self.repo / "src" / "detector.py").write_text(
            "import re\n"
            "PAT = re.compile(\n"
            "    r'stub for now|optional hardcore',\n"
            ")\n"
            "MSG = '/deep Hardcore Mode never defer to (optional hardcore mode)'\n",
            encoding="utf-8",
        )
        diff1 = self_grill.inspect_diff(self.repo)
        self.assertEqual(diff1["toy_shortcut_count"], 0)

        docs_dir = self.repo / "docs"
        docs_dir.mkdir(exist_ok=True)
        for i in range(26):
            (docs_dir / f"a{i:02d}.md").write_text(f"# Doc {i}\n", encoding="utf-8")
        big_lines = [f"def fn_{i}(): return {i}" for i in range(500)]
        (self.repo / "src" / "auth_gate.py").write_text("\n".join(big_lines) + "\n", encoding="utf-8")
        (self.repo / "src" / "orders_api.py").write_text(
            "import requests\n"
            "async def get_orders():\n"
            "    return requests.get('https://billing.internal/orders')\n",
            encoding="utf-8",
        )
        diff2 = self_grill.inspect_diff(self.repo)
        self.assertGreaterEqual(diff2["backend_perf_count"], 1)
        qids = {q["id"] for q in diff2["questions"]}
        self.assertIn("backend-systems-hygiene", qids)

        bun = self_grill.build_prosecutor_bundle(self.repo, slug="rank-check")
        btxt = Path(bun["bundle_path"]).read_text(encoding="utf-8")
        self.assertIn("UNTRACKED WINDOW, 500 total lines", btxt)
        self.assertIn("def fn_0(): return 0", btxt)
        self.assertIn("def fn_499(): return 499", btxt)


    def test_proof_escapes_lean_bundle_and_non_git_workspace_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            nongit = Path(tmp) / "math-workspace"
            nongit.mkdir()
            lean_lines = [f"-- line {i}" for i in range(580)] + [
                "theorem main_bound (n : Nat) : n + 1 > n := by",
                "  sorry",
            ]
            (nongit / "Solution.lean").write_text("\n".join(lean_lines) + "\n", encoding="utf-8")
            (nongit / "report.md").write_text("# Proof Notes\n\nVerified small cases n=3,4.\n", encoding="utf-8")

            digest = self_grill.compute_tree_digest(nongit)
            self.assertEqual(len(digest), 24)

            diff = self_grill.inspect_diff(nongit)
            self.assertFalse(diff["in_git"])
            self.assertNotEqual(diff["measured_size"], "none")
            self.assertGreaterEqual(diff["proof_escape_count"], 1)
            qids = {q["id"] for q in diff["questions"]}
            self.assertIn("proof-and-math-soundness", qids)

            bun = self_grill.build_prosecutor_bundle(nongit, slug="lean-check")
            btxt = Path(bun["bundle_path"]).read_text(encoding="utf-8")
            self.assertIn("FILE: Solution.lean (582 lines)", btxt)
            self.assertNotIn("lines elided", btxt)
if __name__ == "__main__":
    unittest.main()
