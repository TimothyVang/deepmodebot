import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5] if len(HERE.parents) > 5 else HERE
SPEC = importlib.util.spec_from_file_location("autoroute_mod", HERE / "autoroute.py")
autoroute = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = autoroute
SPEC.loader.exec_module(autoroute)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


class AutoRouteLoopTests(unittest.TestCase):
    def setUp(self):
        base_tmp = ROOT / ".scratch" / "tmp" if (ROOT / "scripts" / "check.py").is_file() else None
        if base_tmp is not None:
            base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="autoroute-test-", dir=str(base_tmp) if base_tmp else None)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test User")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "init")

    def run_cli(self, *args: str, stdin_text: str | None = None) -> tuple[int, str]:
        buf = io.StringIO()
        if stdin_text is not None:
            with contextlib.redirect_stdout(buf), unittest.mock.patch.object(sys, "stdin", io.StringIO(stdin_text)):
                code = autoroute.main(list(args))
        else:
            with contextlib.redirect_stdout(buf):
                code = autoroute.main(list(args))
        return code, buf.getvalue()

    def test_menu_discovers_live_catalog_and_marks_prior_advisory_only(self):
        code, raw = self.run_cli(
            "menu", "--root", str(self.repo), "--stdin", "--json",
            stdin_text="my worker has a memory leak and idle cpu hits 100%",
        )
        self.assertEqual(code, 0)
        packet = json.loads(raw)
        self.assertTrue(packet["advisory_only"])
        self.assertGreaterEqual(packet["catalog_counts"]["playbooks"], 29)
        self.assertGreaterEqual(packet["catalog_counts"]["techniques"], 51)
        self.assertIn("video-forensics (route_file:", packet["llm_router_prompt"])
        self.assertIn("runtime-forensics (route_file:", packet["llm_router_prompt"])
        self.assertNotIn("Advisory heuristic prior", packet["llm_router_prompt"])
        self.assertIn("runtime-forensics", packet["advisory_prior"]["specialized_hints"])

    def test_verify_rejects_hallucinated_route_and_under_sized_sensitive_work(self):
        bad_decision = {
            "decoded_intent": "Fix OAuth login token check",
            "deliverables": ["1. Fix OAuth login"],
            "primary_mode": "made-up-playbook",
            "route_file": "references/playbooks/made-up.md",
            "secondary_techniques": ["fake-tech"],
            "reference_skills": ["skill://nonexistent"],
            "size": "S",
            "self_grill": "none",
            "confidence": 0.95,
            "runner_up": "bug-fix",
            "why_not_runner_up": "n/a",
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", "fix oauth login token check",
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(bad_decision),
        )
        self.assertEqual(code, 2)
        res = json.loads(raw)
        self.assertEqual(res["status"], "REJECTED")
        joined = " ".join(res["violations"])
        self.assertIn("made-up-playbook", joined)
        self.assertIn("fake-tech", joined)
        self.assertIn("nonexistent", joined)
        self.assertIn("cannot be sized S", joined)

    def test_verify_triggers_critic_on_shallow_collapse_and_approves_after_critic_review(self):
        shallow = {
            "decoded_intent": "Diagnose worker memory leak and idle CPU spike",
            "deliverables": ["1. Find root cause of leak and CPU spike"],
            "primary_mode": "bug-fix",
            "route_file": "references/playbooks/bug-fix.md",
            "secondary_techniques": ["self-grill", "no-comments"],
            "reference_skills": [],
            "size": "M",
            "self_grill": "checks",
            "confidence": 0.85,
            "runner_up": "runtime-forensics",
            "why_not_runner_up": "Just fix it",
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", "my worker has a memory leak and idle cpu hits 100%",
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(shallow),
        )
        self.assertEqual(code, 2)
        res = json.loads(raw)
        self.assertEqual(res["status"], "CRITIC_REQUIRED")
        self.assertIn("runtime-forensics", " ".join(res["critic_reasons"]))
        self.assertIn("Adversarial Route Critic", res["critic_prompt"])

        revised = {
            "decoded_intent": "Diagnose live worker memory leak and idle CPU spike",
            "deliverables": ["1. Instrument and diagnose leak and idle CPU"],
            "primary_mode": "runtime-forensics",
            "route_file": "references/playbooks/runtime-forensics.md",
            "secondary_techniques": ["self-grill"],
            "reference_skills": [],
            "size": "none",
            "self_grill": "checks",
            "confidence": 0.94,
            "runner_up": "bug-fix",
            "why_not_runner_up": "Live memory and CPU symptom needs runtime instrumentation diagnosis first.",
            "critic_reviewed": True,
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", "my worker has a memory leak and idle cpu hits 100%",
            "--decision-stdin", "--critic-round", "2", "--strict", "--json",
            stdin_text=json.dumps(revised),
        )
        self.assertEqual(code, 0)
        res = json.loads(raw)
        self.assertEqual(res["status"], "APPROVED")
        self.assertEqual(res["locked_plan"]["route_file"], "references/playbooks/runtime-forensics.md")

    def test_verify_auto_attaches_missing_reference_skills_and_blocks_lazy_tournament(self):
        lazy = {
            "decoded_intent": "Fix React sidebar animation in src/sidebar.tsx",
            "deliverables": ["1. Fix animation"],
            "primary_mode": "tournament",
            "route_file": "references/techniques/tournament.md",
            "secondary_techniques": [],
            "reference_skills": [],
            "size": "none",
            "self_grill": "none",
            "confidence": 0.9,
            "runner_up": "bug-fix",
            "why_not_runner_up": "dunno",
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", "fix react sidebar animation in src/sidebar.tsx",
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(lazy),
        )
        self.assertEqual(code, 2)
        res = json.loads(raw)
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("tournament", " ".join(res["violations"]))
        self.assertIn("skill://frontend-ui", res["auto_repairs"].get("add_reference_skills", []))

    def test_hardcore_mode_default_blocks_sandbagging_and_allows_explicit_opt_out(self):
        ambitious_prompt = (
            "1. Upgrade src/shared/WorldGen.luau to a 3D Volumetric Density Field + Domain Warping + "
            "Droplet Hydraulic Erosion in Parallel Luau Actors. "
            "2. Add a pure-Luau 3D WFC Modular Architecture Solver. "
            "3. Replace Roblox Terrain with Surface Nets / Dual Contouring EditableMesh."
        )
        code, raw = self.run_cli("menu", "--root", str(self.repo), "--stdin", "--json", stdin_text=ambitious_prompt)
        self.assertEqual(code, 0)
        packet = json.loads(raw)
        self.assertTrue(packet["hardcore_mode"])
        self.assertTrue(packet["advisory_prior"]["hardcore_system_signal"])
        self.assertIn("HARDCORE MODE", packet["llm_router_prompt"])

        sandbagged = {
            "decoded_intent": "Make a tiny terrain tweak",
            "deliverables": ["1. Volumetric WorldGen", "2. 3D WFC Solver", "3. Dual Contouring EditableMesh"],
            "primary_mode": "feature",
            "route_file": "references/playbooks/feature.md",
            "secondary_techniques": [],
            "reference_skills": [],
            "size": "S",
            "self_grill": "none",
            "hardcore_mode": False,
            "confidence": 0.9,
            "runner_up": "phased-build",
            "why_not_runner_up": "smaller",
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", ambitious_prompt,
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(sandbagged),
        )
        self.assertEqual(code, 2)
        res = json.loads(raw)
        self.assertEqual(res["status"], "REJECTED")
        joined = " ".join(res["violations"])
        self.assertIn("Hardcore Mode is ON by default", joined)
        self.assertIn("cannot be under-sized to S", joined)

        hardcore_ok = {
            "decoded_intent": "Build 3D volumetric eroded WorldGen, 3D WFC solver, and Dual Contouring EditableMesh",
            "deliverables": ["1. Volumetric WorldGen", "2. 3D WFC Solver", "3. Dual Contouring EditableMesh"],
            "primary_mode": "phased-build",
            "route_file": "references/playbooks/phased-build.md",
            "secondary_techniques": ["self-grill", "no-comments"],
            "reference_skills": [],
            "size": "L",
            "self_grill": "both",
            "hardcore_mode": True,
            "hardcore_ceiling": "Parallel 3D density/erosion + 3D WFC + Dual Contouring EditableMesh with LODs",
            "confidence": 0.95,
            "runner_up": "feature",
            "why_not_runner_up": "Three coupled subsystems need phased architecture and verification.",
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", ambitious_prompt,
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(hardcore_ok),
        )
        self.assertEqual(code, 0)
        res = json.loads(raw)
        self.assertEqual(res["status"], "APPROVED")
        self.assertTrue(res["locked_plan"]["hardcore_mode"])
        self.assertIn("architect", res["locked_plan"]["secondary_techniques"])


    def test_shootout_regressions_dotenv_tla_negation_routefile_and_round1_critic_bypass(self):
        self.assertIsNotNone(autoroute.SENSITIVE_RE.search("Add API_URL to .env"))
        self.assertIsNotNone(autoroute.SENSITIVE_RE.search("Update .github/workflows/ci.yml"))
        self.assertIn("formal-verification", autoroute.detect_specialized_signals("Write a TLA+ spec"))
        self.assertIn("runtime-forensics", autoroute.detect_specialized_signals("fix cpu 100% spike"))
        self.assertIn("trace-forensics", autoroute.detect_specialized_signals("inspect .heapsnapshot"))
        self.assertFalse(autoroute.has_minimal_opt_out("Build 3D solver, do NOT ship a minimal MVP or quick hack"))
        self.assertTrue(autoroute.has_minimal_opt_out("just a typo in README"))

        spoof = {
            "decoded_intent": "spoof",
            "deliverables": ["1. spoof"],
            "primary_mode": "security-audit",
            "route_file": "../../../../README.md",
            "secondary_techniques": [],
            "reference_skills": [],
            "size": "none",
            "self_grill": "none",
            "confidence": 0.10,
            "runner_up": "pr-review",
            "why_not_runner_up": "test",
            "critic_reviewed": True,
        }
        code, raw = self.run_cli(
            "verify", "--root", str(self.repo), "--prompt", "run security audit",
            "--decision-stdin", "--strict", "--json",
            stdin_text=json.dumps(spoof),
        )
        self.assertEqual(code, 2)
        res = json.loads(raw)
        self.assertEqual(res["status"], "REJECTED")
        joined = " ".join(res["violations"])
        self.assertIn("does not match primary_mode", joined)
        self.assertIn("--critic-round 2", joined)

    def test_natural_grill_struggle_gaps_and_overclaims_phrases_route_cleanly(self):
        tn = autoroute._load_sibling("ar_tn_check", "tournament/tournament.py")
        self.assertEqual(tn.classify_prompt("grill it")["mode"], "grill")
        self.assertEqual(tn.classify_prompt("are you sure grill it")["mode"], "grill")
        self.assertEqual(tn.classify_prompt("grill my code")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("find gaps and overclaims")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("look for 100 gaps and 100 overclaims")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("what gaps did you miss")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("are there any overclaims here")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("are you sure")["mode"], "self-grill")
        self.assertEqual(tn.classify_prompt("im struggling with this it keeps breaking")["mode"], "bug-fix")
        self.assertEqual(tn.classify_prompt("im stuck idk why this doesnt work")["mode"], "bug-fix")
        self.assertIn("self-grill", autoroute.detect_specialized_signals("look for 100 gaps and 100 overclaims"))
        self.assertIn("grill", autoroute.detect_specialized_signals("are you sure grill it"))
        self.assertIsNotNone(autoroute.STRUGGLE_SIGNAL_RE.search("im struggling with this it keeps breaking"))

    def test_route_with_llm_runs_semantic_decision_and_round2_critic_and_blocks_omp(self):
        calls = []

        def fake_llm(prompt_text: str, round_no: int) -> str:
            calls.append(round_no)
            if round_no == 1:
                return json.dumps({
                    "decoded_intent": "Reverse-engineer reference video shot by shot into VIDEO.md",
                    "deliverables": ["1. Run rea-video survey/decompose and validate VIDEO.md"],
                    "primary_mode": "feature",
                    "route_file": "references/playbooks/feature.md",
                    "secondary_techniques": ["self-grill", "no-comments"],
                    "reference_skills": [],
                    "size": "M",
                    "self_grill": "checks",
                    "confidence": 0.65,
                    "runner_up": "video-forensics",
                    "why_not_runner_up": "unsure",
                })
            return "```json\n" + json.dumps({
                "decoded_intent": "Reverse-engineer reference video shot by shot into VIDEO.md",
                "deliverables": ["1. Run rea-video survey/decompose and validate VIDEO.md"],
                "primary_mode": "video-forensics",
                "route_file": "references/techniques/video-forensics.md",
                "secondary_techniques": ["self-grill"],
                "reference_skills": ["skill://frontend-ui"],
                "size": "none",
                "self_grill": "checks",
                "confidence": 0.96,
                "runner_up": "scrape",
                "why_not_runner_up": "User wants shot-by-shot filmed/AI/code breakdown in VIDEO.md format.",
            }) + "\n```"

        res = autoroute.route_with_llm(
            "reverse-engineer this promo video shot by shot with rea-video into VIDEO.md",
            root=self.repo,
            llm_runner=fake_llm,
        )
        self.assertEqual(res["status"], "APPROVED")
        self.assertEqual(res["rounds_used"], 2)
        self.assertEqual(
            res["locked_plan"]["decoded_intent"],
            "Reverse-engineer reference video shot by shot into VIDEO.md",
        )
        self.assertEqual(calls, [1, 2])
        self.assertEqual(res["locked_plan"]["primary_mode"], "video-forensics")
        self.assertEqual(res["locked_plan"]["route_file"], "references/techniques/video-forensics.md")

        with self.assertRaises(SystemExit):
            autoroute._resolve_subscription_harness("omp")
    def test_reroute_escalates_on_sensitive_diff_and_two_failed_attempts(self):
        (self.repo / "src" / "auth.py").write_text("def check(tok):\n    return bool(tok)\n", encoding="utf-8")
        code, raw = self.run_cli(
            "reroute", "--root", str(self.repo), "--current-mode", "bug-fix",
            "--current-size", "S", "--failed-attempts", "2", "--competing-shapes", "2", "--json",
        )
        self.assertEqual(code, 0)
        res = json.loads(raw)
        self.assertTrue(res["reroute_needed"])
        self.assertEqual(res["recommended_size"], "M")
        self.assertEqual(res["recommended_mode"], "investigation")
        self.assertIn("security-audit", res["add_techniques"])
        self.assertIn("architect", res["add_techniques"])


    def test_prosecutor_regressions_subpath_traversal_json_prose_sandboxing_and_backend_perf(self):
        bad_dec = {
            "decoded_intent": "Test subpath traversal",
            "deliverables": ["1. Check"],
            "primary_mode": "feature",
            "route_file": "references/playbooks/feature.md",
            "secondary_techniques": "self-grill",
            "reference_skills": [
                "skill://frontend-ui/../../../../etc/passwd",
                "skill://frontend-ui/references/nonexistent.md",
            ],
            "size": "M",
            "self_grill": "checks",
            "confidence": 0.95,
            "runner_up": "bug-fix",
            "why_not_runner_up": "Feature work.",
        }
        ver = autoroute.verify_decision(bad_dec, prompt="build UI", root=self.repo)
        self.assertEqual(ver["status"], "REJECTED")
        joined = " ".join(ver["violations"])
        self.assertIn("secondary_techniques must be a JSON list", joined)
        self.assertIn("escapes skill root", joined)
        self.assertIn("does not exist on disk", joined)

        parsed = autoroute._extract_json_object('Thinking about {prompt} and {context}...\n{"primary_mode": "perf-issue", "size": "M"}')
        self.assertEqual(parsed["primary_mode"], "perf-issue")

        perf_prompt = "Optimize FastAPI /orders: fix N+1 ORM queries, sync event-loop blocking, and slow JSON serialization"
        self.assertIn("perf-issue", autoroute.detect_specialized_signals(perf_prompt))
        catalog = autoroute.discover_live_catalog(root=self.repo)
        refs = autoroute.detect_expected_reference_skills(perf_prompt, catalog["sibling_skills"])
        self.assertIn("skill://domain-rules", refs)
        self.assertIn("skill://software-architecture", refs)


    def test_quota_budget_anti_stacking_and_lean_mode_in_locked_plan(self):
        ok_dec = {
            "decoded_intent": "Implement caching layer without killing weekly usage",
            "deliverables": ["1. Implement caching layer"],
            "primary_mode": "feature",
            "route_file": "references/playbooks/feature.md",
            "secondary_techniques": ["self-grill", "no-comments"],
            "reference_skills": ["skill://agent-harnesses"],
            "size": "L",
            "self_grill": "both",
            "hardcore_mode": True,
            "hardcore_ceiling": "Zero-allocation LRU cache with deterministic eviction tests",
            "confidence": 0.94,
            "runner_up": "perf-issue",
            "why_not_runner_up": "Net-new feature build.",
        }
        lean_ver = autoroute.verify_decision(
            ok_dec,
            prompt="Implement caching layer without killing weekly usage",
            root=self.repo,
        )
        self.assertEqual(lean_ver["status"], "APPROVED")
        qb = lean_ver["locked_plan"]["quota_budget"]
        self.assertEqual(qb["budget_mode"], "lean-single-bundle")
        self.assertEqual(qb["max_review_subagents"], 1)
        self.assertEqual(lean_ver["locked_plan"]["panel_seats"], [])
        self.assertEqual(qb["subagent_models"]["scout"], "flash_lite")
        self.assertEqual(qb["subagent_models"]["comment-sicko"], "flash")
        self.assertEqual(qb["subagent_models"]["reviewer"], "flash")
        self.assertEqual(qb["subagent_models"]["security-reviewer"], "flash")
        self.assertEqual(qb["subagent_models"]["panel_verifier"], "flash")
        with unittest.mock.patch.dict("os.environ", {"TEAMWORK_RUN_ID": "tw-777"}):
            nested_ver = autoroute.verify_decision(ok_dec, prompt="Implement caching layer", root=self.repo)
        self.assertEqual(nested_ver["status"], "APPROVED")
        nqb = nested_ver["locked_plan"]["quota_budget"]
        self.assertTrue(nqb["nested_anti_stacking"])
        self.assertEqual(nqb["max_subagents_per_task"], 0)
        self.assertEqual(nested_ver["locked_plan"]["panel_seats"], [])

    def test_specialized_signal_detects_adversarial_research_and_gap_matrix(self):
        sigs = autoroute.detect_specialized_signals("/research SOTA gaps in our repo vs cloudflare/agents")
        self.assertIn("research", sigs)
        cat = autoroute.discover_live_catalog(root=self.repo)
        self.assertIn("research", cat["sibling_skills"])

    def test_menu_includes_pre_flight_clarification_gate_for_zero_thought_deep_autopilot(self):
        _, raw_vague = self.run_cli("menu", "--root", str(self.repo), "--stdin", "--json", stdin_text="improve this")
        pkt_vague = json.loads(raw_vague)
        self.assertTrue(pkt_vague["pre_flight_clarification"]["needs_clarification"])

        _, raw_clear = self.run_cli("menu", "--root", str(self.repo), "--stdin", "--json", stdin_text="fix bug in src/app.py")
        pkt_clear = json.loads(raw_clear)
        self.assertFalse(pkt_clear["pre_flight_clarification"]["needs_clarification"])
if __name__ == "__main__":
    unittest.main()
