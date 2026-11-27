"""Unit tests for assets/e2e/rehearsal_gate.py."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "rehearsal_gate.py"
SPEC = importlib.util.spec_from_file_location("rehearsal_gate_mod", MOD_PATH)
rg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rg
SPEC.loader.exec_module(rg)


class RehearsalGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rehearsal-gate-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        vid_dir = self.root / ".scratch" / "evidence"
        vid_dir.mkdir(parents=True)
        self.video = vid_dir / "flow-v1.mp4"
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42demo-video-bytes")

    def test_enforces_user_approval_full_video_collective_review_and_critic_across_versions(self):
        rg.init_workflow(
            self.root,
            slug="checkout-flow",
            app_name="Halves",
            target_kind="web",
            intent="Add expense, split 3 ways, roll balances, light settle button.",
            beats=["open-form", "submit-bill", "roll-balances", "settle-active"],
            max_rounds=25,
        )

        v0 = rg.evaluate_verdict(self.root, slug="checkout-flow")
        self.assertEqual(v0["verdict"], "REHEARSAL_BLOCKED")
        self.assertIn("intent-grilled-and-approved", v0["failed_gates"])

        v1 = rg.record_rehearsal_run(
            self.root,
            slug="checkout-flow",
            video_rel=".scratch/evidence/flow-v1.mp4",
            duration_sec=12.4,
            beats_covered=["open-form", "submit-bill", "roll-balances"],
            auto_gate_ok=True,
            watched_full_video=False,
            video_notes="only checked one still",
            critic_verdict="revise",
            open_p0_p1=1,
            critic_notes="Missing settle-active beat and digit popped instead of rolling.",
        )
        self.assertEqual(v1["verdict"], "REHEARSAL_BLOCKED")
        self.assertEqual(v1["version"], 1)
        self.assertIn("intent-grilled-and-approved", v1["failed_gates"])
        self.assertIn("full-e2e-video-recorded", v1["failed_gates"])
        self.assertIn("full-video-collective-playback-reviewed", v1["failed_gates"])
        self.assertIn("fresh-eye-critic-approved", v1["failed_gates"])
        self.assertEqual(v1["missing_beats"], ["settle-active"])

        rg.approve_workflow(self.root, slug="checkout-flow", note="User approved 4-beat checkout flow after grill.")
        v2 = rg.record_rehearsal_run(
            self.root,
            slug="checkout-flow",
            video_rel=".scratch/evidence/flow-v1.mp4",
            duration_sec=13.2,
            beats_covered=["open-form", "submit-bill", "roll-balances", "settle-active"],
            auto_gate_ok=True,
            watched_full_video=True,
            video_notes="Watched full 13.2s video end-to-end: smooth transitions, rolling digits settle cleanly, zero mid-flight pops or seam flicker.",
            critic_verdict="approve",
            open_p0_p1=0,
            critic_notes="Clean pacing, desktop 1440px and mobile 390px verified.",
        )
        self.assertEqual(v2["verdict"], "REHEARSAL_PASSED", v2)
        self.assertEqual(v2["version"], 2)
        self.assertEqual(v2["failed_gates"], [])

        md = Path(v2["rehearsal_md"]).read_text(encoding="utf-8")
        self.assertIn("REHEARSAL_PASSED", md)
        self.assertIn("| v1 |", md)
        self.assertIn("| v2 |", md)

    def test_rejects_non_video_still_image_and_tampered_video_hash(self):
        png = self.root / ".scratch" / "evidence" / "still.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        rg.init_workflow(
            self.root, slug="demo", app_name="Demo", target_kind="cli",
            intent="Run CLI end to end.", beats=["start", "finish"],
        )
        rg.approve_workflow(self.root, slug="demo", note="Approved by user.")
        with self.assertRaises(ValueError):
            rg.record_rehearsal_run(
                self.root, slug="demo", video_rel=".scratch/evidence/still.png",
                duration_sec=5.0, beats_covered=["start", "finish"],
                auto_gate_ok=True, watched_full_video=True,
                video_notes="Watched full clip end to end with clean transitions.",
                critic_verdict="approve", open_p0_p1=0,
            )

    def test_enforces_locked_references_and_provenance_receipt_against_reward_hacking(self):
        ref = self.root / "concept.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\nghibli-airship-concept")
        rg.init_workflow(
            self.root, slug="airship", app_name="Zephyr", target_kind="demo",
            intent="Turntable of sculpted Ghibli skyship.", beats=["turntable", "propeller-spin"],
            references=["concept.png"], required_producer="dgx-spark",
        )
        rg.approve_workflow(self.root, slug="airship", note="Approved 2-beat turntable.")
        v1 = rg.record_rehearsal_run(
            self.root, slug="airship", video_rel=".scratch/evidence/flow-v1.mp4",
            duration_sec=6.0, beats_covered=["turntable", "propeller-spin"],
            auto_gate_ok=True, watched_full_video=True,
            video_notes="Watched full turntable clip; boxes used instead of sculpted hull.",
            critic_verdict="approve", open_p0_p1=0,
            provenance_receipt="local:primitive-script",
            compared_references=[],
        )
        self.assertEqual(v1["verdict"], "REHEARSAL_BLOCKED")
        self.assertIn("reference-comparison-verified", v1["failed_gates"])
        self.assertIn("provenance-verified", v1["failed_gates"])

        v2 = rg.record_rehearsal_run(
            self.root, slug="airship", video_rel=".scratch/evidence/flow-v1.mp4",
            duration_sec=6.0, beats_covered=["turntable", "propeller-spin"],
            auto_gate_ok=True, watched_full_video=True,
            video_notes="Watched full 360 turntable; sculpted balloon and brass gondola match concept.",
            critic_verdict="approve", open_p0_p1=0,
            provenance_receipt="dgx-spark:prompt-77419",
            compared_references=["concept.png"],
        )
        self.assertEqual(v2["verdict"], "REHEARSAL_PASSED", v2)


if __name__ == "__main__":
    unittest.main()
