"""Tests for the local omp MCP bridge (mcp_config.json and scripts/omp-mcp-server.mjs)."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[3]
SERVER = PLUGIN / "scripts" / "omp-mcp-server.mjs"
MCP_CONFIG = PLUGIN / "mcp_config.json"

MOCK_OMP_PY = """import json
import os
import re
import sys
import time

args = sys.argv[1:]
if "--version" in args or "-v" in args:
    print("omp 18.20.0-mock")
    sys.exit(0)

started = time.time()
stdin_text = sys.stdin.read()
if "__HANG__" in stdin_text:
    time.sleep(60)
sleep_match = re.search(r"__SLEEP_MS:(\\d+)__", stdin_text)
if sleep_match:
    time.sleep(int(sleep_match.group(1)) / 1000.0)
finished = time.time()

record = {
    "args": args,
    "stdin": stdin_text,
    "cwd": os.getcwd(),
    "started": started,
    "finished": finished,
    "has_anthropic_key": "ANTHROPIC_API_KEY" in os.environ,
    "has_anthropic_auth_token": "ANTHROPIC_AUTH_TOKEN" in os.environ,
    "has_openai_key": "OPENAI_API_KEY" in os.environ,
    "has_codex_key": "CODEX_API_KEY" in os.environ,
    "has_gemini_key": "GEMINI_API_KEY" in os.environ,
    "has_google_key": "GOOGLE_API_KEY" in os.environ,
    "has_bedrock": "CLAUDE_CODE_USE_BEDROCK" in os.environ,
    "has_vertex": "CLAUDE_CODE_USE_VERTEX" in os.environ,
    "has_foundry": "CLAUDE_CODE_USE_FOUNDRY" in os.environ,
    "tmpdir": os.environ.get("TMPDIR", ""),
}
event = {
    "type": "message_end",
    "message": {
        "role": "assistant",
        "model": "claude-sonnet-mock",
        "provider": "anthropic",
        "stopReason": "stop",
        "content": [{"type": "text", "text": json.dumps(record)}],
        "usage": {"input": 12, "output": 8},
    },
}
print(json.dumps({"type": "session_init", "sessionId": "mock-s1"}))
print(json.dumps(event))
"""


def remove_tree(path):
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(folder, name), stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


@unittest.skipUnless(shutil.which("node"), "node is not on PATH")
class OmpMcpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        cls.tmp = Path(tempfile.mkdtemp(prefix="omp-mcp-test-")).resolve()
        cls.home = cls.tmp / "home"
        cls.bin_dir = cls.tmp / "bin"
        cls.workspace = cls.tmp / "workspace"
        cls.bin_dir.mkdir(parents=True)
        cls.workspace.mkdir(parents=True)

        # Create workspace & user skill fixtures and MCP config with secret values to test redaction.
        ws_skill = cls.workspace / ".omp" / "skills" / "ws-demo"
        ws_skill.mkdir(parents=True)
        (ws_skill / "SKILL.md").write_text(
            '---\nname: ws-demo\ndescription: "Workspace demo skill"\n---\nWorkspace skill body.\n',
            encoding="utf-8",
        )
        (ws_skill / "notes.txt").write_text("extra reference note", encoding="utf-8")

        ag_skill = cls.workspace / ".agents" / "skills" / "agents-demo"
        ag_skill.mkdir(parents=True)
        (ag_skill / "SKILL.md").write_text(
            '---\nname: agents-demo\ndescription: "Agents dir skill"\n---\nAgents skill body.\n',
            encoding="utf-8",
        )

        user_skill = cls.home / ".omp" / "agent" / "skills" / "user-demo"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text(
            '---\nname: user-demo\ndescription: "User skill"\n---\nUser skill body.\n',
            encoding="utf-8",
        )

        nm_skill = cls.home / ".omp" / "plugins" / "node_modules" / "pkg-a" / "skills" / "nm-demo"
        nm_skill.mkdir(parents=True)
        (nm_skill / "SKILL.md").write_text(
            '---\nname: nm-demo\ndescription: "Node modules skill"\n---\nNM skill body.\n',
            encoding="utf-8",
        )

        mcp_file = cls.home / ".omp" / "agent" / "mcp.json"
        mcp_file.write_text(
            json.dumps({
                "mcpServers": {
                    "local-db": {
                        "command": "node",
                        "args": ["db.js", "--token=TOP_SECRET_ARG"],
                        "env": {"DB_PASSWORD": "SUPER_SECRET_ENV_VALUE"},
                    },
                    "remote-api": {
                        "url": "https://mcp.example.com/v1?key=SUPER_SECRET_QUERY",
                        "headers": {"Authorization": "Bearer SUPER_SECRET_HEADER_TOKEN"},
                    },
                }
            }),
            encoding="utf-8",
        )

        # Create cross-platform mocked `omp` binary on PATH.
        mock_py = cls.bin_dir / "mock_omp.py"
        mock_py.write_text(MOCK_OMP_PY, encoding="utf-8")
        if os.name == "nt":
            shim = cls.bin_dir / "omp.cmd"
            shim.write_text(f'@"{sys.executable}" "{mock_py}" %*\r\n', encoding="utf-8")
        else:
            shim = cls.bin_dir / "omp"
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{mock_py}" "$@"\n', encoding="utf-8")
            shim.chmod(0o755)

        overridden = {
            "PATH",
            "OMP_BIN",
            "HOME",
            "USERPROFILE",
            "PI_CODING_AGENT_DIR",
            "PLUGIN_ROOT",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        }
        existing_path = os.environ.get("PATH") or os.environ.get("Path") or ""
        clean_env = {
            k: v for k, v in os.environ.items() if k.upper() not in overridden
        }
        cls.base_env = {
            **clean_env,
            "HOME": str(cls.home),
            "USERPROFILE": str(cls.home),
            "PI_CODING_AGENT_DIR": str(cls.home / ".omp" / "agent"),
            "PLUGIN_ROOT": str(PLUGIN),
            "PATH": str(cls.bin_dir) + (os.pathsep + existing_path if existing_path else ""),
            "ANTHROPIC_API_KEY": "sk-ant-should-be-stripped",
            "ANTHROPIC_AUTH_TOKEN": "tok-ant-should-be-stripped",
            "OPENAI_API_KEY": "sk-openai-should-be-stripped",
            "CODEX_API_KEY": "sk-codex-should-be-stripped",
            "GEMINI_API_KEY": "gem-should-be-stripped",
            "GOOGLE_API_KEY": "goog-should-be-stripped",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "CLAUDE_CODE_USE_VERTEX": "1",
            "CLAUDE_CODE_USE_FOUNDRY": "1",
        }

    @classmethod
    def tearDownClass(cls):
        remove_tree(cls.tmp)

    def rpc_lines(self, messages):
        raw = "\n".join(json.dumps(m) for m in messages) + "\n"
        proc = subprocess.run(
            [self.node, str(SERVER)],
            input=raw.encode("utf-8"),
            capture_output=True,
            env=self.base_env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
        lines = [
            json.loads(line)
            for line in proc.stdout.decode("utf-8").splitlines()
            if line.strip()
        ]
        return lines

    def rpc_content_length(self, messages):
        chunks = []
        for msg in messages:
            body = json.dumps(msg).encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            chunks.append(header + body)
        proc = subprocess.run(
            [self.node, str(SERVER)],
            input=b"".join(chunks),
            capture_output=True,
            env=self.base_env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
        out = proc.stdout
        parsed = []
        idx = 0
        while idx < len(out):
            sep = out.find(b"\r\n\r\n", idx)
            self.assertNotEqual(sep, -1, f"Expected Content-Length header in {out!r}")
            head = out[idx:sep].decode("ascii")
            self.assertTrue(head.lower().startswith("content-length:"))
            length = int(head.split(":", 1)[1].strip())
            body_start = sep + 4
            body_end = body_start + length
            parsed.append(json.loads(out[body_start:body_end].decode("utf-8")))
            idx = body_end
        return parsed

    def test_mcp_config_json_schema(self):
        cfg = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        self.assertIn("omp", cfg["mcpServers"])
        entry = cfg["mcpServers"]["omp"]
        self.assertEqual(entry["command"], "node")
        self.assertEqual(entry["args"], ["${PLUGIN_ROOT}/scripts/omp-mcp-server.mjs"])
        self.assertEqual(entry["timeoutSeconds"], 3600)
        self.assertNotIn("variables", entry)

    def test_initialize_ping_and_tools_list_over_both_framings(self):
        batch = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ]
        for runner in (self.rpc_lines, self.rpc_content_length):
            responses = runner(batch)
            self.assertEqual([r["id"] for r in responses], [1, 2, 3])
            init_res = responses[0]["result"]
            self.assertEqual(init_res["protocolVersion"], "2024-11-05")
            self.assertEqual(init_res["serverInfo"]["name"], "deepmodebot-omp")
            self.assertEqual(responses[1]["result"], {})
            tool_names = [t["name"] for t in responses[2]["result"]["tools"]]
            self.assertEqual(tool_names, ["omp_run", "omp_task", "omp_resolve"])

    def test_omp_resolve_lists_skills_and_redacts_mcp_secrets(self):
        responses = self.rpc_lines([{
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "omp_resolve",
                "arguments": {"cwd": str(self.workspace)},
            },
        }])
        res = responses[0]["result"]
        self.assertFalse(res.get("isError"))
        raw_text = res["content"][0]["text"]
        # Secret values from mcp.json must NEVER appear anywhere in output!
        for secret in (
            "TOP_SECRET_ARG",
            "SUPER_SECRET_ENV_VALUE",
            "SUPER_SECRET_QUERY",
            "SUPER_SECRET_HEADER_TOKEN",
        ):
            self.assertNotIn(secret, raw_text)

        data = json.loads(raw_text)
        self.assertTrue(data["omp"]["available"])
        self.assertEqual(data["omp"]["version"], "omp 18.20.0-mock")
        names = {s["name"] for s in data["skills"]}
        self.assertTrue({"ws-demo", "agents-demo", "user-demo", "nm-demo"}.issubset(names))
        mcp_by_name = {m["name"]: m for m in data["mcpServers"]}
        self.assertEqual(mcp_by_name["local-db"]["transport"], "stdio")
        self.assertEqual(mcp_by_name["local-db"]["envKeys"], ["DB_PASSWORD"])
        self.assertEqual(mcp_by_name["remote-api"]["transport"], "http")
        self.assertEqual(mcp_by_name["remote-api"]["headerKeys"], ["Authorization"])

    def test_omp_resolve_reads_skill_uris_and_blocks_traversal(self):
        responses = self.rpc_lines([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "omp_resolve", "arguments": {"uri": "skill://deepmodebot"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "omp_resolve",
                    "arguments": {"uri": "skill://ws-demo/notes.txt", "cwd": str(self.workspace)},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "omp_resolve",
                    "arguments": {"uri": "skill://ws-demo/../../outside.txt", "cwd": str(self.workspace)},
                },
            },
        ])
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])
        by_id = {r["id"]: r for r in responses}
        self.assertFalse(by_id[1]["result"]["isError"])
        self.assertIn("name: deepmodebot", by_id[1]["result"]["content"][0]["text"])

        self.assertFalse(by_id[2]["result"]["isError"])
        self.assertEqual(by_id[2]["result"]["content"][0]["text"], "extra reference note")

        self.assertTrue(by_id[3]["result"]["isError"])
        self.assertIn("traversal", by_id[3]["result"]["content"][0]["text"])

    def test_omp_run_strips_api_keys_by_default_and_passes_flags(self):
        responses = self.rpc_lines([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "omp_run",
                    "arguments": {
                        "prompt": "Check status",
                        "cwd": str(self.workspace),
                        "role": "smol",
                        "thinking": "medium",
                        "tools": ["read", "grep"],
                        "noSkills": True,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "omp_run",
                    "arguments": {
                        "prompt": "With explicit key opt-in",
                        "cwd": str(self.workspace),
                        "useSubscription": False,
                    },
                },
            },
        ])
        self.assertEqual(sorted(r["id"] for r in responses), [1, 2])
        by_id = {r["id"]: r for r in responses}
        res1 = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertEqual(res1["exitCode"], 0)
        inner1 = json.loads(res1["response"])
        self.assertFalse(inner1["has_anthropic_key"])
        self.assertFalse(inner1["has_anthropic_auth_token"])
        self.assertFalse(inner1["has_openai_key"])
        self.assertFalse(inner1["has_codex_key"])
        self.assertFalse(inner1["has_gemini_key"])
        self.assertFalse(inner1["has_google_key"])
        self.assertFalse(inner1["has_bedrock"])
        self.assertFalse(inner1["has_vertex"])
        self.assertFalse(inner1["has_foundry"])
        self.assertEqual(Path(inner1["tmpdir"]).resolve(), (self.workspace / ".scratch" / "tmp").resolve())
        self.assertIn("--model", inner1["args"])
        self.assertIn("@smol", inner1["args"])
        self.assertIn("--thinking", inner1["args"])
        self.assertIn("medium", inner1["args"])
        self.assertIn("--tools", inner1["args"])
        self.assertIn("read,grep", inner1["args"])
        self.assertIn("--no-skills", inner1["args"])
        self.assertNotIn("Check status", inner1["args"])
        self.assertEqual(inner1["stdin"], "Check status")

        res2 = json.loads(by_id[2]["result"]["content"][0]["text"])
        inner2 = json.loads(res2["response"])
        self.assertTrue(inner2["has_anthropic_key"])
        self.assertTrue(inner2["has_anthropic_auth_token"])
        self.assertTrue(inner2["has_openai_key"])
        self.assertTrue(inner2["has_codex_key"])

    def test_omp_task_enforces_subagent_tool_allowlists_and_preset_defaults(self):
        responses = self.rpc_lines([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "omp_task",
                    "arguments": {
                        "agent": "scout",
                        "task": "Find entrypoints",
                        "context": "Repo uses Node ESM",
                        "cwd": str(self.workspace),
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "omp_task",
                    "arguments": {
                        "agent": "security-reviewer",
                        "task": "Audit auth handlers",
                        "cwd": str(self.workspace),
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "omp_task",
                    "arguments": {
                        "agent": "reviewer",
                        "task": "Review PR diff",
                        "cwd": str(self.workspace),
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "omp_task",
                    "arguments": {
                        "agent": "scout",
                        "task": "Deep dive override",
                        "model": "anthropic/claude-opus-4-6",
                        "thinking": "high",
                        "cwd": str(self.workspace),
                    },
                },
            },
        ])
        self.assertEqual(sorted(r["id"] for r in responses), [1, 2, 3, 4])
        by_id = {r["id"]: r for r in responses}
        scout_out = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertEqual(scout_out["agent"], "scout")
        scout_inner = json.loads(scout_out["findings"])
        tools_idx = scout_inner["args"].index("--tools")
        self.assertEqual(scout_inner["args"][tools_idx + 1], "read,grep,glob,web_search")
        model_idx = scout_inner["args"].index("--model")
        self.assertEqual(scout_inner["args"][model_idx + 1], "@smol")
        think_idx = scout_inner["args"].index("--thinking")
        self.assertEqual(scout_inner["args"][think_idx + 1], "medium")
        self.assertIn("# Context", scout_inner["stdin"])
        self.assertIn("Find entrypoints", scout_inner["stdin"])
        self.assertFalse(scout_inner["has_anthropic_key"])
        self.assertFalse(scout_inner["has_anthropic_auth_token"])

        sec_out = json.loads(by_id[2]["result"]["content"][0]["text"])
        self.assertEqual(sec_out["agent"], "security-reviewer")
        sec_inner = json.loads(sec_out["findings"])
        sec_tools_idx = sec_inner["args"].index("--tools")
        self.assertEqual(sec_inner["args"][sec_tools_idx + 1], "read,grep,glob")

        rev_out = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertEqual(rev_out["agent"], "reviewer")
        rev_inner = json.loads(rev_out["findings"])
        rev_tools_idx = rev_inner["args"].index("--tools")
        self.assertEqual(rev_inner["args"][rev_tools_idx + 1], "read,grep,glob")
        rev_model_idx = rev_inner["args"].index("--model")
        self.assertEqual(rev_inner["args"][rev_model_idx + 1], "@slow")

        override_out = json.loads(by_id[4]["result"]["content"][0]["text"])
        override_inner = json.loads(override_out["findings"])
        ov_model_idx = override_inner["args"].index("--model")
        self.assertEqual(override_inner["args"][ov_model_idx + 1], "anthropic/claude-opus-4-6")
        ov_think_idx = override_inner["args"].index("--thinking")
        self.assertEqual(override_inner["args"][ov_think_idx + 1], "high")

    def test_concurrent_tools_call_dispatch_runs_in_parallel_without_interleaving(self):
        batch = [
            {
                "jsonrpc": "2.0",
                "id": idx,
                "method": "tools/call",
                "params": {
                    "name": "omp_task",
                    "arguments": {
                        "agent": "scout",
                        "task": f"__SLEEP_MS:600__ parallel scout {idx}",
                        "cwd": str(self.workspace),
                    },
                },
            }
            for idx in (1, 2, 3)
        ]
        for runner in (self.rpc_lines, self.rpc_content_length):
            responses = runner(batch)
            self.assertEqual(sorted(r["id"] for r in responses), [1, 2, 3])
            inners = [
                json.loads(json.loads(r["result"]["content"][0]["text"])["findings"])
                for r in responses
            ]
            # All 3 children overlap in flight: latest start occurs strictly before earliest finish.
            max_started = max(item["started"] for item in inners)
            min_finished = min(item["finished"] for item in inners)
            self.assertLess(
                max_started,
                min_finished,
                f"expected concurrent execution overlap, got started={[i['started'] for i in inners]} finished={[i['finished'] for i in inners]}",
            )

    def test_omp_run_timeout_kills_hung_child_and_rejects_invalid_timeout(self):
        import time

        started = time.monotonic()
        responses = self.rpc_lines([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "omp_run",
                    "arguments": {
                        "prompt": "__HANG__ simulate stuck subagent",
                        "cwd": str(self.workspace),
                        "timeoutSeconds": 0.25,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "omp_run",
                    "arguments": {
                        "prompt": "invalid timeout",
                        "cwd": str(self.workspace),
                        "timeoutSeconds": -5,
                    },
                },
            },
        ])
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 15.0, f"timeout kill took too long: {elapsed:.2f}s")
        self.assertEqual(sorted(r["id"] for r in responses), [1, 2])
        by_id = {r["id"]: r for r in responses}

        self.assertTrue(by_id[1]["result"]["isError"])
        timed_out_payload = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertEqual(timed_out_payload["exitCode"], 124)
        self.assertTrue(timed_out_payload["timedOut"])
        self.assertIn("timed out", timed_out_payload["errorMessage"])

        self.assertTrue(by_id[2]["result"]["isError"])
        self.assertIn("timeoutSeconds", by_id[2]["result"]["content"][0]["text"])

    def test_omp_run_delivers_long_special_char_prompt_intact_via_stdin(self):
        tricky = (
            "Line 1: %PATH% %USERPROFILE% & echo INJECTED | cat < /dev/null > out\n"
            "Line 2: \"double quotes\" and 'single quotes' and ^carets^ and !bangs!\n"
            + ("0123456789abcdef" * 600)
        )
        self.assertGreater(len(tricky), 9000)
        responses = self.rpc_lines([{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "omp_run",
                "arguments": {
                    "prompt": tricky,
                    "cwd": str(self.workspace),
                },
            },
        }])
        res = responses[0]["result"]
        self.assertFalse(res.get("isError"), res)
        outer = json.loads(res["content"][0]["text"])
        self.assertEqual(outer["exitCode"], 0)
        inner = json.loads(outer["response"])
        self.assertEqual(inner["stdin"], tricky)
        self.assertFalse(any("INJECTED" in arg or len(arg) > 500 for arg in inner["args"]))


if __name__ == "__main__":
    unittest.main()
