"""Tests for per-role model & reasoning-budget setup (model_setup.py)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("model_setup", HERE / "model_setup.py")
ms = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ms
spec.loader.exec_module(ms)


class ModelSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_budget_ladder_shifts_opus_fable_and_neon_cleanly(self):
        large = ms.build_plan(self.root, budget="large")
        self.assertEqual(large["roles"]["bug_fix"], "claude-opus-5-5-xhigh-fast")
        self.assertIn("gemini-4-neon-xhigh", large["roles"]["arena_runners"])

        med = ms.build_plan(self.root, budget="medium")
        self.assertEqual(med["roles"]["bug_fix"], "claude-opus-5-5-high-fast")
        self.assertEqual(
            med["roles"]["arena_runners"],
            ["claude-fable-5-2-medium", "claude-opus-5-5-medium-fast", "gemini-4-neon-high"],
        )

        small = ms.build_plan(self.root, budget="small")
        self.assertEqual(small["roles"]["bug_fix"], "claude-opus-5-5-medium-fast")
        self.assertEqual(
            small["roles"]["arena_runners"],
            ["claude-fable-5-2-low", "claude-opus-5-5-low-fast", "gemini-4-neon-medium"],
        )

    def test_migrates_legacy_defaults_and_drops_retired_roles(self):
        cfg = self.root / ".deepmodebot" / "models.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            json.dumps({
                "defaults_version": 1,
                "budget": "unlimited",
                "roles": {
                    "hardest tasks": "claude-opus-5-5-xhigh-fast",
                    "bug-fix": "grok-4-high",
                    "judgment and prose": "inherit-parent",
                    "arena runners": ["claude-fable-5-2-high", "claude-opus-5-5-high-fast", "gemini-4-neon-high"],
                    "arena cross-judge pool": ["claude-fable-5-2-high", "claude-opus-5-5-high-fast", "gemini-4-pro-high"],
                },
            }),
            encoding="utf-8",
        )
        plan = ms.build_plan(self.root)
        self.assertEqual(plan["budget"], "large")
        self.assertIn("hardest tasks", plan["dropped_roles"])
        self.assertEqual(plan["roles"]["bug_fix"], "claude-opus-5-5-xhigh-fast")
        self.assertEqual(plan["roles"]["judgment_and_prose"], "inherit-parent")
        self.assertIn("gemini-4-neon-xhigh", plan["roles"]["arena_runners"])
        self.assertEqual(plan["roles"]["arena_cross_judge_pool"], ["claude-opus-5-5-high-fast", "gemini-4-neon-xhigh"])

    def test_rejects_unavailable_or_above_xhigh_or_alias_judge(self):
        plan = ms.build_plan(
            self.root,
            budget="large",
            available={"claude-opus-5-5-xhigh-fast", "claude-opus-5-5-high-fast", "gemini-4-neon-xhigh", "claude-fable-5-2-high"},
            overrides={"arena_cross_judge_pool": ["inherit-parent", "gemini-4-neon-xhigh"], "bug_fix": "claude-opus-5-5-max-fast"},
        )
        self.assertTrue(any("inherit-parent" in e for e in plan["errors"]))
        self.assertTrue(any("exceeds xhigh" in e for e in plan["errors"]))

    def test_write_is_idempotent(self):
        plan = ms.build_plan(self.root, budget="medium")
        out = ms.write_config(plan)
        first = out.read_text(encoding="utf-8")
        plan2 = ms.build_plan(self.root, budget="medium")
        ms.write_config(plan2)
        self.assertEqual(first, out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
