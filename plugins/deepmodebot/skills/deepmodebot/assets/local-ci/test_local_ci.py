"""Unit tests for assets/local-ci/local_ci.py."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

MOD_PATH = Path(__file__).resolve().parent / "local_ci.py"
SPEC = importlib.util.spec_from_file_location("local_ci_mod", MOD_PATH)
lci = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lci
SPEC.loader.exec_module(lci)

SAMPLE_CI = """name: sample-ci
on: [local-edit, pre-pr]
env:
  DEMO_FLAG: "1"
jobs:
  lint:
    inputs: ["src/*.txt"]
    steps:
      - name: check flag
        run: python -B -c "import os; assert os.environ['DEMO_FLAG'] == '1'"
  unit:
    inputs: ["src/*.txt"]
    steps:
      - name: pass
        run: python -B -c "print('ok')"
  summary:
    needs: [lint, unit]
    steps:
      - name: final
        run: python -B -c "print('done')"
"""


class LocalCiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-ci-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src/a.txt").write_text("hello", encoding="utf-8")
        (self.root / ".deepmodebot").mkdir()
        self.ci = self.root / ".deepmodebot/ci.yml"
        self.ci.write_text(SAMPLE_CI, encoding="utf-8")

    def test_dag_waves_run_and_merkle_cache_hit_and_invalidation(self):
        doc = lci.parse_yaml_lite(SAMPLE_CI)
        self.assertEqual(lci.validate_workflow(doc), [])
        self.assertEqual(lci.plan_dag(doc), [["lint", "unit"], ["summary"]])

        r1 = lci.run_workflow(self.root, self.ci, use_cache=True)
        self.assertTrue(r1["ok"], r1)
        by_id1 = {j["id"]: j["status"] for j in r1["jobs"]}
        self.assertEqual(by_id1, {"lint": "passed", "unit": "passed", "summary": "passed"})
        r2 = lci.run_workflow(self.root, self.ci, use_cache=True)
        self.assertTrue(r2["ok"])
        by_id2 = {j["id"]: j["status"] for j in r2["jobs"]}
        self.assertEqual(by_id2["lint"], "cached")
        self.assertEqual(by_id2["unit"], "cached")

        (self.root / "src/a.txt").write_text("changed", encoding="utf-8")
        r3 = lci.run_workflow(self.root, self.ci, use_cache=True)
        by_id3 = {j["id"]: j["status"] for j in r3["jobs"]}
        self.assertEqual(by_id3["lint"], "passed")

    def test_merkle_rejects_parent_traversal_inputs(self):
        with self.assertRaises(ValueError):
            lci.compute_job_merkle(self.root, "evil", {"inputs": ["../outside.txt"], "steps": [{"run": "echo hi"}]}, {})

    def test_cycle_detection_rejects_cyclic_dag(self):
        cyclic = """name: bad
jobs:
  a:
    needs: [b]
    steps:
      - name: s
        run: echo a
  b:
    needs: [a]
    steps:
      - name: s
        run: echo b
"""
        doc = lci.parse_yaml_lite(cyclic)
        errs = lci.validate_workflow(doc)
        self.assertTrue(any("cycle" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
