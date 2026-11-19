"""Tests for the Antigravity write-containment hook (hooks.json and scripts/antigravity-guard.mjs)."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[3]
GUARD = PLUGIN / "scripts" / "antigravity-guard.mjs"
HOOKS_JSON = PLUGIN / "hooks.json"

WRITE_TOOL_CASES = (
    ("write_file", "Path"),
    ("edit_file", "Path"),
    ("write_to_file", "TargetFile"),
    ("replace_file_content", "TargetFile"),
    ("multi_replace_file_content", "TargetFile"),
)


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def remove_tree(path):
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(folder, name), stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


@unittest.skipUnless(shutil.which("node"), "node is not on PATH")
class AntigravityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        cls.tmp = Path(tempfile.mkdtemp(prefix="agy-guard-test-")).resolve()
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        cls.plugin_data = cls.tmp / "plugin-data"
        cls.plugin_data.mkdir()

        cls.proj = cls.tmp / "proj"
        cls.proj.mkdir()
        git(cls.proj, "init", "-q", "-b", "main")
        git(cls.proj, "commit", "-q", "--allow-empty", "-m", "init")

        cls.inner_wt = cls.proj / ".worktrees" / "wt"
        git(cls.proj, "worktree", "add", "-q", "--detach", str(cls.inner_wt))

        cls.ext_wt = cls.tmp / "ext-wt"
        git(cls.proj, "worktree", "add", "-q", "--detach", str(cls.ext_wt))

        cls.outside = cls.tmp / "outside"
        cls.outside.mkdir()
        cls.artifacts = cls.tmp / "artifacts" / "conv-1"

        cls.base_env = {
            **os.environ,
            "GIT_CEILING_DIRECTORIES": str(cls.tmp),
            "HOME": str(cls.home),
            "USERPROFILE": str(cls.home),
            "PLUGIN_DATA": str(cls.plugin_data),
        }

    @classmethod
    def tearDownClass(cls):
        remove_tree(cls.tmp)

    def run_hook(self, payload, cli_args=(), env_extra=None, cwd=None):
        env = {**self.base_env, **(env_extra or {})}
        raw_in = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run(
            [self.node, str(GUARD), *cli_args],
            input=raw_in,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(cwd or PLUGIN),
            env=env,
        )
        self.assertEqual(proc.returncode, 0, f"Hook exited non-zero: {proc.stderr}")
        out = json.loads(proc.stdout.strip())
        return out, proc.stderr

    def pre_tool_payload(
        self,
        tool_name,
        target,
        arg_key="Path",
        conv_id="conv-enforce",
        workspace=None,
        cwd=None,
        artifact_dir=None,
        include_event_name=True,
    ):
        ws = [str(workspace or self.proj)]
        payload = {
            "conversationId": conv_id,
            "workspacePaths": ws,
            "artifactDirectoryPath": str(artifact_dir or self.artifacts),
            "toolCall": {
                "name": tool_name,
                "args": {arg_key: str(target)},
            },
        }
        if cwd is not None:
            payload["cwd"] = str(cwd)
        if include_event_name:
            payload["hookEventName"] = "PreToolUse"
        return payload

    def test_hooks_json_schema_and_relative_command(self):
        data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        self.assertIn("deepmodebot-contain", data)
        group = data["deepmodebot-contain"]
        self.assertTrue(group.get("enabled", True))
        pre_inv = group["PreInvocation"]
        self.assertIsInstance(pre_inv, list)
        self.assertEqual(pre_inv[0]["command"], "node ./scripts/antigravity-guard.mjs")
        self.assertEqual(pre_inv[0]["timeout"], 10)
        pre_tool = group["PreToolUse"]
        self.assertEqual(
            pre_tool[0]["matcher"],
            "write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content",
        )
        self.assertEqual(pre_tool[0]["hooks"][0]["command"], "node ./scripts/antigravity-guard.mjs")

    def test_inactive_session_passes_through_until_activated_by_slash_command(self):
        outside_file = self.outside / "note.txt"
        out, _ = self.run_hook(
            self.pre_tool_payload("write_file", outside_file, conv_id="conv-inactive")
        )
        self.assertEqual(out, {"decision": "allow"})

        # Mentioning /deep mid-sentence must not activate containment.
        pre_res, _ = self.run_hook({
            "conversationId": "conv-inactive",
            "workspacePaths": [str(self.proj)],
            "lastUserInput": "Could we try /deep later?",
        })
        self.assertEqual(pre_res, {})
        out, _ = self.run_hook(
            self.pre_tool_payload("write_file", outside_file, conv_id="conv-inactive")
        )
        self.assertEqual(out, {"decision": "allow"})

        # Leading /deep activates containment for this conversationId only.
        pre_res, _ = self.run_hook({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-inactive",
            "workspacePaths": [str(self.proj)],
            "lastUserInput": "  /deep fix the flaky test",
        })
        self.assertEqual(pre_res, {})
        denied, _ = self.run_hook(
            self.pre_tool_payload("write_file", outside_file, conv_id="conv-inactive")
        )
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("deepmodebot keeps all writes inside the project root", denied["reason"])
        self.assertIn(".deepmodebot.json", denied["reason"])

        # Another conversation stays unaffected.
        other, _ = self.run_hook(
            self.pre_tool_payload("write_file", outside_file, conv_id="conv-other")
        )
        self.assertEqual(other, {"decision": "allow"})

    def test_namespaced_and_workflow_slash_commands_activate_session(self):
        prompts = [
            "/deepmodebot:deep ship feature",
            "/deepmodebot:tournament find gaps",
            "/tournament find architecture gaps",
            "/deepmodebot:review-pr 12",
            "/review-pr 12",
            "/land-pr 12",
            "/pr-thread 12",
            "/contribute",
            "/project-brief",
        ]
        for idx, prompt in enumerate(prompts):
            conv = f"conv-cmd-{idx}"
            with self.subTest(prompt=prompt):
                self.run_hook({
                    "conversationId": conv,
                    "workspacePaths": [str(self.proj)],
                    "lastUserInput": prompt,
                })
                res, _ = self.run_hook(
                    self.pre_tool_payload("write_file", self.outside / "x.txt", conv_id=conv)
                )
                self.assertEqual(res["decision"], "deny")

    def test_marks_older_than_30_days_are_pruned(self):
        prune_data = self.tmp / "prune-data"
        marks = prune_data / "active-sessions"
        marks.mkdir(parents=True)
        stale = marks / "stale-session"
        fresh = marks / "fresh-session"
        stale.write_text("", encoding="utf-8")
        fresh.write_text("", encoding="utf-8")
        old_ts = stale.stat().st_mtime - 31 * 24 * 3600
        os.utime(stale, (old_ts, old_ts))

        self.run_hook(
            {
                "conversationId": "new-session",
                "workspacePaths": [str(self.proj)],
                "lastUserInput": "/deep check",
            },
            env_extra={"PLUGIN_DATA": str(prune_data)},
        )
        self.assertEqual(sorted(p.name for p in marks.iterdir()), ["fresh-session", "new-session"])

    def test_inside_root_and_outside_root_across_all_write_tools(self):
        for tool_name, arg_key in WRITE_TOOL_CASES:
            with self.subTest(tool=tool_name):
                allow_res, _ = self.run_hook(
                    self.pre_tool_payload(
                        tool_name,
                        self.proj / "src" / "new_file.ts",
                        arg_key=arg_key,
                        include_event_name=False,
                    ),
                    cli_args=("enforce",),
                )
                self.assertEqual(allow_res, {"decision": "allow"})

                deny_res, _ = self.run_hook(
                    self.pre_tool_payload(
                        tool_name,
                        self.outside / "escaped.ts",
                        arg_key=arg_key,
                        include_event_name=False,
                    ),
                    cli_args=("enforce",),
                )
                self.assertEqual(deny_res["decision"], "deny")

    def test_prefix_sibling_and_dot_dot_traversal_are_denied(self):
        sibling, _ = self.run_hook(
            self.pre_tool_payload("write_file", self.tmp / "proj-evil" / "x.txt"),
            cli_args=("enforce",),
        )
        self.assertEqual(sibling["decision"], "deny")

        traversal, _ = self.run_hook(
            self.pre_tool_payload("write_file", "../outside/x.txt", cwd=self.proj),
            cli_args=("enforce",),
        )
        self.assertEqual(traversal["decision"], "deny")

    def test_linked_worktree_allows_both_worktree_and_main_checkout(self):
        for wt in (self.inner_wt, self.ext_wt):
            with self.subTest(worktree=wt.name):
                in_wt, _ = self.run_hook(
                    self.pre_tool_payload("write_file", wt / "local.txt", workspace=wt),
                    cli_args=("enforce",),
                )
                self.assertEqual(in_wt, {"decision": "allow"})

                in_main, _ = self.run_hook(
                    self.pre_tool_payload("write_file", self.proj / "README.md", workspace=wt),
                    cli_args=("enforce",),
                )
                self.assertEqual(in_main, {"decision": "allow"})

                out_wt, _ = self.run_hook(
                    self.pre_tool_payload("write_file", self.outside / "no.txt", workspace=wt),
                    cli_args=("enforce",),
                )
                self.assertEqual(out_wt["decision"], "deny")

    def test_extra_write_roots_artifact_dir_and_brain_dirs_are_allowed(self):
        cfg = self.proj / ".deepmodebot.json"
        cfg.write_text(
            json.dumps({"extraWriteRoots": [str(self.outside / "allowed-sub")]}),
            encoding="utf-8",
        )
        try:
            ok_extra, _ = self.run_hook(
                self.pre_tool_payload("write_file", self.outside / "allowed-sub" / "ok.txt"),
                cli_args=("enforce",),
            )
            self.assertEqual(ok_extra, {"decision": "allow"})

            no_extra, _ = self.run_hook(
                self.pre_tool_payload("write_file", self.outside / "other-sub" / "no.txt"),
                cli_args=("enforce",),
            )
            self.assertEqual(no_extra["decision"], "deny")
        finally:
            cfg.unlink()

        ok_artifact, _ = self.run_hook(
            self.pre_tool_payload("write_file", self.artifacts / "plan.md"),
            cli_args=("enforce",),
        )
        self.assertEqual(ok_artifact, {"decision": "allow"})

        for surface in ("antigravity", "antigravity-cli", "antigravity-ide"):
            brain_target = self.home / ".gemini" / surface / "brain" / "c1" / "task.md"
            ok_brain, _ = self.run_hook(
                self.pre_tool_payload("write_file", brain_target),
                cli_args=("enforce",),
            )
            self.assertEqual(ok_brain, {"decision": "allow"})

        # ~/.gemini/config outside brain/ must still be blocked!
        bad_gemini, _ = self.run_hook(
            self.pre_tool_payload("write_file", self.home / ".gemini" / "config" / "hooks.json"),
            cli_args=("enforce",),
        )
        self.assertEqual(bad_gemini["decision"], "deny")

    def test_malformed_stdin_exits_zero_without_crashing(self):
        out, err = self.run_hook("not-valid-json", cli_args=("enforce",))
        self.assertEqual(out, {})
        self.assertIn("unreadable hook input", err)


if __name__ == "__main__":
    unittest.main()
