import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_proof import audit_static, dag_init, dag_update, main, run_able_to_fail


class VerifyProofTests(unittest.TestCase):
    def test_audit_static_catches_lean_escapes_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proofs"
            root.mkdir()
            (root / "Challenge.lean").write_text(
                "-- comment mentioning sorry and axiom\n"
                "/- block sorry native_decide -/\n"
                "theorem erdos_bound (n : Nat) (h : n >= 3) : n + 1 > n := by sorry\n",
                encoding="utf-8",
            )
            (root / "BadSolution.lean").write_text(
                "axiom magic_truth : False\n"
                "theorem erdos_bound (n : Nat) (h : n >= 4) : n + 1 > n := by\n"
                "  native_decide\n",
                encoding="utf-8",
            )
            bad = audit_static(
                root,
                challenge=root / "Challenge.lean",
                solution=root / "BadSolution.lean",
            )
            self.assertFalse(bad["valid"])
            rule_ids = {f["rule_id"] for f in bad["findings"]}
            self.assertIn("PROOF-LEAN-AXIOM", rule_ids)
            self.assertIn("PROOF-LEAN-NATIVE", rule_ids)
            self.assertTrue(any("statement mismatch on 'erdos_bound'" in e for e in bad["comparator_errors"]))

            (root / "BadSolution.lean").unlink()
            (root / "GoodSolution.lean").write_text(
                "-- clean proof, no sorry\n"
                "theorem erdos_bound (n : Nat) (h : n >= 3) : n + 1 > n := by\n"
                "  omega\n",
                encoding="utf-8",
            )
            (root / "formalization.yaml").write_text(
                "theorems:\n"
                "  - name: erdos_bound\n"
                "    nl_statement: For every integer n >= 3, n + 1 > n.\n",
                encoding="utf-8",
            )
            good = audit_static(
                root,
                challenge=root / "Challenge.lean",
                solution=root / "GoodSolution.lean",
                formalization=root / "formalization.yaml",
            )
            self.assertTrue(good["valid"], good)

    def test_able_to_fail_rejects_vacuous_check_and_accepts_real_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "math-repo"
            repo.mkdir()
            vacuous = repo / "vacuous_check.py"
            vacuous.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            vac_res = run_able_to_fail(repo, slug="vacuous", script=vacuous)
            self.assertFalse(vac_res["able_to_fail_proven"])
            self.assertTrue(any("VACUOUS_CHECK" in e for e in vac_res["errors"]))

            argparse_no_mutate = repo / "no_mutate_flag.py"
            argparse_no_mutate.write_text(
                "import argparse\n"
                "p = argparse.ArgumentParser()\n"
                "p.parse_args()\n",
                encoding="utf-8",
            )
            cli_err_res = run_able_to_fail(repo, slug="cli-err", script=argparse_no_mutate)
            self.assertFalse(cli_err_res["able_to_fail_proven"])
            self.assertTrue(any("CLI_USAGE_ERROR" in e for e in cli_err_res["errors"]))

            honest = repo / "honest_check.py"
            honest.write_text(
                "import sys\n"
                "mut = '--mutate' in sys.argv\n"
                "lhs = sum(range(1, 6))\n"
                "rhs = (5 * 6) // 2 + (1 if mut else 0)\n"
                "sys.exit(0 if lhs == rhs else 1)\n",
                encoding="utf-8",
            )
            ok_res = run_able_to_fail(repo, slug="gauss-sum", script=honest)
            self.assertTrue(ok_res["able_to_fail_proven"])
            self.assertEqual(ok_res["clean_exit"], 0)
            self.assertNotEqual(ok_res["mutate_exit"], 0)
            self.assertTrue(Path(ok_res["receipt_path"]).is_file())

    def test_claim_dag_bottom_up_leaves_and_siege_dual_audit_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "dag-repo"
            repo.mkdir()
            nodes = [
                {"id": "lemma_a", "statement": "Base pigeonhole bound", "depends_on": []},
                {"id": "lemma_b", "statement": "Telescoping tail bound", "depends_on": []},
                {"id": "main_thm", "statement": "Main theorem", "depends_on": ["lemma_a", "lemma_b"], "status": "sorry_stub"},
            ]
            nodes_file = repo / "nodes.json"
            nodes_file.write_text(json.dumps(nodes), encoding="utf-8")
            init_res = dag_init(repo, slug="imo-p1", goal="Prove sunny lines characterisation", initial_nodes=nodes)
            self.assertFalse(init_res["theorem_proved"])
            self.assertEqual(init_res["ready_leaves"], ["lemma_a", "lemma_b"])

            dag_update(repo, slug="imo-p1", node_id="lemma_a", status="kernel_verified", receipt="Solution.lean:12")
            dag_update(repo, slug="imo-p1", node_id="lemma_b", status="proved_single", receipt="ledger.md:40", auditor="auditor-1")
            with self.assertRaises(SystemExit):
                dag_update(repo, slug="imo-p1", node_id="lemma_b", status="proved_dual_verified", receipt="ledger.md:40", auditor="auditor-1")

            up_b = dag_update(repo, slug="imo-p1", node_id="lemma_b", status="proved_dual_verified", receipt="ledger.md:40", auditor="auditor-2")
            self.assertEqual(up_b["ready_leaves"], ["main_thm"])

            done = dag_update(repo, slug="imo-p1", node_id="main_thm", status="kernel_verified", receipt="Solution.lean:55")
            self.assertTrue(done["theorem_proved"])
            self.assertEqual(main(["dag", "status", "--root", str(repo), "--slug", "imo-p1", "--strict"]), 0)


if __name__ == "__main__":
    unittest.main()
