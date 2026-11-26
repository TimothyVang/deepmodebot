"""Unit tests for assets/memory/project_memory.py."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "project_memory.py"
SPEC = importlib.util.spec_from_file_location("project_memory_mod", MOD_PATH)
pm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pm
SPEC.loader.exec_module(pm)


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pm-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True, capture_output=True)
    def test_put_dedups_identical_content_and_recalls_within_token_budget(self):
        r1 = pm.put_memory(self.root, key="inv:root", kind="convention", content="Keep all writes inside project root.", priority=0, tags="contain")
        self.assertEqual(r1["status"], "inserted")
        r2 = pm.put_memory(self.root, key="inv:root-dup", kind="convention", content="Keep all   writes inside project root.", priority=2, tags="extra")
        self.assertEqual(r2["status"], "deduped")
        self.assertEqual(r2["key"], "inv:root")

        pm.put_memory(self.root, key="gotcha:sqlite", kind="gotcha", content="Always enable WAL and mmap_size for fast SQLite reads.", priority=1, tags="db,perf")
        pm.put_memory(self.root, key="note:large", kind="fact", content=" ".join(["verbose"] * 220), priority=3)

        recalled = pm.recall_memories(self.root, query="sqlite WAL", budget_tokens=90)
        keys = [i["key"] for i in recalled["items"]]
        self.assertIn("inv:root", keys)
        self.assertIn("gotcha:sqlite", keys)
        self.assertNotIn("note:large", keys)
        self.assertLessEqual(recalled["used_tokens"], 90)

        xml_out = pm.format_xml(recalled)
        self.assertIn("<deepmode-memory", xml_out)
        self.assertIn('k="gotcha:sqlite"', xml_out)
        yaml_out = pm.format_yaml(recalled)
        self.assertIn("used_tokens:", yaml_out)

        zero_match = pm.recall_memories(self.root, query="zzz_nonexistent_token_999", budget_tokens=500)
        self.assertEqual([i["key"] for i in zero_match["items"]], ["inv:root"])

    def test_compact_evicts_expired_and_respects_max_records_keeping_p0(self):
        pm.put_memory(self.root, key="p0:rule", kind="convention", content="Critical invariant.", priority=0)
        for i in range(6):
            pm.put_memory(self.root, key=f"f:{i}", kind="fact", content=f"Fact number {i}", priority=3)
        res = pm.compact_memory(self.root, max_records=3)
        self.assertEqual(res["remaining"], 3)
        self.assertEqual(res["trimmed"], 4)
        after = pm.recall_memories(self.root, budget_tokens=2000)
        self.assertIn("p0:rule", [i["key"] for i in after["items"]])


if __name__ == "__main__":
    unittest.main()
