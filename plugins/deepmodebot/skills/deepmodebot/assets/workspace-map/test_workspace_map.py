#!/usr/bin/env python3
"""Fast deterministic tests for workspace_map.py (zero-bloat SQLite FTS5/mmap indexer)."""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace_map as wm


def _rmtree(path):
    """Windows-safe rmtree that clears read-only bits on .git/objects files."""
    if not os.path.exists(path):
        return

    def _clear_ro(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_ro)
    else:
        shutil.rmtree(path, onerror=_clear_ro)


def _git(cwd, *args):
    res = subprocess.run(
        ["git", "-C", cwd, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=wm.CREATE_NO_WINDOW,
    )
    if res.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}:\n{res.stdout}\n{res.stderr}")
    return res.stdout.strip()


def _write(root, rel, content):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if isinstance(content, bytes) else {"encoding": "utf-8", "newline": "\n"}
    with open(full, mode, **kwargs) as handle:
        handle.write(content)
    return full


def _init_repo(root, remote="https://github.com/acme/demo-app.git"):
    os.makedirs(root, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    if remote:
        _git(root, "remote", "add", "origin", remote)


def _run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = wm.main(argv)
    return rc, buf.getvalue()


class WorkspaceMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wmap-")
        self.addCleanup(lambda: _rmtree(self.tmp))

    def test_pragmas_and_incremental_sync_and_deletion(self):
        repo = os.path.join(self.tmp, "repo-inc")
        _init_repo(repo)
        _write(repo, "README.md", "# Demo App\n\n## Architecture\nDetails.\n")
        _write(repo, "app.py", "def alpha_worker(x, y):\n    return x + y\n")
        _write(repo, "remove_me.py", "def obsolete_hook():\n    pass\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "init")

        db = os.path.join(self.tmp, "inc.db")
        rc, out1 = _run_cli(["sync", repo, "--db", db, "--offline", "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        s1 = json.loads(out1)
        self.assertEqual(s1["files_indexed"], 3)
        self.assertEqual(s1["files_skipped"], 0)
        self.assertEqual(s1["files_removed"], 0)

        # Verify SQLite PRAGMAs (WAL, mmap, incremental auto_vacuum, foreign_keys).
        conn = wm.connect_db(db)
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertGreaterEqual(conn.execute("PRAGMA mmap_size").fetchone()[0], wm.MMAP_SIZE_BYTES)
            self.assertEqual(conn.execute("PRAGMA auto_vacuum").fetchone()[0], 2)
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        finally:
            conn.close()

        # Second sync without changes skips all files.
        rc, out2 = _run_cli(["sync", repo, "--db", db, "--offline", "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        s2 = json.loads(out2)
        self.assertEqual(s2["files_indexed"], 0)
        self.assertEqual(s2["files_skipped"], 3)

        # Modify one file and remove another; bump mtime_ns deterministically.
        app_path = _write(repo, "app.py", "def beta_worker(x, y, z=1):\n    return x + y + z\n")
        st = os.stat(app_path)
        os.utime(app_path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
        _git(repo, "rm", "-f", "remove_me.py")

        rc, out3 = _run_cli(["sync", repo, "--db", db, "--offline", "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        s3 = json.loads(out3)
        self.assertEqual(s3["files_indexed"], 1)
        self.assertEqual(s3["files_skipped"], 1)
        self.assertEqual(s3["files_removed"], 1)
        self.assertEqual(s3["total_files"], 2)

        # Verify FTS5 reflects updated and deleted symbols cleanly.
        rc, q_beta = _run_cli(["query", "beta_worker", repo, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_beta)["count"], 1)

        rc, q_alpha = _run_cli(["query", "alpha_worker", repo, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_alpha)["count"], 0)

        rc, q_obs = _run_cli(["query", "obsolete_hook", repo, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_obs)["count"], 0)

        conn = wm.connect_db(db)
        try:
            conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('integrity-check')")
        finally:
            conn.close()

    def test_shared_index_across_linked_git_worktrees_zero_duplication(self):
        main_repo = os.path.join(self.tmp, "main-checkout")
        _init_repo(main_repo)
        _write(main_repo, "engine.py", "class Engine:\n    def run_tick(self, dt):\n        return dt\n")
        _git(main_repo, "add", ".")
        _git(main_repo, "commit", "-m", "initial")

        linked_wt = os.path.join(self.tmp, "wt-feature")
        _git(main_repo, "worktree", "add", "-b", "feat/linked", linked_wt)

        with mock.patch.dict(os.environ, {"DEEPMODEBOT_MAP_DB": ""}, clear=False):
            info_main = wm.resolve_repo(main_repo)
            info_wt = wm.resolve_repo(linked_wt)
            self.assertEqual(info_main["repo_key"], info_wt["repo_key"])

            rc1, out1 = _run_cli(["sync", main_repo, "--offline", "--no-orca", "--json"])
            self.assertEqual(rc1, 0)
            s1 = json.loads(out1)

            rc2, out2 = _run_cli(["sync", linked_wt, "--offline", "--no-orca", "--json"])
            self.assertEqual(rc2, 0)
            s2 = json.loads(out2)

        expected_db = os.path.join(main_repo, ".scratch", "workspace-map.db")
        self.assertTrue(os.path.isfile(expected_db))
        self.assertEqual(wm.normalize_path_key(s1["db_path"]), wm.normalize_path_key(expected_db))
        self.assertEqual(wm.normalize_path_key(s2["db_path"]), wm.normalize_path_key(expected_db))

        gitignore = os.path.join(main_repo, ".scratch", ".gitignore")
        self.assertTrue(os.path.isfile(gitignore))
        with open(gitignore, encoding="utf-8") as handle:
            self.assertIn("*", handle.read())

        # Zero duplicate repos, files, or symbols across both checkouts; 2 distinct workspaces.
        conn = wm.connect_db(expected_db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0], 2)
        finally:
            conn.close()

    def test_anti_bloat_filtering_and_signature_cap(self):
        repo = os.path.join(self.tmp, "repo-bloat")
        _init_repo(repo)
        long_args = ", ".join(f"param_{i}=0" for i in range(25))
        _write(repo, "clean.py", f"def very_long_signature({long_args}):\n    return 1\n")
        _write(repo, "package-lock.json", '{"lockfileVersion": 3}\n')
        _write(repo, "Cargo.lock", "version = 3\n")
        _write(repo, "uv.lock", "version = 1\n")
        _write(repo, "dist/app.min.js", "function minified(){return 1}\n")
        _write(repo, "dist/site.min.css", "body{margin:0}\n")
        _write(repo, "assets/model.glb", b"glTF\x02\x00\x00\x00binary")
        _write(repo, "assets/icon.png", b"\x89PNG\r\n\x1a\n\x00\x00")
        _write(repo, "assets/logo.svg", "<svg></svg>\n")
        _write(repo, "sneaky_bin.txt", b"hello\x00world\x00binary")
        _write(repo, "huge.py", "# " + ("x" * (wm.MAX_FILE_BYTES + 2048)) + "\ndef never_indexed():\n    pass\n")
        _write(repo, ".scratch/note.py", "def scratch_ignored():\n    pass\n")
        _write(repo, ".worktrees/nested/x.py", "def wt_ignored():\n    pass\n")
        _git(repo, "add", "-f", ".")
        _git(repo, "commit", "-m", "bloat fixtures")

        db = os.path.join(self.tmp, "bloat.db")
        rc, out = _run_cli(["sync", repo, "--db", db, "--offline", "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        stats = json.loads(out)
        self.assertEqual(stats["total_files"], 1)
        self.assertEqual(stats["total_symbols"], 1)

        rc, q = _run_cli(["query", "very_long_signature", repo, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        rows = json.loads(q)["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rel_path"], "clean.py")
        self.assertLessEqual(len(rows[0]["signature"]), wm.MAX_SIGNATURE_CHARS)

    def test_fts5_query_across_languages_and_markdown_fences(self):
        repo = os.path.join(self.tmp, "repo-langs")
        _init_repo(repo)
        _write(repo, "src/calc.py", "class Planner:\n    def compute_score(self, items):\n        return len(items)\n")
        _write(
            repo,
            "web/router.ts",
            "export interface RouteSpec { path: string; }\n"
            "export const dispatchRoute = async (path: string) => path;\n",
        )
        _write(
            repo,
            "core/engine.rs",
            "pub struct PhysicsWorld { pub gravity: f32 }\n"
            "pub fn step_simulation(dt: f32) -> f32 { dt }\n",
        )
        _write(repo, "svc/server.go", "package main\nfunc StartGateway(port int) error { return nil }\n")
        _write(repo, "game/Actor.cs", "public class PlayerActor {\n    public void ApplyImpulse(float force) {}\n}\n")
        _write(
            repo,
            "docs/guide.md",
            "# Workspace Guide\n\n```python\n# fake_comment_in_fence\n```\n\n## Deployment Checklist\nSteps.\n",
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "multilang")

        db = os.path.join(self.tmp, "langs.db")
        rc, _ = _run_cli(["sync", repo, "--db", db, "--offline", "--no-orca"])
        self.assertEqual(rc, 0)

        expectations = [
            ("compute_score", "src/calc.py:2 method"),
            ("dispatchRoute", "web/router.ts:2 function"),
            ("RouteSpec", "web/router.ts:1 interface"),
            ("step_simulation", "core/engine.rs:2 function"),
            ("PhysicsWorld", "core/engine.rs:1 struct"),
            ("StartGateway", "svc/server.go:2 function"),
            ("PlayerActor", "game/Actor.cs:1 class"),
            ("Deployment Checklist", "docs/guide.md:7 heading"),
            ("step*", "core/engine.rs:2 function"),
            ("router.ts", "web/router.ts:"),
        ]
        for term, expected_fragment in expectations:
            rc, text_out = _run_cli(["query", term, repo, "--db", db])
            self.assertEqual(rc, 0, f"query {term} failed")
            self.assertIn(expected_fragment, text_out, f"term={term!r} output={text_out!r}")

        # Code block comment inside Markdown must NOT be indexed as a heading.
        rc, fence_out = _run_cli(["query", "fake_comment_in_fence", repo, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(fence_out)["count"], 0)

    def test_mocked_orca_gh_manifest_and_latest_summary_projection(self):
        main_repo = os.path.join(self.tmp, "orca-main")
        _init_repo(main_repo, remote="https://github.com/acme/orca-demo.git")
        _write(main_repo, "README.md", "# Orca Demo\n")
        _write(main_repo, "scripts/check.py", "def run_checks():\n    return 0\n")
        _write(main_repo, ".agents/skills/verify-demo/SKILL.md", "# Verify Demo\n")
        _git(main_repo, "add", ".")
        _git(main_repo, "commit", "-m", "init")

        feat_wt = os.path.join(self.tmp, "orca-feat")
        _git(main_repo, "worktree", "add", "-b", "feat/indexer", feat_wt)
        # Make feat_wt dirty so dirty state is reflected.
        _write(feat_wt, "dirty_untracked.txt", "wip\n")

        # Real scope manifest + latest-summary.json inside feat_wt.
        _write(
            feat_wt,
            "docs/specs/app-manifest.json",
            json.dumps({
                "product": "Indexer MVP",
                "active_sprint": 1,
                "sme_gate": "required",
                "slices": [
                    {"id": "s1", "title": "Core", "sprint": 1, "check": "true"},
                    {"id": "s2", "title": "UI", "sprint": 2, "check": "true"},
                ],
                "inventory": [
                    {"id": "inv-1", "status": "included"},
                    {"id": "inv-2", "status": "pending"},
                ],
            }),
        )
        _write(
            feat_wt,
            ".scratch/goals/ship-indexer/latest-summary.json",
            json.dumps({
                "goal": "Ship Indexer MVP",
                "exit_code": 6,
                "exit_reason": "sme_gate_required",
                "scope": {
                    "manifest": "docs/specs/app-manifest.json",
                    "active_sprint": 1,
                    "passed_slices": 1,
                    "active_slices": 1,
                    "total_slices": 2,
                    "deferred_slices": ["s2"],
                    "pending_inventory": ["inv-2"],
                    "sme_gate_blocked": True,
                },
            }),
        )

        gh_calls = []
        pr_payload = [
            {
                "number": 91,
                "title": "Overhaul workspace indexer",
                "headRefName": "feat/indexer",
                "baseRefName": "main",
                "state": "OPEN",
                "isDraft": False,
                "mergeStateStatus": "CLEAN",
                "reviewDecision": "APPROVED",
                "url": "https://github.com/acme/orca-demo/pull/91",
                "updatedAt": "2026-11-19T12:00:00Z",
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS", "status": "COMPLETED"},
                    {"conclusion": "SUCCESS", "status": "COMPLETED"},
                ],
            },
            {
                "number": 77,
                "title": "Docs polish",
                "headRefName": "docs/polish",
                "baseRefName": "main",
                "state": "OPEN",
                "isDraft": True,
                "mergeStateStatus": "BLOCKED",
                "reviewDecision": "",
                "url": "https://github.com/acme/orca-demo/pull/77",
                "updatedAt": "2026-11-18T10:00:00Z",
                "statusCheckRollup": [{"conclusion": "FAILURE", "status": "COMPLETED"}],
            },
        ]
        orca_payload = {
            "worktrees": [
                {
                    "id": "wt-91",
                    "name": "indexer-pod",
                    "path": feat_wt,
                    "branch": "feat/indexer",
                    "host": "local",
                    "status": "active",
                }
            ]
        }

        real_run_cmd = wm.run_cmd
        real_which = shutil.which

        def fake_which(cmd):
            if cmd in ("orca", "gh"):
                return f"/fake/bin/{cmd}"
            return real_which(cmd)

        def fake_run_cmd(args, cwd=None, timeout=15):
            if args and args[0] == "orca":
                return subprocess.CompletedProcess(args, 0, json.dumps(orca_payload), "")
            if args and args[0] == "gh":
                gh_calls.append(list(args))
                return subprocess.CompletedProcess(args, 0, json.dumps(pr_payload), "")
            return real_run_cmd(args, cwd=cwd, timeout=timeout)

        db = os.path.join(self.tmp, "orca-gh.db")
        with mock.patch("workspace_map.shutil.which", side_effect=fake_which), mock.patch(
            "workspace_map.run_cmd", side_effect=fake_run_cmd
        ):
            rc, ov_text = _run_cli(["overview", feat_wt, "--db", db])
            self.assertEqual(rc, 0)
            self.assertLessEqual(len(ov_text.encode("utf-8")), wm.DEFAULT_OVERVIEW_BYTES)
            self.assertIn("acme/orca-demo", ov_text)
            self.assertIn("verify-demo/SKILL.md", ov_text)
            self.assertIn("#91", ov_text)
            self.assertIn("git+orca", ov_text)
            self.assertIn("SME_BLOCKED", ov_text)
            self.assertIn("exit=6(sme_gate_required)", ov_text)
            self.assertEqual(len(gh_calls), 1)

            # Second sync within TTL uses PR cache (no second gh call).
            rc, sync_cached = _run_cli(["sync", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(sync_cached)["prs_cached"])
            self.assertEqual(len(gh_calls), 1)

            # workspaces joins git+orca, dirty, PR #91, and project_state.
            rc, ws_json = _run_cli(["workspaces", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            ws_items = json.loads(ws_json)["workspaces"]
            feat_entry = next(w for w in ws_items if w["branch"] == "feat/indexer")
            self.assertEqual(feat_entry["source"], "git+orca")
            self.assertEqual(feat_entry["orca_host"], "local")
            self.assertEqual(feat_entry["is_dirty"], 1)
            self.assertEqual(feat_entry["pr"]["number"], 91)
            self.assertEqual(feat_entry["pr"]["checks_summary"], "pass:2")
            self.assertEqual(len(feat_entry["project_state"]), 1)
            ps = feat_entry["project_state"][0]
            self.assertEqual(ps["active_sprint"], 1)
            self.assertEqual(ps["passed_slices"], 1)
            self.assertEqual(ps["total_slices"], 2)
            self.assertEqual(ps["deferred_count"], 1)
            self.assertEqual(ps["pending_inventory"], 1)
            self.assertEqual(ps["sme_gate_blocked"], 1)
            self.assertEqual(ps["last_exit_code"], 6)
            self.assertEqual(ps["last_exit_reason"], "sme_gate_required")

            # prs joins local worktree path & check/merge status.
            rc, prs_json = _run_cli(["prs", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            prs_list = json.loads(prs_json)["prs"]
            self.assertEqual(len(prs_list), 2)
            pr91 = next(p for p in prs_list if p["number"] == 91)
            self.assertEqual(wm.normalize_path_key(pr91["worktree_path"]), wm.normalize_path_key(feat_wt))
            self.assertEqual(pr91["merge_state"], "CLEAN")
            self.assertEqual(pr91["checks_summary"], "pass:2")
            pr77 = next(p for p in prs_list if p["number"] == 77)
            self.assertIsNone(pr77["worktree_path"])
            self.assertEqual(pr77["checks_summary"], "fail:1")

            # --force-prs refreshes and automatically deletes closed PR #77.
            pr_payload.pop(1)
            rc, sync_forced = _run_cli(["sync", feat_wt, "--db", db, "--force-prs", "--json"])
            self.assertEqual(rc, 0)
            self.assertFalse(json.loads(sync_forced)["prs_cached"])
            self.assertEqual(json.loads(sync_forced)["prs_count"], 1)
            self.assertEqual(len(gh_calls), 2)

    def test_overview_strict_byte_cap(self):
        repo = os.path.join(self.tmp, "repo-cap")
        _init_repo(repo, remote="https://github.com/acme/very-long-repository-name-for-byte-cap.git")
        for idx in range(8):
            _write(repo, f"docs/document_{idx}_overview_notes.md", f"# Heading {idx} — café\n")
            _write(repo, f"scripts/entrypoint_{idx}.py", f"def entry_{idx}():\n    return {idx}\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "cap test")

        db = os.path.join(self.tmp, "cap.db")
        for cap in (180, 320, 1400):
            rc, out = _run_cli(["overview", repo, "--db", db, "--offline", "--no-orca", "--max-bytes", str(cap)])
            self.assertEqual(rc, 0)
            # Strip trailing newline added by print() before measuring rendered overview text.
            rendered = out.rstrip("\n")
            self.assertLessEqual(len(rendered.encode("utf-8")), cap)
            self.assertGreater(len(rendered), 0)

    def test_prune_and_all_repos_query(self):
        repo_a = os.path.join(self.tmp, "repo-a")
        repo_b = os.path.join(self.tmp, "repo-b")
        _init_repo(repo_a, remote="https://github.com/acme/alpha.git")
        _init_repo(repo_b, remote="https://github.com/acme/beta.git")
        _write(repo_a, "a.py", "def shared_token_alpha():\n    return 'a'\n")
        _write(repo_b, "b.py", "def shared_token_beta():\n    return 'b'\n")
        _git(repo_a, "add", ".")
        _git(repo_a, "commit", "-m", "a")
        _git(repo_b, "add", ".")
        _git(repo_b, "commit", "-m", "b")

        db = os.path.join(self.tmp, "global.db")
        self.assertEqual(_run_cli(["sync", repo_a, "--db", db, "--offline", "--no-orca"])[0], 0)
        self.assertEqual(_run_cli(["sync", repo_b, "--db", db, "--offline", "--no-orca"])[0], 0)

        rc, q_all = _run_cli(["query", "shared_token*", repo_a, "--db", db, "--all-repos", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_all)["count"], 2)

        # Remove repo_b from disk and insert a stale PR row on repo_a.
        _rmtree(repo_b)
        conn = wm.connect_db(db)
        try:
            rkey_a = wm.resolve_repo(repo_a)["repo_key"]
            old_ts = time.time() - (45 * 86400)
            conn.execute(
                "INSERT INTO prs(repo_key, number, title, head_branch, base_branch, synced_at) "
                "VALUES(?, 12, 'Old PR', 'old', 'main', ?)",
                (rkey_a, old_ts),
            )
            conn.commit()
        finally:
            conn.close()

        rc, prune_out = _run_cli(["prune", "--days", "30", "--db", db, "--json"])
        self.assertEqual(rc, 0)
        pdata = json.loads(prune_out)
        self.assertEqual(pdata["dropped_repos"], 1)
        self.assertEqual(pdata["dropped_prs"], 1)
        self.assertGreaterEqual(pdata["reclaimed_bytes"], 0)

        rc, q_after = _run_cli(["query", "shared_token*", repo_a, "--db", db, "--all-repos", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_after)["count"], 1)

    def test_offline_overview_does_not_poison_prs_workspaces_or_query(self):
        main_repo = os.path.join(self.tmp, "stale-main")
        _init_repo(main_repo, remote="https://github.com/acme/fresh-demo.git")
        _write(main_repo, "mod.py", "def initial_symbol():\n    return 1\n")
        _git(main_repo, "add", ".")
        _git(main_repo, "commit", "-m", "init")

        feat_wt = os.path.join(self.tmp, "stale-feat")
        _git(main_repo, "worktree", "add", "-b", "feat/fresh", feat_wt)

        db = os.path.join(self.tmp, "fresh.db")
        # Step 1: Turn-1 offline + no-orca overview (like Antigravity's hook).
        rc, _ = _run_cli(["overview", feat_wt, "--db", db, "--fast", "--offline", "--no-orca"])
        self.assertEqual(rc, 0)

        gh_calls = []
        orca_calls = []
        pr_payload = [
            {
                "number": 91,
                "title": "Live PR after offline overview",
                "headRefName": "feat/fresh",
                "baseRefName": "main",
                "state": "OPEN",
                "isDraft": False,
                "mergeStateStatus": "CLEAN",
                "reviewDecision": "APPROVED",
                "url": "https://github.com/acme/fresh-demo/pull/91",
                "updatedAt": "2026-11-19T12:00:00Z",
                "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}],
            }
        ]
        orca_payload = {
            "worktrees": [
                {
                    "id": "wt-live",
                    "name": "fresh-pod",
                    "path": feat_wt,
                    "branch": "feat/fresh",
                    "host": "local",
                    "status": "active",
                }
            ]
        }

        real_run_cmd = wm.run_cmd
        real_which = shutil.which

        def fake_which(cmd):
            if cmd in ("orca", "gh"):
                return f"/fake/bin/{cmd}"
            return real_which(cmd)

        def fake_run_cmd(args, cwd=None, timeout=15):
            if args and args[0] == "orca":
                orca_calls.append(list(args))
                return subprocess.CompletedProcess(args, 0, json.dumps(orca_payload), "")
            if args and args[0] == "gh":
                gh_calls.append(list(args))
                return subprocess.CompletedProcess(args, 0, json.dumps(pr_payload), "")
            return real_run_cmd(args, cwd=cwd, timeout=timeout)

        # Make feat_wt dirty AFTER offline overview so workspaces must refresh dirty state too.
        _write(feat_wt, "dirty_after_overview.txt", "wip\n")

        with mock.patch("workspace_map.shutil.which", side_effect=fake_which), mock.patch(
            "workspace_map.run_cmd", side_effect=fake_run_cmd
        ):
            # Step 2: `prs` MUST refresh live via gh even though DB already exists!
            rc, prs_out = _run_cli(["prs", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            prs_data = json.loads(prs_out)["prs"]
            self.assertEqual(len(prs_data), 1)
            self.assertEqual(prs_data[0]["number"], 91)
            self.assertEqual(len(gh_calls), 1)

            # Second `prs` within TTL uses cache (no extra gh call), while `--force-prs` bypasses TTL.
            rc, _ = _run_cli(["prs", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(gh_calls), 1)
            rc, _ = _run_cli(["prs", feat_wt, "--db", db, "--force-prs", "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(gh_calls), 2)
            rc, _ = _run_cli(["prs", feat_wt, "--db", db, "--offline", "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(gh_calls), 2)

            # Step 3: `workspaces` MUST refresh Orca + dirty state even though DB already exists!
            rc, ws_out = _run_cli(["workspaces", feat_wt, "--db", db, "--json"])
            self.assertEqual(rc, 0)
            ws_items = json.loads(ws_out)["workspaces"]
            feat_entry = next(w for w in ws_items if w["branch"] == "feat/fresh")
            self.assertEqual(feat_entry["source"], "git+orca")
            self.assertEqual(feat_entry["is_dirty"], 1)
            self.assertEqual(feat_entry["pr"]["number"], 91)
            self.assertEqual(len(orca_calls), 1)

        # Step 4: Edit a tracked file after overview; `query` MUST incrementally sync and find it!
        mod_path = _write(feat_wt, "mod.py", "def fresh_live_symbol(v):\n    return v * 2\n")
        st = os.stat(mod_path)
        os.utime(mod_path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))

        rc, q_fresh = _run_cli(["query", "fresh_live_symbol", feat_wt, "--db", db, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_fresh)["count"], 1)

        # Step 5: `--no-sync` opt-out reads cached DB without syncing new edits.
        mod_path2 = _write(feat_wt, "mod.py", "def skipped_when_nosync():\n    return 3\n")
        st2 = os.stat(mod_path2)
        os.utime(mod_path2, ns=(st2.st_atime_ns, st2.st_mtime_ns + 4_000_000_000))
        rc, q_nosync = _run_cli(["query", "skipped_when_nosync", feat_wt, "--db", db, "--no-sync", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(q_nosync)["count"], 0)

    def test_fast_flag_limits_dirty_checks_to_current_and_main_worktrees(self):
        main_repo = os.path.join(self.tmp, "fast-main")
        _init_repo(main_repo)
        _write(main_repo, "a.py", "def a():\n    return 1\n")
        _git(main_repo, "add", ".")
        _git(main_repo, "commit", "-m", "init")

        wts = []
        for idx in range(3):
            wt = os.path.join(self.tmp, f"fast-wt-{idx}")
            _git(main_repo, "worktree", "add", "-b", f"feat/wt-{idx}", wt)
            wts.append(wt)

        db = os.path.join(self.tmp, "fast.db")
        checked_paths = []
        real_check_dirty = wm._check_dirty

        def spy_check_dirty(raw_path):
            checked_paths.append(wm.normalize_path_key(raw_path))
            return real_check_dirty(raw_path)

        with mock.patch("workspace_map._check_dirty", side_effect=spy_check_dirty):
            rc, _ = _run_cli(["overview", wts[0], "--db", db, "--fast", "--offline", "--no-orca"])
            self.assertEqual(rc, 0)
            self.assertEqual(
                set(checked_paths),
                {wm.normalize_path_key(wts[0]), wm.normalize_path_key(main_repo)},
            )
            self.assertEqual(len(checked_paths), 2)

            checked_paths.clear()
            rc, _ = _run_cli(["sync", wts[0], "--db", db, "--offline", "--no-orca"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(checked_paths), 4)

    def test_project_state_reads_goal_frontmatter_and_merges_latest_summary(self):
        repo = os.path.join(self.tmp, "goal-frontmatter-repo")
        _init_repo(repo)
        _write(repo, "README.md", "# Goal State Demo\n")
        # Real loop.py manifest JSON has NO active_sprint or slice status fields.
        _write(
            repo,
            "docs/specs/real-manifest.json",
            json.dumps({
                "product": "Billing Engine",
                "slices": [
                    {"id": "s1", "title": "Core", "sprint": 1, "check": "true"},
                    {"id": "s2", "title": "Exports", "sprint": 2, "sme_gate": "required", "check": "true"},
                ],
                "inventory": [
                    {"id": "inv-1", "status": "included", "slice": "s1"},
                    {"id": "inv-2", "status": "pending"},
                ],
            }),
        )
        _write(
            repo,
            ".scratch/goals/billing.md",
            "---\n"
            "goal: Ship Billing Engine\n"
            "manifest: docs/specs/real-manifest.json\n"
            "active_sprint: 1\n"
            "check: true\n"
            "protect: docs/specs/real-manifest.json\n"
            "max_iterations: 3\n"
            "---\n"
            "Deliver Sprint 1.\n",
        )
        _git(repo, "add", "README.md", "docs/specs/real-manifest.json")
        _git(repo, "commit", "-m", "init")

        db = os.path.join(self.tmp, "goal-state.db")
        rc, ws1 = _run_cli(["workspaces", repo, "--db", db, "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        states1 = json.loads(ws1)["workspaces"][0]["project_state"]
        self.assertEqual(len(states1), 1)
        ps1 = states1[0]
        self.assertEqual(ps1["product"], "Billing Engine")
        self.assertEqual(ps1["active_sprint"], 1)
        self.assertEqual(ps1["active_slices"], 1)
        self.assertEqual(ps1["total_slices"], 2)
        self.assertEqual(ps1["deferred_count"], 1)
        self.assertEqual(ps1["pending_inventory"], 1)
        # Sprint 2's sme_gate is deferred while active_sprint=1!
        self.assertEqual(ps1["sme_gate_blocked"], 0)
        self.assertEqual(ps1["passed_slices"], 0)

        # Now write latest-summary.json (e.g. from already-passing loop.py run) and confirm clean merge.
        _write(
            repo,
            ".scratch/goals/billing/latest-summary.json",
            json.dumps({
                "goal": "Ship Billing Engine",
                "exit_code": 0,
                "exit_reason": "sprint_already_passed",
                "scope": {
                    "manifest": "docs/specs/real-manifest.json",
                    "active_sprint": 1,
                    "passed_slices": 1,
                    "active_slices": 1,
                    "total_slices": 2,
                    "deferred_slices": ["s2"],
                    "pending_inventory": ["inv-2"],
                    "sme_gate_blocked": False,
                },
            }),
        )
        rc, ws2 = _run_cli(["workspaces", repo, "--db", db, "--no-orca", "--json"])
        self.assertEqual(rc, 0)
        states2 = json.loads(ws2)["workspaces"][0]["project_state"]
        self.assertEqual(len(states2), 1)
        ps2 = states2[0]
        self.assertEqual(ps2["active_sprint"], 1)
        self.assertEqual(ps2["passed_slices"], 1)
        self.assertEqual(ps2["total_slices"], 2)
        self.assertEqual(ps2["deferred_count"], 1)
        self.assertEqual(ps2["last_exit_code"], 0)
        self.assertEqual(ps2["last_exit_reason"], "sprint_already_passed")


if __name__ == "__main__":
    unittest.main()
