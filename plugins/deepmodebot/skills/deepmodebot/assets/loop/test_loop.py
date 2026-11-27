"""Tests for loop.py, driven through a fake `omp` on PATH.

Run: python -m unittest discover -s <this folder> -p "test_*.py"
Needs git and bash (Git for Windows ships both).
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LOOP = Path(__file__).resolve().parent / "loop.py"

FAKE = """
import json, os, re, subprocess, sys, time
action = os.environ.get("FAKE_ACTION", "noop")
record = os.environ.get("FAKE_RECORD")
prompt = sys.stdin.read()
if record:
    with open(record, "w", encoding="utf-8") as handle:
        json.dump({"env": dict(os.environ), "argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": prompt}, handle)
if action == "hang":
    time.sleep(120)
elif action == "forge-cache":
    os.makedirs("tests/__pycache__", exist_ok=True)
    open("tests/__pycache__/test_x.cpython-313.pyc", "w").close()
if action == "done":
    open("ok.txt", "w").close()
elif action == "progress":
    with open("progress.txt", "a") as handle:
        handle.write("x")
elif action == "tamper-goal":
    text = open("goals/g.md", encoding="utf-8").read()
    open("goals/g.md", "w", encoding="utf-8").write(text.replace("max_iterations: ", "max_iterations: 9"))
elif action == "tamper-protect":
    with open("check.sh", "a") as handle:
        handle.write("exit 0\\n")
elif action == "create-conftest":
    open("conftest.py", "w").close()
elif action == "diagnostic-repair":
    log_path = next(line.removeprefix("Complete check output: ") for line in prompt.splitlines()
                    if line.startswith("Complete check output: "))
    diagnostic = open(log_path, encoding="utf-8").read()
    missing = re.search(r"missing output artifact: ([a-z.-]+)", diagnostic)
    if missing:
        open(missing.group(1), "w").close()
elif action in ("revise-plan", "adapt"):
    path = "goals/g.md"
    text = open(path, encoding="utf-8").read()
    if action == "adapt" and "Next action: create the missing output." in prompt and "missing output artifact" in prompt:
        open("ok.txt", "w").close()
    else:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\\nObserved missing output. Next action: create the missing output.\\n")
elif action == "fast-then-check":
    if not os.path.exists("step1.txt"):
        open("step1.txt", "w").close()
    elif "[fast_check failed]" in prompt and not os.path.exists("fast_ok.txt"):
        open("fast_ok.txt", "w").close()
    elif os.path.exists("fast_ok.txt"):
        open("ok.txt", "w").close()
elif action == "slop-then-clean":
    with open("legacy.py", "r+", encoding="utf-8") as handle:
        old = handle.read()
        handle.seek(0)
        handle.write("HEADER = '# type: ignore in string literal'\\n" + old)
    if "[slop_guard failed]" in prompt:
        open("app.py", "w", encoding="utf-8").write(
            "def parse_num(raw: str) -> int:\\n    return int(raw.strip())\\n"
        )
        open("client.ts", "w", encoding="utf-8").write(
            "const note = '@ts-ignore inside string literal';\\nexport function load(): string { return note; }\\n"
        )
        open("ok.txt", "w").close()
    else:
        open("app.py", "w", encoding="utf-8").write(
            "def parse_num(raw: str) -> int:\\n"
            "    try:\\n        return raw  # type: ignore\\n"
            "    except Exception:\\n        pass\\n    return 0\\n"
        )
        open("client.ts", "w", encoding="utf-8").write(
            "// @ts-ignore\\nexport function load() { try { work(); } catch (e) {} }\\n"
        )
        open("ok.txt", "w").close()
elif action == "weaken-ruff-toml":
    open("ruff.toml", "w", encoding="utf-8").write("line-length = 999\\n")
elif action == "weaken-pyproject-ruff":
    text = open("pyproject.toml", encoding="utf-8").read()
    open("pyproject.toml", "w", encoding="utf-8").write(text.replace('select = ["E", "F"]', 'select = []'))
elif action == "edit-pyproject-deps":
    text = open("pyproject.toml", encoding="utf-8").read()
    open("pyproject.toml", "w", encoding="utf-8").write(text.replace("dependencies = []", 'dependencies = ["httpx"]'))
    open("ok.txt", "w").close()
elif action == "revert-pilot":
    if "Plan after revert: create ok.txt cleanly." in prompt:
        open("ok.txt", "w").close()
    else:
        open("tracked.txt", "w", encoding="utf-8").write("broken edit\\n")
        open("dead_end.py", "w", encoding="utf-8").write("BROKEN = True\\n")
        with open("goals/g.md", "a", encoding="utf-8") as handle:
            handle.write("\\nPlan after revert: create ok.txt cleanly.\\n")
elif action == "repeat-broken-edit":
    open("tracked.txt", "w", encoding="utf-8").write("same broken edit\\n")
elif action == "stubs-then-real":
    open("base.py", "w", encoding="utf-8").write(
        "from abc import ABC, abstractmethod\\n"
        "class Store(ABC):\\n"
        "    @abstractmethod\\n"
        "    def save(self, value: str) -> None:\\n"
        "        raise NotImplementedError\\n"
    )
    if "[slop_guard failed]" in prompt:
        open("service.py", "w", encoding="utf-8").write(
            "def export_csv(rows: list[str]) -> str:\\n    return '\\n'.join(rows)\\n"
        )
        open("ui.ts", "w", encoding="utf-8").write(
            "const msg = 'not implemented inside string literal';\\nexport function render(): string { return msg; }\\n"
        )
        open("ok.txt", "w").close()
    else:
        open("service.py", "w", encoding="utf-8").write(
            "# TODO: wire CSV export\\n"
            "def export_csv(rows: list[str]) -> str:\\n"
            "    raise NotImplementedError('stub')\\n"
        )
        open("ui.ts", "w", encoding="utf-8").write(
            "// FIXME: finish view\\nexport function render(): string { throw new Error('not implemented'); }\\n"
        )
        open("ok.txt", "w").close()
elif action == "tamper-manifest":
    open("goals/manifest.json", "w", encoding="utf-8").write('{"product": "x", "slices": []}\\n')
elif action == "manifest-stepwise":
    if not os.path.exists("s1.txt"):
        open("s1.txt", "w").close()
    elif "[manifest 1/3 slices green]" in prompt and not os.path.exists("s2.txt"):
        open("s2.txt", "w").close()
    elif "[manifest 2/3 slices green]" in prompt and not os.path.exists("s3.txt"):
        open("s3.txt", "w").close()
        open("ok.txt", "w").close()
elif action == "stage-and-commit":
    open("tracked.txt", "w", encoding="utf-8").write("committed broken edit\\n")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam", "agent"], check=True)
    open("staged_new.py", "w", encoding="utf-8").write("X = 1\\n")
    subprocess.run(["git", "add", "staged_new.py"], check=True)
elif action == "link-escape":
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", "escape", os.environ["FAKE_OUTSIDE"]], check=True, capture_output=True)
    else:
        os.symlink(os.environ["FAKE_OUTSIDE"], "escape")
elif action == "create-nested-conftest":
    os.makedirs("src", exist_ok=True)
    open("src/conftest.py", "w", encoding="utf-8").write("collect_ignore_glob = ['*']\\n")
elif action == "weaken-package-lint":
    data = json.load(open("package.json", encoding="utf-8"))
    data["scripts"]["lint"] = "true"
    json.dump(data, open("package.json", "w", encoding="utf-8"))
elif action == "rate-limit-then-done":
    marker = "rate_limit_attempts.txt"
    count = int(open(marker).read()) if os.path.exists(marker) else 0
    with open(marker, "w") as handle:
        handle.write(str(count + 1))
    if count == 0:
        print("HTTP 429 rate limit exceeded; Retry-After: 0.01", file=sys.stderr)
        sys.exit(1)
    open("ok.txt", "w").close()
elif action == "quota-exhausted":
    print("Error: weekly limit reached for current plan", file=sys.stderr)
    sys.exit(1)
elif action == "escalate-on-strong-model":
    if "strong-model" in sys.argv:
        open("ok.txt", "w").close()
elif action == "quota-then-fallback":
    if "fallback-model" in sys.argv:
        open("ok.txt", "w").close()
    else:
        print("Error: weekly limit reached for current plan", file=sys.stderr)
        sys.exit(1)
elif action == "rate-limit-then-fallback":
    if "fallback-model" in sys.argv:
        open("ok.txt", "w").close()
    else:
        print("HTTP 429 rate limit exceeded; Retry-After: 0.01", file=sys.stderr)
        sys.exit(1)
elif action == "sprint1-done":
    open("s1.txt", "w").close()
    open("ok.txt", "w").close()
elif action == "sprint2-done":
    open("s2.txt", "w").close()
    open("ok.txt", "w").close()
if action == "fail":
    sys.exit(3)
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


