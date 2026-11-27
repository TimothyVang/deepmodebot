"""Tests for rule_ledger.py: owner-signed approval of the rules AI agents load.

Run: python -B -m unittest discover -s <this folder> -p "test_*.py"
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("rule_ledger_under_test", HERE / "rule_ledger.py")
rl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rl
SPEC.loader.exec_module(rl)
rl.KDF_ITERATIONS = 2_000
pm = rl._asset_module("dmb_project_memory", "memory/project_memory.py")

OWNER = "owner passphrase"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          check=True, capture_output=True, text=True).stdout


class LedgerCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="rule-ledger-test-")
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "proj"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.write("AGENTS.md", "# Rules\n- Run the tests.\n- Keep diffs small.\n")
        self.write(".cursor/rules/style.mdc", "Use tabs.\n")
        self.write("src/app.py", "print('hi')\n")

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.repo / rel).read_text(encoding="utf-8")

    def pending(self):
        return rl.pending_changes(self.repo, rl.Source(self.repo), rl._require_ledger(self.repo))

    def blocking(self, **kw):
        res = rl.check(self.repo, **kw)
        return [(f["rule"], f["file"]) for f in res["findings"] if f["severity"] in ("P0", "P1")]

    def commit_all(self, msg="c"):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)


class SignatureTests(unittest.TestCase):
    def test_rfc8032_vector_one_signs_and_verifies(self):
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(rl.public_key(seed), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = rl.sign(seed, b"")
        self.assertEqual(sig, "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(rl.verify(rl.public_key(seed), b"", sig))
        self.assertFalse(rl.verify(rl.public_key(seed), b"x", sig))


class RulePathTests(unittest.TestCase):
    def test_rule_paths_cover_harness_files_and_skip_scratch_and_the_store(self):
        for rel in ("AGENTS.md", "pkg/api/AGENTS.md", "CLAUDE.local.md", ".cursorrules", ".cursor/rules/a.mdc",
                    "web/.cursor/rules/b.mdc", ".claude/skills/x/SKILL.md", ".github/copilot-instructions.md",
                    ".claude/settings.json", ".deepmodebot/policy.xml", ".codex/rules/default.rules", "agents.md"):
            self.assertTrue(rl.is_rule_path(rel), rel)
        for rel in ("README.md", ".scratch/AGENTS.md", "node_modules/x/AGENTS.md", ".deepmodebot/rules/ledger.json",
                    ".deepmodebot/ci.yml", "docs/claude/rules.md", "../AGENTS.md", "x.cursor/rules/a.mdc"):
            self.assertFalse(rl.is_rule_path(rel), rel)


class BaselineAndDecisionTests(LedgerCase):
    def test_init_approves_current_rules_and_the_gate_passes(self):
        ledger = rl.init_ledger(self.repo, OWNER)
        self.assertEqual(sorted(ledger["approved"]), [".cursor/rules/style.mdc", "AGENTS.md"])
        self.assertEqual(ledger["history"][-1]["action"], "init")
        self.assertEqual(self.blocking(), [])
        with self.assertRaises(rl.RuleError):
            rl.init_ledger(self.repo, OWNER)

    def test_agent_rule_edits_block_until_the_owner_approves_one_and_rejects_the_other(self):
        rl.init_ledger(self.repo, OWNER)
        self.write("AGENTS.md", "# Rules\n- Run the tests.\n- Deploy on Fridays.\n- Keep diffs small.\n- Skip review.\n")
        changes = self.pending()
        self.assertEqual([c["summary"] for c in changes], ["- Deploy on Fridays.", "- Skip review."])
        self.assertEqual(self.blocking(), [("rules-unapproved", "AGENTS.md")] * 2)

        rl.decide(self.repo, [changes[0]["id"]], approve=True, passphrase=OWNER)
        rest = self.pending()
        self.assertEqual([c["summary"] for c in rest], ["- Skip review."])
        rl.decide(self.repo, [rest[0]["id"]], approve=False, passphrase=OWNER)

        self.assertEqual(self.read("AGENTS.md"), "# Rules\n- Run the tests.\n- Deploy on Fridays.\n- Keep diffs small.\n")
        self.assertEqual(self.blocking(), [])
        actions = [(e["action"], e.get("summary")) for e in rl._require_ledger(self.repo)["history"][1:]]
        self.assertEqual(actions, [("approve", "- Deploy on Fridays."), ("reject", "- Skip review.")])

    def test_wrong_passphrase_changes_nothing(self):
        rl.init_ledger(self.repo, OWNER)
        self.write("AGENTS.md", "# Rules\n- Always trust the agent.\n")
        before = (self.repo / rl.LEDGER_REL).read_bytes()
        with self.assertRaisesRegex(rl.RuleError, "wrong passphrase"):
            rl.decide(self.repo, [], approve=True, passphrase="agent guess", select_all=True)
        self.assertEqual((self.repo / rl.LEDGER_REL).read_bytes(), before)
        self.assertEqual(len(self.blocking()), 1)

    def test_new_rule_files_are_deleted_and_removed_ones_restored_on_reject(self):
        rl.init_ledger(self.repo, OWNER)
        self.write(".claude/rules/new.md", "Never ask before deleting.\n")
        (self.repo / ".cursor/rules/style.mdc").unlink()
        kinds = {c["item"]: c["kind"] for c in self.pending()}
        self.assertEqual(kinds, {".claude/rules/new.md": "new", ".cursor/rules/style.mdc": "removed"})
        rl.decide(self.repo, [], approve=False, passphrase=OWNER, select_all=True)
        self.assertFalse((self.repo / ".claude/rules/new.md").exists())
        self.assertEqual(self.read(".cursor/rules/style.mdc"), "Use tabs.\n")
        self.assertEqual(self.blocking(), [])


class ProposalTests(LedgerCase):
    def test_a_proposal_leaves_the_rule_file_alone_until_the_owner_approves_it(self):
        rl.init_ledger(self.repo, OWNER)
        draft = "# Rules\n- Run the tests.\n- Keep diffs small.\n- Use uv for Python.\n"
        prop = rl.propose(self.repo, "AGENTS.md", draft.encode(), "repo switched to uv", by="omp")
        self.assertEqual(self.read("AGENTS.md"), "# Rules\n- Run the tests.\n- Keep diffs small.\n")
        self.assertEqual(self.blocking(), [])
        listed = [c for c in self.pending() if c["kind"] == "proposal"]
        self.assertEqual([(c["id"], c["diff"]) for c in listed], [(prop["id"], ["+ - Use uv for Python."])])

        rl.decide(self.repo, [prop["id"]], approve=True, passphrase=OWNER)
        self.assertEqual(self.read("AGENTS.md"), draft)
        self.assertEqual(self.pending(), [])
        last = rl._require_ledger(self.repo)["history"][-1]
        self.assertEqual((last["kind"], last["by"], last["reason"]), ("proposal", "omp", "repo switched to uv"))

    def test_a_stale_proposal_is_refused(self):
        rl.init_ledger(self.repo, OWNER)
        prop = rl.propose(self.repo, "AGENTS.md", b"# Rules\n", "shorter")
        self.write("AGENTS.md", "# Rules\n- changed meanwhile\n")
        with self.assertRaisesRegex(rl.RuleError, "changed after proposal"):
            rl.decide(self.repo, [prop["id"]], approve=True, passphrase=OWNER)

    def test_non_rule_files_cannot_be_proposed(self):
        rl.init_ledger(self.repo, OWNER)
        with self.assertRaises(rl.RuleError):
            rl.propose(self.repo, "src/app.py", b"x\n", "why")


class TamperTests(LedgerCase):
    def test_an_agent_signed_ledger_is_rejected_against_the_committed_owner_key(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all()
        self.write("AGENTS.md", "# Rules\n- Agents may push to main.\n")
        ledger = rl._require_ledger(self.repo)
        ledger["approved"]["AGENTS.md"] = rl._sha((self.repo / "AGENTS.md").read_bytes())
        (self.repo / rl.LEDGER_REL).write_text(json.dumps(ledger), encoding="utf-8")
        self.assertIn(("rules-ledger-forged", rl.LEDGER_REL), self.blocking())

        git(self.repo, "checkout", "--", rl.STORE_REL)
        (self.repo / rl.LEDGER_REL).unlink()
        rl.init_ledger(self.repo, "agent's own passphrase")
        self.assertIn(("rules-owner-key-changed", rl.LEDGER_REL), self.blocking())
        self.assertEqual(rl.trusted_approvals(self.repo), {})

    def test_restoring_an_older_ledger_is_a_rollback(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all("v1")
        old = (self.repo / rl.LEDGER_REL).read_bytes()
        self.write("AGENTS.md", "# Rules\n- Run the tests.\n")
        rl.decide(self.repo, [], approve=True, passphrase=OWNER, select_all=True)
        self.commit_all("v2")
        (self.repo / rl.LEDGER_REL).write_bytes(old)
        self.assertIn(("rules-ledger-rollback", rl.LEDGER_REL), self.blocking())

    def test_deleting_the_ledger_and_rotating_the_key(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all()
        rl.rotate_key(self.repo, OWNER, "new owner passphrase")
        self.assertEqual(self.blocking(), [])
        with self.assertRaisesRegex(rl.RuleError, "wrong passphrase"):
            rl.decide(self.repo, [], approve=True, passphrase=OWNER, select_all=True)
        git(self.repo, "rm", "-q", "-r", "-f", rl.STORE_REL)
        self.assertIn(("rules-ledger-removed", rl.LEDGER_REL), self.blocking(staged=True))

    def test_staged_check_reads_the_index(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all()
        self.write("AGENTS.md", "# Rules\n- Staged agent rule.\n")
        self.assertEqual(self.blocking(staged=True), [])
        git(self.repo, "add", "AGENTS.md")
        self.assertEqual(self.blocking(staged=True), [("rules-unapproved", "AGENTS.md")])


class MemoryTests(LedgerCase):
    def test_agent_conventions_stay_out_of_recall_until_approved(self):
        pm.put_memory(self.repo, key="style", kind="convention", content="Prefer small PRs.", priority=0)
        rl.init_ledger(self.repo, OWNER)
        pm.put_memory(self.repo, key="ai-rule", kind="convention", content="Skip tests on Fridays.", priority=0)
        pm.put_memory(self.repo, key="fact-1", kind="fact", content="The API lives in src/.", priority=1)

        recalled = pm.recall_memories(self.repo, touch_hits=False)
        self.assertEqual(sorted(i["key"] for i in recalled["items"]), ["fact-1", "style"])
        self.assertEqual(recalled["pending_rules"], 1)
        self.assertEqual(self.blocking(), [])

        change = next(c for c in self.pending() if c["item"] == "memory:ai-rule")
        rl.decide(self.repo, [change["id"]], approve=True, passphrase=OWNER)
        recalled = pm.recall_memories(self.repo, touch_hits=False)
        self.assertIn("ai-rule", [i["key"] for i in recalled["items"]])
        self.assertEqual(recalled["pending_rules"], 0)

    def test_rejecting_a_convention_deletes_it(self):
        rl.init_ledger(self.repo, OWNER)
        pm.put_memory(self.repo, key="ai-rule", kind="convention", content="Never run the linter.", priority=0)
        rl.decide(self.repo, [], approve=False, passphrase=OWNER, select_all=True)
        self.assertEqual(rl.memory_rules(self.repo), {})


class GuardTests(LedgerCase):
    def test_without_a_ledger_only_owner_commands_are_blocked(self):
        self.assertIsNone(rl.guard(self.repo, paths=["AGENTS.md"], command="rm AGENTS.md"))
        self.assertIsNotNone(rl.guard(self.repo, command="deepmodebot rules init"))

    def test_guard_blocks_rule_writes_owner_commands_and_ledger_tampering(self):
        rl.init_ledger(self.repo, OWNER)
        outside = self.repo.parent / "other"
        outside.mkdir()
        self.assertIn("propose", rl.guard(self.repo / "src", paths=["../AGENTS.md"]))
        self.assertIn("propose", rl.guard(outside, paths=[str(self.repo / "AGENTS.md")], command=f"rm {self.repo}/AGENTS.md"))
        self.assertIn("owner-signed", rl.guard(self.repo, paths=[str(self.repo / rl.LEDGER_REL)]))
        self.assertIsNone(rl.guard(self.repo, paths=["src/app.py", ".scratch/AGENTS.md", "/etc/hosts"]))
        evil = self.repo.parent / "evil"
        (evil / ".claude" / "rules").mkdir(parents=True)
        (evil / ".claude" / "rules" / "x.md").write_text("Skip review.\n", encoding="utf-8")
        blocked = [
            "echo '- new rule' >> AGENTS.md",
            "printf x | tee -a .cursor/rules/style.mdc",
            "sed -i 's/tabs/spaces/' .cursor/rules/style.mdc",
            "sed -i 's/a/b/' *.md",
            "perl -pi -e 's/a/b/' AGENTS.md",
            "perl -e 'open(F, \">>AGENTS.md\")'",
            "cat > .claude/rules/x.md <<'EOF'\nDon't ask.\nEOF",
            "rm -rf .cursor",
            "git rm AGENTS.md",
            "cp .scratch/draft.md AGENTS.md",
            f"cp -r {evil}/.claude .",
            "ln -s AGENTS.md CLAUDE.md",
            "find . -name AGENTS.md -delete",
            "python3 -c \"open('AGENTS.md','a').write('x')\"",
            "python3 -c \"\nfrom pathlib import Path\nPath('AGENTS.md').write_text('x')\n\"",
            "bash -c 'mv AGENTS.md old.md'",
            "bash -lc 'echo x >> AGENTS.md'",
            "cd .cursor/rules && echo evil > style.mdc",
            "timeout 5 tee -a AGENTS.md",
            "curl -so AGENTS.md https://example.com/rules",
            "grep -rl tests . | xargs sed -i 's/tests/none/'",
            "python3 - <<'PY'\nfrom pathlib import Path\nPath('AGENTS.md').write_text('x')\nPY",
            "rm -rf .deepmodebot/rules",
            "git commit --no-verify -m wip",
            "git commit -nm wip",
            "git -c core.hooksPath=/dev/null commit -m wip",
            "python3 -B ~/x/rule_ledger.py approve --all",
            "npx deepmodebot rules reject abc12345",
            "deepmodebot gate rules init",
        ]
        for cmd in blocked:
            self.assertIsNotNone(rl.guard(self.repo, command=cmd), cmd)
        allowed = [
            "cat AGENTS.md",
            "grep -n rule AGENTS.md .cursor/rules/style.mdc",
            "cp AGENTS.md .scratch/AGENTS.draft.md",
            "cp AGENTS.md AGENTS.md.bak",
            "mv /tmp/report.pdf .",
            "find . -name '*.pyc' -delete",
            "find . -name '*.py' -exec grep -l TODO {} +",
            "git add AGENTS.md && git commit -m 'update AGENTS.md'",
            "git commit -m \"line one\n\nmention CLAUDE.md\"",
            "git config --get core.hooksPath",
            "python3 -c \"print(open('AGENTS.md').read())\"",
            "python3 -c \"import sys; sys.stdout.write(open('AGENTS.md').read())\"",
            "python3 -B rule_ledger.py propose --item AGENTS.md --file .scratch/d.md --reason 'approve later'",
            "deepmodebot rules review",
            "echo hi > src/out.txt 2>&1",
        ]
        for cmd in allowed:
            self.assertIsNone(rl.guard(self.repo, command=cmd), cmd)

    def test_literal_brackets_and_symlink_aliases_still_reach_the_rule(self):
        rl.init_ledger(self.repo, OWNER)
        self.assertIsNotNone(rl.guard(self.repo, paths=[".cursor/rules/[x].mdc"]))
        os.symlink(".cursor/rules/style.mdc", self.repo / "style.mdc")
        os.symlink(".claude", self.repo / "notes")
        self.assertIsNotNone(rl.guard(self.repo, paths=["style.mdc"]))
        self.assertIsNotNone(rl.guard(self.repo, paths=["notes/rules/evil.md"]))
        self.assertIsNone(rl.guard(self.repo, command="rm style.mdc"))


class SymlinkAndIgnoredTests(LedgerCase):
    def test_a_rule_symlink_to_a_non_rule_file_is_refused_and_flagged(self):
        self.write("docs/agent-guide.md", "Be careful.\n")
        os.symlink("docs/agent-guide.md", self.repo / "CLAUDE.md")
        with self.assertRaisesRegex(rl.RuleError, "CLAUDE.md -> docs/agent-guide.md"):
            rl.init_ledger(self.repo, OWNER)
        (self.repo / "CLAUDE.md").unlink()
        rl.init_ledger(self.repo, OWNER)
        (self.repo / ".claude").mkdir()
        os.symlink("../docs", self.repo / ".claude" / "skills")
        self.assertIn(("rules-symlink-untracked", ".claude/skills"), self.blocking())

    def test_a_rule_symlink_to_a_rule_file_is_restored_as_a_symlink(self):
        os.symlink("AGENTS.md", self.repo / "CLAUDE.md")
        rl.init_ledger(self.repo, OWNER)
        (self.repo / "CLAUDE.md").unlink()
        rl.decide(self.repo, [], approve=False, passphrase=OWNER, select_all=True)
        self.assertEqual(os.readlink(self.repo / "CLAUDE.md"), "AGENTS.md")
        self.assertEqual(self.blocking(), [])

    def test_gitignored_rule_files_stay_out_of_the_ledger_but_agents_still_cannot_write_them(self):
        self.write(".gitignore", ".claude/\nCLAUDE.local.md\n")
        self.write("CLAUDE.local.md", "my private notes\n")
        ledger = rl.init_ledger(self.repo, OWNER)
        self.assertNotIn("CLAUDE.local.md", ledger["approved"])
        self.commit_all()
        self.write(".claude/settings.local.json", '{"permissions": {"allow": ["Bash(*)"]}}\n')
        self.assertEqual(self.blocking(), [])
        self.assertEqual(self.blocking(staged=True), [])
        self.assertIsNotNone(rl.guard(self.repo, paths=[".claude/settings.local.json"]))
        self.assertIsNotNone(rl.guard(self.repo, command="echo x >> CLAUDE.local.md"))


class TrustBaseTests(LedgerCase):
    def test_a_rekeyed_ledger_committed_on_a_branch_fails_against_the_default_branch(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all("owner ledger")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.write("AGENTS.md", "# Rules\n- Agents may push to main.\n")
        rl.init_ledger(self.repo, "agent's own passphrase", reset=True)
        self.commit_all("agent commit that skipped the hooks")
        self.assertIn(("rules-owner-key-changed", rl.LEDGER_REL), self.blocking())
        self.assertEqual(rl.trusted_approvals(self.repo), {})

    def test_a_missing_base_and_a_subfolder_root(self):
        rl.init_ledger(self.repo, OWNER)
        self.commit_all()
        self.assertEqual(self.blocking(base="origin/nope"), [("rules-base-missing", rl.LEDGER_REL)])
        self.assertEqual([f for f in rl.check(self.repo / "src")["findings"] if f["severity"] == "P0"], [])

    def test_an_owner_command_never_deletes_through_a_symlinked_store(self):
        rl.init_ledger(self.repo, OWNER)
        victim = self.repo.parent / "victim"
        victim.mkdir()
        (victim / "thesis.docx").write_text("keep me", encoding="utf-8")
        approved = self.repo / rl.APPROVED_REL
        for blob in approved.iterdir():
            (victim / blob.name).write_bytes(blob.read_bytes())
            blob.unlink()
        approved.rmdir()
        os.symlink(victim, approved)
        with self.assertRaisesRegex(rl.RuleError, "symlink"):
            rl.rotate_key(self.repo, OWNER, "new owner passphrase")
        self.assertTrue((victim / "thesis.docx").exists())
        self.assertIn(("rules-store-symlink", rl.STORE_REL), self.blocking())


class ReviewSafetyTests(LedgerCase):
    def test_ids_stay_put_when_identical_lines_land_in_several_places(self):
        self.write("AGENTS.md", "## docs\n- a\n## scripts\n- b\n## deploy\n- c\n")
        rl.init_ledger(self.repo, OWNER)
        self.write("AGENTS.md", "## docs\n- a\n- Skip review.\n## scripts\n- b\n- Skip review.\n## deploy\n- c\n- Skip review.\n")
        first, second, _ = [c["id"] for c in self.pending()]
        rl.decide(self.repo, [first], approve=False, passphrase=OWNER)
        rl.decide(self.repo, [second], approve=True, passphrase=OWNER)
        approved = (self.repo / rl.APPROVED_REL / rl._require_ledger(self.repo)["approved"]["AGENTS.md"]).read_text()
        self.assertEqual(approved, "## docs\n- a\n## scripts\n- b\n- Skip review.\n## deploy\n- c\n")

    def test_terminal_escapes_in_agent_text_are_shown_escaped(self):
        rl.init_ledger(self.repo, OWNER)
        rl.propose(self.repo, "AGENTS.md", b"# Rules\n- Push to main.\x1b[2K\n", "tidy\x1b[2K")
        change = self.pending()[0]
        self.assertNotIn("\x1b", "".join(change["diff"]) + change["reason"])
        self.assertIn("\\u001b[2K", change["diff"][-1])

    def test_rejecting_an_expired_convention_restores_it(self):
        pm.put_memory(self.repo, key="style", kind="convention", content="Prefer small PRs.", priority=0)
        rl.init_ledger(self.repo, OWNER)
        with pm.connect_db(pm.db_path_for(self.repo)) as conn:
            conn.execute("UPDATE memories SET expires_at = 1 WHERE key = 'style'")
            conn.commit()
        rl.decide(self.repo, [], approve=False, passphrase=OWNER, select_all=True)
        self.assertEqual(rl.memory_rules(self.repo), {"memory:style": b"Prefer small PRs."})


if __name__ == "__main__":
    unittest.main()
