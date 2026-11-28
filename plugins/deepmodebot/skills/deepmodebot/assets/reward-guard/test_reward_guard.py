"""Adversarial red-to-green tests for Cracks 1-5 in reward_guard.py."""

import contextlib
import hashlib
import importlib.util
import inspect
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "reward_guard.py"
SPEC = importlib.util.spec_from_file_location("reward_guard_mod", MOD_PATH)
rg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rg
SPEC.loader.exec_module(rg)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=30)


def _sign_spark_receipt(priv: Ed25519PrivateKey, art_path: Path, host: str = "dgx-spark", job_id: str = "spark-88412a") -> dict:
    outputs = [{"file": art_path.name, "bytes": art_path.stat().st_size, "sha256": hashlib.sha256(art_path.read_bytes()).hexdigest()}]
    payload_dict = {
        "host": host,
        "job_id": job_id,
        "endpoint": "/generate",
        "comfy_prompt_ids": ["f75d120f-e41d-4b7b-bcc6-c94f7525ec17"],
        "studio_runner": "",
        "model_checkpoints": ["pixal3d_multiview_bf16.safetensors"],
        "raw_spark_outputs": outputs,
    }
    canonical = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = priv.sign(canonical).hex()
    return {"schema": "spark3d.provenance_receipt.v1", **payload_dict, "receipt_ed25519_sig": sig}


def _install_fake_omp_bin(bin_dir: Path, mode_file: Path) -> None:
    shim_py = bin_dir / "fake_omp.py"
    shim_py.write_text(
        """import json, pathlib, sys
args = sys.argv[1:]
assert "--no-tools" in args and "--mode" in args
prompt_txt = pathlib.Path("prompt.txt").read_text(encoding="utf-8")
inp = json.loads(prompt_txt.split("INPUT DATA:\\n", 1)[1])
mode = pathlib.Path(r'''""" + str(mode_file) + """''').read_text(encoding="utf-8").strip()
payload = {
    "schema_version": 1,
    "artifact_sha256": inp["artifact_sha256"],
    "vision_available": True,
    "verdict": "approve",
    "open_p0_p1": 0,
    "is_primitive_or_shortcut": (mode == "shortcut"),
    "reference_observations": [{"ref": r["ref"], "finding": "Detailed Ghibli workbench with curved brass tools."} for r in inp["references"]],
    "render_observations": [{"render": r["render"], "finding": "Side-by-side silhouette and clay topology inspection."} for r in inp["candidate_renders"]],
    "goal_match_notes": "Side-by-side multi-angle comparison against the locked Ghibli reference painting.",
    "shortcut_audit": "Audited untextured clay and textured views for primitive cubes, cones, or flat slabs.",
}
print(json.dumps({
    "type": "message_end",
    "message": {
        "role": "assistant",
        "provider": "test-prov",
        "model": "smol",
        "credentialId": "cred-1",
        "stopReason": "stop",
        "content": [{"type": "text", "text": json.dumps(payload)}],
    },
}))
""",
        encoding="utf-8",
    )
    if os.name == "nt":
        (bin_dir / "omp.cmd").write_text(f'@"{sys.executable}" "{shim_py}" %*\r\n', encoding="utf-8")
    else:
        omp = bin_dir / "omp"
        omp.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{shim_py}" "$@"\n', encoding="utf-8")
        omp.chmod(0o755)


class RewardGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="reward-guard-test-", ignore_cleanup_errors=True)
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
        (self.repo / "refs/painting.png").write_bytes(b"\x89PNG\r\n\x1a\nghibli-concept-art-bytes-0001")
        (self.repo / "tests/test_gate.py").write_text(
            "def test_corsair_beak():\n    protrusion = 0.06\n    assert protrusion >= 0.045\n",
            encoding="utf-8",
        )
        (self.repo / "app.py").write_text("def step():\n    acc = 1\n    weapon.accuracy = 0.95\n    return acc\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "init")

    def test_scan_catches_sub_050_iou_gap_scratch_primitives_and_mode_off(self):
        (self.repo / ".scratch/tmp").mkdir(parents=True)
        (self.repo / ".scratch/tmp/make_cones.py").write_text(
            "import bpy\nbpy.ops.mesh.primitive_cube_add(size=2)\ncreate_cone(radius=1)\n",
            encoding="utf-8",
        )
        (self.repo / "build_props.py").write_text(
            "cmd1 = ['python', 'gate.py', '--min-iou', '+0.25']\n"
            "cmd2 = ['python', 'gate.py', '--min-iou', '0.25e0']\n"
            "cmd3 = ['python', 'gate.py', '--min-iou', '-.5']\n"
            "cmd4 = ['python', 'gate.py', '--min-iou', '0.']\n"
            "cmd5 = ['python', 'gate.py', '--min-i', '.1']\n"
            "cmd6 = ['python', 'gate.py', '--min-iou', '-inf', '--min', '0.0_1']\n"
            "cfg = {'min_ssim': .4}\n",
            encoding="utf-8",
        )
        (self.repo / "clean_clip.py").write_text(
            "cmd = ['python', 'gate.py', '--min-iou', '0.72', '--min-clip-score', '0.28', '--min-port', '80']\n",
            encoding="utf-8",
        )
        (self.repo / "gates/fidelity_gate.py").write_text(
            "MIN_IOU = 0.30\nMAX_HOLES = 12\ndef check(iou, holes):\n    return {'verdict': 'PASS', 'iou': 1.0}\n",
            encoding="utf-8",
        )
        (self.repo / "tests/test_gate.py").write_text(
            "import pytest\n@pytest.mark.skip('flaky')\ndef test_corsair_beak():\n    protrusion = 0.01\n",
            encoding="utf-8",
        )
        (self.repo / ".scratch/test_gate.sh").write_text(
            ("echo pad\n" * 35000) + "pytest --no-cov --cov-fail-under 15\n",
            encoding="utf-8",
        )
        (self.repo / ".github/workflows/ci.yml").write_text(
            "name: ci\njobs:\n  test:\n    continue-on-error: true\n",
            encoding="utf-8",
        )
        (self.repo / "tsconfig.json").write_text('{\n  "compilerOptions": {\n    "strict": false\n  }\n}\n', encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src/service.py").write_text(
            "import os\ndef charge():\n    if 'PYTEST_CURRENT_TEST' in os.environ:\n        return {'paid': True}\n    return {'paid': False}\n",
            encoding="utf-8",
        )
        (self.repo / "app.py").write_text("def step():\n    acc = 0\n    weapon.accuracy = 0.85\n    return acc\n", encoding="utf-8")

        res = rg.scan_reward_hacking(self.repo, base="HEAD")
        self.assertFalse(res["ok"])
        by_file = {}
        for f in res["findings"]:
            by_file.setdefault(f["file"], set()).add(f["rule"])
        self.assertIn("reward-hack-primitive-standin", by_file[".scratch/tmp/make_cones.py"])
        self.assertIn("reward-hack-threshold-zero", by_file["build_props.py"])
        self.assertEqual(sum(1 for f in res["findings"] if f["file"] == "build_props.py" and f["rule"] == "reward-hack-threshold-zero"), 7)
        self.assertNotIn("clean_clip.py", by_file)
        self.assertIn("reward-hack-hardcoded-pass", by_file["gates/fidelity_gate.py"])
        self.assertIn("reward-hack-assertion-weakened", by_file["gates/fidelity_gate.py"])
        self.assertIn("reward-hack-test-skip", by_file["tests/test_gate.py"])
        self.assertIn("reward-hack-threshold-zero", by_file[".scratch/test_gate.sh"])
        self.assertIn("reward-hack-ci-or-typecheck-neutered", by_file[".github/workflows/ci.yml"])
        self.assertIn("reward-hack-ci-or-typecheck-neutered", by_file["tsconfig.json"])
        self.assertIn("reward-hack-prod-test-branch", by_file["src/service.py"])
        self.assertNotIn("app.py", by_file)

    def test_no_runner_injection_rejects_3d_render_swap_and_sqlite_forgery_without_spark_ed25519(self):
        # Crack 2: runner= injection parameter is permanently removed from run_judge.
        self.assertNotIn("runner", inspect.signature(rg.run_judge).parameters)
        with self.assertRaises(SystemExit):
            rg.build_parser().parse_args(["record-judge", "--slug", "x"])
        with self.assertRaises(ValueError):
            rg._parse_thresholds(["min_iou=0.25"])

        farm_priv = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"farm-secret-seed").digest())
        farm_pub = farm_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        spark_priv = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"spark-secret-seed").digest())
        spark_pub = spark_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

        holdout = Path(self.tmp.name) / "outer-holdout"
        rg.lock_contract(
            self.repo,
            slug="render-2d",
            gates=["gates/fidelity_gate.py"],
            references=["refs/painting.png"],
            thresholds=["min_iou=0.72"],
            required_producers=["render-farm"],
            trusted_pubkeys=[f"render-farm={farm_pub}"],
            artifacts=["out/poster.png"],
            state_dir=holdout,
        )
        (self.repo / "out").mkdir()
        poster = self.repo / "out/poster.png"
        poster.write_bytes(b"\x89PNG\r\n\x1a\nrendered-ghibli-poster-output")
        dummy_glb = self.repo / "out/model.glb"
        dummy_glb.write_bytes(b"glTF\x02\x00\x00\x00mesh")

        # Crack 1: 3D mesh artifact rejects caller-supplied --renders to block 1-pixel ref swap.
        with self.assertRaises(ValueError):
            rg.run_judge(
                self.repo, slug="render-2d", artifact_rel="out/model.glb",
                renders=["out/poster.png"], state_dir=holdout,
            )
        dummy_glb.unlink()

        rec_p = self.repo / "out/receipt.json"
        rec_p.write_text(json.dumps(_sign_spark_receipt(farm_priv, poster, host="render-farm")), encoding="utf-8")
        _git(self.repo, "add", "out")
        _git(self.repo, "commit", "-q", "-m", "add poster")

        rg.record_provenance(
            self.repo, slug="render-2d", artifact_rel="out/poster.png",
            receipt_rel="out/receipt.json", inputs=["refs/painting.png"], state_dir=holdout,
        )

        bin_dir = Path(self.tmp.name) / "fake-bin"
        bin_dir.mkdir()
        mode_file = Path(self.tmp.name) / "judge-mode.txt"
        _install_fake_omp_bin(bin_dir, mode_file)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
        try:
            mode_file.write_text("shortcut", encoding="utf-8")
            blocked = rg.run_judge(self.repo, slug="render-2d", artifact_rel="out/poster.png", state_dir=holdout)
            self.assertEqual(blocked["verdict"], "REWARD_GUARD_BLOCKED")

            mode_file.write_text("approve", encoding="utf-8")
            passed = rg.run_judge(self.repo, slug="render-2d", artifact_rel="out/poster.png", state_dir=holdout)
            self.assertEqual(passed["verdict"], "REWARD_GUARD_PASSED", passed)
        finally:
            os.environ["PATH"] = old_path

        # Crack 2: When required_producers includes dgx-spark, forging SQLite without dgx-spark's Ed25519 verdict_sig fails closed!
        rg.lock_contract(
            self.repo,
            slug="spark-sealed",
            gates=["gates/fidelity_gate.py"],
            references=["refs/painting.png"],
            thresholds=["min_iou=0.72"],
            required_producers=["dgx-spark"],
            trusted_pubkeys=[f"dgx-spark={spark_pub}"],
            artifacts=["out/poster.png"],
            state_dir=holdout,
        )
        spark_rec = self.repo / "out/spark_receipt.json"
        spark_rec.write_text(json.dumps(_sign_spark_receipt(spark_priv, poster, host="dgx-spark")), encoding="utf-8")
        _git(self.repo, "add", "out/spark_receipt.json")
        _git(self.repo, "commit", "-q", "-m", "add spark receipt")
        rg.record_provenance(
            self.repo, slug="spark-sealed", artifact_rel="out/poster.png",
            receipt_rel="out/spark_receipt.json", inputs=["refs/painting.png"], state_dir=holdout,
        )
        # Copy real transcript from render-2d into spark-sealed SQLite WITHOUT dgx-spark Ed25519 verdict_sig:
        src_db = holdout / "render-2d" / "reward-guard.db"
        dst_db = holdout / "spark-sealed" / "reward-guard.db"
        with contextlib.closing(sqlite3.connect(src_db)) as sc:
            sc.row_factory = sqlite3.Row
            jv = dict(sc.execute("SELECT * FROM judge_verdicts").fetchone())
        for sub in (holdout / "render-2d").glob("judge-*"):
            target_sub = (holdout / "spark-sealed") / sub.name
            target_sub.mkdir(exist_ok=True)
            for f in sub.iterdir():
                if f.is_file():
                    (target_sub / f.name).write_bytes(f.read_bytes())
        with contextlib.closing(sqlite3.connect(dst_db)) as dc:
            dc.execute(
                """INSERT INTO judge_verdicts(
                       slug, artifact_path, artifact_sha256, judge_model, credential_id,
                       transcript_path, transcript_sha256, renders_json, compared_refs_json,
                       verdict, open_p0_p1, is_shortcut, goal_match_notes, shortcut_audit,
                       verdict_signer, verdict_sig, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "spark-sealed", jv["artifact_path"], jv["artifact_sha256"], jv["judge_model"], jv["credential_id"],
                    jv["transcript_path"], jv["transcript_sha256"], jv["renders_json"], jv["compared_refs_json"],
                    "approve", 0, 0, jv["goal_match_notes"], jv["shortcut_audit"],
                    "dgx-spark", "00" * 64, jv["created_at"],
                ),
            )
            dc.commit()
        forged_eval = rg.evaluate_verdict(self.repo, slug="spark-sealed", state_dir=holdout)
        self.assertEqual(forged_eval["verdict"], "REWARD_GUARD_BLOCKED")
        self.assertIn("independent-judge-approved", forged_eval["failed_gates"])

        # Sign canonical verdict with real spark_priv -> passes offline Ed25519 verification!
        v_canon = rg.canonical_verdict_payload(
            slug="spark-sealed",
            artifact_sha256=jv["artifact_sha256"],
            transcript_sha256=jv["transcript_sha256"],
            renders_sha256=json.loads(jv["renders_json"]),
            refs_sha256=json.loads(jv["compared_refs_json"]),
            verdict="approve",
        )
        real_v_sig = spark_priv.sign(v_canon).hex()
        with contextlib.closing(sqlite3.connect(dst_db)) as dc:
            dc.execute("UPDATE judge_verdicts SET verdict_sig = ? WHERE slug = 'spark-sealed'", (real_v_sig,))
            dc.commit()
        signed_eval = rg.evaluate_verdict(self.repo, slug="spark-sealed", state_dir=holdout)
        self.assertEqual(signed_eval["verdict"], "REWARD_GUARD_PASSED", signed_eval)

        # Tampering SQLite trusted_pubkeys or required_producers without matching contract-lock.json fails closed!
        with contextlib.closing(sqlite3.connect(dst_db)) as dc:
            dc.execute("UPDATE contracts SET required_producers_json = '[]' WHERE slug = 'spark-sealed'")
            dc.commit()
        mismatch_eval = rg.evaluate_verdict(self.repo, slug="spark-sealed", state_dir=holdout)
        self.assertEqual(mismatch_eval["verdict"], "REWARD_GUARD_BLOCKED")
        self.assertIn("contract-locked-and-intact", mismatch_eval["failed_gates"])

        # Clean judge-owned .blend rendering ignores 50% resolution_percentage and compositor hijacks when Blender is present.
        try:
            blender_exe = rg._find_blender_executable()
        except ValueError:
            blender_exe = None
        if blender_exe is not None:
            hijack_py = Path(self.tmp.name) / "make_hijack_blend.py"
            hijack_blend = Path(self.tmp.name) / "hijack.blend"
            hijack_py.write_text(
                "import bpy, sys\n"
                "out = sys.argv[sys.argv.index('--') + 1]\n"
                "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
                "bpy.ops.mesh.primitive_cube_add(size=1.0)\n"
                "s = bpy.context.scene\n"
                "s.render.resolution_percentage = 50\n"
                "s.render.use_compositing = True\n"
                "bpy.ops.wm.save_as_mainfile(filepath=out)\n",
                encoding="utf-8",
            )
            subprocess.run(
                [str(blender_exe), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(hijack_py), "--", str(hijack_blend)],
                check=True, capture_output=True, text=True,
            )
            rdir = Path(self.tmp.name) / "owned-blend-out"
            rdir.mkdir()
            rendered = rg._render_3d_artifact_owned(hijack_blend, rdir)
            self.assertEqual(len(rendered), 3)
            for _fn, _fp, data, _sha in rendered:
                self.assertEqual((int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")), (384, 384))

    def test_universal_code_diff_judge_and_pure_python_ed25519_work_without_dgx_spark(self):
        # 1. Verify pure-Python RFC 8032 ed25519_pubkey + ed25519_sign match cryptography byte-for-byte!
        seed = hashlib.sha256(b"universal-supervisor-ephemeral-seed").digest()
        ck = Ed25519PrivateKey.from_private_bytes(seed)
        expected_pub = ck.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.assertEqual(rg.ed25519_pubkey(seed), expected_pub)
        msg = b"universal-code-verdict-payload"
        self.assertEqual(rg.ed25519_sign(seed, msg), ck.sign(msg).hex())
        self.assertTrue(rg.ed25519_verify(expected_pub, msg, rg.ed25519_sign(seed, msg)))

        # 2. Pure software repo (zero PNGs, zero 3D meshes, zero dgx-spark!): lock-contract + run-judge + supervisor Ed25519!
        holdout = Path(self.tmp.name) / "code-holdout"
        rg.lock_contract(
            self.repo,
            slug="api-bugfix",
            goal="Compute real tax rate in app.py without hardcoding test inputs",
            verify_cmd=f'"{sys.executable}" -c "import pathlib, sys; sys.exit(0 if pathlib.Path(\'app.py\').is_file() else 1)"',
            gates=["tests/test_gate.py"],
            trusted_pubkeys=[f"loop-supervisor={expected_pub}"],
            state_dir=holdout,
        )
        (self.repo / "app.py").write_text("def step():\n    return 42\n", encoding="utf-8")

        bin_dir = Path(self.tmp.name) / "code-fake-bin"
        bin_dir.mkdir()
        mode_file = Path(self.tmp.name) / "code-judge-mode.txt"
        _install_fake_omp_bin(bin_dir, mode_file)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
        try:
            mode_file.write_text("shortcut", encoding="utf-8")
            rej = rg.run_judge(
                self.repo, slug="api-bugfix", state_dir=holdout,
                signing_seed_hex=seed.hex(), signer_name="loop-supervisor",
            )
            self.assertEqual(rej["verdict"], "REWARD_GUARD_BLOCKED")

            mode_file.write_text("approve", encoding="utf-8")
            ok = rg.run_judge(
                self.repo, slug="api-bugfix", state_dir=holdout,
                signing_seed_hex=seed.hex(), signer_name="loop-supervisor",
            )
            self.assertEqual(ok["verdict"], "REWARD_GUARD_PASSED", ok)
        finally:
            os.environ["PATH"] = old_path

        # 3. Editing code after run-judge invalidates the signed code-diff verdict immediately!
        (self.repo / "app.py").write_text("def step():\n    return 999\n", encoding="utf-8")
        stale = rg.evaluate_verdict(self.repo, slug="api-bugfix", state_dir=holdout)
        self.assertEqual(stale["verdict"], "REWARD_GUARD_BLOCKED")
        self.assertIn("independent-judge-approved", stale["failed_gates"])

        # 4. Adding a >262 KB untracked Python file invalidates the signed code-diff verdict too!
        (self.repo / "app.py").write_text("def step():\n    return 42\n", encoding="utf-8")
        self.assertEqual(rg.evaluate_verdict(self.repo, slug="api-bugfix", state_dir=holdout)["verdict"], "REWARD_GUARD_PASSED")
        (self.repo / "large_untracked.py").write_text("x = 1\n" * 60000, encoding="utf-8")
        large_stale = rg.evaluate_verdict(self.repo, slug="api-bugfix", state_dir=holdout)
        self.assertEqual(large_stale["verdict"], "REWARD_GUARD_BLOCKED")
        self.assertIn("independent-judge-approved", large_stale["failed_gates"])


    def test_all_domain_software_ml_e2e_perf_compiler_and_security_reward_hacks(self):
        # Verify Python scanner catches non-3D reward hacks across Web/E2E, Perf, ML, Compilers, Security, and Snapshots.
        (self.repo / "package.json").write_text('{\n  "scripts": {\n    "test": "echo ok",\n    "lint": "echo err && exit 1"\n  }\n}\n', encoding="utf-8")
        (self.repo / "pyproject.toml").write_text('[tool.mypy]\ndisallow_untyped_defs = false\n', encoding="utf-8")
        (self.repo / "train_model.py").write_text("def run(model, X_test, y_test):\n    model.fit(X_test, y_test)\n", encoding="utf-8")
        (self.repo / "e2e").mkdir()
        (self.repo / "e2e" / "orders.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('orders', async ({ page }) => {\n"
            "  await page.route('**/api/orders', r => r.fulfill({ status: 200, body: '[]' }));\n"
            "  await expect(page).toHaveScreenshot({ maxDiffPixelRatio: 0.35 });\n"
            "  await axe.disableRules(['color-contrast']);\n"
            "});\n",
            encoding="utf-8",
        )
        (self.repo / "src_client.py").write_text("import requests\ndef fetch(u):\n    return requests.get(u, verify=False)\n", encoding="utf-8")
        (self.repo / "run_ci.sh").write_text("jest -u\ngo test ./... -run=^$\n", encoding="utf-8")
        res = rg.scan_reward_hacking(self.repo)
        self.assertFalse(res["ok"])
        rules = {f["rule"] for f in res["findings"]}
        for expected_rule in (
            "reward-hack-noop-script",
            "reward-hack-ci-or-typecheck-neutered",
            "reward-hack-eval-leakage",
            "reward-hack-e2e-api-stubbed",
            "reward-hack-visual-tolerance-inflated",
            "reward-hack-a11y-disabled",
            "reward-hack-integrity-bypass",
            "reward-hack-snapshot-overwrite",
            "reward-hack-threshold-zero",
        ):
            self.assertIn(expected_rule, rules, res["findings"])
        pkg_hits = [f for f in res["findings"] if f["file"] == "package.json"]
        self.assertEqual(len(pkg_hits), 1)

    def test_universal_artifact_judge_inspects_xlsx_wav_svg_sqlite_and_proof_iac_rules_without_refs_or_dgx(self):
        import shutil as _sh
        import struct as _st
        import wave as _wv
        import zipfile as _zf

        # 1. Static parity on Formal Proofs (.lean/.cfg/.smt2), IaC suppressions (.tf), vacuous SQL, and Three.js/Unreal primitives.
        (self.repo / "Theorem.lean").write_text("theorem t1 : 1 + 1 = 2 := by\n  sorry\n", encoding="utf-8")
        (self.repo / "Spec.cfg").write_text("\\* INVARIANT TypeOK\n", encoding="utf-8")
        (self.repo / "main.tf").write_text("# checkov:skip=CKV_AWS_20\nresource \"aws_s3_bucket\" \"b\" {}\n", encoding="utf-8")
        (self.repo / "validators").mkdir()
        (self.repo / "validators" / "dq.sql").write_text("SELECT id FROM broken_rows WHERE 1=0;\n", encoding="utf-8")
        (self.repo / "scene.ts").write_text("const mesh = new THREE.BoxGeometry(1, 1, 1);\n", encoding="utf-8")
        sres = rg.scan_reward_hacking(self.repo)
        srules = {f["rule"] for f in sres["findings"]}
        for r in ("reward-hack-proof-escape", "reward-hack-scanner-suppressed", "reward-hack-vacuous-query", "reward-hack-primitive-standin"):
            self.assertIn(r, srules, sres["findings"])
        for clean_f in ("Theorem.lean", "Spec.cfg", "main.tf", "scene.ts"):
            (self.repo / clean_f).unlink()
        _sh.rmtree(self.repo / "validators")

        # 2. Multi-domain owned artifact telemetry: .xlsx formulas, .svg primitive-only detection, .sqlite rows/FKs, and silent .wav rejection!
        out_dir = self.repo / "artifacts"
        out_dir.mkdir()
        xlsx_p = out_dir / "budget.xlsx"
        with _zf.ZipFile(xlsx_p, "w") as zf:
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet><sheetData>'
                '<row r="1"><c r="A1"><v>100</v></c><c r="A2"><v>250</v></c><c r="A3"><f>SUM(A1:A2)</f><v>350</v></c></row>'
                '</sheetData></worksheet>',
            )
        xlsx_info = rg._inspect_office_or_pdf_artifact(xlsx_p)
        self.assertEqual(xlsx_info["formula_cell_count"], 1)
        self.assertEqual(xlsx_info["value_cell_count"], 3)
        self.assertEqual(xlsx_info["formula_error_count"], 0)

        svg_p = out_dir / "diagram.svg"
        svg_p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="50" height="50"/><circle r="10"/></svg>', encoding="utf-8")
        svg_info = rg._inspect_svg_or_data_artifact(svg_p)
        self.assertTrue(svg_info["primitive_box_circle_only"])

        silent_wav = out_dir / "silent.wav"
        with _wv.open(str(silent_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 8000)

        real_wav = out_dir / "speech.wav"
        with _wv.open(str(real_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            pcm = [_st.pack("<h", int(12000 * ((i % 97) / 97.0 - 0.5) * (0.3 + 0.7 * ((i // 1600) % 2)))) for i in range(8000)]
            wf.writeframes(b"".join(pcm))

        # 3. Reference-free run-judge on .xlsx and .wav (zero reference images, zero dgx-spark!):
        seed = hashlib.sha256(b"artifact-supervisor-seed").digest()
        pub = rg.ed25519_pubkey(seed)
        holdout = Path(self.tmp.name) / "artifact-holdout"
        rg.lock_contract(
            self.repo,
            slug="multi-domain",
            goal="Produce an Excel budget with live SUM formulas and non-silent spoken audio",
            trusted_pubkeys=[f"loop-supervisor={pub}"],
            artifacts=["artifacts/budget.xlsx", "artifacts/speech.wav"],
            state_dir=holdout,
        )
        # Silent WAV is deterministically rejected BEFORE even calling the LLM!
        with self.assertRaises(ValueError):
            rg.run_judge(self.repo, slug="multi-domain", artifact_rel="artifacts/silent.wav", state_dir=holdout)

        bin_dir = Path(self.tmp.name) / "art-fake-bin"
        bin_dir.mkdir()
        mode_file = Path(self.tmp.name) / "art-judge-mode.txt"
        _install_fake_omp_bin(bin_dir, mode_file)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
        try:
            mode_file.write_text("approve", encoding="utf-8")
            rg.run_judge(
                self.repo, slug="multi-domain", artifact_rel="artifacts/budget.xlsx",
                state_dir=holdout, signing_seed_hex=seed.hex(), signer_name="loop-supervisor",
            )
            final_v = rg.run_judge(
                self.repo, slug="multi-domain", artifact_rel="artifacts/speech.wav",
                state_dir=holdout, signing_seed_hex=seed.hex(), signer_name="loop-supervisor",
            )
            self.assertEqual(final_v["verdict"], "REWARD_GUARD_PASSED", final_v)
        finally:
            os.environ["PATH"] = old_path

if __name__ == "__main__":
    unittest.main()