def remove_tree(path):
    """git marks its object files read-only, which stops shutil.rmtree on Windows and leaves the folder behind."""
    for folder, _, files in os.walk(path):
        for name in files:
            os.chmod(os.path.join(folder, name), stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(path, ignore_errors=True)


class LoopCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="loop-test-")).resolve()
        self.addCleanup(remove_tree, self.tmp)
        self.repo = self.tmp / "proj"
        (self.repo / "goals").mkdir(parents=True)
        (self.repo / "check.sh").write_text("test -f ok.txt\n", encoding="utf-8", newline="\n")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "fake.py").write_text(FAKE, encoding="utf-8")
        if os.name == "nt":
            (bin_dir / "omp.cmd").write_text(f'@"{sys.executable}" "%~dp0fake.py" %*\r\n', encoding="utf-8")
        else:
            wrapper = bin_dir / "omp"
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake.py" "$@"\n', encoding="utf-8")
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.path = str(bin_dir) + os.pathsep + os.environ["PATH"]

    def goal(self, **fields):
        merged = {"goal": "ok.txt exists", "check": "sh ./check.sh", "protect": "check.sh", "max_iterations": 3, "max_cost_usd": 1, **fields}
        body = "".join(f"{key}: {value}\n" for key, value in merged.items() if value is not None)
        (self.repo / "goals" / "g.md").write_text(f"---\n{body}---\nCreate ok.txt.\n", encoding="utf-8", newline="\n")

    def loop(self, *args, action="noop", **env):
        full_env = {**os.environ, "PATH": self.path, "FAKE_ACTION": action, **env}
        return subprocess.run([sys.executable, str(LOOP), *args], cwd=self.repo, env=full_env, capture_output=True, text=True)

    def trail_rows(self):
        trail = self.repo / ".scratch" / "goals" / "g" / "trail.tsv"
        return trail.read_text(encoding="utf-8").strip().splitlines()[1:]

    def latest_summary(self):
        logs = self.repo / ".scratch" / "goals" / "g"
        latest = logs / "latest-summary.json"
        data = json.loads(latest.read_text(encoding="utf-8"))
        run_summary = logs / f"{data['run_id']}-summary.json"
        self.assertTrue(run_summary.is_file())
        self.assertEqual(json.loads(run_summary.read_text(encoding="utf-8")), data)
        return data

    def test_stops_with_0_when_the_check_passes(self):
        self.goal()
        run = self.loop("run", "goals/g.md", action="done")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("goal met", run.stdout)
        self.assertEqual(len(self.trail_rows()), 1)

    def test_nothing_runs_when_the_check_already_passes(self):
        self.goal()
        (self.repo / "ok.txt").write_text("", encoding="utf-8")
        run = self.loop("run", "goals/g.md", action="fail")
        self.assertEqual(run.returncode, 0)
        self.assertIn("already passes", run.stdout)
        summary = self.latest_summary()
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["exit_reason"], "already_passed")
        self.assertEqual(summary["iterations_run"], 0)

    def test_already_passing_sprint_run_writes_latest_summary_with_scope(self):
        manifest = {
            "product": "Already Passing Sprint",
            "slices": [
                {"id": "s1", "title": "Core", "sprint": 1, "check": "test -f s1.txt"},
                {"id": "s2", "title": "Later", "sprint": 2, "check": "test -f s2.txt"},
            ],
        }
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (self.repo / "s1.txt").write_text("", encoding="utf-8")
        (self.repo / "ok.txt").write_text("", encoding="utf-8")
        self.goal(manifest="goals/manifest.json", active_sprint=1)
        run = self.loop("run", "goals/g.md", action="fail")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("sprint 1 check already passes", run.stdout)
        summary = self.latest_summary()
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["exit_reason"], "sprint_already_passed")
        self.assertEqual(summary["iterations_run"], 0)
        self.assertEqual(summary["scope"]["active_sprint"], 1)
        self.assertEqual(summary["scope"]["passed_slices"], 1)
        self.assertEqual(summary["scope"]["deferred_slices"], ["s2"])

    def test_iteration_cap_exits_2(self):
        self.goal(max_iterations=2, stall_after=9)
        run = self.loop("run", "goals/g.md", action="progress")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertEqual(len(self.trail_rows()), 2)

    def test_no_progress_exits_3_as_stalled(self):
        self.goal(max_iterations=5, stall_after=2)
        run = self.loop("run", "goals/g.md", action="noop")
        self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
        self.assertEqual(len(self.trail_rows()), 2)

    def test_revised_plan_and_check_feedback_drive_the_next_iteration(self):
        (self.repo / "check.sh").write_text(
            "test -f ok.txt || { echo 'missing output artifact'; exit 1; }\n", encoding="utf-8")
        self.goal()
        run = self.loop("run", "goals/g.md", action="adapt")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(len(self.trail_rows()), 2)
        logs = self.repo / ".scratch" / "goals" / "g"
        first = next(logs.glob("*-iteration-1-prompt.txt")).read_text(encoding="utf-8")
        second = next(logs.glob("*-iteration-2-prompt.txt")).read_text(encoding="utf-8")
        self.assertNotIn("Next action: create the missing output.", first)
        self.assertIn("Next action: create the missing output.", second)
        self.assertIn("missing output artifact", second)
        self.assertTrue((self.repo / "ok.txt").exists())

    def test_complete_check_evidence_survives_bounded_prompt_feedback(self):
        diagnostic = "early failure\n" + "head noise\n" * 250 + "middle evidence\n" + "tail noise\n" * 250 + "final failure\n"
        (self.repo / "check.sh").write_text(
            "cat <<'DIAGNOSTIC'\n" + diagnostic + "DIAGNOSTIC\nexit 1\n", encoding="utf-8", newline="\n")
        self.goal(max_iterations=1)
        record = self.tmp / "seen.json"
        run = self.loop("run", "goals/g.md", FAKE_RECORD=str(record))
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        logs = self.repo / ".scratch" / "goals" / "g"
        input_log = next(logs.glob("*-iteration-1-input-check.log"))
        output_log = next(logs.glob("*-iteration-1-check.log"))
        self.assertEqual(input_log.read_text(encoding="utf-8"), "exit: 1\n" + diagnostic)
        self.assertEqual(output_log.read_text(encoding="utf-8"), "exit: 1\n" + diagnostic)
        prompt = next(logs.glob("*-iteration-1-prompt.txt")).read_text(encoding="utf-8")
        self.assertEqual(prompt, json.loads(record.read_text(encoding="utf-8"))["stdin"])
        feedback = prompt.split("<check-output>\n", 1)[1].split("\n</check-output>", 1)[0]
        head, tail = feedback.split("\n[check output truncated; middle omitted]\n")
        self.assertEqual(head, diagnostic[:2000])
        self.assertEqual(tail, diagnostic[-2000:])
        self.assertNotIn("middle evidence", feedback)
        log_path = next(line.removeprefix("Complete check output: ") for line in prompt.splitlines()
                        if line.startswith("Complete check output: "))
        self.assertEqual((self.repo / log_path).resolve(), input_log.resolve())

    def test_full_diagnostics_direct_repair_despite_noisy_trailing_output(self):
        diagnostic = "startup noise\n" * 250 + "missing output artifact: repaired.txt\n" + "trailing noise\n" * 400
        (self.repo / "check.sh").write_text(
            "test -f repaired.txt && exit 0\ncat <<'DIAGNOSTIC'\n" + diagnostic + "DIAGNOSTIC\nexit 1\n",
            encoding="utf-8", newline="\n")
        self.goal(max_iterations=1)
        run = self.loop("run", "goals/g.md", action="diagnostic-repair")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("goal met", run.stdout)
        self.assertTrue((self.repo / "repaired.txt").exists())
        self.assertEqual(len(self.trail_rows()), 1)
        prompt = next((self.repo / ".scratch" / "goals" / "g").glob("*-prompt.txt")).read_text(encoding="utf-8")
        self.assertNotIn("missing output artifact: repaired.txt", prompt)

    def test_plan_only_revisions_do_not_avoid_the_stall_stop(self):
        self.goal(max_iterations=5, stall_after=2)
        run = self.loop("run", "goals/g.md", action="revise-plan")
        self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
        self.assertEqual(len(self.trail_rows()), 2)
        self.assertFalse((self.repo / "ok.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Windows paths are case-insensitive")
    def test_case_aliased_goal_plan_edits_still_stall(self):
        self.goal(max_iterations=3, stall_after=1)
        run = self.loop("run", "GOALS/G.MD", action="revise-plan")
        self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
        trail = self.repo / ".scratch" / "goals" / "G" / "trail.tsv"
        self.assertEqual(len(trail.read_text(encoding="utf-8").strip().splitlines()), 2)
        self.assertFalse((self.repo / "ok.txt").exists())

    def test_editing_the_goal_or_a_protected_file_exits_4(self):
        for action in ("tamper-goal", "tamper-protect"):
            with self.subTest(action=action):
                self.goal()
                git(self.repo, "checkout", "-q", "--", "check.sh")
                run = self.loop("run", "goals/g.md", action=action)
                self.assertEqual(run.returncode, 4, run.stdout + run.stderr)

    def test_a_failing_harness_exits_5(self):
        self.goal()
        run = self.loop("run", "goals/g.md", action="fail")
        self.assertEqual(run.returncode, 5, run.stdout + run.stderr)

    def test_creating_a_path_declared_absent_exits_4(self):
        self.goal(protect="check.sh absent:conftest.py")
        check = self.loop("check", "goals/g.md")
        self.assertIn("absent, must stay absent: conftest.py", check.stdout)
        run = self.loop("run", "goals/g.md", action="create-conftest")
        self.assertEqual(run.returncode, 4, run.stdout + run.stderr)
        self.assertIn("conftest.py", run.stdout)

    def test_a_protect_typo_is_an_error_not_a_silently_absent_path(self):
        self.goal(protect="chekc.sh")
        run = self.loop("run", "goals/g.md", action="done")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("does not exist", run.stdout + run.stderr)
        self.goal(protect="absent:check.sh")
        run = self.loop("check", "goals/g.md")
        self.assertIn("exists; drop its `absent:` prefix", run.stdout + run.stderr)

    def test_goal_files_need_protect_and_a_cost_cap(self):
        self.goal(protect=None)
        run = self.loop("check", "goals/g.md")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("protect", run.stdout + run.stderr)
        self.goal(max_cost_usd=None)
        run = self.loop("run", "goals/g.md")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("max_cost_usd", run.stdout + run.stderr)

    def test_nonfinite_cost_caps_are_rejected_before_harness_execution(self):
        record = self.tmp / "seen.json"
        for harness in ("omp", "claude"):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(harness=harness, value=value):
                    self.goal(harness=harness, max_cost_usd=value)
                    run = self.loop("run", "goals/g.md", action="done", FAKE_RECORD=str(record))
                    self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
                    self.assertIn("max_cost_usd must be a positive number", run.stdout + run.stderr)
                    self.assertFalse(record.exists())
                    self.assertFalse((self.repo / "ok.txt").exists())
                    self.assertFalse((self.repo / ".scratch").exists())

    def test_check_reports_without_running_the_harness(self):
        self.goal()
        run = self.loop("check", "goals/g.md", action="done")
        self.assertEqual(run.returncode, 0)
        self.assertIn("check exit 1", run.stdout)
        self.assertFalse((self.repo / "ok.txt").exists())

    def test_dry_run_prints_the_command_and_touches_nothing(self):
        self.goal()
        run = self.loop("run", "goals/g.md", "--dry-run", action="done")
        self.assertEqual(run.returncode, 0)
        self.assertIn("--max-cost", run.stdout)
        self.assertFalse((self.repo / "ok.txt").exists())
        self.assertFalse((self.repo / ".scratch").exists())

    def test_the_harness_runs_in_the_root_without_api_keys_and_with_in_repo_temp(self):
        self.goal()
        record = self.tmp / "record.json"
        run = self.loop("run", "goals/g.md", action="done", FAKE_RECORD=str(record),
                        ANTHROPIC_API_KEY="k", OPENAI_API_KEY="k", CODEX_API_KEY="k")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        seen = json.loads(record.read_text(encoding="utf-8"))
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
            self.assertNotIn(key, seen["env"])
        self.assertEqual(Path(seen["cwd"]).resolve(), self.repo)
        self.assertEqual(Path(seen["env"]["TMPDIR"]).resolve(), self.repo / ".scratch" / "tmp")
        self.assertIn("--max-cost", seen["argv"])

    def test_the_prompt_travels_on_stdin_not_in_the_command(self):
        # On Windows the harness is a .cmd shim: cmd.exe would run `& echo INJECTED` if the prompt were an argument.
        self.goal(check='sh ./check.sh || { echo "a" & echo INJECTED >/dev/null; false; }', max_iterations=1)
        record = self.tmp / "seen.json"
        run = self.loop("run", "goals/g.md", FAKE_RECORD=str(record))
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        seen = json.loads(record.read_text(encoding="utf-8"))
        self.assertIn("echo INJECTED", seen["stdin"])
        self.assertIn("goals/g.md", seen["stdin"])
        self.assertFalse([arg for arg in seen["argv"] if "INJECTED" in arg or "goals/g.md" in arg])

    def test_a_hung_harness_is_stopped_and_exits_5(self):
        self.goal(iteration_minutes=0.03)
        run = self.loop("run", "goals/g.md", action="hang")
        self.assertEqual(run.returncode, 5, run.stdout + run.stderr)
        self.assertIn("ran past 0.03 minutes", run.stdout)

    def test_a_hung_check_stops_the_run_before_any_harness_call(self):
        self.goal(check="sleep 120", check_minutes=0.02, protect="none")
        record = self.tmp / "seen.json"
        run = self.loop("run", "goals/g.md", FAKE_RECORD=str(record))
        self.assertEqual(run.returncode, 5, run.stdout + run.stderr)
        self.assertIn("check ran past 0.02 minutes", run.stdout)
        self.assertFalse(record.exists())

    def test_a_check_that_exits_124_is_a_failing_check_not_a_timeout(self):
        self.goal(check="exit 124", protect="none", max_iterations=1)
        run = self.loop("run", "goals/g.md")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)

    def test_time_limits_must_be_finite(self):
        for value in ("inf", "nan", "0", "-1", "soon"):
            with self.subTest(value=value):
                self.goal(check_minutes=value)
                run = self.loop("check", "goals/g.md")
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("check_minutes must be a positive number", run.stdout + run.stderr)

    def test_caches_under_protected_paths_are_cleared_before_the_check(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_x.py").write_text("", encoding="utf-8")
        self.goal(protect="check.sh tests", max_iterations=1)
        run = self.loop("run", "goals/g.md", action="forge-cache")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertFalse((self.repo / "tests" / "__pycache__").exists())

    def test_caches_beside_a_protected_file_are_cleared_too(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_x.py").write_text("", encoding="utf-8")
        self.goal(protect="check.sh tests/test_x.py", max_iterations=1)
        run = self.loop("run", "goals/g.md", action="forge-cache")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertFalse((self.repo / "tests" / "__pycache__").exists())

    def test_audit_reports_layers_gaps_and_scaffolds_a_goal_contract(self):
        initial = self.loop("audit", "--json")
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        report = json.loads(initial.stdout)
        self.assertFalse(report["ready"])
        self.assertGreaterEqual(len(report["gaps"]), 2)
        strict_fail = self.loop("audit", "--strict")
        self.assertEqual(strict_fail.returncode, 1)

        (self.repo / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text(
            "[tool.mypy]\nstrict = true\n[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
            encoding="utf-8",
        )
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
        (self.repo / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
        (self.repo / ".omp" / "skills" / "verify-demo").mkdir(parents=True)
        (self.repo / ".omp" / "skills" / "verify-demo" / "SKILL.md").write_text("---\nname: verify-demo\n---\n", encoding="utf-8")

        ready = self.loop("audit", "--json", "--strict", "--write-goal", "goals/scaffold.md")
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
        ready_report = json.loads(ready.stdout)
        self.assertTrue(ready_report["ready"])
        self.assertEqual(ready_report["gaps"], [])
        self.assertIn("ruff check .", ready_report["layers"]["static_checks"])
        self.assertIn("mypy .", ready_report["layers"]["static_checks"])
        self.assertEqual(ready_report["layers"]["test_checks"], ["pytest"])
        self.assertEqual(ready_report["layers"]["runtime_verify"], [".omp/skills/verify-demo"])
        scaffold = (self.repo / "goals" / "scaffold.md").read_text(encoding="utf-8")
        self.assertIn("fast_check: ruff check . && mypy .", scaffold)
        self.assertIn("check: pytest", scaffold)
        self.assertIn("ruff.toml", scaffold)

        dup = self.loop("audit", "--write-goal", "goals/scaffold.md")
        self.assertNotEqual(dup.returncode, 0)
        outside = self.loop("audit", "--write-goal", str(self.tmp / "outside.md"))
        self.assertNotEqual(outside.returncode, 0)

    def test_fast_check_short_circuits_before_slow_acceptance_check(self):
        (self.repo / "fast.sh").write_text(
            "test -f fast_ok.txt || { echo 'typecheck error: bad return'; exit 1; }\n",
            encoding="utf-8", newline="\n",
        )
        (self.repo / "check.sh").write_text(
            "echo ran >> check_runs.txt\ntest -f ok.txt\n",
            encoding="utf-8", newline="\n",
        )
        self.goal(fast_check="sh ./fast.sh", protect="fast.sh check.sh", max_iterations=4)
        run = self.loop("run", "goals/g.md", action="fast-then-check")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].endswith("\tfast_check"), rows)
        self.assertTrue(rows[1].endswith("\tcheck"), rows)
        self.assertTrue(rows[2].endswith("\tpass"), rows)
        self.assertEqual(len((self.repo / "check_runs.txt").read_text(encoding="utf-8").splitlines()), 2)

    def test_forbid_slop_blocks_newly_added_suppressions_and_swallowed_exceptions_until_cleaned(self):
        (self.repo / "legacy.py").write_text("import sys  # noqa: E402\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "legacy.py")
        git(self.repo, "commit", "-q", "-m", "legacy")
        self.goal(max_iterations=3)
        run = self.loop("run", "goals/g.md", action="slop-then-clean")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].endswith("\tslop_guard"), rows)
        self.assertTrue(rows[1].endswith("\tpass"), rows)
        second_prompt = next((self.repo / ".scratch" / "goals" / "g").glob("*-iteration-2-prompt.txt")).read_text(encoding="utf-8")
        self.assertIn("[slop_guard failed]", second_prompt)
        self.assertIn("app.py:3: [suppression-comment]", second_prompt)
        self.assertIn("app.py:4: [swallowed-exception]", second_prompt)
        self.assertIn("client.ts:1: [suppression-comment]", second_prompt)
        self.assertIn("client.ts:2: [swallowed-exception]", second_prompt)
        self.assertNotIn("legacy.py", second_prompt)

    def test_forbid_slop_can_be_disabled_explicitly(self):
        (self.repo / "legacy.py").write_text("x = 1\n", encoding="utf-8")
        self.goal(forbid_slop="false", max_iterations=2)
        run = self.loop("run", "goals/g.md", action="slop-then-clean")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(len(self.trail_rows()), 1)

    def test_protect_configs_guards_linter_configs_and_pyproject_tool_tables(self):
        (self.repo / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = []\n\n[tool.ruff]\nselect = ["E", "F"]\n',
            encoding="utf-8",
        )
        git(self.repo, "add", "ruff.toml", "pyproject.toml")
        git(self.repo, "commit", "-q", "-m", "configs")

        self.goal()
        tamper_cfg = self.loop("run", "goals/g.md", action="weaken-ruff-toml")
        self.assertEqual(tamper_cfg.returncode, 4, tamper_cfg.stdout + tamper_cfg.stderr)
        self.assertIn("ruff.toml", tamper_cfg.stdout)
        git(self.repo, "checkout", "-q", "--", "ruff.toml")

        self.goal()
        tamper_py = self.loop("run", "goals/g.md", action="weaken-pyproject-ruff")
        self.assertEqual(tamper_py.returncode, 4, tamper_py.stdout + tamper_py.stderr)
        self.assertIn("pyproject.toml", tamper_py.stdout)
        git(self.repo, "checkout", "-q", "--", "pyproject.toml")

        self.goal()
        allow_deps = self.loop("run", "goals/g.md", action="edit-pyproject-deps")
        self.assertEqual(allow_deps.returncode, 0, allow_deps.stdout + allow_deps.stderr)
        self.assertIn('"httpx"', (self.repo / "pyproject.toml").read_text(encoding="utf-8"))
        (self.repo / "ok.txt").unlink()
        git(self.repo, "checkout", "-q", "--", "pyproject.toml")

        self.goal(protect_configs="false", max_iterations=1)
        opt_out = self.loop("run", "goals/g.md", action="weaken-ruff-toml")
        self.assertEqual(opt_out.returncode, 2, opt_out.stdout + opt_out.stderr)

    def test_revert_on_fail_resets_failed_edits_keeps_plan_and_stalls_on_identical_repeats(self):
        (self.repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
        git(self.repo, "add", "tracked.txt")
        git(self.repo, "commit", "-q", "-m", "tracked")

        (self.repo / "dirty.txt").write_text("user work\n", encoding="utf-8")
        self.goal(revert_on_fail="true")
        refused = self.loop("run", "goals/g.md", action="done")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("clean working tree", refused.stdout + refused.stderr)
        self.assertTrue((self.repo / "dirty.txt").exists())
        (self.repo / "dirty.txt").unlink()

        self.goal(revert_on_fail="true", max_iterations=3)
        recovered = self.loop("run", "goals/g.md", action="revert-pilot")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(len(self.trail_rows()), 2)
        self.assertEqual((self.repo / "tracked.txt").read_text(encoding="utf-8"), "clean\n")
        self.assertFalse((self.repo / "dead_end.py").exists())
        self.assertTrue((self.repo / "ok.txt").exists())
        (self.repo / "ok.txt").unlink()
        shutil.rmtree(self.repo / ".scratch" / "goals" / "g")

        self.goal(revert_on_fail="true", max_iterations=5, stall_after=2)
        stalled = self.loop("run", "goals/g.md", action="repeat-broken-edit")
        self.assertEqual(stalled.returncode, 3, stalled.stdout + stalled.stderr)
        self.assertEqual(len(self.trail_rows()), 3)
        self.assertEqual((self.repo / "tracked.txt").read_text(encoding="utf-8"), "clean\n")

    def test_stub_placeholders_block_todos_and_not_implemented_while_allowing_abstract_methods(self):
        self.goal(max_iterations=3)
        run = self.loop("run", "goals/g.md", action="stubs-then-real")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].endswith("\tslop_guard"), rows)
        self.assertTrue(rows[1].endswith("\tpass"), rows)
        second_prompt = next((self.repo / ".scratch" / "goals" / "g").glob("*-iteration-2-prompt.txt")).read_text(encoding="utf-8")
        self.assertNotIn("base.py", second_prompt)
        self.assertIn("service.py:1: [stub-placeholder]", second_prompt)
        self.assertIn("service.py:3: [stub-placeholder]", second_prompt)
        self.assertIn("ui.ts:1: [stub-placeholder]", second_prompt)
        self.assertIn("ui.ts:2: [stub-placeholder]", second_prompt)

    def test_manifest_drives_all_slices_to_completion_and_auto_protects_manifest_file(self):
        manifest = {
            "product": "Complete three-slice CLI",
            "slices": [
                {"id": "slice-1", "title": "Storage layer", "check": "test -f s1.txt"},
                {"id": "slice-2", "title": "Command layer", "check": "test -f s2.txt"},
                {"id": "slice-3", "title": "End-to-end persistence", "check": "test -f s3.txt"},
            ],
        }
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        initial = self.loop("manifest", "goals/manifest.json", "--json")
        self.assertEqual(initial.returncode, 1)
        summary = json.loads(initial.stdout)
        self.assertEqual((summary["passed"], summary["total"], summary["ready"]), (0, 3, False))

        self.goal(manifest="goals/manifest.json", max_iterations=5)
        tamper = self.loop("run", "goals/g.md", action="tamper-manifest")
        self.assertEqual(tamper.returncode, 4, tamper.stdout + tamper.stderr)
        self.assertIn("goals/manifest.json", tamper.stdout)
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        shutil.rmtree(self.repo / ".scratch")

        self.goal(manifest="goals/manifest.json", max_iterations=5)
        run = self.loop("run", "goals/g.md", action="manifest-stepwise")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].endswith("\tmanifest"), rows)
        self.assertTrue(rows[1].endswith("\tmanifest"), rows)
        self.assertTrue(rows[2].endswith("\tpass"), rows)
        green = self.loop("manifest", "goals/manifest.json", "--json")
        self.assertEqual(green.returncode, 0)
        self.assertTrue(json.loads(green.stdout)["ready"])

    def test_revert_on_fail_undoes_agent_commits_and_staged_files(self):
        (self.repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
        git(self.repo, "add", "tracked.txt")
        git(self.repo, "commit", "-q", "-m", "tracked")
        base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.goal(revert_on_fail="true", max_iterations=1)
        run = self.loop("run", "goals/g.md", action="stage-and-commit")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.assertEqual(head, base)
        self.assertEqual((self.repo / "tracked.txt").read_text(encoding="utf-8"), "clean\n")
        self.assertFalse((self.repo / "staged_new.py").exists())
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain", "-uall"], capture_output=True, text=True).stdout
        self.assertEqual(status.split(), ["??", "goals/g.md"])

    def test_revert_on_fail_removes_an_escaping_link_without_touching_its_target(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "victim.txt").write_text("keep me\n", encoding="utf-8")
        self.goal(revert_on_fail="true", max_iterations=1)
        run = self.loop("run", "goals/g.md", action="link-escape", FAKE_OUTSIDE=str(outside))
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertEqual((outside / "victim.txt").read_text(encoding="utf-8"), "keep me\n")
        self.assertFalse(os.path.lexists(self.repo / "escape"))

    def test_protect_configs_blocks_creating_new_guardrail_configs(self):
        self.goal()
        root_cfg = self.loop("run", "goals/g.md", action="weaken-ruff-toml")
        self.assertEqual(root_cfg.returncode, 4, root_cfg.stdout + root_cfg.stderr)
        self.assertIn("ruff.toml", root_cfg.stdout)
        (self.repo / "ruff.toml").unlink()

        self.goal()
        nested = self.loop("run", "goals/g.md", action="create-nested-conftest")
        self.assertEqual(nested.returncode, 4, nested.stdout + nested.stderr)
        self.assertIn("src/conftest.py", nested.stdout)

        shutil.rmtree(self.repo / "src")
        self.goal(protect_configs="false", max_iterations=1)
        opt_out = self.loop("run", "goals/g.md", action="create-nested-conftest")
        self.assertEqual(opt_out.returncode, 2, opt_out.stdout + opt_out.stderr)

    def test_manifest_dry_run_validates_from_any_cwd_without_running_slices(self):
        manifest = {"product": "demo", "slices": [{"id": "s1", "title": "never run", "check": "touch ran.txt; exit 1"}]}
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        full_env = {**os.environ, "PATH": self.path}
        run = subprocess.run([sys.executable, str(LOOP), "manifest", "manifest.json", "--dry-run", "--json"],
                             cwd=self.repo / "goals", env=full_env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout), {"manifest": "goals/manifest.json", "product": "demo", "total": 1, "valid": True})
        self.assertFalse((self.repo / "ran.txt").exists())

    def test_protect_configs_guards_package_json_scripts_but_not_dependencies(self):
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint ."}, "dependencies": {}}), encoding="utf-8")
        git(self.repo, "add", "package.json")
        git(self.repo, "commit", "-q", "-m", "pkg")
        self.goal()
        run = self.loop("run", "goals/g.md", action="weaken-package-lint")
        self.assertEqual(run.returncode, 4, run.stdout + run.stderr)
        self.assertIn("package.json scripts", run.stdout)

    def test_slop_in_nested_vendored_folders_is_ignored(self):
        vendored = self.repo / "packages" / "web" / "node_modules" / "dep"
        vendored.mkdir(parents=True)
        (vendored / "index.js").write_text("// @ts-ignore\ntry { a(); } catch (e) {}\n", encoding="utf-8")
        self.goal()
        run = self.loop("check", "goals/g.md")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("slop_guard", run.stdout)

    def test_transient_rate_limit_backs_off_and_retries_without_burning_iteration(self):
        self.goal(max_iterations=1, rate_limit_retries=2, rate_limit_backoff_seconds=0.01)
        run = self.loop("run", "goals/g.md", action="rate-limit-then-done")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("transient rate limit; backing off", run.stdout)
        self.assertIn("goal met", run.stdout)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 2)
        self.assertIn("\trate_limited\t", rows[0])
        self.assertIn("\t0\t", rows[1])
        summary = self.latest_summary()
        self.assertEqual(summary["rate_limit_retries_used"], 1)
        self.assertEqual(summary["exit_code"], 0)

    def test_hard_quota_exhaustion_stops_without_retrying(self):
        self.goal(max_iterations=3, rate_limit_retries=3, rate_limit_backoff_seconds=0.01)
        run = self.loop("run", "goals/g.md", action="quota-exhausted")
        self.assertEqual(run.returncode, 5, run.stdout + run.stderr)
        self.assertIn("quota exhausted", run.stdout)
        rows = self.trail_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("\tquota\t", rows[0])
        summary = self.latest_summary()
        self.assertEqual(summary["exit_code"], 5)
        self.assertEqual(summary["exit_reason"], "quota_exhausted")

    def test_invalid_rate_limit_settings_are_rejected(self):
        for field, value in [("cooldown_seconds", "-1"), ("rate_limit_retries", "-1"), ("rate_limit_backoff_seconds", "0")]:
            with self.subTest(field=field, value=value):
                self.goal(**{field: value})
                run = self.loop("check", "goals/g.md")
                self.assertNotEqual(run.returncode, 0)

    def test_escalate_after_switches_harness_args_and_succeeds(self):
        self.goal(
            max_iterations=4,
            stall_after=2,
            harness_args="--model cheap-model",
            escalate_after=2,
            escalate_harness_args="--model strong-model",
        )
        run = self.loop("run", "goals/g.md", action="escalate-on-strong-model")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("escalating to escalate_harness_args", run.stdout)
        self.assertIn("goal met", run.stdout)
        self.assertTrue((self.repo / "ok.txt").exists())
        rows = self.trail_rows()
        self.assertTrue(any("switch:escalated(--model strong-model)" in row for row in rows))
        summary = self.latest_summary()
        self.assertEqual(summary["goal"], "ok.txt exists")
        self.assertEqual(summary["harness"], "omp")
        self.assertEqual(summary["iterations_run"], 3)
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["exit_reason"], "goal_met")
        self.assertEqual(summary["check_exit"], 0)
        self.assertEqual(summary["rate_limit_retries_used"], 0)
        self.assertEqual(summary["trail"], ".scratch/goals/g/trail.tsv")
        self.assertIsInstance(summary["elapsed_seconds"], (int, float))
        self.assertEqual(len(summary["active_args_history"]), 2)
        self.assertEqual(summary["active_args_history"][0]["tier"], "default")
        self.assertEqual(summary["active_args_history"][0]["args"], "--model cheap-model")
        self.assertEqual(summary["active_args_history"][1]["tier"], "escalated")
        self.assertEqual(summary["active_args_history"][1]["args"], "--model strong-model")
        self.assertEqual(summary["active_args_history"][1]["reason"], "escalate_after")
        self.assertEqual(summary["active_args_history"][1]["iteration"], 3)

    def test_fallback_harness_args_recovers_from_hard_quota_error(self):
        self.goal(
            max_iterations=2,
            harness_args="--model primary-model",
            fallback_harness_args="--model fallback-model",
        )
        run = self.loop("run", "goals/g.md", action="quota-then-fallback")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("switching to fallback_harness_args", run.stdout)
        self.assertIn("goal met", run.stdout)
        self.assertTrue((self.repo / "ok.txt").exists())
        rows = self.trail_rows()
        self.assertTrue(any("\tquota\t" in row for row in rows))
        self.assertTrue(any("switch:fallback(--model fallback-model)" in row for row in rows))
        summary = self.latest_summary()
        self.assertEqual(summary["iterations_run"], 1)
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["exit_reason"], "goal_met")
        self.assertEqual(len(summary["active_args_history"]), 2)
        self.assertEqual(summary["active_args_history"][1]["tier"], "fallback")
        self.assertEqual(summary["active_args_history"][1]["args"], "--model fallback-model")
        self.assertEqual(summary["active_args_history"][1]["reason"], "quota")

    def test_fallback_harness_args_recovers_from_persistent_rate_limit_and_aborts_if_fallback_fails(self):
        self.goal(
            max_iterations=2,
            rate_limit_retries=1,
            rate_limit_backoff_seconds=0.01,
            harness_args="--model primary-model",
            fallback_harness_args="--model fallback-model",
        )
        run = self.loop("run", "goals/g.md", action="rate-limit-then-fallback")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = self.latest_summary()
        self.assertEqual(summary["rate_limit_retries_used"], 1)
        self.assertEqual(summary["active_args_history"][1]["tier"], "fallback")
        self.assertEqual(summary["active_args_history"][1]["reason"], "rate_limit")

        (self.repo / "ok.txt").unlink()
        run_both_fail = self.loop("run", "goals/g.md", action="quota-exhausted")
        self.assertEqual(run_both_fail.returncode, 5, run_both_fail.stdout + run_both_fail.stderr)
        summary_fail = self.latest_summary()
        self.assertEqual(summary_fail["exit_code"], 5)
        self.assertEqual(summary_fail["exit_reason"], "quota_exhausted")
        self.assertEqual(len(summary_fail["active_args_history"]), 2)

    def test_checkpoint_every_pauses_with_exit_6_and_writes_summary(self):
        self.goal(max_iterations=5, stall_after=9, checkpoint_every=2)
        run = self.loop("run", "goals/g.md", action="progress")
        self.assertEqual(run.returncode, 6, run.stdout + run.stderr)
        self.assertIn("checkpoint reached after 2 iterations", run.stdout)
        self.assertIn("latest-summary.json", run.stdout)
        self.assertEqual(len(self.trail_rows()), 2)
        summary = self.latest_summary()
        self.assertEqual(summary["iterations_run"], 2)
        self.assertEqual(summary["exit_code"], 6)
        self.assertEqual(summary["exit_reason"], "checkpoint")
        self.assertEqual(summary["check_exit"], 1)
        self.assertEqual(summary["trail"], ".scratch/goals/g/trail.tsv")

    def test_invalid_escalation_fallback_and_checkpoint_settings_are_rejected(self):
        cases = [
            ({"escalate_after": "0", "escalate_harness_args": "--model opus"}, "escalate_after must be a positive integer"),
            ({"escalate_after": "-2", "escalate_harness_args": "--model opus"}, "escalate_after must be a positive integer"),
            ({"escalate_after": "two", "escalate_harness_args": "--model opus"}, "escalate_after must be a positive integer"),
            ({"escalate_after": "2"}, "escalate_after requires escalate_harness_args"),
            ({"escalate_harness_args": "--model opus"}, "escalate_harness_args requires escalate_after"),
            ({"fallback_harness_args": ""}, "fallback_harness_args must not be empty"),
            ({"fallback_harness_args": "--model 'unterminated"}, "invalid shell quoting"),
            ({"checkpoint_every": "0"}, "checkpoint_every must be a positive integer"),
            ({"checkpoint_every": "-1"}, "checkpoint_every must be a positive integer"),
            ({"checkpoint_every": "soon"}, "checkpoint_every must be a positive integer"),
            ({"active_sprint": "0"}, "active_sprint must be a positive integer"),
            ({"active_sprint": "-1"}, "active_sprint must be a positive integer"),
            ({"active_sprint": "one"}, "active_sprint must be a positive integer"),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.goal(**fields)
                run = self.loop("check", "goals/g.md")
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(expected, run.stdout + run.stderr)

    def test_sprint_scoped_manifest_defers_later_sprints_and_catches_earlier_regressions(self):
        manifest = {
            "product": "Two-sprint app",
            "slices": [
                {"id": "slice-1", "title": "Core flow", "sprint": 1, "check": "test -f s1.txt"},
                {"id": "slice-2", "title": "Admin export", "sprint": 2, "check": "test -f s2.txt"},
            ],
            "inventory": [
                {"id": "inv-1", "status": "included", "slice": "slice-1"},
                {"id": "inv-2", "status": "included", "slice": "slice-2"},
            ],
        }
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # Sprint 1 runs and passes while explicitly reporting Sprint 2 deferred (total scope incomplete).
        self.goal(manifest="goals/manifest.json", active_sprint=1, max_iterations=2)
        run_s1 = self.loop("run", "goals/g.md", action="sprint1-done")
        self.assertEqual(run_s1.returncode, 0, run_s1.stdout + run_s1.stderr)
        self.assertIn("total scope incomplete", run_s1.stdout)
        self.assertIn("slice-2", run_s1.stdout)
        summary_s1 = self.latest_summary()
        self.assertEqual(summary_s1["exit_code"], 0)
        scope_s1 = summary_s1["scope"]
        self.assertEqual(scope_s1["active_sprint"], 1)
        self.assertEqual(scope_s1["deferred_slices"], ["slice-2"])
        self.assertEqual(scope_s1["total_slices"], 2)
        self.assertFalse(scope_s1["scope_complete"])
        self.assertFalse(scope_s1["sme_gate_blocked"])
        self.assertEqual(scope_s1["inventory_counts"]["included"], 2)

        cli_s1 = self.loop("manifest", "goals/manifest.json", "--sprint", "1", "--json")
        self.assertEqual(cli_s1.returncode, 0, cli_s1.stdout + cli_s1.stderr)
        s1_json = json.loads(cli_s1.stdout)
        self.assertEqual((s1_json["passed"], s1_json["total"], s1_json["total_slices"]), (1, 1, 2))
        self.assertEqual(s1_json["active_sprint"], 1)
        self.assertEqual(s1_json["deferred_slices"], ["slice-2"])
        self.assertTrue(s1_json["ready"])
        self.assertFalse(s1_json["scope_complete"])

        # Regressing Sprint 1 while targeting Sprint 2 must fail even when Sprint 2 passes.
        (self.repo / "s1.txt").unlink()
        (self.repo / "s2.txt").write_text("", encoding="utf-8")
        cli_reg = self.loop("manifest", "goals/manifest.json", "--sprint", "2", "--json")
        self.assertEqual(cli_reg.returncode, 1, cli_reg.stdout + cli_reg.stderr)
        reg_json = json.loads(cli_reg.stdout)
        self.assertEqual((reg_json["passed"], reg_json["total"], reg_json["deferred_slices"]), (1, 2, []))
        self.assertFalse(reg_json["ready"])
        self.assertFalse(reg_json["scope_complete"])

        # Restoring Sprint 1 makes Sprint 2 (and total scope) complete.
        (self.repo / "s1.txt").write_text("", encoding="utf-8")
        (self.repo / "ok.txt").unlink()
        self.goal(manifest="goals/manifest.json", active_sprint=2, max_iterations=2)
        run_s2 = self.loop("run", "goals/g.md", action="sprint2-done")
        self.assertEqual(run_s2.returncode, 0, run_s2.stdout + run_s2.stderr)
        self.assertIn("goal met", run_s2.stdout)
        self.assertNotIn("total scope incomplete", run_s2.stdout)
        summary_s2 = self.latest_summary()
        self.assertTrue(summary_s2["scope"]["scope_complete"])
        self.assertEqual(summary_s2["scope"]["deferred_slices"], [])
        self.assertEqual(summary_s2["scope"]["active_sprint"], 2)

        bad_sprint = self.loop("manifest", "goals/manifest.json", "--sprint", "0")
        self.assertNotEqual(bad_sprint.returncode, 0)
        self.assertIn("--sprint must be a positive integer", bad_sprint.stdout + bad_sprint.stderr)

    def test_manifest_inventory_schema_validation_and_pending_gate(self):
        base_slices = [{"id": "s1", "title": "Slice 1", "check": "test -f s1.txt"}]
        invalid_cases = [
            ({"product": "p", "slices": [{**base_slices[0], "sprint": 0}]}, "'sprint' must be a positive integer"),
            ({"product": "p", "slices": [{**base_slices[0], "sprint": True}]}, "'sprint' must be a positive integer"),
            ({"product": "p", "slices": base_slices, "inventory": "bad"}, "'inventory' must be a list"),
            ({"product": "p", "slices": base_slices, "inventory": [{"id": "a", "status": "bogus"}]}, "'status' must be one of"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "a", "status": "pending"}, {"id": "a", "status": "pending"}
            ]}, "duplicate inventory id"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "d1", "status": "duplicate"}
            ]}, "requires a non-empty 'representative'"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "d1", "status": "duplicate", "representative": "d1"}
            ]}, "cannot reference itself"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "d1", "status": "duplicate", "representative": "missing"}
            ]}, "must match an inventory or slice id"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "n1", "status": "non_target"}
            ]}, "requires a non-empty 'reason'"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "b1", "status": "blocked", "evidence": "403 log"}
            ]}, "requires a non-empty 'unblock'"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "b1", "status": "blocked", "unblock": "grant token"}
            ]}, "requires a non-empty 'evidence'"),
            ({"product": "p", "slices": base_slices, "inventory": [
                {"id": "i1", "status": "included", "slice": "no-such-slice"}
            ]}, "must match a slice id"),
        ]
        mpath = self.repo / "goals" / "manifest.json"
        for payload, expected in invalid_cases:
            with self.subTest(expected=expected):
                mpath.write_text(json.dumps(payload), encoding="utf-8")
                res = self.loop("manifest", "goals/manifest.json", "--dry-run")
                self.assertNotEqual(res.returncode, 0)
                self.assertIn(expected, res.stdout + res.stderr)

        # Valid schema with an unclassified pending item fails the manifest gate even when slices pass.
        (self.repo / "s1.txt").write_text("", encoding="utf-8")
        (self.repo / "ok.txt").write_text("", encoding="utf-8")
        pending_manifest = {
            "product": "Inventory app",
            "slices": base_slices,
            "inventory": [
                {"id": "item-1", "status": "included", "slice": "s1"},
                {"id": "item-2", "status": "pending"},
            ],
        }
        mpath.write_text(json.dumps(pending_manifest, indent=2), encoding="utf-8")
        dry = self.loop("manifest", "goals/manifest.json", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertEqual(json.loads(dry.stdout)["inventory_counts"]["pending"], 1)

        blocked_pending = self.loop("manifest", "goals/manifest.json", "--json")
        self.assertEqual(blocked_pending.returncode, 1, blocked_pending.stdout + blocked_pending.stderr)
        p_json = json.loads(blocked_pending.stdout)
        self.assertFalse(p_json["ready"])
        self.assertEqual(p_json["pending_inventory"], ["item-2"])
        self.assertEqual(p_json["inventory_counts"], {
            "included": 1, "duplicate": 0, "non_target": 0, "blocked": 0, "pending": 1,
        })

        # Classifying all items passes the gate and reports exact inventory counts.
        classified_manifest = {
            "product": "Inventory app",
            "slices": base_slices,
            "inventory": [
                {"id": "item-1", "status": "included", "slice": "s1"},
                {"id": "item-2", "status": "duplicate", "representative": "item-1"},
                {"id": "item-3", "status": "non_target", "reason": "legacy archive excluded by spec"},
                {"id": "item-4", "status": "blocked", "evidence": "401 from partner API", "unblock": "provision key", "attempts": 2},
            ],
        }
        mpath.write_text(json.dumps(classified_manifest, indent=2), encoding="utf-8")
        ok_res = self.loop("manifest", "goals/manifest.json", "--json")
        self.assertEqual(ok_res.returncode, 0, ok_res.stdout + ok_res.stderr)
        ok_json = json.loads(ok_res.stdout)
        self.assertTrue(ok_json["ready"])
        self.assertTrue(ok_json["scope_complete"])
        self.assertEqual(ok_json["inventory_counts"], {
            "included": 1, "duplicate": 1, "non_target": 1, "blocked": 1, "pending": 0,
        })

    def test_sme_gate_blocks_manifest_check_and_run_until_cleared(self):
        (self.repo / "s1.txt").write_text("", encoding="utf-8")
        (self.repo / "s2.txt").write_text("", encoding="utf-8")
        (self.repo / "ok.txt").write_text("", encoding="utf-8")
        mpath = self.repo / "goals" / "manifest.json"

        # Invalid sme_gate rejected.
        mpath.write_text(json.dumps({
            "product": "Complex domain",
            "sme_gate": "maybe",
            "slices": [{"id": "s1", "title": "Core", "check": "test -f s1.txt"}],
        }), encoding="utf-8")
        bad = self.loop("manifest", "goals/manifest.json", "--dry-run")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("'sme_gate' must be one of", bad.stdout + bad.stderr)

        # Manifest-level sme_gate: required blocks manifest, check, and run (without invoking harness).
        manifest = {
            "product": "Complex domain",
            "sme_gate": "required",
            "slices": [
                {"id": "s1", "title": "Sprint 1", "sprint": 1, "check": "test -f s1.txt"},
                {"id": "s2", "title": "Sprint 2", "sprint": 2, "sme_gate": "required", "check": "test -f s2.txt"},
            ],
        }
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        m_blocked = self.loop("manifest", "goals/manifest.json", "--json")
        self.assertEqual(m_blocked.returncode, 1)
        m_data = json.loads(m_blocked.stdout)
        self.assertTrue(m_data["sme_gate_blocked"])
        self.assertFalse(m_data["ready"])
        self.assertIn("manifest", m_data["sme_gate_blockers"])

        self.goal(manifest="goals/manifest.json", max_iterations=2)
        chk_blocked = self.loop("check", "goals/g.md")
        self.assertEqual(chk_blocked.returncode, 0)
        self.assertIn("check exit 1 (sme_gate)", chk_blocked.stdout)
        self.assertIn("SME gate required before advancing", chk_blocked.stdout)

        record = self.tmp / "sme_harness.json"
        run_blocked = self.loop("run", "goals/g.md", action="done", FAKE_RECORD=str(record))
        self.assertEqual(run_blocked.returncode, 6, run_blocked.stdout + run_blocked.stderr)
        self.assertIn("SME gate required before advancing", run_blocked.stdout)
        self.assertFalse(record.exists())
        summary = self.latest_summary()
        self.assertEqual(summary["exit_code"], 6)
        self.assertEqual(summary["exit_reason"], "sme_gate_required")
        self.assertTrue(summary["scope"]["sme_gate_blocked"])

        # Clearing manifest sme_gate lets Sprint 1 pass while Sprint 2's slice sme_gate still blocks Sprint 2.
        manifest["sme_gate"] = "cleared"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        s1_ok = self.loop("manifest", "goals/manifest.json", "--sprint", "1", "--json")
        self.assertEqual(s1_ok.returncode, 0, s1_ok.stdout + s1_ok.stderr)
        self.assertFalse(json.loads(s1_ok.stdout)["sme_gate_blocked"])

        s2_blocked = self.loop("manifest", "goals/manifest.json", "--sprint", "2", "--json")
        self.assertEqual(s2_blocked.returncode, 1)
        self.assertEqual(json.loads(s2_blocked.stdout)["sme_gate_blockers"], ["slice:s2"])

        # Clearing Sprint 2's sme_gate unblocks both manifest and check.
        manifest["slices"][1]["sme_gate"] = "cleared"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        s2_ok = self.loop("manifest", "goals/manifest.json", "--sprint", "2", "--json")
        self.assertEqual(s2_ok.returncode, 0, s2_ok.stdout + s2_ok.stderr)
        self.assertTrue(json.loads(s2_ok.stdout)["scope_complete"])

        chk_ok = self.loop("check", "goals/g.md")
        self.assertEqual(chk_ok.returncode, 0)
        self.assertIn("check exit 0 (pass) (already done)", chk_ok.stdout)

    def test_status_reports_not_started_checkpoint_sprint_and_sme_resume_commands(self):
        manifest = {
            "product": "Status demo",
            "slices": [
                {"id": "slice-1", "title": "Core", "sprint": 1, "check": "test -f s1.txt"},
                {"id": "slice-2", "title": "Admin", "sprint": 2, "sme_gate": "required", "check": "test -f s2.txt"},
            ],
            "inventory": [
                {"id": "i1", "status": "included", "slice": "slice-1"},
                {"id": "i2", "status": "included", "slice": "slice-2"},
            ],
        }
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.goal(manifest="goals/manifest.json", active_sprint=1, max_iterations=4, stall_after=9, checkpoint_every=1)

        expected_launcher = "py -3 -B" if os.name == "nt" else "python -B"
        expected_script = f'"{LOOP}"' if any(ch.isspace() for ch in str(LOOP)) else str(LOOP)
        expected_s1_cmd = f"{expected_launcher} {expected_script} run goals/g.md --sprint 1"
        expected_s2_cmd = f"{expected_launcher} {expected_script} run goals/g.md --sprint 2"

        pre_json_run = self.loop("status", "goals/g.md", "--json")
        self.assertEqual(pre_json_run.returncode, 0, pre_json_run.stdout + pre_json_run.stderr)
        pre = json.loads(pre_json_run.stdout)
        self.assertEqual(pre["status"], "not_started")
        self.assertEqual(pre["iterations_run"], 0)
        self.assertIsNone(pre["last_exit_code"])
        self.assertEqual(pre["scope"]["active_sprint"], 1)
        self.assertEqual(pre["scope"]["deferred_slices"], ["slice-2"])
        self.assertEqual(pre["scope"]["inventory_counts"]["included"], 2)
        self.assertEqual(pre["resume_command"], expected_s1_cmd)

        pre_text = self.loop("status", "goals/g.md")
        self.assertEqual(pre_text.returncode, 0)
        self.assertIn("goal status (not_started)", pre_text.stdout)
        self.assertIn(f"resume: {expected_s1_cmd}", pre_text.stdout)

        chkpt = self.loop("run", "goals/g.md", action="progress")
        self.assertEqual(chkpt.returncode, 6, chkpt.stdout + chkpt.stderr)
        post_chkpt = json.loads(self.loop("status", "goals/g.md", "--json").stdout)
        self.assertEqual(post_chkpt["status"], "checkpoint")
        self.assertEqual(post_chkpt["last_exit_code"], 6)
        self.assertEqual(post_chkpt["last_exit_reason"], "checkpoint")
        self.assertEqual(post_chkpt["iterations_run"], 1)
        self.assertIsNotNone(post_chkpt["last_trail"])
        self.assertEqual(post_chkpt["resume_command"], expected_s1_cmd)

        s1 = self.loop("run", "goals/g.md", action="sprint1-done")
        self.assertEqual(s1.returncode, 0, s1.stdout + s1.stderr)
        post_s1 = json.loads(self.loop("status", "goals/g.md", "--json").stdout)
        self.assertEqual(post_s1["status"], "sprint_complete")
        self.assertEqual(post_s1["last_exit_code"], 0)
        self.assertEqual(post_s1["scope"]["next_sprint"], 2)
        self.assertEqual(post_s1["resume_command"], expected_s2_cmd)

        s2_sme = json.loads(self.loop("status", "goals/g.md", "--sprint", "2", "--json").stdout)
        self.assertTrue(s2_sme["scope"]["sme_gate_blocked"])
        self.assertIn("SME gate required before advancing", s2_sme["resume_note"])

    def test_sprint_cli_override_on_check_and_run_without_editing_frontmatter(self):
        manifest = {
            "product": "CLI sprint override",
            "slices": [
                {"id": "slice-1", "title": "Core", "sprint": 1, "check": "test -f s1.txt"},
                {"id": "slice-2", "title": "Extra", "sprint": 2, "check": "test -f s2.txt"},
            ],
        }
        (self.repo / "goals" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (self.repo / "s1.txt").write_text("", encoding="utf-8")
        (self.repo / "ok.txt").write_text("", encoding="utf-8")
        self.goal(manifest="goals/manifest.json", active_sprint=1, max_iterations=2)
        original_goal = (self.repo / "goals" / "g.md").read_text(encoding="utf-8")

        chk_s1 = self.loop("check", "goals/g.md")
        self.assertEqual(chk_s1.returncode, 0)
        self.assertIn("check exit 0 (pass) (already done)", chk_s1.stdout)

        chk_s2 = self.loop("check", "goals/g.md", "--sprint", "2")
        self.assertEqual(chk_s2.returncode, 0)
        self.assertIn("active_sprint=2 (CLI override)", chk_s2.stdout)
        self.assertIn("check exit 1 (manifest)", chk_s2.stdout)

        run_s2 = self.loop("run", "goals/g.md", "--sprint", "2", action="sprint2-done")
        self.assertEqual(run_s2.returncode, 0, run_s2.stdout + run_s2.stderr)
        self.assertIn("using CLI --sprint 2 override", run_s2.stdout)
        self.assertIn("goal met", run_s2.stdout)
        self.assertEqual((self.repo / "goals" / "g.md").read_text(encoding="utf-8"), original_goal)
        summary = self.latest_summary()
        self.assertEqual(summary["scope"]["active_sprint"], 2)
        self.assertEqual(summary["scope"]["active_sprint_source"], "cli")
        self.assertTrue(summary["scope"]["scope_complete"])
        self.assertEqual(summary["scope"]["deferred_slices"], [])

        # Passing --sprint on a goal without a manifest fails cleanly.
        self.goal(manifest=None)
        no_manifest = self.loop("check", "goals/g.md", "--sprint", "1")
        self.assertNotEqual(no_manifest.returncode, 0)
        self.assertIn("--sprint requires a manifest", no_manifest.stdout + no_manifest.stderr)

    def test_audit_write_goal_auto_detects_single_valid_manifest_and_skips_ambiguous_or_invalid(self):
        specs = self.repo / "docs" / "specs"
        specs.mkdir(parents=True)
        valid_manifest = {"product": "Demo", "slices": [{"id": "s1", "title": "Core", "check": "true"}]}
        (specs / "app-manifest.json").write_text(json.dumps(valid_manifest), encoding="utf-8")
        # Invalid manifest should be ignored rather than crashing audit.
        (specs / "broken-manifest.json").write_text("{not json", encoding="utf-8")

        single = self.loop("audit", "--json", "--write-goal", "goals/auto.md")
        self.assertEqual(single.returncode, 0, single.stdout + single.stderr)
        report = json.loads(single.stdout)
        self.assertEqual(report["guardrails"]["manifests"], ["docs/specs/app-manifest.json"])
        self.assertEqual(report["recommended"]["manifest"], "docs/specs/app-manifest.json")
        scaffold = (self.repo / "goals" / "auto.md").read_text(encoding="utf-8")
        self.assertIn("manifest: docs/specs/app-manifest.json", scaffold)
        self.assertIn("docs/specs/app-manifest.json", [line for line in scaffold.splitlines() if line.startswith("protect:")][0])

        # Adding a second valid manifest makes selection ambiguous, so audit lists both without guessing.
        scratch_goals = self.repo / ".scratch" / "goals"
        scratch_goals.mkdir(parents=True)
        (scratch_goals / "other-manifest.json").write_text(json.dumps(valid_manifest), encoding="utf-8")
        multi = self.loop("audit", "--json", "--write-goal", "goals/auto2.md")
        self.assertEqual(multi.returncode, 0, multi.stdout + multi.stderr)
        multi_report = json.loads(multi.stdout)
        self.assertEqual(
            multi_report["guardrails"]["manifests"],
            ["docs/specs/app-manifest.json", ".scratch/goals/other-manifest.json"],
        )
        self.assertNotIn("manifest", multi_report["recommended"])
        scaffold2 = (self.repo / "goals" / "auto2.md").read_text(encoding="utf-8")
        self.assertNotIn("\nmanifest:", scaffold2)


class ScanTextSlopCase(unittest.TestCase):
    def scan(self, name, text):
        sys.path.insert(0, str(LOOP.parent))
        self.addCleanup(sys.path.remove, str(LOOP.parent))
        import loop
        return [(line, rule) for _, line, rule, _, _ in loop.scan_text_slop(name, text)]

    def test_rust_lifetimes_char_literals_and_raw_strings_do_not_hide_later_slop(self):
        text = ("fn first<'a>(x: &'a str) -> &'a str { x }\n#[allow(dead_code)]\nfn unused() { todo!() }\n"
                "let c = '\'';\nlet r = r#\"// TODO inside a raw string\"#;\n")
        self.assertEqual(self.scan("lib.rs", text), [(2, "suppression-comment"), (3, "stub-placeholder")])

    def test_stray_quotes_in_jsx_and_regex_literals_do_not_hide_later_slop(self):
        self.assertEqual(self.scan("view.tsx", "const A = () => <p>Don't stop</p>;\n// @ts-ignore\nconst x = 1;\n"),
                         [(2, "suppression-comment")])
        self.assertEqual(self.scan("re.js", "s.replace(/['\"]/g, '');\ntry { go(); } catch (e) {}\n"),
                         [(2, "swallowed-exception")])

    def test_go_raw_strings_have_no_escapes(self):
        self.assertEqual(self.scan("raw.go", "var p = `C:\\path\\`\n// nolint\n"), [(2, "suppression-comment")])

    def test_prose_mentioning_placeholder_is_not_a_stub_but_leading_markers_are(self):
        self.assertEqual(self.scan("ui.ts", "// Renders the placeholder text when empty\n"), [])
        self.assertEqual(self.scan("ui.ts", "// placeholder until the API lands\n// later TODO wire it\n"),
                         [(1, "stub-placeholder"), (2, "stub-placeholder")])
    def test_broad_catches_that_only_continue_return_or_break_are_swallowed(self):
        text = ("def a(xs):\n    for x in xs:\n        try:\n            go(x)\n        except Exception:\n            continue\n"
                "def b():\n    try:\n        return go()\n    except Exception:\n        return None\n"
                "def c():\n    with contextlib.suppress(Exception):\n        go()\n"
                "def d():\n    try:\n        go()\n    except Exception:\n        log.exception('x')\n        raise\n")
        self.assertEqual(self.scan("m.py", text), [(5, "swallowed-exception"), (10, "swallowed-exception"),
                                                   (13, "swallowed-exception")])

    def test_bare_except_that_reraises_is_allowed(self):
        self.assertEqual(self.scan("m.py", "try:\n    go()\nexcept:\n    cleanup()\n    raise\n"), [])

    def test_not_implemented_stubs_inside_handlers_and_match_cases_are_found_but_dispatch_fallbacks_are_not(self):
        text = ("def a(x):\n    try:\n        return go(x)\n    except KeyError:\n        raise NotImplementedError\n"
                "def b(kind):\n    match kind:\n        case 'csv':\n            raise NotImplementedError('todo: csv')\n"
                "def c(kind):\n    if kind == 'json':\n        return 1\n    raise NotImplementedError(f'unsupported kind {kind}')\n")
        self.assertEqual(self.scan("m.py", text), [(5, "stub-placeholder"), (9, "stub-placeholder")])

    def test_more_python_and_rust_suppressions_are_recognized(self):
        text = ("x = 1  # pylint: disable=unused-variable\ny = eval(s)  # nosec\n"
                "def z():  # pragma: no cover\n    return 1\n# mypy: ignore-errors\n")
        self.assertEqual([r for _, r in self.scan("m.py", text)], ["suppression-comment"] * 4)
        self.assertEqual(self.scan("lib.rs", "#[expect(dead_code)]\nfn f() {}\n"), [(1, "suppression-comment")])

    def test_block_comment_continuation_lines_are_scanned(self):
        text = "/**\n * Loads the view.\n * TODO wire the cache\n * eslint-disable no-console\n */\nexport const a = 1;\n"
        self.assertEqual(self.scan("ui.ts", text), [(3, "stub-placeholder"), (4, "suppression-comment")])

    def test_inline_block_comment_rust_stub_multi_comment_and_js_regex_slop(self):
        self.assertEqual(self.scan("lib.rs", "/* ok */ todo!();\n"), [(1, "stub-placeholder")])
        self.assertEqual(
            self.scan("multi.ts", "/* a */ const x = 1; /* b\n * TODO finish\n */\n"),
            [(2, "stub-placeholder")],
        )
        self.assertEqual(
            self.scan("re.js", "const re = /https?:\\/\\//; try { go(); } catch (e) {}\n"),
            [(1, "swallowed-exception")],
        )

    def test_nested_pyproject_and_package_json_and_root_tool_sections_protected(self):
        sys.path.insert(0, str(LOOP.parent))
        self.addCleanup(sys.path.remove, str(LOOP.parent))
        import loop
        with tempfile.TemporaryDirectory(prefix="loop-guard-") as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps({"name": "root", "eslintConfig": {"rules": {"no-console": "error"}}}),
                encoding="utf-8",
            )
            (root / "subpkg").mkdir()
            (root / "subpkg" / "pyproject.toml").write_text('[tool.ruff]\nselect = ["E"]\n', encoding="utf-8")
            (root / "packages" / "app").mkdir(parents=True)
            (root / "packages" / "app" / "package.json").write_text(
                json.dumps({"name": "app", "scripts": {"lint": "eslint ."}}),
                encoding="utf-8",
            )
            before = loop.guardrail_state(str(root), set())
            self.assertIn("package.json scripts", before)
            self.assertIn("subpkg/pyproject.toml [tool.*]", before)
            self.assertIn("packages/app/package.json [guardrails]", before)

            # Weakening root eslintConfig, nested pyproject.toml, or nested package.json scripts must change state.
            (root / "package.json").write_text(
                json.dumps({"name": "root", "eslintConfig": {"rules": {}}}),
                encoding="utf-8",
            )
            self.assertNotEqual(before, loop.guardrail_state(str(root), set()))

            (root / "subpkg" / "pyproject.toml").write_text("[tool.ruff]\nselect = []\n", encoding="utf-8")
            after_sub = loop.guardrail_state(str(root), set())
            self.assertNotEqual(before["subpkg/pyproject.toml [tool.*]"], after_sub["subpkg/pyproject.toml [tool.*]"])

            (root / "packages" / "app" / "package.json").write_text(
                json.dumps({"name": "app", "scripts": {"lint": "true"}}),
                encoding="utf-8",
            )
            after_pkg = loop.guardrail_state(str(root), set())
            self.assertNotEqual(
                before["packages/app/package.json [guardrails]"],
                after_pkg["packages/app/package.json [guardrails]"],
            )

            # _rel_inside_root allows `..env` inside root and rejects `../outside`.
            self.assertEqual(loop._rel_inside_root(str(root / "..env"), str(root)), "..env")
            self.assertIsNone(loop._rel_inside_root(str(root.parent / "outside.txt"), str(root)))

    def test_corrupted_goal_frontmatter_exits_4_and_writes_summary(self):
        with tempfile.TemporaryDirectory(prefix="loop-corrupt-") as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (root / "check.sh").write_text("#!/bin/sh\ntest -f ok.txt\n", encoding="utf-8")
            (root / "goals").mkdir()
            goal = root / "goals" / "g.md"
            goal.write_text(
                "---\ngoal: test corrupt\ncheck: test -f ok.txt\nprotect: check.sh\nmax_iterations: 2\nmax_cost_usd: 1\n---\nPlan.\n",
                encoding="utf-8",
            )
            corrupt_script = bin_dir / "corrupt_omp.py"
            corrupt_script.write_text(
                'import sys; sys.stdin.read(); open("goals/g.md", "w", encoding="utf-8").write("no frontmatter\\n")\n',
                encoding="utf-8",
            )
            if os.name == "nt":
                (bin_dir / "omp.cmd").write_text(f'@"{sys.executable}" "{corrupt_script}" %*\r\n', encoding="utf-8")
            else:
                omp = bin_dir / "omp"
                omp.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{corrupt_script}" "$@"\n', encoding="utf-8")
                omp.chmod(0o755)
            env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
            proc = subprocess.run(
                [sys.executable, "-B", str(LOOP), "run", "goals/g.md", "--harness", "omp"],
                cwd=str(root), capture_output=True, text=True, env=env,
            )
            self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
            summary = json.loads((root / ".scratch" / "goals" / "g" / "latest-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["exit_code"], 4)
            self.assertEqual(summary["exit_reason"], "tampered_frontmatter")


    def test_outer_supervisor_blocks_scratch_reward_hack_and_unverified_artifact(self):
        sys.path.insert(0, str(LOOP.parent))
        import loop as loop_mod

        with tempfile.TemporaryDirectory(prefix="loop-reward-guard-") as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "t@e.com"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "T"], check=True, capture_output=True)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (root / "refs").mkdir()
            (root / "refs" / "art.png").write_bytes(b"\x89PNG\r\n\x1a\nref-art")
            (root / "check.py").write_text("import pathlib, sys; sys.exit(0 if pathlib.Path('out/model.glb').is_file() else 1)\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True, capture_output=True)
            (root / "goals").mkdir()

            # 1. Holdout directory is strictly outside `root` even when TMP/TEMP points inside `.scratch/tmp`.
            old_tmp = os.environ.get("TEMP")
            os.environ["TEMP"] = str(root / ".scratch" / "tmp")
            try:
                hd = loop_mod._allocate_outside_holdout(str(root), "ship")
                self.assertIsNone(loop_mod._rel_inside_root(hd, str(root)))
                shutil.rmtree(hd, ignore_errors=True)
            finally:
                if old_tmp is not None:
                    os.environ["TEMP"] = old_tmp

            # 2. Incomplete reward_artifacts without references/producers is rejected at parse time.
            bad_goal = root / "goals" / "incomplete.md"
            bad_goal.write_text(
                f'---\ngoal: bad\ncheck: "{sys.executable}" check.py\nprotect: check.py\nreward_artifacts: out/model.glb\nmax_iterations: 1\nmax_cost_usd: 1\n---\nPlan.\n',
                encoding="utf-8",
            )
            bad_proc = subprocess.run([sys.executable, "-B", str(LOOP), "check", "goals/incomplete.md"], cwd=str(root), capture_output=True, text=True)
            self.assertNotEqual(bad_proc.returncode, 0)

            # 3. Clean scan + green check + unverified artifact reaches evaluate_outer_reward_contract and fails provenance!
            goal = root / "goals" / "ship.md"
            goal.write_text(
                f'---\ngoal: generate real 3d ship\ncheck: "{sys.executable}" check.py\nprotect: check.py\n'
                "reward_references: refs/art.png\nreward_artifacts: out/model.glb\nreward_producers: dgx-spark\n"
                "max_iterations: 1\nmax_cost_usd: 1\n---\nPlan.\n",
                encoding="utf-8",
            )
            clean_unverified_agent = bin_dir / "unverified_omp.py"
            clean_unverified_agent.write_text(
                "import os, pathlib, sys\n"
                "assert 'DEEPMODEBOT_REWARD_STATE_DIR' not in os.environ\n"
                "sys.stdin.read()\n"
                "pathlib.Path('out').mkdir(exist_ok=True)\n"
                "pathlib.Path('out/model.glb').write_bytes(b'unverified-glb-bytes')\n",
                encoding="utf-8",
            )
            if os.name == "nt":
                (bin_dir / "omp.cmd").write_text(f'@"{sys.executable}" "{clean_unverified_agent}" %*\r\n', encoding="utf-8")
            else:
                omp = bin_dir / "omp"
                omp.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{clean_unverified_agent}" "$@"\n', encoding="utf-8")
                omp.chmod(0o755)
            env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""), "DEEPMODEBOT_REWARD_STATE_DIR": "/secret"}
            proc = subprocess.run(
                [sys.executable, "-B", str(LOOP), "run", "goals/ship.md", "--harness", "omp"],
                cwd=str(root), capture_output=True, text=True, env=env,
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            summary = json.loads((root / ".scratch" / "goals" / "ship" / "latest-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stage"], "reward_guard")
            chk_logs = list((root / ".scratch" / "goals" / "ship").glob("*-check.log"))
            self.assertTrue(any("outer-supervisor verification error" in p.read_text(encoding="utf-8") for p in chk_logs))

            # 4. Check command that mutates a protected reward_references file exits 4 immediately!
            (root / "mutate_ref.py").write_text("import pathlib; pathlib.Path('refs/art.png').write_bytes(b'tampered')\n", encoding="utf-8")
            mut_goal = root / "goals" / "mut.md"
            mut_goal.write_text(
                f'---\ngoal: mut\ncheck: "{sys.executable}" mutate_ref.py\nprotect: none\nreward_references: refs/art.png\nreward_artifacts: out/model.glb\nmax_iterations: 1\nmax_cost_usd: 1\n---\nPlan.\n',
                encoding="utf-8",
            )
            mut_proc = subprocess.run([sys.executable, "-B", str(LOOP), "run", "goals/mut.md", "--harness", "omp"], cwd=str(root), capture_output=True, text=True, env=env)
            self.assertEqual(mut_proc.returncode, 4, mut_proc.stdout + mut_proc.stderr)

            # 5. Green preflight check that drops a .scratch bypass script does NOT report already-done!
            (root / "refs" / "art.png").write_bytes(b"\x89PNG\r\n\x1a\nref-art")
            (root / "sneaky_check.py").write_text(
                "import pathlib\npathlib.Path('.scratch').mkdir(exist_ok=True)\n"
                "pathlib.Path('.scratch/gate.sh').write_text('quality-eval --skip-reference\\n', encoding='utf-8')\n",
                encoding="utf-8",
            )
            sneaky_goal = root / "goals" / "sneaky.md"
            sneaky_goal.write_text(
                f'---\ngoal: sneaky\ncheck: "{sys.executable}" sneaky_check.py\nprotect: none\nmax_iterations: 1\nmax_cost_usd: 1\n---\nPlan.\n',
                encoding="utf-8",
            )
            sneaky_proc = subprocess.run([sys.executable, "-B", str(LOOP), "run", "goals/sneaky.md", "--harness", "omp"], cwd=str(root), capture_output=True, text=True, env=env)
            self.assertNotEqual(sneaky_proc.returncode, 0, sneaky_proc.stdout + sneaky_proc.stderr)
            self.assertNotIn("already passes", sneaky_proc.stdout)

            # 6. fast_check or check that creates tests/conftest.py exits 4 (tampered_configs)!
            (root / ".scratch" / "gate.sh").unlink(missing_ok=True)
            (root / "tests").mkdir(exist_ok=True)
            (root / "make_conftest.py").write_text("import pathlib; pathlib.Path('tests/conftest.py').write_text('x = 1\\n')\n", encoding="utf-8")
            cfg_goal = root / "goals" / "cfg.md"
            cfg_goal.write_text(
                f'---\ngoal: cfg\ncheck: "{sys.executable}" make_conftest.py\nprotect: check.py\nmax_iterations: 1\nmax_cost_usd: 1\n---\nPlan.\n',
                encoding="utf-8",
            )
            cfg_proc = subprocess.run([sys.executable, "-B", str(LOOP), "run", "goals/cfg.md", "--harness", "omp"], cwd=str(root), capture_output=True, text=True, env=env)
            self.assertEqual(cfg_proc.returncode, 4, cfg_proc.stdout + cfg_proc.stderr)
if __name__ == "__main__":
    unittest.main()
