import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5] if len(HERE.parents) > 5 else HERE
SPEC = importlib.util.spec_from_file_location("tournament_mod", HERE / "tournament.py")
tournament = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tournament
SPEC.loader.exec_module(tournament)


class AutoRouterTests(unittest.TestCase):
    def test_matches_all_golden_routing_cases(self):
        cases_path = ROOT / "evals" / "routing" / "cases.json"
        if not cases_path.is_file():
            self.skipTest("evals/routing/cases.json is outside standalone plugin copy")
        data = json.loads(cases_path.read_text(encoding="utf-8"))
        for case in data["cases"]:
            ctx = case.get("context", data["context"]).lower()
            verdict = tournament.classify_prompt(
                case["request"],
                has_factory="has a factory.json" in ctx,
                empty_dir="empty folder" in ctx,
            )
            self.assertEqual(
                verdict["mode"],
                case["route"],
                f"case {case['id']} routed to {verdict['mode']} ({verdict['reason']}), expected {case['route']}",
            )

    def test_routes_readme_examples_and_near_miss_workflows_accurately(self):
        expected_pairs = [
            ("the coupon total is wrong. fix it", {}, "bug-fix"),
            ("add CSV export to the reports page", {}, "feature"),
            ("grill me on this plan, then write the spec and cut tickets", {}, "grill"),
            ("implement spec #12", {}, "phased-build"),
            ("triage the open issues", {}, "triage"),
            ("review PR 42", {}, "pr-review"),
            ("PR #42", {}, "pr-review"),
            ("https://github.com/org/repo/pull/42", {}, "pr-review"),
            ("start a new app: a CLI that converts Sigma rules for our SIEM", {}, "prior-art"),
            ("check on PR 42, and ship it when it's green", {}, "babysit"),
            ("get PR 42 green", {}, "babysit"),
            ("land PR 42", {}, "pr-conversation"),
            ("retro", {}, "retro"),
            ("write a handoff", {}, "handoff"),
            ("block dangerous git commands", {}, "git-guardrails"),
            ("add pre-commit hooks", {}, "pre-commit"),
            ("write integration tests for the checkout webhook", {}, "tdd"),
            ("Fix login redirect loop on mobile Safari", {}, "bug-fix"),
            ("Checkout fails when cart has zero-dollar items", {}, "bug-fix"),
            ("Sort invoices by due date on the billing page", {}, "feature"),
            ("Send a confirmation email when an order completes", {}, "feature"),
            ("Remove the legacy login modal from the settings page", {}, "feature"),
            ("grill with docs on our webhook schema", {}, "grill"),
            ("Grill me on my plan to migrate auth and point out blind spots", {}, "grill"),
            ("Here is my draft plan: add a billing_interval column to subscriptions and handle the webhook", {}, "grill"),
            ("Draft plan: move cron jobs to a Postgres queue with retries", {}, "grill"),
            ("Create a CLI", {"empty_dir": True}, "tournament"),
            ("Create me an AI app.", {"empty_dir": True}, "tournament"),
            ("Fix our whole architecture", {}, "tournament"),
            ("@deepmodebot implement", {}, "issue-conversation"),
            ("install deepmodebot on my repos", {}, "github-app"),
            ("set up deepmodebot here", {}, "setup"),
            ("explain the deepmodebot workflow", {}, "flows"),
            ("In src/auth implement OAuth", {}, "feature"),
            ("On /checkout implement Apple Pay", {}, "feature"),
            ("Set up husky here", {}, "pre-commit"),
            ("Set up pre-commit hooks here", {}, "pre-commit"),
            ("Set up git safety hooks here", {}, "git-guardrails"),
            ("Set up Stripe webhooks here", {}, "feature"),
            ("Explain the checkout workflow", {}, "investigation"),
        ]
        for prompt, kwargs, expected in expected_pairs:
            verdict = tournament.classify_prompt(prompt, **kwargs)
            self.assertEqual(
                verdict["mode"],
                expected,
                f"prompt {prompt!r} routed to {verdict['mode']} ({verdict['reason']}), expected {expected}",
            )

        with unittest.mock.patch.multiple(
            tournament, BRAND_SLUG="acme-review", BRAND_DISPLAY="Acme Review", BRAND_TRIGGER="/acme-review"
        ):
            rebrand_pairs = [
                ("/acme-review implement", "issue-conversation"),
                ("install Acme Review on my repos", "github-app"),
                ("set up Acme Review here", "setup"),
                ("set up acme-review here", "setup"),
                ("explain the Acme Review workflow", "flows"),
            ]
            for prompt, expected in rebrand_pairs:
                self.assertEqual(tournament.classify_prompt(prompt)["mode"], expected)

    def test_tournament_sets_proposal_checkpoint_and_supports_stdin(self):
        gap = tournament.classify_prompt("What architecture gaps and research blind spots is our agent missing?")
        self.assertEqual(gap["mode"], "tournament")
        self.assertEqual(gap["intent"], "discover")
        self.assertTrue(gap["checkpoint_before_code"])

        vague = tournament.classify_prompt("Upgrade our AI pipeline")
        self.assertEqual(vague["mode"], "tournament")
        self.assertEqual(vague["vagueness"], "high")
        self.assertTrue(vague["checkpoint_before_code"])

        for empty in (True, False):
            build = tournament.classify_prompt("Build me an AI app.", empty_dir=empty)
            self.assertEqual(build["mode"], "tournament")
            self.assertEqual(build["intent"], "execute")
            self.assertFalse(build["checkpoint_before_code"])

        medium = tournament.classify_prompt("Add rate limiting across customer requests")
        self.assertEqual(medium["mode"], "grill")
        self.assertEqual(medium["vagueness"], "medium")
        self.assertFalse(medium["checkpoint_before_code"])

        stdin_buf = io.StringIO("The quickstart in README.md says `npm run devv` with $SECRET_KEY. Fix it.\n")
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), unittest.mock.patch.object(sys, "stdin", stdin_buf):
            code = tournament.main(["route", "--stdin", "--json"])
        self.assertEqual(code, 0)
        parsed = json.loads(out_buf.getvalue())
        self.assertEqual(parsed["mode"], "bug-fix")


