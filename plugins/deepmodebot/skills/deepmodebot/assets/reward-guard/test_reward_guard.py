"""Behavioral red-to-green tests for assets/reward-guard/reward_guard.py."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "reward_guard.py"
SPEC = importlib.util.spec_from_file_location("reward_guard_mod", MOD_PATH)
rg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rg
SPEC.loader.exec_module(rg)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=30)


class RewardGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="reward-guard-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test")
        (self.repo / "gates").mkdir()
        (self.repo / "refs").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / ".github/workflows").mkdir(parents=True)
        (self.repo / ".github/workflows/ci.yml").write_text("name: ci\n", encoding="utf-8")
        (self.repo / "gates/fidelity_gate.py").write_text(
            "MIN_IOU = 0.72\nMAX_HOLES = 0\ndef check(iou, holes):\n    return iou >= 0.72 and holes <= 0\n",
            encoding="utf-8",
        )
        (self.repo / "refs/painting.png").write_bytes(b"\x89PNG\r\n\x1a\nghibli-concept-art-bytes")
        (self.repo / "tests/test_gate.py").write_text(
            "def test_corsair_beak():\n    protrusion = 0.06\n    assert protrusion >= 0.045\n",
            encoding="utf-8",
        )
        (self.repo / "app.py").write_text("def step():\n    acc = 1\n    weapon.accuracy = 0.95\n    return acc\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "init")

    def test_scan_catches_negative_scientific_thresholds_primitives_skips_and_avoids_false_positives(self):
        (self.repo / "build_props.py").write_text(
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add(size=2)\n"
            "bpy.ops.mesh.primitive_cone_add(radius1=1)\n"
            "cmd1 = ['python', 'gate.py', '--min-iou', '-0.5']\n"
            "cmd2 = ['python', 'gate.py', '--min-clip-score', '1e-9', '--skip-reference']\n",
            encoding="utf-8",
        )
        (self.repo / "gates/fidelity_gate.py").write_text(
            "MIN_IOU = 1e-9\nMAX_HOLES = 12\ndef check(iou, holes):\n    return {'verdict': 'PASS', 'iou': 1.0}\n",
            encoding="utf-8",
        )
        (self.repo / "tests/test_gate.py").write_text(
            "import pytest\n@pytest.mark.skip('flaky')\ndef test_corsair_beak():\n    protrusion = 0.01\n    assert protrusion >= 0.005\n",
            encoding="utf-8",
        )
        (self.repo / "tests/e2e.spec.ts").write_text(
            "test.skip(browserName === 'webkit', 'webkit unsupported');\n"
            "def helper():\n"
            "    if not has_gpu:\n"
            "        pytest.skip('needs gpu')\n",
            encoding="utf-8",
        )
        (self.repo / "app.py").write_text("def step():\n    acc = 0\n    weapon.accuracy = 0.85\n    return acc\n", encoding="utf-8")
        (self.repo / "src_lib.rs").write_text(
            "#[cfg(test)]\nuse std::sync::Mutex;\npub fn prod() { let _ = ['--min-iou', '0']; }\n",
            encoding="utf-8",
        )

        res = rg.scan_reward_hacking(self.repo, base="HEAD")
        self.assertFalse(res["ok"])
        by_file = {}
        for f in res["findings"]:
            by_file.setdefault(f["file"], set()).add(f["rule"])
        self.assertIn("reward-hack-threshold-zero", by_file["build_props.py"])
        self.assertIn("reward-hack-primitive-standin", by_file["build_props.py"])
        self.assertIn("reward-hack-hardcoded-pass", by_file["gates/fidelity_gate.py"])
        self.assertIn("reward-hack-assertion-weakened", by_file["gates/fidelity_gate.py"])
        self.assertIn("reward-hack-test-skip", by_file["tests/test_gate.py"])
        self.assertIn("reward-hack-threshold-zero", by_file["src_lib.rs"])
        self.assertNotIn("app.py", by_file)
        self.assertNotIn("tests/e2e.spec.ts", by_file)

    def test_contract_lock_dotfiles_lock_deletion_defense_provenance_and_judge(self):
        for bad_t in ("min_iou=0.0", "min_iou=-0.5", "min_iou=1e-9"):
            with self.assertRaises(ValueError):
                rg.lock_contract(
                    self.repo,
                    slug="ghibli-3d",
                    gates=["gates/fidelity_gate.py", ".github/workflows/ci.yml"],
                    references=["refs/painting.png"],
                    thresholds=[bad_t],
                )

        lock_info = rg.lock_contract(
            self.repo,
            slug="ghibli-3d",
            gates=["gates/fidelity_gate.py", ".github/workflows/ci.yml"],
            references=["refs/painting.png"],
            thresholds=["min_iou=0.72"],
            required_producers=["dgx-spark"],
            artifacts=["out/workstation.glb"],
        )
        self.assertIn(".github/workflows/ci.yml", lock_info["gates"])

        (self.repo / "out").mkdir()
        glb = self.repo / "out/workstation.glb"
        glb.write_bytes(b"glTF\x02\x00\x00\x00sculpted-dgx-spark-mesh")
        _git(self.repo, "add", "out/workstation.glb")
        _git(self.repo, "commit", "-q", "-m", "add glb")

        rg.record_provenance(
            self.repo,
            slug="ghibli-3d",
            artifact_rel="out/workstation.glb",
            producer="dgx-spark",
            job_id="spark-job-88412a",
            inputs=["refs/painting.png"],
        )
        passed = rg.record_judge(
            self.repo,
            slug="ghibli-3d",
            artifact_rel="out/workstation.glb",
            judge_model="gemini-4-flash",
            independent_context=True,
            verdict="approve",
            open_p0_p1=0,
            goal_match_notes="Side-by-side 6-angle render matches the Ghibli workstation painting silhouette and brass tools.",
            shortcut_audit="Inspected mesh topology and textures; zero primitive cubes/cones or glued geometry.",
            compared_references=["refs/painting.png"],
        )
        self.assertEqual(passed["verdict"], "REWARD_GUARD_PASSED", passed)

        Path(lock_info["lock_file"]).unlink()
        deleted_lock = rg.evaluate_verdict(self.repo, slug="ghibli-3d")
        self.assertEqual(deleted_lock["verdict"], "REWARD_GUARD_BLOCKED")
        self.assertIn("contract-locked-and-intact", deleted_lock["failed_gates"])
        with self.assertRaises(ValueError):
            rg.lock_contract(self.repo, slug="ghibli-3d", gates=["gates/fidelity_gate.py"])


if __name__ == "__main__":
    unittest.main()
