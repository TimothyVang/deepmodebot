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

    def test_detects_universal_backend_hot_path_traps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "orders.py").write_text(
                "import asyncio, requests, time\n"
                "from sqlalchemy import create_engine\n\n"
                "@router.get('/orders')\n"
                "async def list_orders(order_ids, db):\n"
                "    eng = create_engine('postgresql://localhost/app')\n"
                "    time.sleep(0.05)\n"
                "    requests.get('https://billing.internal/status')\n"
                "    rows = []\n"
                "    for oid in order_ids:\n"
                "        rows.append(await db.fetchrow('SELECT * FROM orders WHERE id = $1', oid))\n"
                "    await asyncio.gather(*[fetch_item(i) for i in order_ids])\n"
                "    return rows\n",
                encoding="utf-8",
            )
            (root / "feed.sql").write_text(
                "SELECT id, body FROM posts ORDER BY id DESC LIMIT 50 OFFSET $1;\n",
                encoding="utf-8",
            )
            (root / "api.ts").write_text(
                "app.get('/users', async (req, res) => {\n"
                "  const pool = new Pool({ connectionString: process.env.DATABASE_URL });\n"
                "  const cfg = fs.readFileSync('cfg.json', 'utf8');\n"
                "  for (const id of req.ids) {\n"
                "    await prisma.user.findUnique({ where: { id } });\n"
                "  }\n"
                "  await Promise.all(req.ids.map(id => fetchUser(id)));\n"
                "});\n",
                encoding="utf-8",
            )

            py_ids = {f.rule_id for f in scan_file(root / "orders.py", root)}
            self.assertTrue(
                {"PERF-POOL-001", "PERF-ASYNC-002", "PERF-HTTP-001", "PERF-ASYNC-001", "PERF-DB-001", "PERF-FANOUT-001"}.issubset(py_ids),
                py_ids,
            )
            sql_ids = {f.rule_id for f in scan_file(root / "feed.sql", root)}
            self.assertIn("PERF-DB-002", sql_ids)

            ts_ids = {f.rule_id for f in scan_file(root / "api.ts", root)}
            self.assertEqual(
                ts_ids,
                {"PERF-POOL-001", "PERF-ASYNC-002", "PERF-ASYNC-001", "PERF-DB-001", "PERF-FANOUT-001"},
            )

    def test_clean_patterns_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gz.cs").write_text(
                "using var gz = new GZipStream(ms, CompressionLevel.Fastest, leaveOpen: true);\n",
                encoding="utf-8",
            )
            (root / "sqlite.sql").write_text(
                "PRAGMA mmap_size = 0;\nSELECT id FROM posts WHERE id < $1 ORDER BY id DESC LIMIT 20;\n",
                encoding="utf-8",
            )
            (root / "db.py").write_text(
                "import asyncio, httpx\n"
                "async def load_feed(conn, ids):\n"
                "    sem = asyncio.Semaphore(16)\n"
                "    stmt = await conn.prepare('SELECT * FROM feed WHERE id = ANY($1)', name='feed')\n"
                "    httpx.get('https://api.example.com/health', timeout=2.5)\n"
                "    await asyncio.gather(*[fetch_one(sem, i) for i in ids])\n"
                "    return stmt\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["--path", str(root), "--fail-on-high"]), 0)


if __name__ == "__main__":
    unittest.main()