class TournamentBracketTests(unittest.TestCase):
    def setUp(self):
        base_tmp = ROOT / ".scratch" / "tmp" if (ROOT / "scripts" / "check.py").is_file() else None
        if base_tmp is not None:
            base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="tournament-test-", dir=str(base_tmp) if base_tmp else None)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src" / "router.py").write_text("def route(prompt):\n    return 'feature'\n", encoding="utf-8")

    def run_cli(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tournament.main(list(args))
        return code, buf.getvalue()

    def test_twelve_agent_bracket_runs_pods_semifinals_final_and_renders_proposal(self):
        code, raw = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "arch-gaps",
            "--prompt", "Find architecture and research gaps in routing", "--entrants", "12", "--json",
        )
        self.assertEqual(code, 0)
        init_out = json.loads(raw)
        tdir = init_out["dir"]
        self.assertEqual(init_out["entrant_count"], 12)
        self.assertTrue((self.repo / ".scratch" / ".gitignore").is_file())

        with self.assertRaises(SystemExit, msg="duplicate init without --force must fail"):
            self.run_cli("init", "--root", str(self.repo), "--slug", "arch-gaps", "--prompt", "Overwrite")

        receipts_cycle = [
            "src/router.py:1-2",
            "https://arxiv.org/abs/2502.18864",
            "cmd:py -3 -c \"print(42)\" -> 42",
        ]
        for idx, entrant in enumerate(init_out["entrants"]):
            code, _ = self.run_cli(
                "pitch", "--dir", tdir, "--entrant", entrant["id"],
                "--title", f"Thesis {entrant['id']}",
                "--thesis", f"System proposal from {entrant['id']}.",
                "--gap-kind", entrant["default_gap_kind"],
                "--receipt", receipts_cycle[idx % len(receipts_cycle)],
                "--receipt", "cmd:python -c 'print(42)' -> fabricated output",
                "--receipt", "https://example.org/unchecked-claim",
                "--counter-risk", "Migration overhead if rollout is unscoped.",
            )
            self.assertEqual(code, 0)

        code, _ = self.run_cli(
            "rebut", "--dir", tdir, "--match", "pod-a",
            "--entrant", "seam-archaeologist", "--target", "data-state-architect",
            "--attack", "Router state is stateless, so coupling lives at the dispatch seam.",
            "--receipt", "src/router.py:1",
        )
        self.assertEqual(code, 0)

        self.run_cli(
            "judge", "--dir", tdir, "--match", "pod-a", "--winner", "seam-archaeologist",
            "--judge-model", "cross-family-judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "seam-archaeologist proved structural leverage.",
            "--graft-from", "data-state-architect", "--graft", "Typed intent envelope from state lens.",
        )

        with self.assertRaises(SystemExit, msg="semifinal must reject judging while pod-b feeder is unfinished"):
            self.run_cli(
                "judge", "--dir", tdir, "--match", "sf-1", "--winner", "seam-archaeologist",
                "--judge-model", "cross-family-judge", "--verified-receipt", "src/router.py:1",
                "--rationale", "Premature semifinal verdict.",
            )

        remaining_pods = [
            ("pod-b", "sota-paper-researcher", "eval-oracle-scientist", "Pairwise tournament rubric from eval lens."),
            ("pod-c", "premise-attacker", "adjacent-capability-scout", "Pre-code checkpoint before build route."),
            ("pod-d", "radical-simplifier", "failure-security-redteam", "Strict path:line receipt verification."),
        ]
        for match_id, winner, loser, graft in remaining_pods:
            code, _ = self.run_cli(
                "judge", "--dir", tdir, "--match", match_id, "--winner", winner,
                "--judge-model", "cross-family-judge", "--verified-receipt", "src/router.py:1",
                "--rationale", f"{winner} proved structural leverage.",
                "--graft-from", loser, "--graft", graft,
            )
            self.assertEqual(code, 0)

        _, status_raw = self.run_cli("status", "--dir", tdir, "--json")
        status = json.loads(status_raw)
        self.assertEqual(status["ready_matches"], ["sf-1", "sf-2"])

        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-1", "--winner", "sota-paper-researcher",
            "--judge-model", "cross-family-judge", "--verified-receipt", "https://arxiv.org/abs/2502.18864",
            "--rationale", "Pairwise tournament synthesis subsumes isolated seam refactor.",
            "--graft-from", "seam-archaeologist", "--graft", "Dispatch seam boundary cleanup.",
        )

        with self.assertRaises(SystemExit, msg="final must reject judging while sf-2 feeder is unfinished"):
            self.run_cli(
                "judge", "--dir", tdir, "--match", "final", "--winner", "sota-paper-researcher",
                "--judge-model", "cross-family-judge", "--verified-receipt", "https://arxiv.org/abs/2502.18864",
                "--rationale", "Premature final verdict.",
            )

        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-2", "--winner", "premise-attacker",
            "--judge-model", "cross-family-judge", "--verified-receipt", "src/router.py:1-2",
            "--rationale", "Attacking premature execution cures tunnel vision at the root.",
        )
        self.run_cli(
            "judge", "--dir", tdir, "--match", "final", "--winner", "sota-paper-researcher",
            "--judge-model", "cross-family-judge", "--verified-receipt", "https://arxiv.org/abs/2502.18864",
            "--rationale", "Combines SOTA tournament debate with grafted seam and eval checks.",
            "--graft-from", "premise-attacker", "--graft", "Intent and vagueness gate before build routes.",
        )

        with self.assertRaises(SystemExit, msg="cannot mark crowned champion as dropout"):
            self.run_cli("dropout", "--dir", tdir, "--entrant", "sota-paper-researcher", "--reason", "late")

        outside_cwd = Path(self.tmp.name)
        prev_cwd = Path.cwd()
        os.chdir(outside_cwd)
        try:
            code, proposal = self.run_cli(
                "render", "--dir", tdir, "--out", ".scratch/tournaments/arch-gaps/custom-proposal.md"
            )
        finally:
            os.chdir(prev_cwd)
        self.assertEqual(code, 0)
        self.assertIn("# Tournament proposal: Thesis sota-paper-researcher", proposal)
        self.assertIn("## Runner-up counter-thesis: Thesis premise-attacker (`premise-attacker`)", proposal)
        self.assertIn("From `eval-oracle-scientist` (pod-b)", proposal)
        self.assertIn("From `premise-attacker` (final)", proposal)
        submitted, verified = proposal.split("### Judge-verified receipts", 1)
        self.assertIn("cmd:python -c 'print(42)' -> fabricated output", submitted)
        self.assertIn("https://example.org/unchecked-claim", submitted)
        self.assertNotIn("fabricated output", verified)
        self.assertNotIn("unchecked-claim", verified)
        self.assertIn("`pod-b` (judge `cross-family-judge`): `src/router.py:1`", verified)
        self.assertIn("`sf-1` (judge `cross-family-judge`): `https://arxiv.org/abs/2502.18864`", verified)
        self.assertIn("`final` (judge `cross-family-judge`): `https://arxiv.org/abs/2502.18864`", verified)
        self.assertTrue((self.repo / ".scratch" / "tournaments" / "arch-gaps" / "custom-proposal.md").is_file())

    def test_rejects_bad_receipts_unsafe_roots_tampered_state_and_symlinks(self):
        with self.assertRaises(SystemExit, msg="home directory must be rejected as project root"):
            self.run_cli("init", "--root", str(Path.home()), "--slug", "bad", "--prompt", "Rethink")

        _, raw = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "guards",
            "--prompt", "Rethink architecture", "--entrants", "4", "--json",
        )
        tdir = json.loads(raw)["dir"]

        bad_receipts = [
            "src/does_not_exist.py:1",
            "src/router.py:99",
            "../outside.py:1",
            f"{(self.repo / 'src' / 'router.py').as_posix()}:1",
            "http://arxiv.org/abs/2502.18864",
            "https://localhost:8080/internal",
            "https://127.0.0.1/secret",
            "https://169.254.169.254/latest/meta-data/",
        ]
        (Path(self.tmp.name) / "outside.py").write_text("x = 1\n", encoding="utf-8")
        for bad in bad_receipts:
            with self.assertRaises(SystemExit, msg=f"bad receipt {bad!r} must fail"):
                self.run_cli(
                    "pitch", "--dir", tdir, "--entrant", "seam-archaeologist",
                    "--title", "T", "--thesis", "Body", "--gap-kind", "architecture",
                    "--receipt", bad,
                )

        with self.assertRaises(SystemExit, msg="rebuttal before pitches must fail"):
            self.run_cli(
                "rebut", "--dir", tdir, "--match", "sf-1",
                "--entrant", "seam-archaeologist", "--target", "sota-paper-researcher",
                "--attack", "Premature", "--receipt", "src/router.py:1",
            )

        outside_dir = Path(self.tmp.name) / "copied_bracket"
        outside_dir.mkdir()
        (outside_dir / "bracket.json").write_text((Path(tdir) / "bracket.json").read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaises(SystemExit, msg="bracket directory outside <root>/.scratch/tournaments/<slug> must fail"):
            self.run_cli("status", "--dir", str(outside_dir))

        symlink_probe = Path(tdir) / "proposal.md"
        outside_target = Path(self.tmp.name) / "outside_proposal.md"
        try:
            symlink_probe.symlink_to(outside_target)
        except OSError:
            symlink_created = False
        else:
            symlink_created = True
        if symlink_created:
            for eid in ("seam-archaeologist", "sota-paper-researcher", "premise-attacker", "radical-simplifier"):
                self.run_cli(
                    "pitch", "--dir", tdir, "--entrant", eid,
                    "--title", f"T {eid}", "--thesis", "Body", "--gap-kind", "architecture",
                    "--receipt", "src/router.py:1",
                )
            self.run_cli(
                "judge", "--dir", tdir, "--match", "sf-1", "--winner", "seam-archaeologist",
                "--judge-model", "j", "--verified-receipt", "src/router.py:1", "--rationale", "ok",
            )
            self.run_cli(
                "judge", "--dir", tdir, "--match", "sf-2", "--winner", "premise-attacker",
                "--judge-model", "j", "--verified-receipt", "src/router.py:1", "--rationale", "ok",
            )
            self.run_cli(
                "judge", "--dir", tdir, "--match", "final", "--winner", "seam-archaeologist",
                "--judge-model", "j", "--verified-receipt", "src/router.py:1", "--rationale", "ok",
            )
            with self.assertRaises(SystemExit, msg="symlinked proposal.md must be refused"):
                self.run_cli("render", "--dir", tdir)
            self.assertFalse(outside_target.exists())

    def test_dropout_forfeits_empty_match_and_renders_walkovers_cleanly(self):
        _, raw = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "eight",
            "--prompt", "Explore SOTA designs", "--entrants", "8", "--json",
        )
        tdir = json.loads(raw)["dir"]
        for eid in ("seam-archaeologist", "sota-paper-researcher", "premise-attacker"):
            self.run_cli(
                "pitch", "--dir", tdir, "--entrant", eid,
                "--title", f"Title {eid}", "--thesis", f"Thesis {eid}.", "--gap-kind", "architecture",
                "--receipt", "src/router.py:1",
            )
        self.run_cli("dropout", "--dir", tdir, "--entrant", "data-state-architect", "--reason", "timed out")
        self.run_cli("dropout", "--dir", tdir, "--entrant", "oss-prior-art-hunter", "--reason", "timed out")
        self.run_cli("dropout", "--dir", tdir, "--entrant", "adjacent-capability-scout", "--reason", "timed out")
        self.run_cli("dropout", "--dir", tdir, "--entrant", "radical-simplifier", "--reason", "timed out")
        self.run_cli("dropout", "--dir", tdir, "--entrant", "failure-security-redteam", "--reason", "timed out")

        _, status_raw = self.run_cli("status", "--dir", tdir, "--json")
        status = json.loads(status_raw)
        self.assertEqual(status["ready_matches"], ["qf-1", "qf-2", "qf-3"])

        for qf_id, winner in (("qf-1", "seam-archaeologist"), ("qf-2", "sota-paper-researcher"), ("qf-3", "premise-attacker")):
            self.run_cli(
                "judge", "--dir", tdir, "--match", qf_id, "--winner", winner,
                "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
                "--rationale", "Sole active verified entrant.",
            )

        _, status_raw = self.run_cli("status", "--dir", tdir, "--json")
        self.assertEqual(json.loads(status_raw)["ready_matches"], ["sf-1", "sf-2"])

        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-1", "--winner", "sota-paper-researcher",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Stronger evidence.",
        )
        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-2", "--winner", "premise-attacker",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Walkover after qf-4 forfeit.",
        )
        self.run_cli(
            "judge", "--dir", tdir, "--match", "final", "--winner", "sota-paper-researcher",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Best overall architecture.",
        )

        code, md = self.run_cli("render", "--dir", tdir)
        self.assertEqual(code, 0)
        self.assertIn("advanced unopposed", md)
        self.assertIn("forfeited (all entrants dropped out)", md)
        self.assertNotIn("beat  (", md)

        _, raw2 = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "cascade-forfeit",
            "--prompt", "Explore SOTA designs", "--entrants", "8", "--json",
        )
        init2 = json.loads(raw2)
        tdir2 = init2["dir"]
        self.run_cli(
            "pitch", "--dir", tdir2, "--entrant", "seam-archaeologist",
            "--title", "Sole survivor", "--thesis", "Only active pitch.", "--gap-kind", "architecture",
            "--receipt", "src/router.py:1",
        )
        for ent in init2["entrants"][1:]:
            self.run_cli("dropout", "--dir", tdir2, "--entrant", ent["id"], "--reason", "timed out")
        self.run_cli(
            "judge", "--dir", tdir2, "--match", "qf-1", "--winner", "seam-archaeologist",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1", "--rationale", "Sole entrant.",
        )
        self.run_cli(
            "judge", "--dir", tdir2, "--match", "sf-1", "--winner", "seam-archaeologist",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1", "--rationale", "Unopposed semifinal.",
        )
        code2, _ = self.run_cli(
            "judge", "--dir", tdir2, "--match", "final", "--winner", "seam-archaeologist",
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1", "--rationale", "sf-2 forfeited cleanly.",
        )
        self.assertEqual(code2, 0)
        _, md2 = self.run_cli("render", "--dir", tdir2)
        self.assertIn("No opposing finalist survived upstream dropouts.", md2)

    def start_announced_init(self, slug, prompt, force=False):
        script = """
import sys
sys.path.insert(0, sys.argv[1])
import tournament
original = tournament.BracketLock.__enter__
def announced(lock):
    print('waiting for bracket lock', flush=True)
    return original(lock)
tournament.BracketLock.__enter__ = announced
tournament.main(sys.argv[2:])
"""
        proc = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(HERE), "init",
             "--root", str(self.repo), "--slug", slug, "--prompt", prompt,
             *(["--force"] if force else [])],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=20)
        self.addCleanup(cleanup)
        return proc

    def test_concurrent_initializers_respect_lock_and_only_one_creates_state(self):
        tdir = self.repo / ".scratch" / "tournaments" / "same-slug"
        tdir.mkdir(parents=True)
        with tournament.BracketLock(tdir / "bracket.lock"):
            procs = [self.start_announced_init("same-slug", title) for title in ("First", "Second")]
            for proc in procs:
                self.assertEqual(proc.stdout.readline().strip(), "waiting for bracket lock")
            self.assertFalse((tdir / "bracket.json").exists())
        outcomes = [(proc.communicate(timeout=20), proc.returncode) for proc in procs]
        self.assertEqual(sorted(code for _, code in outcomes), [0, 1])
        failed = next(output for output, code in outcomes if code != 0)
        self.assertIn("tournament already exists", failed[1])
        _, _, state = tournament.load_state(tdir)
        winning_prompt = ("First", "Second")[next(i for i, (_, code) in enumerate(outcomes) if code == 0)]
        self.assertEqual(state["prompt"], winning_prompt)

    def test_init_waits_for_pitch_transaction_with_and_without_force(self):
        _, raw = self.run_cli("init", "--root", str(self.repo), "--slug", "updating",
                              "--prompt", "Original", "--json")
        tdir = Path(json.loads(raw)["dir"])
        for force in (False, True):
            with self.subTest(force=force):
                with tournament.state_transaction(str(tdir)) as (_, _, state):
                    state["entrants"][0]["pitch"] = {"title": "Concurrent pitch"}
                    proc = self.start_announced_init("updating", "Replacement", force=force)
                    self.assertEqual(proc.stdout.readline().strip(), "waiting for bracket lock")
                    self.assertIsNone(proc.poll())
                _, stderr = proc.communicate(timeout=20)
                _, _, saved = tournament.load_state(tdir)
                if force:
                    self.assertEqual(proc.returncode, 0, stderr)
                    self.assertEqual(saved["prompt"], "Replacement")
                    self.assertIsNone(saved["entrants"][0]["pitch"])
                else:
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("tournament already exists", stderr)
                    self.assertEqual(saved["entrants"][0]["pitch"]["title"], "Concurrent pitch")

    def test_concurrent_pitch_processes_serialize_via_lock_without_lost_updates(self):
        _, raw = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "parallel",
            "--prompt", "Concurrent pitch stress test", "--entrants", "8", "--json",
        )
        init_out = json.loads(raw)
        tdir = init_out["dir"]
        script = str(HERE / "tournament.py")
        procs = [
            subprocess.Popen(
                [
                    sys.executable, "-B", script, "pitch",
                    "--dir", tdir,
                    "--entrant", ent["id"],
                    "--title", f"Concurrent {ent['id']}",
                    "--thesis", f"Parallel thesis from {ent['id']}.",
                    "--gap-kind", ent["default_gap_kind"],
                    "--receipt", "src/router.py:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for ent in init_out["entrants"]
        ]
        outcomes = [(proc.communicate(timeout=20)[1], proc.returncode) for proc in procs]
        for stderr, code in outcomes:
            self.assertEqual(code, 0, stderr)

        _, status_raw = self.run_cli("status", "--dir", tdir, "--json")
        status = json.loads(status_raw)
        self.assertEqual(status["pending_pitches"], [])
        self.assertEqual(status["ready_matches"], ["qf-1", "qf-2", "qf-3", "qf-4"])


if __name__ == "__main__":
    unittest.main()
