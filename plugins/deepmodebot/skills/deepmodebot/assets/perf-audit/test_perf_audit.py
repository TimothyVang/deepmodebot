import tempfile
import unittest
from pathlib import Path

from perf_audit import main, scan_file


class PerfAuditTests(unittest.TestCase):
    def test_detects_high_confidence_anti_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "srv.go").write_text('import "github.com/gin-contrib/gzip"\n', encoding="utf-8")
            (root / "db.py").write_text("pool = asyncpg.create_pool(statement_cache_size=0)\n", encoding="utf-8")
            (root / "gz.cs").write_text("using var gz = new GZipStream(ms, CompressionLevel.Fastest);\n", encoding="utf-8")
            (root / "sqlite.sql").write_text("PRAGMA mmap_size = 268435456;\nLIMIT $1;\n", encoding="utf-8")
            (root / "sim.cpp").write_text("std::unordered_map<int, int> m;\nstd::cout << 1 << std::endl;\n", encoding="utf-8")
            (root / "pg.cs").write_text('var cs = "Host=localhost;Database=app;";\n', encoding="utf-8")

            findings = []
            for name in ("srv.go", "db.py", "gz.cs", "sqlite.sql", "sim.cpp", "pg.cs"):
                findings.extend(scan_file(root / name, root))

            ids = {f.rule_id for f in findings}
            self.assertEqual(
                ids,
                {
                    "PERF-GO-001",
                    "PERF-PY-001",
                    "PERF-NET-001",
                    "PERF-SQLITE-001",
                    "PERF-SQL-001",
                    "PERF-CPP-001",
                    "PERF-CPP-002",
                    "PERF-NET-002",
                },
            )
            self.assertEqual(main(["--path", str(root), "--fail-on-high"]), 1)

    def test_clean_patterns_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gz.cs").write_text(
                "using var gz = new GZipStream(ms, CompressionLevel.Fastest, leaveOpen: true);\n",
                encoding="utf-8",
            )
            (root / "sqlite.sql").write_text("PRAGMA mmap_size = 0;\nLIMIT 20;\n", encoding="utf-8")
            (root / "db.py").write_text("stmt = await conn.prepare(sql, name='feed')\n", encoding="utf-8")

            self.assertEqual(main(["--path", str(root), "--fail-on-high"]), 0)


if __name__ == "__main__":
    unittest.main()
