#!/usr/bin/env python3
"""Unit tests for gen_ui.py (A2UI v1.0 surface compiler, validator, and interactive HTML cockpit)."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN_UI_PY = HERE / "gen_ui.py"
PROMPT_TOOLS_PY = HERE.parent / "prompt-tools" / "prompt_tools.py"

spec = importlib.util.spec_from_file_location("gen_ui", GEN_UI_PY)
gen_ui = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gen_ui
spec.loader.exec_module(gen_ui)


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(root), check=True)


class GenUiTests(unittest.TestCase):
    def test_from_suggest_emits_valid_a2ui_and_escaped_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "sample-app"
            repo.mkdir()
            _init_git_repo(repo)
            (repo / "src").mkdir()
            (repo / "src" / "engine.py").write_text(
                "def compute(x):\n    return x * 2\n\ndef solve(items):\n    return sorted(items)\n",
                encoding="utf-8",
            )
            (repo / "README.md").write_text(
                "# Sample\n\nThis system guarantees 100% bug-free execution "
                "and links [missing](docs/</script><script>alert(1)</script>.md).\n",
                encoding="utf-8",
            )

            out = gen_ui.generate_from_suggest(repo, slug="suggest-check", limit=6)
            surface = out["ui_surface"]
            self.assertTrue(surface["valid"])
            self.assertEqual(surface["version"], "1.0")
            a2ui_path = Path(surface["a2ui_path"])
            html_path = Path(surface["html_path"])
            self.assertTrue(a2ui_path.is_file())
            self.assertTrue(html_path.is_file())
            self.assertIn(".scratch/gen-ui/suggest-check", a2ui_path.as_posix())

            bundle = json.loads(a2ui_path.read_text(encoding="utf-8"))
            val = gen_ui.validate_a2ui_bundle(bundle)
            self.assertTrue(val["valid"], val["errors"])

            html = html_path.read_text(encoding="utf-8")
            self.assertIn('type="application/a2ui+json"', html)
            self.assertIn("--bg-canvas: oklch(", html)
            self.assertNotIn("</script><script>alert(1)", html)
            self.assertIn("\\u003c/script>", html)

    def test_from_grill_diff_and_custom_decision_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "grill-app"
            repo.mkdir()
            _init_git_repo(repo)
            (repo / "auth.py").write_text("def verify(tok):\n    return bool(tok)\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True)
            (repo / "auth.py").write_text(
                "def verify(tok):\n    # narrating comment\n    return True\n",
                encoding="utf-8",
            )

            diff_surface = gen_ui.generate_from_grill(repo, slug="diff-audit")
            self.assertTrue(diff_surface["valid"])
            diff_bundle = json.loads(Path(diff_surface["a2ui_path"]).read_text(encoding="utf-8"))
            self.assertTrue(gen_ui.validate_a2ui_bundle(diff_bundle)["valid"])

            custom_spec = {
                "title": "Agent UI Protocol Decision",
                "subtitle": "Compare A2UI 1.0 vs raw iframe",
                "decisions": [
                    {
                        "id": "ui-wire",
                        "question": "How should remote agents send interactive UI?",
                        "choice": "A2UI 1.0 declarative catalog",
                        "options": ["A2UI 1.0 declarative catalog", "MCP Apps iframe only", "Plain Markdown"],
                        "why": "Inherits host design tokens and prevents arbitrary script execution.",
                        "reverse": "Wrap bespoke WebGL canvases inside an MCP App component (Pattern 2).",
                    }
                ],
            }
            dec_surface = gen_ui.generate_from_grill(repo, slug="decision-tree", custom_spec=custom_spec)
            self.assertTrue(dec_surface["valid"])
            dec_bundle = json.loads(Path(dec_surface["a2ui_path"]).read_text(encoding="utf-8"))
            self.assertTrue(gen_ui.validate_a2ui_bundle(dec_bundle)["valid"])

    def test_validate_a2ui_catches_cycles_unknown_components_bad_pointers_and_xss(self) -> None:
        base = gen_ui.compile_spec_to_a2ui(
            {
                "title": "Validator Check",
                "metrics": [{"label": "Files", "value": 4, "tone": "ok"}],
            },
            surface_id="val-surface",
        )
        self.assertTrue(gen_ui.validate_a2ui_bundle(base)["valid"])

        bad_comp = copy.deepcopy(base)
        bad_comp["messages"][1]["updateComponents"]["components"].append(
            {"id": "rogue", "component": "RawHtmlIframe", "html": "<h1>bad</h1>"}
        )
        bad_comp["messages"][1]["updateComponents"]["components"][0]["children"].append("rogue")
        res_comp = gen_ui.validate_a2ui_bundle(bad_comp)
        self.assertFalse(res_comp["valid"])
        self.assertTrue(any("uncataloged component" in e for e in res_comp["errors"]))

        bad_cycle = copy.deepcopy(base)
        comps = bad_cycle["messages"][1]["updateComponents"]["components"]
        comps.append({"id": "sec_a", "component": "Section", "heading": "A", "children": ["sec_b"]})
        comps.append({"id": "sec_b", "component": "Section", "heading": "B", "children": ["sec_a"]})
        comps[0]["children"].append("sec_a")
        res_cycle = gen_ui.validate_a2ui_bundle(bad_cycle)
        self.assertFalse(res_cycle["valid"])
        self.assertTrue(any("cycle detected" in e for e in res_cycle["errors"]))

        bad_ptr = copy.deepcopy(base)
        bad_ptr["messages"][1]["updateComponents"]["components"][0]["title"] = {"@path": "/meta/doesNotExist"}
        res_ptr = gen_ui.validate_a2ui_bundle(bad_ptr)
        self.assertFalse(res_ptr["valid"])
        self.assertTrue(any("does not resolve" in e for e in res_ptr["errors"]))

        bad_xss = copy.deepcopy(base)
        bad_xss["messages"][1]["updateComponents"]["components"].append(
            {"id": "evil_txt", "component": "Text", "text": "<script>alert(1)</script>"}
        )
        bad_xss["messages"][1]["updateComponents"]["components"][0]["children"].append("evil_txt")
        res_xss = gen_ui.validate_a2ui_bundle(bad_xss)
        self.assertFalse(res_xss["valid"])
        self.assertTrue(any("forbidden executable/script" in e for e in res_xss["errors"]))

    def test_containment_sanitizes_traversal_slug_and_rejects_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "contained-app"
            repo.mkdir()
            _init_git_repo(repo)
            res = gen_ui.write_surface_artifacts(
                repo,
                slug="../../escape/attempt",
                spec={"title": "Contained", "metrics": [{"label": "OK", "value": 1}]},
            )
            out_path = Path(res["html_path"]).resolve()
            expected_parent = (repo / ".scratch" / "gen-ui").resolve()
            self.assertTrue(str(out_path).startswith(str(expected_parent)))

        with self.assertRaises(SystemExit):
            gen_ui.write_surface_artifacts(Path.home(), slug="bad", spec={"title": "Nope"})

    def test_prompt_tools_suggest_ui_flag_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "cli-app"
            repo.mkdir()
            _init_git_repo(repo)
            (repo / "app.py").write_text("def run():\n    return 42\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-B", str(PROMPT_TOOLS_PY), "suggest", "--root", str(repo), "--ui", "--json"],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(proc.stdout)
            self.assertIn("ui_surface", payload)
            self.assertTrue(payload["ui_surface"]["valid"])
            self.assertTrue(Path(payload["ui_surface"]["a2ui_path"]).is_file())
            self.assertTrue(Path(payload["ui_surface"]["html_path"]).is_file())


    def test_prosecutor_regressions_html_comment_escape_duplicate_msgs_types_and_decision_ids(self) -> None:
        spec = {
            "title": "Check __A2UI_JSON__ Title",
            "findings": [
                {
                    "severity": "P0",
                    "category": "escape",
                    "location": "doc.md:1",
                    "detail": "Contains <!-- html comment --> and </script> safely",
                }
            ],
            "decisions": [
                {
                    "id": "arch_decision_1",
                    "question": "Pick query batching strategy",
                    "choice": "ANY($1)",
                    "options": ["ANY($1)", "DataLoader"],
                    "why": "Single round trip",
                    "reverse": "Fallback to JOIN",
                }
            ],
        }
        bundle = gen_ui.compile_spec_to_a2ui(spec, surface_id="deepmodebot-reg-surface")
        self.assertTrue(gen_ui.validate_a2ui_bundle(bundle)["valid"])
        html = gen_ui.render_html_cockpit(bundle, spec["title"])
        self.assertIn("<title>Check __A2UI_JSON__ Title</title>", html)
        self.assertNotIn("<\\!--", html)
        m = __import__("re").search(r'<script id="a2ui-payload" type="application/a2ui\+json">\s*(.*?)\s*</script>', html, __import__("re").S)
        self.assertIsNotNone(m)
        parsed_embedded = json.loads(m.group(1))
        self.assertEqual(parsed_embedded["messages"][2]["updateDataModel"]["value"]["findings"][0]["detail"], "Contains <!-- html comment --> and </script> safely")
        self.assertIn("min-height: 44px;", html)
        self.assertIn("FORBIDDEN_KEYS", html)

        dup_bundle = copy.deepcopy(bundle)
        evil_update = copy.deepcopy(bundle["messages"][1])
        evil_update["updateComponents"]["components"].append({"id": "evil", "component": "RawHtmlIframe"})
        dup_bundle["messages"].insert(1, evil_update)
        dup_res = gen_ui.validate_a2ui_bundle(dup_bundle)
        self.assertFalse(dup_res["valid"])
        self.assertTrue(any("duplicate updateComponents" in e for e in dup_res["errors"]))

        bad_type = copy.deepcopy(bundle)
        bad_type["messages"][2]["updateDataModel"]["value"]["decisions"][0]["options"] = "not-a-list"
        type_res = gen_ui.validate_a2ui_bundle(bad_type)
        self.assertFalse(type_res["valid"])
        self.assertTrue(any("invalid type" in e for e in type_res["errors"]))

    def test_surface_cap_retains_at_most_eight_recent_surfaces(self) -> None:
        import os as _os
        import time as _time
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "cap-app"
            repo.mkdir()
            _init_git_repo(repo)
            base_ts = _time.time() - 100
            for idx in range(11):
                res = gen_ui.write_surface_artifacts(
                    repo,
                    slug=f"surf-{idx:02d}",
                    spec={"title": f"Surface {idx}", "metrics": [{"label": "N", "value": idx}]},
                )
                sdir = Path(res["html_path"]).parent
                ts = base_ts + idx
                _os.utime(sdir, (ts, ts))
            gen_base = repo / ".scratch" / "gen-ui"
            self_grill = gen_ui._load_sibling("genui_cap_sg", "self-grill/self_grill.py")
            gen_ui._prune_old_gen_ui_surfaces(gen_base, repo.resolve(), self_grill.ensure_contained, keep=8)
            kept = sorted(d.name for d in gen_base.iterdir() if d.is_dir())
            self.assertEqual(len(kept), 8)
            self.assertEqual(kept, [f"surf-{idx:02d}" for idx in range(3, 11)])

if __name__ == "__main__":
    unittest.main()
