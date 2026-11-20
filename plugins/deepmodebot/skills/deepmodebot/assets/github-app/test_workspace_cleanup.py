"""Offline real-Git disposal and bot completion-dispatch contracts.

Run: python -B -m unittest test_workspace_cleanup
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import bot
import workspace_cleanup as cleanup


class WorkspaceCleanupTest(unittest.TestCase):
    def setUp(self):
        root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
        scratch = root / ".scratch" / "workspace-cleanup-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.base = Path(tempfile.mkdtemp(dir=scratch))
        self.addCleanup(self.remove_fixture)
        self.env = mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Cleanup test", "GIT_AUTHOR_EMAIL": "cleanup@example.invalid",
            "GIT_COMMITTER_NAME": "Cleanup test", "GIT_COMMITTER_EMAIL": "cleanup@example.invalid"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.work = self.base / "work"
        self.repo = "owner/project"
        self.clone = self.work / "repos" / "owner-project"
        self.tree = self.work / "worktrees" / "owner-project" / "issue1"
        self.remote = self.base / "remote.git"
        seed = self.base / "seed"
        self.git(self.base, "init", "--bare", str(self.remote))
        self.git(self.base, "init", "-b", "main", str(seed))
        (seed / "file.txt").write_text("original\n", encoding="utf-8")
        self.git(seed, "add", "file.txt")
        self.git(seed, "commit", "-m", "initial")
        self.git(seed, "remote", "add", "origin", str(self.remote))
        self.git(seed, "push", "origin", "main")
        self.git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.clone.parent.mkdir(parents=True)
        self.git(self.base, "clone", "--no-hardlinks", str(self.remote), str(self.clone))
        cleanup.claim_clone(self.work, self.repo)
        self.item = {"status": "discussed", "workspacePaths": ["issue1"], "workspaceCleanupReady": True}
        self.items = {"owner/project#issue:1": self.item}
        self.add_tree()
        cleanup.record_worktree(self.tree, self.item)

    def remove_fixture(self):
        def retry(fn, path, exc):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            fn(path)
        shutil.rmtree(self.base, onerror=retry)

    def git(self, cwd, *args):
        proc = subprocess.run(["git", "-C", str(cwd), *map(str, args)], text=True,
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def add_tree(self):
        self.tree.parent.mkdir(parents=True, exist_ok=True)
        self.git(self.clone, "worktree", "add", "--detach", str(self.tree), "origin/main")

    def dispose(self, apply=True):
        return cleanup.cleanup_item(self.work, self.repo, "issue", 1, self.item, apply=apply)

    def assert_retained(self, reason):
        rows = self.dispose()
        self.assertEqual(rows[0]["action"], "retain", rows)
        self.assertIn(reason, rows[0]["reason"])
        self.assertTrue(self.tree.exists())

    def test_preview_then_owned_lifecycle_disposes_tree_and_clone(self):
        logs = self.work / "logs"
        logs.mkdir()
        evidence = logs / "resume.txt"
        evidence.write_text("retain this", encoding="utf-8")
        self.assertEqual(self.dispose(False)[0]["action"], "would-remove")
        self.assertTrue(self.tree.exists())
        self.assertEqual(self.dispose()[0]["action"], "removed")
        self.assertFalse(self.tree.exists())
        self.assertEqual(cleanup.cleanup_clone(self.work, self.repo, self.items)[0]["action"], "would-remove")
        self.assertTrue(self.clone.exists())
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertEqual(rows[0]["action"], "removed", rows)
        self.assertFalse(self.clone.exists())
        self.assertFalse(cleanup._receipt(self.work, self.repo).exists())
        self.assertEqual(evidence.read_text(), "retain this")

    def test_unfinished_and_unknown_statuses_keep_everything(self):
        for status in ("error", "blocked", "awaiting-checks", "merge-pending", "merged-red", "dry-run", "unknown"):
            with self.subTest(status=status):
                self.item["status"] = status
                self.assert_retained("unfinished")
                self.assertEqual(cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)[0]["action"],
                                 "retain")
        self.item["status"] = "discussed"
        for key in ("workspaceActive", "workspaceIncomplete", "afterMerge", "pendingComments"):
            self.item[key] = True
            self.assert_retained("unfinished")
            self.item.pop(key)
        self.item.pop("workspaceCleanupReady")
        self.assert_retained("receipt")

    def test_modified_untracked_and_ignored_files_survive(self):
        for name in ("file.txt", "untracked.txt", "ignored.tmp"):
            with self.subTest(name=name):
                if name == "ignored.tmp":
                    (self.clone / ".git" / "info" / "exclude").write_text("*.tmp\n")
                target = self.tree / name
                target.write_text("important", encoding="utf-8")
                self.assert_retained("files remain")
                if name == "file.txt":
                    self.git(self.tree, "restore", "file.txt")
                else:
                    target.unlink()

    def test_detached_unpushed_head_and_reflog_survive(self):
        original = self.git(self.tree, "rev-parse", "HEAD")
        self.git(self.tree, "commit", "--allow-empty", "-m", "unpushed")
        self.assert_retained("not recoverable")
        self.git(self.tree, "checkout", "--detach", original)
        self.assert_retained("not recoverable")

    def test_stale_remote_tracking_ref_is_not_remote_proof(self):
        self.git(self.tree, "commit", "--allow-empty", "-m", "temporary remote")
        self.git(self.tree, "push", "origin", "HEAD:refs/heads/temporary")
        self.git(self.remote, "update-ref", "-d", "refs/heads/temporary")
        self.assert_retained("not recoverable")

    def test_locks_and_in_progress_git_operations_survive(self):
        self.git(self.clone, "worktree", "lock", str(self.tree))
        self.assert_retained("unlocked")
        self.git(self.clone, "worktree", "unlock", str(self.tree))
        lock = self.clone / ".git" / "index.lock"
        lock.write_text("active")
        self.assert_retained("operation/lock")

    def test_symlink_paths_and_linked_children_survive(self):
        target = self.tree / "linked"
        try:
            target.symlink_to(self.base / "seed", target_is_directory=True)
        except OSError as err:
            self.skipTest(f"OS does not permit symlinks: {err}")
        self.assert_retained("linked/reparse")

    def test_foreign_git_membership_and_manifest_escape_survive(self):
        self.git(self.clone, "worktree", "remove", str(self.tree))
        self.git(self.base, "clone", "--no-hardlinks", str(self.remote), str(self.tree))
        self.assert_retained("member")
        self.item["workspacePaths"] = ["../../../seed"]
        self.assert_retained("does not belong")

    def test_clone_retains_foreign_worktrees_and_unfinished_jobs(self):
        self.assertEqual(self.dispose()[0]["action"], "removed")
        foreign = self.base / "foreign"
        self.git(self.clone, "worktree", "add", "--detach", str(foreign), "HEAD")
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("worktrees", rows[0]["reason"])
        self.assertTrue(foreign.exists())
        self.git(self.clone, "worktree", "remove", str(foreign))
        self.items["owner/project#issue:2"] = {"status": "blocked"}
        self.assertIn("unfinished", cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)[0]["reason"])

    def test_clone_retains_changed_configuration_and_unowned_metadata(self):
        self.dispose()
        self.git(self.clone, "config", "user.cleanupEvidence", "keep")
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("metadata changed", rows[0]["reason"])
        cleanup._receipt(self.work, self.repo).unlink()
        self.assertIn("no creation-ownership", cleanup.cleanup_clone(
            self.work, self.repo, self.items, apply=True)[0]["reason"])

    def test_clone_retains_unpushed_refs_and_recovery_objects(self):
        self.dispose()
        self.git(self.clone, "commit", "--allow-empty", "-m", "local only")
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("not recoverable", rows[0]["reason"])
        self.assertTrue(self.clone.exists())

    def test_inspection_and_removal_fail_closed(self):
        real_git = cleanup._git
        for operation in ("status", "remove"):
            def fail(cwd, *args):
                if operation in args:
                    raise OSError("injected external Git failure")
                return real_git(cwd, *args)
            with mock.patch.object(cleanup, "_git", side_effect=fail):
                self.assert_retained("external Git failure")

    def test_actual_handle_dispatch_saves_before_cleanup_and_preserves_unfinished_dry_runs(self):
        coordinator = object.__new__(bot.Bot)
        coordinator.dry = False
        coordinator.cfg = {"author": {"agent": "omp"}, "reviewer": {"agent": "omp"}}
        coordinator.state = {"items": {}}
        coordinator.ident = SimpleNamespace(owner="owner")
        state_path = self.base / "bot-state.json"
        data = {"number": 1, "author": {"login": "owner"}}
        # Agent/network boundary only: real Bot.handle, worktree_at, Git and durable save execute.
        def conversation_run(conversation):
            bot.worktree_at(self.clone, self.tree, "origin/main", item=conversation.item)
            return desired[0]
        self.git(self.clone, "worktree", "remove", str(self.tree))
        desired = ["blocked"]
        with mock.patch.object(bot, "WORK", self.work), mock.patch.object(bot, "LOGS", self.work / "logs"), \
                mock.patch.object(bot, "STATE_PATH", state_path), \
                mock.patch.object(bot.IssueConversation, "run", conversation_run):
            coordinator.handle(self.repo, "issue", data, ["test"], [], self.clone, "main")
            self.assertTrue(self.tree.exists())
            self.assertEqual(json.loads(state_path.read_text())["items"]["owner/project#issue:1"]["status"], "blocked")
            coordinator.dry = True
            desired[0] = "discussed"
            coordinator.handle(self.repo, "issue", data, ["test"], [], self.clone, "main")
            self.assertTrue(self.tree.exists())
            self.assertEqual(json.loads(state_path.read_text())["items"]["owner/project#issue:1"]["status"], "blocked")
            coordinator.dry = False
            real_git = cleanup._git
            def cannot_remove(cwd, *args):
                if args[:2] == ("worktree", "remove"):
                    raise OSError("external removal failure")
                return real_git(cwd, *args)
            with mock.patch.object(cleanup, "_git", side_effect=cannot_remove):
                coordinator.handle(self.repo, "issue", data, ["test"], [], self.clone, "main")
            saved = json.loads(state_path.read_text())["items"]["owner/project#issue:1"]
            self.assertEqual(saved["status"], "discussed")
            self.assertNotIn("errors", saved)
            self.assertTrue(self.tree.exists())
            real_remove = cleanup._git
            def observe_save(cwd, *args):
                if args[:2] == ("worktree", "remove"):
                    saved = json.loads(state_path.read_text())["items"]["owner/project#issue:1"]
                    self.assertEqual(saved["status"], "discussed")
                    self.assertTrue(saved["workspaceCleanupReady"])
                return real_remove(cwd, *args)
            with mock.patch.object(cleanup, "_git", side_effect=observe_save):
                coordinator.handle(self.repo, "issue", data, ["test"], [], self.clone, "main")
            self.assertFalse(self.tree.exists())

    def test_cleanup_command_defaults_preview_and_uses_bot_lock(self):
        state_path = self.base / "bot-state.json"
        state_path.write_text(json.dumps({"items": self.items}))
        lock = self.work / "bot.lock"
        with mock.patch.object(bot, "WORK", self.work), mock.patch.object(bot, "STATE_PATH", state_path), \
                mock.patch.object(bot.Lock, "path", lock), contextlib.redirect_stdout(io.StringIO()) as output:
            bot.cmd_cleanup(SimpleNamespace(repo=None, apply=False))
            self.assertIn("would-remove", output.getvalue())
            self.assertTrue(self.tree.exists())
            with bot.Lock():
                with self.assertRaises(SystemExit):
                    bot.cmd_cleanup(SimpleNamespace(repo=None, apply=True))
            bot.cmd_cleanup(SimpleNamespace(repo=None, apply=True))
            self.assertFalse(self.tree.exists())
            self.assertFalse(self.clone.exists())
        self.assertTrue(state_path.exists())

    def test_ensure_clone_claims_only_new_creation(self):
        self.dispose()
        self.assertEqual(cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)[0]["action"], "removed")
        real_run = bot.run
        def local_clone(cmd, **kwargs):
            if cmd[:3] == ["gh", "repo", "clone"]:
                cmd = ["git", "clone", "--no-hardlinks", str(self.remote), str(cmd[4])]
            return real_run(cmd, **kwargs)
        with mock.patch.object(bot, "WORK", self.work), mock.patch.object(bot, "run", side_effect=local_clone):
            self.assertEqual(bot.ensure_clone(self.repo), self.clone)
            receipt = cleanup._receipt(self.work, self.repo)
            self.assertTrue(receipt.exists())
            receipt.unlink()
            bot.ensure_clone(self.repo)
            self.assertFalse(receipt.exists(), "an existing clone must never be adopted")

    def test_bot_branch_allocation_does_not_mutate_protected_clone_config(self):
        tree = self.tree.with_name("issue1-impl")
        with mock.patch.object(bot, "WORK", self.work):
            bot.worktree_at(self.clone, tree, "origin/main", branch="bot-issue1", item=self.item)
        self.assertIn("issue1-impl", self.item["workspacePaths"])
        self.assertEqual([r["action"] for r in self.dispose()], ["removed", "removed"])
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertEqual(rows[0]["action"], "removed", rows)

    def test_failed_session_close_retains_session_for_disposal_gate(self):
        item = bot.Item(SimpleNamespace(dry=False, save=lambda: None), self.repo, "issue", 1)
        item.sessions["one"] = ["acpx", "sessions"]
        with mock.patch.object(bot, "run", side_effect=OSError("cannot close")), mock.patch.object(bot, "log"):
            item.close_sessions(("one",))
        self.assertIn("one", item.sessions)

    def test_owned_generated_ignored_caches_are_removed_without_force(self):
        (self.clone / ".git" / "info" / "exclude").write_text(
            "node_modules/\n__pycache__/\n.pytest_cache/\n.scratch/\n.env\n", encoding="utf-8")
        for name in ("node_modules/package/index.js", "pkg/__pycache__/module.pyc",
                     ".pytest_cache/v/cache/result", ".scratch/tmp/generated.txt"):
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("generated", encoding="utf-8")
        self.assertEqual(self.dispose(False)[0]["action"], "would-remove")
        self.assertTrue(self.tree.exists())
        self.assertEqual(self.dispose()[0]["action"], "removed")
        self.assertFalse(self.tree.exists())

    def test_ignored_secret_evidence_and_original_cache_are_retained(self):
        (self.clone / ".git" / "info" / "exclude").write_text(
            ".env\n.scratch/\nnode_modules/\n", encoding="utf-8")
        for name in (".env", ".scratch/evidence/results.json", "node_modules/.env", "node_modules/original.txt"):
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("important", encoding="utf-8")
            if name == "node_modules/original.txt":
                cleanup.record_worktree(self.tree, self.item)
            self.assert_retained("non-cache or original")
            path.unlink()

    def test_safety_git_ignores_repository_and_config_environment_injection(self):
        foreign = self.base / "seed"
        injected = {
            "GIT_DIR": str(foreign / ".git"), "GIT_WORK_TREE": str(foreign),
            "GIT_COMMON_DIR": str(foreign / ".git"), "GIT_INDEX_FILE": str(self.base / "injected-index"),
            "GIT_OBJECT_DIRECTORY": str(foreign / ".git" / "objects"), "GIT_NAMESPACE": "wrong",
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true",
            "GIT_CONFIG_PARAMETERS": "malformed injection"}
        (self.tree / "file.txt").write_text("keep changes", encoding="utf-8")
        with mock.patch.dict(os.environ, injected):
            self.assert_retained("files remain")
        self.git(self.tree, "restore", "file.txt")
        with mock.patch.dict(os.environ, injected):
            self.assertEqual(self.dispose()[0]["action"], "removed")
        self.assertTrue((foreign / ".git").exists())
        self.assertFalse((self.base / "injected-index").exists())
        self.assertEqual(self.git(foreign, "status", "--porcelain"), "")

    def prepare_pull_ref(self):
        self.dispose()
        self.git(self.clone, "checkout", "-b", "feature")
        self.git(self.clone, "commit", "--allow-empty", "-m", "PR change")
        self.git(self.clone, "push", "origin", "HEAD:refs/pull/2/head")
        local = f"refs/{bot.B['branchPrefix']}/pr/2"
        self.git(self.clone, "fetch", "origin", f"+refs/pull/2/head:{local}")
        self.git(self.clone, "checkout", "main")
        self.git(self.clone, "commit", "--allow-empty", "-m", "squashed result")
        self.git(self.clone, "push", "origin", "main")
        self.items["owner/project#pr:2"] = {
            "status": "merged", "workspaceCleanupReady": True, "workspacePaths": [],
            "workspaceRefs": {local: "refs/pull/2/head"}}
        return local

    def test_recorded_pr_ref_and_squashed_head_are_recoverable_from_live_pull_ref(self):
        self.prepare_pull_ref()
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertEqual(rows[0]["action"], "removed", rows)
        self.assertFalse(self.clone.exists())

    def test_missing_live_pull_ref_and_unrecorded_custom_refs_are_retained(self):
        local = self.prepare_pull_ref()
        self.git(self.remote, "update-ref", "-d", "refs/pull/2/head")
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("live pull ref", rows[0]["reason"])
        self.git(self.clone, "push", "origin", f"{local}:refs/pull/2/head")
        self.git(self.clone, "update-ref", "refs/user/recovery", "HEAD")
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("non-disposable ref", rows[0]["reason"])

    def test_baseline_only_records_do_not_block_owned_clone_disposal(self):
        self.dispose()
        self.items["owner/project#pr:99"] = {"heads": {"abc": "before-install"}}
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertEqual(rows[0]["action"], "removed", rows)

    def test_idle_cycle_retries_completed_cleanup_without_conversations(self):
        coordinator = object.__new__(bot.Bot)
        coordinator.dry = False
        coordinator.args = SimpleNamespace(item=None)
        coordinator.cfg = {"mention": "@test"}
        coordinator.ident = SimpleNamespace(owner="owner", is_ours=lambda _: False,
                                            open_items=lambda *_: [])
        coordinator.state = {"items": self.items}
        with mock.patch.object(bot, "WORK", self.work), mock.patch.object(bot, "LOGS", self.work / "logs"), \
                mock.patch.object(bot, "STATE_PATH", self.base / "bot-state.json"), \
                mock.patch.object(bot, "ensure_clone", side_effect=AssertionError("must not clone")), \
                mock.patch.object(bot.IssueConversation, "run", side_effect=AssertionError("must not run agents")):
            coordinator.repo_cycle(self.repo, None)
        self.assertFalse(self.tree.exists())
        self.assertFalse(self.clone.exists())

    def test_session_intent_survives_failed_ensure_retry_and_failed_close(self):
        coordinator = object.__new__(bot.Bot)
        coordinator.dry = False
        coordinator.cfg = {"author": {"agent": "omp"}, "reviewer": {"agent": "omp"}}
        coordinator.state = {"items": self.items}
        coordinator.ident = SimpleNamespace(owner="owner")
        state_path = self.base / "bot-state.json"
        phase = ["ensure"]
        real_run = bot.run
        def external(cmd, **kwargs):
            if str(cmd[0]) == "acpx":
                saved = json.loads(state_path.read_text())["items"]["owner/project#issue:1"]
                self.assertIn("persistent", saved["workspaceSessions"])
                if "ensure" in cmd:
                    raise OSError("ensure failed after possibly opening")
                return subprocess.CompletedProcess(cmd, 1 if phase[0] == "close-fails" else 0, "", "")
            return real_run(cmd, **kwargs)
        def conversation_run(conversation):
            if phase[0] == "ensure":
                conversation.it.ask({"agent": "omp"}, "prompt", self.tree, "--approve-reads", "persistent")
            return "discussed"
        with mock.patch.object(bot, "WORK", self.work), mock.patch.object(bot, "LOGS", self.work / "logs"), \
                mock.patch.object(bot, "STATE_PATH", state_path), \
                mock.patch.object(bot.shutil, "which", return_value="acpx"), \
                mock.patch.object(bot, "known_agents", return_value={"omp"}), \
                mock.patch.object(bot, "run", side_effect=external), \
                mock.patch.object(bot.IssueConversation, "run", conversation_run):
            for current in ("ensure", "close-fails"):
                phase[0] = current
                coordinator.handle(self.repo, "issue", {"number": 1}, ["test"], [], self.clone, "main")
                coordinator.state = json.loads(state_path.read_text())
                self.assertIn("persistent", coordinator.state["items"]["owner/project#issue:1"]["workspaceSessions"])
                self.assertTrue(self.tree.exists())
            phase[0] = "closed"
            with mock.patch.object(bot.Lock, "path", self.work / "bot.lock"), \
                    contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(bot, "run", side_effect=AssertionError("preview must not close sessions")):
                    bot.cmd_cleanup(SimpleNamespace(repo=None, apply=False))
                self.assertTrue(self.tree.exists())
                bot.cmd_cleanup(SimpleNamespace(repo=None, apply=True))
        saved = json.loads(state_path.read_text())["items"]["owner/project#issue:1"]
        self.assertEqual(saved["workspaceSessions"], {})
        self.assertTrue(saved["workspaceCleanupReady"])
        self.assertFalse(self.tree.exists())

    def test_repository_storage_aliases_block_cleanup_and_parallel_dispatch(self):
        self.items["OWNER/PROJECT#issue:99"] = {"status": "blocked"}
        coordinator = object.__new__(bot.Bot)
        coordinator.dry, coordinator.state = False, {"items": self.items}
        rows = coordinator.cleanup_completed(self.repo)
        self.assertIn("aliases", rows[0]["reason"])
        rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("aliases", rows[0]["reason"])
        self.assertTrue(self.tree.exists())
        coordinator.dry = True
        coordinator.state = {"items": {}, "since": "2026-01-01T00:00:00Z"}
        coordinator.args = SimpleNamespace(backlog=False, repo=None)
        coordinator.cfg = {"parallelRepos": 2}
        coordinator.ident = SimpleNamespace(describe=lambda: "offline", repos=lambda: ["a-b/c", "a/b-c"])
        with mock.patch.object(coordinator, "repo_cycle", side_effect=AssertionError("aliased workers started")), \
                mock.patch.object(bot, "log"):
            coordinator.cycle()

    def test_clone_revalidates_after_object_inspection(self):
        self.dispose()
        real_git = cleanup._git
        def concurrent_change(cwd, *args):
            result = real_git(cwd, *args)
            if args[0] == "fsck":
                self.git(self.clone, "config", "user.externalChange", "preserve")
            return result
        with mock.patch.object(cleanup, "_git", side_effect=concurrent_change):
            rows = cleanup.cleanup_clone(self.work, self.repo, self.items, apply=True)
        self.assertIn("changed during disposal", rows[0]["reason"])
        self.assertTrue(self.clone.exists())

    def test_prompt_removed_on_creation_session_note_and_log_failures(self):
        item = bot.Item(SimpleNamespace(dry=False, save=lambda: None), self.repo, "issue", 1)
        role = {"agent": "omp"}
        original_write = Path.write_text
        def partial_write(path, text, **kwargs):
            original_write(path, "partial", **kwargs)
            raise OSError("disk write failed")
        for seam in ("creation", "session", "note", "log"):
            with self.subTest(seam=seam), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(bot, "WORK", self.work))
                stack.enter_context(mock.patch.object(bot.shutil, "which", return_value="acpx"))
                stack.enter_context(mock.patch.object(bot, "known_agents", return_value={"omp"}))
                stack.enter_context(mock.patch.object(bot, "run", side_effect=OSError("session failed")
                                                     if seam == "session" else None))
                if seam == "creation":
                    stack.enter_context(mock.patch.object(Path, "write_text", partial_write))
                elif seam == "note":
                    stack.enter_context(mock.patch.object(item, "note", side_effect=OSError("note failed")))
                elif seam == "log":
                    stack.enter_context(mock.patch.object(item, "note"))
                    stack.enter_context(mock.patch.object(bot, "log", side_effect=OSError("log failed")))
                with self.assertRaises(OSError):
                    item.ask(role, "prompt", self.tree, "--approve-reads", "session")
                self.assertEqual(list((self.work / "prompts").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
