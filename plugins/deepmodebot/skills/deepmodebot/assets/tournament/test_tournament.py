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
            self.assertEqual(
                verdict["size"],
                case["size"],
                f"case {case['id']} sized as {verdict['size']}, expected {case['size']}",
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
            ("self-grill my checks and diff", {}, "self-grill"),
            ("grill my checks before opening a PR", {}, "self-grill"),
            ("audit my checks for check theater", {}, "self-grill"),
            ("sharpen this prompt before I run it", {}, "sharpen"),
            ("reflect on this session", {}, "reflect"),
            ("catch me up on auth refactors", {}, "recall"),
            ("what could this break in checkout?", {}, "blast-radius"),
            ("throw it in the arena", {}, "arena"),
            ("run an adversarial review on this diff", {}, "interrogate"),
            ("check domain invariants with SME review", {}, "sme-review"),
            ("ship this stack", {}, "shipping"),
            ("clean up merged worktrees", {}, "worktree-cleanup"),
            ("run a blinded eval on this skill", {}, "eval"),
            ("remove stale code comments from this diff", {}, "no-comments"),
            ("run no-comments on my branch", {}, "no-comments"),
            ("model-check our notification sync with TLA+ and draw a statechart", {}, "formal-verification"),
            ("prove this invariant for our retry queue", {}, "formal-verification"),
            ("run codebase gardening and ban this anti-pattern", {}, "correct"),
            ("fuzz the release build like a real user", {}, "swarm"),
            ("deepmode suggest", {}, "suggest"),
            ("suggest prompts for gaps and overclaims in this repo", {}, "suggest"),
            ("did we overclaim anything in our README?", {}, "suggest"),
            ("what should i fix next in this repo?", {}, "suggest"),
            ("review my prompt and convert it to a deepmode prompt", {}, "prompt-upgrade"),
            ("make my prompt better before running: fix auth naetc", {}, "prompt-upgrade"),
            ("upgrade my prompt to full scope", {}, "prompt-upgrade"),
            ("my worker has a memory leak and idle cpu hits 100%", {}, "runtime-forensics"),
            ("analyze this chrome cpuprofile and heap snapshot", {}, "trace-forensics"),
            ("get our search latency from 400ms down below 80ms step by step", {}, "hillclimb"),
            ("make the new checkout modal pixel-exact to the legacy CSS version", {}, "visual-parity"),
            ("rebuild our dashboard UI to match Linear quality", {}, "reference-rebuild"),
            ("quick throwaway prototype to test whether websockets beat SSE here", {}, "prototype"),
            ("pick up where the previous agent left off on this branch", {}, "session-pickup"),
            ("pause safely here so I can resume tomorrow", {}, "pause-safely"),
            ("teach me how the scheduler works", {}, "teach"),
            ("check if my tests are actually catching bugs or just mocking stuff", {}, "self-grill"),
            ("strip all the dumb comments from my diff", {}, "no-comments"),
            ("delete old merged worktrees", {}, "worktree-cleanup"),
            ("deploy terraform iam policy for s3 bucket", {}, "feature"),
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
        self.assertEqual(parsed["self_grill"], "both")
        self.assertEqual(parsed["effort"], "high")

        stripe_l = tournament.classify_prompt(
            "Add annual billing. Create a yearly price in Stripe, store each subscription's billing interval "
            "in Postgres with a migration, handle the webhook for plan changes, and show the interval on the account page."
        )
        self.assertEqual(stripe_l["size"], "L")
        self.assertEqual(stripe_l["self_grill"], "both")
        self.assertEqual(stripe_l["effort"], "xhigh")
        self.assertIn("gemini-4-flash", stripe_l["panel_seats"])
        self.assertIn("claude-haiku-5-5-high", stripe_l["panel_seats"])
        typo_s = tournament.classify_prompt("The quickstart in README.md says `npm run devv`. It should be `npm run dev`. Fix it.")
        self.assertEqual(typo_s["size"], "S")
        self.assertEqual(typo_s["self_grill"], "none")
        self.assertEqual(typo_s["model_tier"], "S")
        self.assertEqual(typo_s["effort"], "low")

    def test_tournament_delivery_constraints_override_default_checkpoint(self):
        cases = [
            ("Build me an AI app; run a tournament and let me choose before coding", "execute", True),
            ("Build me an AI app; run a tournament and wait for my approval", "execute", True),
            ("Build me an AI app; run a tournament, but get my approval before coding", "execute", True),
            ("Build me an AI app; run a tournament; obtain my permission before implementing", "execute", True),
            ("Rethink the architecture and implement it; my approval before coding is required", "execute", True),
            ("Run a tournament and build the winner; get my sign-off before you code", "execute", True),
            ("Run a tournament and build the winner; get my consent first", "execute", True),
            ("Run a tournament and implement approval checks", "execute", False),
            ("Build me an AI app; run a tournament, but do not implement yet", "execute", True),
            ("Build me an AI app; run a tournament, but don't code yet", "execute", True),
            ("Build me an AI app; run a tournament; only propose the winner", "execute", True),
            ("Rethink the architecture and implement it", "execute", False),
            ("Run a tournament and build the winner", "execute", False),
            ("Find architecture gaps, then implement the best proposal", "execute", False),
            ("Rethink the architecture and implement it; ask me before coding", "execute", True),
            ("Run a tournament to decide what to build next", "discover", True),
            ("Find architecture gaps before we build", "discover", True),
            ("Run a tournament; do not implement anything", "discover", True),
            ("Rethink the architecture without code changes", "discover", True),
            ("Run a tournament and create a proposal", "discover", True),
            ("Run a tournament and deliver a research report", "discover", True),
        ]
        for prompt, intent, checkpoint in cases:
            for empty in (False, True):
                with self.subTest(prompt=prompt, empty_dir=empty):
                    verdict = tournament.classify_prompt(prompt, empty_dir=empty)
                    self.assertEqual(verdict["mode"], "tournament")
                    self.assertEqual(verdict["intent"], intent)
                    self.assertEqual(verdict["checkpoint_before_code"], checkpoint)

    def test_routes_all_extended_playbooks_and_specialist_techniques(self):
        cases = [
            ("Run an SME review on our medical claims customer spec", "sme-review"),
            ("Check the sme_gate before Sprint 2", "sme-review"),
            ("Turn this vague goal into measurable milestones with goal-review", "goal-review"),
            ("Review my goal with three agents before running the loop", "goal-review"),
            ("Run the routing eval suite against our updated skill", "eval"),
            ("Compare this skill against baseline before promotion", "eval"),
            ("Hillclimb the parser throughput metric until it hits 50k/s", "hillclimb"),
            ("Optimize the pass rate in a loop using autoresearch", "hillclimb"),
            ("Record a visual E2E video of the invoice flow", "visual-e2e"),
            ("Export editable design evidence to Penpot", "open-design-evidence"),
            ("Explain native sibling messaging and agent-collaboration handoffs", "agent-collaboration"),
            ("Which tool should we use here? Check tool-routing", "tool-routing"),
            ("Build a quick prototype to settle the fork between SQLite and DuckDB", "prototype"),
            ("Open a PR for this branch with our proof", "opening-a-pr"),
            ("Ship this PR and verify trunk after merge", "shipping"),
            ("Pause safely and save a resume note before I step away", "pause-safely"),
            ("Pick up this handoff and continue from the resume note", "session-pickup"),
            ("Clean up stale git worktrees under .worktrees", "worktree-cleanup"),
            ("index / map workspace", "workspace-map"),
            ("index workspace", "workspace-map"),
            ("list Orca worktrees / open PRs", "workspace-map"),
            ("list Orca worktrees and open PRs", "workspace-map"),
            ("find symbol fast", "workspace-map"),
            ("search symbols for evaluate_manifest", "workspace-map"),
            ("Reach visual-parity with pixel-diff zero against the Figma mockup", "visual-parity"),
            ("Run a reference-rebuild to rebuild our UI to match Linear", "reference-rebuild"),
            ("Run runtime-forensics to diagnose why this live worker is wedged", "runtime-forensics"),
            ("Inspect this heap dump and CPU profile with trace-forensics", "trace-forensics"),
            ("Build spec #14 in incremental sprints", "phased-build"),
            ("auto-update local deepmodebot copies", "github-app"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt, expected=expected):
                verdict = tournament.classify_prompt(prompt)
                self.assertEqual(
                    verdict["mode"],
                    expected,
                    f"prompt {prompt!r} routed to {verdict['mode']} ({verdict['reason']}), expected {expected}",
                )

    def test_ordinary_engineering_prompts_do_not_misroute_to_false_positive_playbooks(self):
        non_matches = [
            ("Why do these queries contribute to high p99?", {}, "contribute"),
            ("Fix bug in UserFactory", {"has_factory": True}, "work-a-queue"),
            ("Fix crash when inline styles have quotes", {}, "refactoring"),
            ("Add a triage status column to the issues table", {}, "triage"),
            ("Add a retro arcade game page with score table", {}, "retro"),
            ("Add a tournament system for chess with an API endpoint and standings table", {}, "tournament"),
            ("Fix parser loop until OOM crash", {}, "run-a-goal"),
        ]
        for prompt, kwargs, forbidden in non_matches:
            with self.subTest(prompt=prompt, forbidden=forbidden):
                verdict = tournament.classify_prompt(prompt, **kwargs)
                self.assertNotEqual(
                    verdict["mode"],
                    forbidden,
                    f"prompt {prompt!r} falsely routed to {forbidden} ({verdict['reason']})",
                )


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

        self.run_cli(
            "pitch", "--dir", tdir, "--entrant", "seam-archaeologist",
            "--title", "Revised before judging", "--thesis", "A revised unjudged proposal.",
            "--gap-kind", "architecture", "--receipt", "src/router.py:1",
        )

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

        state_path = Path(tdir) / "bracket.json"
        judged_state = state_path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "already judged"):
            self.run_cli(
                "pitch", "--dir", tdir, "--entrant", "seam-archaeologist",
                "--title", "Substituted winner", "--thesis", "This thesis never faced the pod judge.",
                "--gap-kind", "architecture", "--receipt", "src/router.py:1",
            )
        self.assertEqual(state_path.read_bytes(), judged_state)

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

        final_state = state_path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "already judged"):
            self.run_cli(
                "pitch", "--dir", tdir, "--entrant", "sota-paper-researcher",
                "--title", "Substituted champion", "--thesis", "This thesis never faced the final judge.",
                "--gap-kind", "research", "--receipt", "src/router.py:1",
            )
        self.assertEqual(state_path.read_bytes(), final_state)

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
        self.assertIn("System proposal from sota-paper-researcher.", proposal)
        self.assertNotIn("Substituted champion", proposal)
        self.assertNotIn("This thesis never faced the final judge.", proposal)
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


    def test_render_and_status_include_full_ranked_portfolio_across_all_lenses(self):
        _, raw = self.run_cli(
            "init", "--root", str(self.repo), "--slug", "portfolio-all",
            "--prompt", "Surface all high-leverage bets", "--entrants", "4", "--json",
        )
        init_out = json.loads(raw)
        tdir = init_out["dir"]
        for ent in init_out["entrants"]:
            self.run_cli(
                "pitch", "--dir", tdir, "--entrant", ent["id"],
                "--title", f"Bet {ent['id']}",
                "--thesis", f"Distinct leverage thesis for {ent['id']}.",
                "--gap-kind", ent["default_gap_kind"],
                "--receipt", "src/router.py:1",
            )
        eids = [e["id"] for e in init_out["entrants"]]
        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-1", "--winner", eids[0],
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Strongest Pod A.", "--graft-from", eids[1], "--graft", "Keep streaming cursor.",
        )
        self.run_cli(
            "judge", "--dir", tdir, "--match", "sf-2", "--winner", eids[2],
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Strongest Pod B.",
        )
        self.run_cli(
            "judge", "--dir", tdir, "--match", "final", "--winner", eids[0],
            "--judge-model", "judge", "--verified-receipt", "src/router.py:1",
            "--rationale", "Best end-to-end leverage.",
        )
        _, st_raw = self.run_cli("status", "--dir", tdir, "--json")
        st = json.loads(st_raw)
        self.assertEqual(st["ranked_portfolio_count"], 4)
        self.assertEqual([p["entrant"] for p in st["ranked_portfolio"]][:2], [eids[0], eids[2]])

        _, md = self.run_cli("render", "--dir", tdir)
        self.assertIn("## Full Ranked High-Leverage Portfolio (4 pitched lenses)", md)
        for eid in eids:
            self.assertIn(f"Distinct leverage thesis for {eid}.", md)

if __name__ == "__main__":
    unittest.main()
