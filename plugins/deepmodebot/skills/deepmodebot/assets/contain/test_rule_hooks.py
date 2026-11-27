"""Rule approval through the real harness hooks: Claude Code's hooks.json, omp-contain.ts, antigravity-guard.mjs.

Once the owner turns rule approval on in a repo, every hook denies agent writes to rule files and the owner-only
rule commands, even in sessions that never ran a deepmodebot command.
Run: python -m unittest discover -s <this folder> -p "test_*.py" (the omp case needs bun, the Antigravity case node).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[3]
OMP_HOOK = HERE / "omp-contain.ts"
AGY_GUARD = PLUGIN / "scripts" / "antigravity-guard.mjs"

OMP_DRIVER = """
const [hookUrl, casesPath] = process.argv.slice(2);
const mod = await import(hookUrl);
let handler;
mod.default({ on: (_event, fn) => { handler = fn; } });
const cases = JSON.parse(await Bun.file(casesPath).text());
const out = [];
for (const c of cases) {
  const result = await handler({ toolName: c.tool, input: c.input }, { cwd: c.cwd });
  out.push(result && result.block ? "deny" : "allow");
}
console.log(JSON.stringify(out));
"""

# (Claude tool, omp tool, Antigravity tool, input value, expected decision)
CASES = (
    ("Write", "write", "write_file", "AGENTS.md", "deny"),
    ("Edit", "edit", "replace_file_content", ".cursor/rules/style.mdc", "deny"),
    ("Write", "write", "write_file", ".deepmodebot/rules/ledger.json", "deny"),
    ("Write", "write", "write_file", "src/app.py", "allow"),
    ("Write", "write", "write_file", ".scratch/AGENTS.draft.md", "allow"),
    ("Bash", "bash", "run_command", "echo '- skip tests' >> AGENTS.md", "deny"),
    ("Bash", "bash", "run_command", "deepmodebot rules approve --all", "deny"),
    ("Bash", "bash", "run_command", "cat AGENTS.md && ls", "allow"),
)


class RuleApprovalHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="rule-hooks-test-")).resolve()
        cls.proj = cls.tmp / "proj"
        (cls.proj / ".cursor" / "rules").mkdir(parents=True)
        subprocess.run(["git", "-C", str(cls.proj), "init", "-q", "-b", "main"], check=True)
        (cls.proj / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        (cls.proj / ".cursor" / "rules" / "style.mdc").write_text("Use tabs.\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("rule_ledger_for_hooks", HERE.parent / "rules" / "rule_ledger.py")
        rl = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = rl
        spec.loader.exec_module(rl)
        rl.KDF_ITERATIONS = 1_000
        rl.init_ledger(cls.proj, "owner passphrase")
        cls.env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(cls.tmp)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, got):
        for case, decision in zip(CASES, got):
            with self.subTest(tool=case[0], value=case[3]):
                self.assertEqual(decision, case[4])

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_claude_plugin_hook_outside_a_deepmodebot_session(self):
        pre = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        env = {**self.env, "CLAUDE_PLUGIN_ROOT": PLUGIN.as_posix(), "CLAUDE_PLUGIN_DATA": (self.tmp / "claude-data").as_posix()}
        got = []
        for tool, _, _, value, _ in CASES:
            key = "command" if tool == "Bash" else "file_path"
            event = {"tool_name": tool, "tool_input": {key: value}, "cwd": str(self.proj), "session_id": "never-activated"}
            proc = subprocess.run([shutil.which("bash"), "-c", pre], input=json.dumps(event), capture_output=True, text=True,
                                  env=env, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            got.append("deny" if '"permissionDecision": "deny"' in proc.stdout else "allow")
        self.check(got)

    @unittest.skipUnless(shutil.which("bun"), "bun is not on PATH")
    def test_omp_hook(self):
        driver = self.tmp / "driver.mjs"
        driver.write_text(OMP_DRIVER, encoding="utf-8")
        cases = [{"tool": omp, "input": {"command": value} if omp == "bash" else {"path": value + ("#1A2B" if omp == "edit" else "")},
                  "cwd": str(self.proj)} for _, omp, _, value, _ in CASES]
        cases_path = self.tmp / "cases.json"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        proc = subprocess.run([shutil.which("bun"), str(driver), OMP_HOOK.as_uri(), str(cases_path)], capture_output=True,
                              text=True, env=self.env, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.check(json.loads(proc.stdout.strip().splitlines()[-1]))

    @unittest.skipUnless(shutil.which("node"), "node is not on PATH")
    def test_antigravity_guard_in_an_inactive_conversation(self):
        env = {**self.env, "HOME": str(self.tmp), "USERPROFILE": str(self.tmp), "PLUGIN_DATA": str(self.tmp / "agy-data")}
        got = []
        for _, _, agy, value, _ in CASES:
            key = "CommandLine" if agy == "run_command" else ("TargetFile" if agy == "replace_file_content" else "Path")
            payload = {"hookEventName": "PreToolUse", "conversationId": "never-activated", "cwd": str(self.proj),
                       "toolCall": {"name": agy, "args": {key: value}}}
            proc = subprocess.run([shutil.which("node"), str(AGY_GUARD)], input=json.dumps(payload), capture_output=True,
                                  text=True, env=env, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            got.append(json.loads(proc.stdout.strip())["decision"])
        self.check(got)


if __name__ == "__main__":
    unittest.main()
