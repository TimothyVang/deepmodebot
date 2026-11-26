import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

import self_cleanup
from self_cleanup import run_self_cleanup


class SelfCleanupTests(unittest.TestCase):
    def test_dry_run_and_apply_preserve_tracked_and_unknown_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "src").mkdir()
            tracked = root / "src" / "app.py"
            tracked.write_text("print('keep')\n", encoding="utf-8")

            pycache = root / "src" / "__pycache__"
            pycache.mkdir()
            (pycache / "app.cpython-312.pyc").write_bytes(b"0" * 4096)

            stale_tmp = root / ".scratch" / "tmp" / "check-999"
            stale_tmp.mkdir(parents=True)
            stale_file = stale_tmp / "out.log"
            stale_file.write_bytes(b"x" * 8192)
            old_ts = time.time() - 72 * 3600
            os.utime(stale_file, (old_ts, old_ts))
            ro_obj = stale_tmp / ".git" / "objects" / "4b" / "readonly_blob"
            ro_obj.parent.mkdir(parents=True)
            ro_obj.write_bytes(b"g" * 1024)
            os.chmod(ro_obj, 0o444)
            os.utime(ro_obj, (old_ts, old_ts))
            os.utime(ro_obj.parent, (old_ts, old_ts))
            os.utime(ro_obj.parent.parent, (old_ts, old_ts))
            os.utime(stale_tmp / ".git", (old_ts, old_ts))
            os.utime(stale_tmp, (old_ts, old_ts))

            for idx in range(4):
                surf = root / ".scratch" / "gen-ui" / f"s{idx}"
                surf.mkdir(parents=True)
                f = surf / "index.html"
                f.write_text("<html></html>", encoding="utf-8")
                ts = time.time() - (10 - idx) * 60
                os.utime(f, (ts, ts))
                os.utime(surf, (ts, ts))

            unknown_big = root / ".scratch" / "consolidation-2026"
            unknown_big.mkdir(parents=True)
            (unknown_big / "big.bin").write_bytes(b"z" * (11 * 1024 * 1024))

            preview = run_self_cleanup(root, apply=False, max_age_hours=24, keep_surfaces=2)
            self.assertFalse(preview["applied"])
            self.assertTrue(pycache.exists())
            self.assertTrue(stale_tmp.exists())
            self.assertEqual(len(preview["protected_large_scratch"]), 1)
            self.assertEqual(preview["protected_large_scratch"][0]["path"], ".scratch/consolidation-2026")

            applied = run_self_cleanup(root, apply=True, max_age_hours=24, keep_surfaces=2)
            self.assertTrue(applied["applied"])
            self.assertFalse(pycache.exists())
            self.assertFalse(stale_tmp.exists())
            self.assertTrue(tracked.exists())
            self.assertTrue(unknown_big.exists())
            remaining_surfaces = sorted(p.name for p in (root / ".scratch" / "gen-ui").iterdir())
            self.assertEqual(remaining_surfaces, ["s2", "s3"])

    def test_cli_defaults_root_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            pycache = root / "pkg" / "__pycache__"
            pycache.mkdir(parents=True)
            (pycache / "mod.pyc").write_bytes(b"1" * 512)
            buf = io.StringIO()
            with patch.object(self_cleanup, "DEFAULT_ROOT", root), contextlib.redirect_stdout(buf):
                rc = self_cleanup.main(["--apply", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["applied"])
            self.assertFalse(pycache.exists())


if __name__ == "__main__":
    unittest.main()
