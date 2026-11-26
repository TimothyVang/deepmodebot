import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quota_guard import audit_transcripts, compute_quota_plan, detect_outer_harness, load_checkpoint, save_checkpoint


class QuotaGuardTests(unittest.TestCase):
    def test_anti_stacking_suppresses_nested_subagents_inside_teamwork_or_swarm(self):
        with patch.dict(os.environ, {"TEAMWORK_RUN_ID": "run-123"}):
            self.assertEqual(detect_outer_harness(), "teamwork")
            plan = compute_quota_plan(size="L", diff_lines=5000, is_sensitive=True, outer_harness=detect_outer_harness())
            self.assertTrue(plan["nested_anti_stacking"])
            self.assertEqual(plan["max_subagents_per_task"], 0)
            self.assertEqual(plan["panel_seats"], 0)
            self.assertEqual(plan["review_strategy"], "inline-4-lens-plus-deterministic-scripts")

    def test_single_bundle_and_light_model_tiers_cut_m_and_l_waste(self):
        m_plan = compute_quota_plan(size="M", diff_lines=220, is_sensitive=False)
        self.assertEqual(m_plan["budget_mode"], "lean-single-bundle")
        self.assertEqual(m_plan["max_review_subagents"], 1)
        self.assertEqual(m_plan["panel_seats"], 0)
        self.assertEqual(m_plan["subagent_models"]["scout"], "flash_lite")
        self.assertEqual(m_plan["subagent_models"]["comment-sicko"], "flash")

        l_mid = compute_quota_plan(size="L", diff_lines=1200, is_sensitive=True, is_merge_gate=False)
        self.assertEqual(l_mid["panel_seats"], 0)
        self.assertEqual(l_mid["max_parallel_worktrees"], 2)

        l_merge = compute_quota_plan(size="L", diff_lines=1200, is_sensitive=True, is_merge_gate=True)
        self.assertEqual(l_merge["panel_seats"], 3)

    def test_checkpoint_roundtrip_and_transcript_audit_flags_runaway_multiplier(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            repo.mkdir()
            (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
            saved = save_checkpoint(
                repo,
                slug="pr-02",
                done_steps=["schema", "tests"],
                open_findings=["main.py:12 missing index"],
                anchors=["main.py:1-20"],
                verified_cmds=["pytest -> exit 0"],
            )
            self.assertTrue(Path(saved["checkpoint_path"]).is_file())
            loaded = load_checkpoint(repo, slug="pr-02")
            self.assertFalse(loaded["stale_tree"])
            self.assertEqual(loaded["open_findings"], ["main.py:12 missing index"])

            brain = Path(tmp) / "brain"
            cdir = brain / "conv-1" / ".system_generated" / "logs"
            cdir.mkdir(parents=True)
            rows = []
            for idx in range(15):
                role = f"explorer_r2_{idx}" if idx < 13 else f"worker_{idx}"
                rows.append(json.dumps({
                    "tool_calls": [{
                        "name": "invoke_subagent",
                        "args": {"TypeName": "self", "Role": role},
                    }]
                }))
            (cdir / "transcript.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

            audit = audit_transcripts(brain)
            self.assertEqual(audit["subagent_spawns"], 15)
            self.assertEqual(audit["overhead_spawns"], 13)
            self.assertEqual(audit["inherit_model_spawns"], 15)
            joined = " ".join(audit["warnings"])
            self.assertIn("HIGH_SUBAGENT_MULTIPLIER", joined)
            self.assertIn("OVERHEAD_DOMINATED", joined)
            self.assertIn("HEAVY_MODEL_INHERITANCE", joined)
            self.assertIn("RESPAWN_TAX", joined)


if __name__ == "__main__":
    unittest.main()
