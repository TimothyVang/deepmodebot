#!/usr/bin/env python3
"""Pure LLM semantic auto-routing loop with live disk catalog discovery and deterministic checks & balances.

    python autoroute.py route --root <repo> --stdin [--harness auto|agy|claude|codex] [--json] <<'EOF'
    python autoroute.py menu --root <repo> --stdin [--json] <<'EOF'
    python autoroute.py verify --root <repo> --prompt <text> --decision-stdin [--critic-round 2] [--strict] [--json] <<'EOF'
    python autoroute.py reroute --root <repo> --current-mode <mode> --current-size <size> [--failed-attempts N] [--json]
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.dont_write_bytecode = True

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SKILL_DIR = Path(__file__).resolve().parents[2]
PLUGINS_SKILLS_DIR = SKILL_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"

READ_ONLY_MODES = frozenset({
    "investigation", "runtime-forensics", "trace-forensics", "triage",
    "pr-review", "grill", "self-grill", "tournament", "research", "flows",
    "architecture-review", "retro", "course", "questionnaire", "re-explain",
    "security-audit", "pr-agent", "blast-radius", "sharpen", "reframe", "reflect", "recall", "catchup-video",
    "interrogate", "sme-review", "formal-verification", "statechart", "prior-art", "wizard",
    "scrape", "suggest", "teach", "why", "how", "autoroute",
    "goal-review", "workspace-map", "open-design-evidence", "deep-stack",
})

FLEXIBLE_SIZE_MODES = frozenset({
    "eval", "arena", "prompt-upgrade", "self-authoring", "video-forensics", "gen-ui", "webhook-ui", "model-setup",
    "pause-safely", "triage", "inner-loop", "tool-routing", "agent-collaboration", "visual-e2e",
    "create-verification-skill", "maintain-verification-skill",
    "create-formal-verification-skill", "maintain-formal-verification-skill",
})

SENSITIVE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\.env\b|\.github/workflows\b)"
    r"|\b(?:auth|oauth|jwt|session|token|tokens|secret|secrets|password|passwords|credential|credentials"
    r"|rbac|acl|permission|permissions|migration|migrations|stripe|billing|payment|payments|webhook|webhooks"
    r"|security|encrypt|decrypt|crypto|signature|ci\s+(?:workflow|pipeline|config|yaml|yml)"
    r"|hooks?\.json|mcp_config|agents\.md|claude\.md|env\s+var|trust\s+boundary|sanitiz\w*|parser)\b",
    re.I,
)

MINIMAL_OPT_OUT_TOKEN_RE = re.compile(
    r"\b(?:minimal\s+(?:fix|patch|change|diff|mvp)|quick\s+(?:spike|hack|fix|typo)|throwaway\s+(?:prototype|spike)"
    r"|just\s+a\s+typo|one[- ]line\s+(?:fix|tweak)|tiny\s+(?:fix|tweak)|no\s+hardcore|skip\s+hardcore)\b",
    re.I,
)
NEGATION_CLAUSE_RE = re.compile(
    r"\b(?:no|not|never|without|don'?t|do\s+not|avoid|instead\s+of|refuse|forbid)\b",
    re.I,
)

HARDCORE_SYSTEM_RE = re.compile(
    r"\b(?:hardcore\s+mode|volumetric|density\s+field|domain\s+warp|hydraulic\s+erosion|wave\s+function\s+collapse"
    r"|wfc|dual\s+contouring|surface\s+nets|editablemesh|voxel\s+mesh|parallel\s+luau|actor\s+pool"
    r"|custom\s+(?:engine|compiler|solver|renderer|scheduler|allocator|mesher)|distributed\s+consensus"
    r"|zero[- ]copy|lock[- ]free|full\s+rewrite|from\s+scratch|real[- ]time\s+physics|procedural\s+generation"
    r"|n\+1|query\s+plan|connection\s+pool|backpressure|transactional\s+outbox|singleflight|cursor\s+pagination"
    r"|tail\s+latency|simd|arena\s+allocator|ring\s+buffer|flat\s+hash)\b",
    re.I,
)

STRUGGLE_SIGNAL_RE = re.compile(
    r"\b(?:i'?m\s+(?:struggling|stuck)|struggling\s+with|stuck\s+on|keeps?\s+(?:breaking|failing|crashing)"
    r"|still\s+(?:broken|not\s+working|failing)|idk\s+why\b.*\b(?:work|broken|fail)|tried\s+\d+\s+times)\b",
    re.I,
)

LEAN_QUOTA_RE = re.compile(
    r"\b(?:lean\s+mode|quota[- ]safe|save\s+(?:weekly\s+)?(?:usage|quota|tokens)"
    r"|low\s+token|without\s+(?:burning|killing)\s+(?:weekly\s+)?(?:quota|usage))\b",
    re.I,
)

SPECIALIZED_SIGNALS = (
    ("gen-ui", re.compile(r"\b(?:a2ui|gen[- ]ui|generative\s+ui)\b|\b(?:interactive|visual)\s+(?:cockpit|surface|ui)\b.{0,35}\b(?:human|talk|visualize|decisions?|prompts?)\b", re.I)),
    ("video-forensics", re.compile(r"\b(?:rea[- ]video|videomd|video\.md)\b|\b(?:reverse[- ]engineer|break\s+down|remake|deconstruct)\b.{0,35}\bvideo\b|\bis\s+this\s+video\s+ai\b", re.I)),
    ("runtime-forensics", re.compile(r"\b(?:memory\s+leak|leaking\s+ram|idle\s+cpu|cpu\s+(?:spike|stuck)\b|freez(?:e|es|ing)\b|hangs?\b|oom\b)|\bcpu\s+100%(?![A-Za-z0-9_])", re.I)),
    ("trace-forensics", re.compile(r"(?<![A-Za-z0-9_])\.(?:cpuprofile|heapsnapshot)\b|\b(?:cpuprofile|heap\s+snapshot|chrome\s+trace|flamegraph)\b", re.I)),
    ("perf-issue", re.compile(r"\b(?:\d+(?:\.\d+)?x\s+slower|got\s+slower|slowness|latency\s+(?:spike|regression)|p9[59]\b.{0,30}\b(?:ms|s|slow|high|jumped)|n\+1\b|(?:optimize|speed\s+up)\b.{0,45}\b(?:endpoint|route|query|queries|api|backend|server|throughput|latency|serialization|pool))\b", re.I)),
    ("hillclimb", re.compile(r"\b(?:hillclimb|from\s+\d+\s*(?:ms|s|%)\s+(?:down\s+)?(?:to|below|under)\s+\d+|below\s+\d+\s*ms|step\s+by\s+step.*(?:latency|accuracy|throughput))", re.I)),
    ("visual-parity", re.compile(r"\b(?:pixel[- ]exact|pixel\s+diff|visual\s+parity|pixel[- ]for[- ]pixel)\b", re.I)),
    ("reference-rebuild", re.compile(r"\b(?:rebuild\b.*\b(?:match|like)\s+[A-Z][a-z]+|to\s+the\s+standard\s+of)\b")),
    ("prototype", re.compile(r"\b(?:throwaway\s+(?:prototype|spike)|quick\s+spike|prototype\b.*\b(?:test\s+whether|beats?|compare))\b", re.I)),
    ("session-pickup", re.compile(r"\b(?:pick\s+up\s+where\s+(?:the\s+)?(?:previous|last)\s+agent|take\s+over\b.*\bin[- ]flight)\b", re.I)),
    ("pause-safely", re.compile(r"\b(?:pause\s+safely|checkpoint\s+and\s+pause|resume\s+tomorrow)\b", re.I)),
    ("reframe", re.compile(r"(?:^\s*/?reframe\b|\b(?:expert\s+words\s+for\s+what\s+(?:i'?m|we'?re)\s+building|what\s+is\s+this\s+problem\s+called|teach\s+(?:me\s+)?the\s+expert\s+(?:words|terms|vocabulary))\b)", re.I)),
    ("catchup-video", re.compile(r"\b(?:catchup[- ]video|catch[- ]up\s+video|subtitled\s+(?:catch[- ]?up\s+|recap\s+)?video|video\s+recap\s+of\s+what\s+happened)\b", re.I)),
    ("webhook-ui", re.compile(r"\b(?:webhook[- ]ui|make[- ]bot[- ]ui)\b|\b(?:custom|tailscale|local)\s+(?:ui|page|dashboard|buttons?)\b.{0,45}\b(?:wake|trigger|post\s+to)\b.{0,30}\bwebhook\b", re.I)),
    ("model-setup", re.compile(r"\b(?:model[- ]setup|per[- ]role\s+models?|configure\s+(?:my\s+|role\s+)?models?\s+(?:and\s+)?(?:reasoning\s+)?budget)\b", re.I)),
    ("statechart", re.compile(r"(?:^\s*/?statechart\b|\b(?:tla\+?\s+statechart|mermaid\s+statechart\b.*\bcounterexample|draw\b.*\btla\+?\s+model\s+as\s+a?\s*statechart)\b)", re.I)),
    ("formal-verification", re.compile(r"\btla\+(?![A-Za-z0-9_])|\b(?:tlc|statechart|lean\s*4?|lean\s+proof|mathlib|coq|rocq|isabelle|smt2|z3|comparator|nanoda|bombadil|model[- ]check|property[- ]based\s+ui|(?:formalize|prove)\s+(?:this|the)\s+(?:theorem|lemma|conjecture|invariant))\b|(?<![A-Za-z0-9_])\.(?:lean|tla|smt2)\b", re.I)),
    ("suggest", re.compile(r"\b(?:deepmode\s+suggest|suggest\s+(?:me\s+)?(?:some\s+)?(?:full[- ]scope\s+)?prompts?|what\s+prompts?\s+should\s+i\s+run|what\s+should\s+i\s+(?:fix|work\s+on)\s+next)\b", re.I)),
    ("prompt-upgrade", re.compile(r"\b(?:make\s+my\s+prompt\s+better|(?:review|improve|upgrade|rewrite|fix)\s+(?:my|this)\s+prompt|convert\b.*\bdeepmode\s*prompt)\b", re.I)),
    ("grill", re.compile(r"(?:^\s*grill(?:\s+(?:it|this|me))?\s*[?!.]*$|(?:\bare\s+you\s+sure\W+grill\b)|\bgrill\s+(?:me|this\s+plan|my\s+plan|our\s+plan|it)\b|\bpoke\s+holes\s+in\b)", re.I)),
    ("self-grill", re.compile(r"\b(?:self[- ]grill|check\s+theater|mocking\s+stuff|tests\s+are\s+actually\s+catching|grill\s+(?:my|our|the|this)\s+(?:checks?|diff|tests?|code|work|implementation)|(?:find|look\s+for|hunt(?:\s+for)?|check\s+for)\s+(?:\d+\s+)?(?!(?:architecture|architectural|research)\s+gaps?\b)gaps?\b|(?<!suggest\s)overclaims?\b|what\s+(?:gaps?\s+)?did\s+(?:you|we)\s+miss|^are\s+you\s+sure\s*[?!.]*$)", re.I)),
    ("no-comments", re.compile(r"\b(?:no[- ]comments|comment[- ]sicko|(?:strip|remove|delete|clean)\b.{0,30}\bcomments)\b", re.I)),
    ("worktree-cleanup", re.compile(r"\b(?:clean\s+up|prune|delete|remove)\b.{0,25}\bworktrees?\b", re.I)),
)

REFERENCE_SKILL_SIGNALS = (
    ("skill://frontend-ui", re.compile(r"\b(?:react|next\.?js|css|tailwind|shadcn|ui|ux|a2ui|vibe[- ]coded|ai\s+studio|sidebar|modal|animation|animations|remotion|hyperframes|figma|pixel|a11y|accessibility|dashboard|layout|chat\s+ui)\b", re.I)),
    ("skill://secrets-and-auth", re.compile(r"(?<![A-Za-z0-9_])\.env\b|\b(?:auth|oauth|jwt|login|password|secret|secrets|credential|credentials|mfa|sso|api\s+key|rbac|session\s+token)\b", re.I)),
    ("skill://software-architecture", re.compile(r"\b(?:postgres|sqlite|mysql|database|schema|migration|monorepo|queue|redis|kafka|microservice|api\s+design|data\s+model|domain\s+model|orm|prisma|drizzle|sqlalchemy|pgx|asyncpg|npgsql|foreign\s+key|n\+1|pagination|cursor|connection\s+pool|outbox|timeout|backpressure)\b", re.I)),
    ("skill://cloud-devsecops", re.compile(r"\b(?:docker|kubernetes|k8s|terraform|iac|aws|gcp|azure|iam|s3|bucket|ci/cd|github\s+actions|container|helm)\b", re.I)),
    ("skill://agent-harnesses", re.compile(r"\b(?:omp|claude\s+code|codex|antigravity|mcp|acp|a2a|ag[- ]ui|a2ui|webmcp|subagent|subagents|teamwork|weekly\s+usage|quota|hooks\.json|skill\.md)\b", re.I)),
    ("skill://domain-rules", re.compile(r"\b(?:llm|rag|evals?|rate\s+limit|distributed|concurrency|race\s+condition|deadlock|caching|idempoten\w*|incident|legacy\s+code|backend|server|endpoint|fastapi|starlette|express|axum|tokio|goroutine|event\s+loop|n\+1|tail\s+latency|p9[59]|throughput|rps|serialization|orjson|gzip|cache\s+stampede|singleflight|simd|cache\s+line|arena|unordered_map)\b", re.I)),
    ("skill://deep-stack", re.compile(r"\b(?:what\s+stack|tech\s+stack|pick\s+a\s+stack|choose\s+a\s+stack|greenfield\s+stack)\b", re.I)),
)

CONCRETE_ANCHOR_RE = re.compile(
    r"(?:[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,6}\b|#\d+\b|https?://\S+|\bPR\s*#?\d+\b)",
    re.I,
)

DEFAULT_PANEL_SEATS = [
    "claude-fable-5-2-high",
    "claude-opus-5-5-high-fast",
    "gemini-4-neon-xhigh",
]

STRIPPED_API_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)


def _load_sibling(name: str, rel_path: str):
    path = ASSETS_DIR / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def has_minimal_opt_out(text: str) -> bool:
    for m in MINIMAL_OPT_OUT_TOKEN_RE.finditer(text):
        tok = m.group(0).lower()
        if tok in ("no hardcore", "skip hardcore"):
            return True
        clause_prefix = re.split(r"[.;!?]", text[: m.start()])[-1]
        if NEGATION_CLAUSE_RE.search(clause_prefix):
            continue
        return True
    return False


def _first_summary_line(md_path: Path) -> str:
    try:
        lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    body_start = 0
    if lines and lines[0].strip() == "---":
        end_idx = None
        for idx in range(1, min(len(lines), 30)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break
        if end_idx is not None:
            body_start = end_idx + 1
            for idx in range(1, end_idx):
                m = re.match(r'^description:\s*(.*)$', lines[idx])
                if m:
                    val = m.group(1).strip().strip('"').strip("'")
                    if val in (">", "|", ">-", "|-", ""):
                        collected = []
                        for sub in lines[idx + 1 : end_idx]:
                            if sub.startswith((" ", "\t")) and sub.strip():
                                collected.append(sub.strip())
                            else:
                                break
                        if collected:
                            return " ".join(collected)[:140]
                    elif val:
                        return val[:140]
    for line in lines[body_start : body_start + 15]:
        s = line.strip()
        if not s or s.startswith("#") or s == "---":
            continue
        return s[:140]
    return ""


def discover_live_catalog(root: Path | None = None) -> dict:
    playbooks: dict[str, dict] = {}
    techniques: dict[str, dict] = {}
    references: dict[str, dict] = {}
    sibling_skills: dict[str, dict] = {}

    pb_dir = SKILL_DIR / "references" / "playbooks"
    if pb_dir.is_dir():
        for md in sorted(pb_dir.glob("*.md")):
            playbooks[md.stem] = {
                "kind": "playbook",
                "file": f"references/playbooks/{md.name}",
                "dir": SKILL_DIR,
                "summary": _first_summary_line(md),
            }

    tech_dir = SKILL_DIR / "references" / "techniques"
    if tech_dir.is_dir():
        for md in sorted(tech_dir.glob("*.md")):
            techniques[md.stem] = {
                "kind": "technique",
                "file": f"references/techniques/{md.name}",
                "dir": SKILL_DIR,
                "summary": _first_summary_line(md),
            }

    if (SKILL_DIR / "references" / "flows.md").is_file():
        references["flows"] = {
            "kind": "reference",
            "file": "references/flows.md",
            "dir": SKILL_DIR,
            "summary": _first_summary_line(SKILL_DIR / "references" / "flows.md"),
        }

    if PLUGINS_SKILLS_DIR.is_dir():
        for smd in sorted(PLUGINS_SKILLS_DIR.glob("*/SKILL.md")):
            name = smd.parent.name
            if name == SKILL_DIR.name:
                continue
            sibling_skills[name] = {
                "kind": "skill",
                "file": f"skill://{name}",
                "dir": smd.parent,
                "summary": _first_summary_line(smd),
            }

    if root is not None and root.is_dir():
        for base in (".omp/skills", ".claude/skills", ".agents/skills"):
            sdir = root / base
            if sdir.is_dir():
                for smd in sorted(sdir.glob("*/SKILL.md")):
                    name = smd.parent.name
                    if name not in sibling_skills and name != SKILL_DIR.name:
                        sibling_skills[name] = {
                            "kind": "project-skill",
                            "file": f"skill://{name}",
                            "dir": smd.parent,
                            "summary": _first_summary_line(smd),
                        }

    all_modes: dict[str, dict] = {}
    all_modes.update(playbooks)
    all_modes.update(techniques)
    all_modes.update(references)
    all_modes.update(sibling_skills)

    return {
        "playbooks": playbooks,
        "techniques": techniques,
        "references": references,
        "sibling_skills": sibling_skills,
        "all_modes": all_modes,
    }


def gather_repo_facts(root: Path | None) -> dict:
    if root is None:
        return {"has_root": False}
    self_grill = _load_sibling("ar_self_grill", "self-grill/self_grill.py")
    safe_root = self_grill.reject_unsafe_root(root)
    diff = self_grill.inspect_diff(safe_root)
    verify_skills = []
    for base in (".omp/skills", ".claude/skills", ".agents/skills"):
        d = safe_root / base
        if d.is_dir():
            for child in sorted(d.glob("verify-*/SKILL.md")):
                verify_skills.append(child.relative_to(safe_root).as_posix())
    entries = [
        p.name for p in safe_root.iterdir()
        if p.name not in {".git", ".scratch", ".worktrees", ".DS_Store"}
    ]
    return {
        "has_root": True,
        "root": str(safe_root),
        "empty_dir": len(entries) == 0,
        "has_factory": (safe_root / "factory.json").is_file(),
        "has_glossary_or_adrs": (safe_root / "GLOSSARY.md").is_file() or (safe_root / "docs" / "adr").is_dir(),
        "verify_skills": verify_skills,
        "diff_size": diff["measured_size"],
        "diff_files": diff["file_count"],
        "diff_sensitive_paths": diff["sensitive_paths"][:10],
        "diff_added_comments": diff["added_comment_count"],
        "diff_workaround_smells": diff["workaround_smell_count"],
    }


def detect_expected_reference_skills(prompt: str, available_skills: dict[str, dict] | None = None) -> list[str]:
    hits = []
    for skill_uri, pat in REFERENCE_SKILL_SIGNALS:
        sname = skill_uri.removeprefix("skill://")
        if available_skills is not None and sname not in available_skills:
            continue
        if pat.search(prompt):
            hits.append(skill_uri)
    return hits


def detect_specialized_signals(prompt: str) -> list[str]:
    hits = []
    for mode, pat in SPECIALIZED_SIGNALS:
        if pat.search(prompt):
            hits.append(mode)
    return hits


def build_menu_packet(prompt: str, root: Path | None = None) -> dict:
    cleaned = " ".join(prompt.strip().split())
    if not cleaned:
        raise SystemExit("prompt cannot be empty")
    repo_facts = gather_repo_facts(root)
    safe_root = Path(repo_facts["root"]) if repo_facts.get("has_root") else None
    catalog = discover_live_catalog(root=safe_root)
    tournament = _load_sibling("ar_tournament", "tournament/tournament.py")
    prior = tournament.classify_prompt(
        cleaned,
        has_factory=bool(repo_facts.get("has_factory")),
        empty_dir=bool(repo_facts.get("empty_dir")),
    )
    ref_hints = detect_expected_reference_skills(cleaned, catalog["sibling_skills"])
    spec_hints = detect_specialized_signals(cleaned)

    compact_playbooks = [f"{k} (route_file: {v['file']}): {v['summary']}" for k, v in catalog["playbooks"].items()]
    compact_techniques = [f"{k} (route_file: {v['file']}): {v['summary']}" for k, v in catalog["techniques"].items()]
    compact_ref_skills = [f"{k} (route_file: {v['file']}): {v['summary']}" for k, v in catalog["sibling_skills"].items()]

    minimal_opt_out = has_minimal_opt_out(cleaned)
    hardcore_default = not minimal_opt_out
    hardcore_system_hit = bool(HARDCORE_SYSTEM_RE.search(cleaned))

    schema = {
        "decoded_intent": "1-sentence semantic restatement of what the user actually wants",
        "deliverables": ["1. concrete deliverable", "2. ..."],
        "primary_mode": "exact mode name from Playbooks, Techniques, or Sibling Skills",
        "route_file": "exact route_file from the catalog",
        "secondary_techniques": ["optional companion technique names, e.g. self-grill, no-comments, security-audit"],
        "reference_skills": ["optional skill://<name> URIs from Reference & Sibling Skills"],
        "size": "S | M | L | none",
        "self_grill": "none | plan | checks | both",
        "hardcore_mode": hardcore_default,
        "hardcore_ceiling": "1-sentence first-principles maximal-craft engineering target (never a watered-down MVP)",
        "confidence": 0.9,
        "runner_up": "closest alternative mode name",
        "why_not_runner_up": "concrete reason primary_mode beats runner_up",
        "needs_prompt_upgrade": False,
        "hard_stops": [],
    }

    llm_router_prompt = (
        "You are deepmodebot's LLM semantic auto-router in HARDCORE MODE by default. "
        "Read what the user literally typed — including typos, shorthand, compound asks, frustration/struggle, "
        "skepticism ('are you sure', 'grill', 'what did you miss', 'find gaps/overclaims'), media/video breakdown "
        "requests ('rea-video', 'VIDEO.md', 'how was this video made', 'remake this video'), or multi-system builds — "
        "and choose the best primary_mode, companion techniques, reference_skills, size, and self_grill mode purely from "
        "semantic understanding against the live catalog below (never naive keyword matching).\n"
        "Routing guidance:\n"
        "- Hardcore Mode is ON by default: aim straight for the first-principles architectural ceiling and promote any "
        "'(Optional hardcore mode)' tier into a mandatory deliverable unless the user explicitly asked for a minimal fix or throwaway prototype.\n"
        "- Read-only/discovery/audit modes (investigation, runtime-forensics, trace-forensics, pr-review, grill, self-grill, "
        "tournament, suggest, formal-verification, etc.) MUST use size='none'.\n"
        "- If the user doubts prior work ('are you sure', 'what did you miss', 'find gaps/overclaims'), route to 'self-grill' "
        "(Confession + Adaptive Hotspot Prosecutor + Sieve). If stress-testing a plan/idea ('grill it', 'grill this plan'), route to 'grill'.\n"
        "- If the user is stuck or struggling ('keeps breaking', 'stuck', 'doesn't work'), route to 'bug-fix' (or 'runtime-forensics') "
        "at size M/L with secondary_techniques including 'self-grill' and 'why'.\n"
        "- If breaking down or remaking a video, route to 'video-forensics' (plus skill://frontend-ui when remaking motion graphics).\n"
        "- If building Google A2UI (v1.0) declarative agent surfaces or generating an interactive visual UI/cockpit to talk to the human, route to 'gen-ui' (plus skill://frontend-ui).\n"
        "- If optimizing backend/API/DB latency, throughput, N+1 queries, connection pools, serialization, or memory layout, route to 'perf-issue' (or 'hillclimb' for iterative metric targets) and attach skill://domain-rules + skill://software-architecture.\n"
        "Output ONLY valid JSON matching the schema (no markdown prose outside JSON).\n\n"
        f"User prompt:\n{cleaned}\n\n"
        f"Live repo facts:\n{json.dumps(repo_facts, indent=2)}\n\n"
        f"Playbooks ({len(compact_playbooks)}):\n- " + "\n- ".join(compact_playbooks) + "\n\n"
        f"Techniques ({len(compact_techniques)}):\n- " + "\n- ".join(compact_techniques) + "\n\n"
        f"Reference & Sibling Skills ({len(compact_ref_skills)}):\n- " + "\n- ".join(compact_ref_skills) + "\n\n"
        f"Required JSON schema:\n{json.dumps(schema, indent=2)}"
    )

    return {
        "prompt": cleaned,
        "routing_engine": "llm-semantic",
        "repo_facts": repo_facts,
        "advisory_only": True,
        "hardcore_mode": hardcore_default,
        "advisory_prior": {
            "deprecated_offline_only": True,
            "mode": prior["mode"],
            "size": prior["size"],
            "self_grill": prior["self_grill"],
            "hardcore_mode": hardcore_default,
            "hardcore_system_signal": hardcore_system_hit,
            "specialized_hints": spec_hints,
            "reference_skill_hints": ref_hints,
        },
        "catalog_counts": {
            "playbooks": len(catalog["playbooks"]),
            "techniques": len(catalog["techniques"]),
            "sibling_skills": len(catalog["sibling_skills"]),
        },
        "decision_schema": schema,
        "llm_router_prompt": llm_router_prompt,
    }


def _validate_route_file(route_file: str, expected_file: str, primary: str, all_modes: dict, sibling_skills: dict) -> str | None:
    if route_file == expected_file:
        return None
    if route_file.startswith("skill://"):
        rest = route_file.removeprefix("skill://")
        parts = [p for p in rest.split("/") if p]
        if not parts:
            return f"invalid skill URI {route_file!r}"
        sname = parts[0]
        if sname != primary:
            return f"route_file {route_file!r} does not match primary_mode {primary!r} (expected {expected_file!r})"
        base_dir = SKILL_DIR if sname == SKILL_DIR.name else (sibling_skills.get(sname) or {}).get("dir")
        if base_dir is None:
            return f"route_file {route_file!r} names non-existent skill {sname!r}"
        if len(parts) > 1:
            sub_target = (base_dir / "/".join(parts[1:])).resolve()
            try:
                sub_target.relative_to(base_dir.resolve())
            except ValueError:
                return f"route_file {route_file!r} escapes skill root"
            if not sub_target.is_file():
                return f"route_file {route_file!r} does not exist on disk"
        return None
    return f"route_file {route_file!r} does not match primary_mode {primary!r} (expected {expected_file!r})"


def verify_decision(
    decision: dict,
    prompt: str = "",
    root: Path | None = None,
    critic_round: int = 1,
    enforce_regex_hints: bool = True,
) -> dict:
    repo_facts = gather_repo_facts(root)
    safe_root = Path(repo_facts["root"]) if repo_facts.get("has_root") else None
    catalog = discover_live_catalog(root=safe_root)
    all_modes = catalog["all_modes"]
    techniques = catalog["techniques"]
    sibling_skills = catalog["sibling_skills"]

    violations: list[str] = []
    warnings: list[str] = []
    auto_repairs: dict = {}

    raw_primary = str(decision.get("primary_mode", "")).strip()
    primary = raw_primary.removeprefix("skill://") if raw_primary.startswith("skill://") else raw_primary
    if primary not in all_modes:
        violations.append(f"unknown primary_mode {raw_primary!r}: must match a live playbook, technique, or sibling skill")

    expected_file = all_modes[primary]["file"] if primary in all_modes else ""
    route_file = str(decision.get("route_file", "")).strip()
    if primary in all_modes:
        if not route_file:
            route_file = expected_file
            auto_repairs["route_file"] = expected_file
        else:
            rf_err = _validate_route_file(route_file, expected_file, primary, all_modes, sibling_skills)
            if rf_err:
                violations.append(rf_err)

    raw_sec = decision.get("secondary_techniques")
    if raw_sec is not None and not isinstance(raw_sec, list):
        violations.append("secondary_techniques must be a JSON list of technique names")
        sec_list: list[str] = []
    else:
        sec_list = [str(x).strip() for x in (raw_sec or []) if str(x).strip()]
    for tech in sec_list:
        if tech not in techniques:
            violations.append(f"unknown secondary_technique {tech!r}: not found in references/techniques/")

    raw_refs = decision.get("reference_skills")
    if raw_refs is not None and not isinstance(raw_refs, list):
        violations.append("reference_skills must be a JSON list of skill:// URIs")
        ref_list: list[str] = []
    else:
        ref_list = []
        for ref in (raw_refs or []):
            ref_str = str(ref).strip()
            if not ref_str:
                continue
            rest = ref_str.removeprefix("skill://")
            parts = [p for p in rest.split("/") if p]
            if not parts:
                violations.append(f"invalid reference_skill {ref_str!r}")
                continue
            sname = parts[0]
            if sname not in sibling_skills:
                violations.append(f"unknown reference_skill {ref_str!r}: skill {sname!r} not found in plugin or repo")
                continue
            base_dir = sibling_skills[sname]["dir"]
            if len(parts) > 1:
                if ".." in parts:
                    violations.append(f"reference_skill {ref_str!r} escapes skill root")
                    continue
                sub_target = (base_dir / "/".join(parts[1:])).resolve()
                try:
                    sub_target.relative_to(base_dir.resolve())
                except ValueError:
                    violations.append(f"reference_skill {ref_str!r} escapes skill root")
                    continue
                if not sub_target.is_file():
                    violations.append(f"reference_skill {ref_str!r} does not exist on disk")
                    continue
                norm_ref = f"skill://{sname}/{'/'.join(parts[1:])}"
            else:
                norm_ref = f"skill://{sname}"
            if norm_ref not in ref_list:
                ref_list.append(norm_ref)
    size = str(decision.get("size", "")).strip()
    if size not in ("S", "M", "L", "none"):
        violations.append(f"invalid size {size!r}: must be S, M, L, or none")

    self_grill_mode = str(decision.get("self_grill", "")).strip()
    if self_grill_mode not in ("none", "plan", "checks", "both"):
        violations.append(f"invalid self_grill {self_grill_mode!r}: must be none, plan, checks, or both")

    try:
        confidence = float(decision.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
        violations.append("confidence must be a number between 0.0 and 1.0")
    if not (0.0 <= confidence <= 1.0):
        violations.append(f"confidence {confidence} out of range [0.0, 1.0]")

    deliverables = decision.get("deliverables") or []
    if not isinstance(deliverables, list) or not deliverables:
        violations.append("deliverables must be a non-empty list covering full request scope")

    decoded_intent = str(decision.get("decoded_intent", "")).strip()
    if not decoded_intent:
        violations.append("decoded_intent cannot be empty")

    sensitive_prompt = bool(SENSITIVE_RE.search(prompt)) if prompt else False
    sensitive_diff = bool(repo_facts.get("diff_sensitive_paths"))
    is_sensitive = sensitive_prompt or sensitive_diff
    minimal_opt_out = has_minimal_opt_out(prompt) if prompt else False
    hardcore_system = bool(HARDCORE_SYSTEM_RE.search(prompt)) if prompt else False
    raw_hardcore = decision.get("hardcore_mode", True)
    if not isinstance(raw_hardcore, bool):
        violations.append(f"hardcore_mode must be boolean, got {raw_hardcore!r}")
        hardcore_mode = True
    else:
        hardcore_mode = raw_hardcore
    hardcore_ceiling = str(decision.get("hardcore_ceiling", "")).strip()

    is_flexible = primary in FLEXIBLE_SIZE_MODES
    is_read_only = (primary in READ_ONLY_MODES) and not is_flexible
    if is_read_only and size != "none":
        violations.append(f"read-only/discovery mode {primary!r} must have size 'none', got {size!r}")
    if primary and not is_read_only and not is_flexible and size == "none":
        violations.append(f"execution mode {primary!r} cannot have size 'none'")
    if is_sensitive and size == "S":
        violations.append("sensitive domain or diff (auth/secrets/migrations/payments/CI/agent-config) cannot be sized S; use M or L")
    if is_sensitive and not is_read_only and size != "none" and self_grill_mode not in ("checks", "both"):
        violations.append("sensitive execution work requires post-edit diff verification; set self_grill to 'both' or 'checks'")
    if primary and not is_read_only and size != "none" and not hardcore_mode and not minimal_opt_out and primary != "prototype":
        violations.append("Hardcore Mode is ON by default; do not set hardcore_mode=false without an explicit minimal/prototype opt-out in the user prompt")
    if primary and not is_read_only and size == "S" and not minimal_opt_out and (hardcore_system or len(deliverables) >= 2):
        violations.append("ambitious hardcore or multi-deliverable task cannot be under-sized to S; use M or L")

    why_not = str(decision.get("why_not_runner_up", "")).strip()
    if primary == "tournament" and prompt and CONCRETE_ANCHOR_RE.search(prompt) and len(why_not) < 15:
        violations.append("routing to 'tournament' despite concrete file/PR/anchor requires a concrete why_not_runner_up justification")

    claimed_critic = bool(decision.get("critic_reviewed", False))
    if claimed_critic and critic_round < 2:
        violations.append("critic_reviewed=true is only valid on --critic-round 2 after a Round-1 CRITIC_REQUIRED pass")
    critic_verified = claimed_critic and critic_round >= 2

    critic_reasons: list[str] = []
    if confidence < 0.80 and not critic_verified:
        critic_reasons.append(f"confidence {confidence:.2f} < 0.80")

    spec_hints = detect_specialized_signals(prompt) if (prompt and enforce_regex_hints) else []
    if spec_hints and primary not in spec_hints and not critic_verified:
        critic_reasons.append(
            f"prompt contains specialized signal(s) {spec_hints} but router picked {primary!r}"
        )

    present_skill_roots = {r.split("/")[2] if r.startswith("skill://") else r.split("/")[0] for r in ref_list}
    expected_refs = detect_expected_reference_skills(prompt, sibling_skills) if prompt else []
    missing_refs = [r for r in expected_refs if r.removeprefix("skill://") not in present_skill_roots]
    if missing_refs:
        warnings.append(f"recommended reference_skills omitted: {missing_refs}")
        auto_repairs["add_reference_skills"] = missing_refs
    struggle_hit = bool(STRUGGLE_SIGNAL_RE.search(prompt)) if prompt else False
    if struggle_hit and size == "S":
        violations.append("user is stuck/struggling; do not under-size to S — use M/L with self_grill and attack-the-premise")

    if (size in ("M", "L") and not is_read_only) or struggle_hit:
        missing_sec = [t for t in ("self-grill", "no-comments") if t not in sec_list and primary != t] if not is_read_only else (["self-grill"] if "self-grill" not in sec_list and primary != "self-grill" else [])
        if struggle_hit and "why" not in sec_list and primary != "why":
            missing_sec.append("why")
        if is_sensitive and "security-audit" not in sec_list and primary != "security-audit":
            missing_sec.append("security-audit")
        if hardcore_mode and (size == "L" or hardcore_system) and len(deliverables) >= 2 and "architect" not in sec_list and primary != "architect":
            missing_sec.append("architect")
        if missing_sec:
            warnings.append(f"recommended secondary_techniques omitted for {size} work: {missing_sec}")
            auto_repairs["add_secondary_techniques"] = missing_sec

    if violations:
        status = "REJECTED"
    elif critic_reasons:
        status = "CRITIC_REQUIRED"
    else:
        status = "APPROVED"

    critic_prompt = ""
    if status != "APPROVED":
        next_round = min(2, max(2, critic_round))
        critic_prompt = (
            f"You are the Adversarial Route Critic (round {next_round} of 2). Attack the proposed route decision below. "
            "Check: (1) based on what the user literally typed, does a more specific playbook or technique fit better than primary_mode? "
            "(2) did deliverables drop any clause from the user prompt? "
            "(3) are size, self_grill, secondary_techniques, and reference_skills accurate and safe? "
            "Output ONLY the corrected full JSON decision with \"critic_reviewed\": true.\n\n"
            f"Original prompt: {prompt}\n"
            f"Proposed decision: {json.dumps(decision, indent=2)}\n"
            f"Gate violations: {violations}\n"
            f"Critic triggers: {critic_reasons}\n"
            f"Auto-repair hints: {json.dumps(auto_repairs)}"
        )

    if size == "S":
        model_tier, effort = "S", "low"
    elif primary in ("investigation", "recall", "flows", "worktree-cleanup"):
        model_tier, effort = "S", "medium"
    elif size == "L" or primary in ("tournament", "architecture-review", "security-audit", "interrogate", "arena", "formal-verification"):
        model_tier, effort = "L", "xhigh"
    elif is_sensitive or is_read_only:
        model_tier, effort = "L", "high"
    else:
        model_tier, effort = "M", "medium"

    final_refs = sorted(set(ref_list) | set(auto_repairs.get("add_reference_skills", [])))
    final_sec = sorted(set(sec_list) | set(auto_repairs.get("add_secondary_techniques", [])))
    qg = _load_sibling("ar_quota_guard", "quota-guard/quota_guard.py")
    outer_harness = qg.detect_outer_harness(root=safe_root)
    lean_quota = bool(decision.get("lean_mode")) or (bool(LEAN_QUOTA_RE.search(prompt)) if prompt else False)
    is_merge_gate = primary in ("shipping", "opening-a-pr", "pr-conversation", "work-a-queue")
    quota_budget = qg.compute_quota_plan(
        size=size if size in ("S", "M", "L", "none") else "M",
        mode=primary,
        diff_lines=int(repo_facts.get("diff_lines", 0) or 0),
        is_sensitive=is_sensitive,
        outer_harness=outer_harness,
        lean_mode=lean_quota,
        is_merge_gate=is_merge_gate,
    )
    if quota_budget["nested_anti_stacking"] or lean_quota:
        panel_seats = []
    else:
        panel_seats = list(DEFAULT_PANEL_SEATS) if (size == "L" or primary in ("tournament", "arena", "interrogate", "security-audit", "shipping")) else []

    return {
        "status": status,
        "critic_round": critic_round,
        "violations": violations,
        "critic_reasons": critic_reasons,
        "warnings": warnings,
        "auto_repairs": auto_repairs,
        "critic_prompt": critic_prompt,
        "locked_plan": {
            "primary_mode": primary,
            "route_file": route_file,
            "secondary_techniques": final_sec,
            "reference_skills": final_refs,
            "size": size,
            "self_grill": self_grill_mode,
            "hardcore_mode": hardcore_mode,
            "hardcore_ceiling": hardcore_ceiling,
            "model_tier": model_tier,
            "effort": effort,
            "panel_seats": panel_seats,
            "quota_budget": quota_budget,
            "deliverables": deliverables,
        } if status == "APPROVED" else None,
    }


def _extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if not text:
        raise ValueError("empty LLM response")
    try:
        outer = json.loads(text)
        if isinstance(outer, dict):
            if "primary_mode" in outer:
                return outer
            for key in ("result", "response", "text", "output", "content", "message"):
                val = outer.get(key)
                if isinstance(val, dict) and "primary_mode" in val:
                    return val
                if isinstance(val, str) and "{" in val:
                    text = val.strip()
                    break
    except ValueError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        try:
            parsed_fenced = json.loads(fenced.group(1))
            if isinstance(parsed_fenced, dict):
                return parsed_fenced
        except ValueError:
            pass
    decoder = json.JSONDecoder()
    best_dict: dict | None = None
    best_span = -1
    idx = text.find("{")
    while idx >= 0:
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                if "primary_mode" in obj:
                    return obj
                if (end_idx - idx) > best_span:
                    best_dict = obj
                    best_span = end_idx - idx
        except ValueError:
            pass
        idx = text.find("{", idx + 1)
    if best_dict is not None:
        return best_dict
    raise ValueError(f"could not locate JSON object in LLM output: {text[:200]!r}")


def _prefer_native_exe_on_windows(name: str, found: str) -> str:
    if os.name != "nt" or not found.lower().endswith((".cmd", ".bat")):
        return found
    if name == "agy":
        local_agy = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
        if local_agy.is_file():
            return str(local_agy)
    sibling_exe = Path(found).with_suffix(".exe")
    if sibling_exe.is_file():
        return str(sibling_exe)
    return found


def _resolve_subscription_harness(harness: str) -> tuple[str, list[str]]:
    choice = harness.lower().strip()
    if choice == "omp":
        raise SystemExit("refusing 'omp' harness for LLM routing: omp model token spend is forbidden; use agy, claude, or codex")
    candidates = ("agy", "claude", "codex") if choice == "auto" else (choice,)
    for name in candidates:
        exe = shutil.which(name)
        if not exe:
            continue
        exe = _prefer_native_exe_on_windows(name, exe)
        if name == "agy":
            return "agy", [exe, "-p"]
        if name == "claude":
            return "claude", [exe, "-p", "--tools", "", "--output-format", "json"]
        if name == "codex":
            return "codex", [exe, "exec", "-s", "read-only", "--skip-git-repo-check"]
    raise SystemExit(f"no subscription LLM CLI found for harness={harness!r} (checked: {', '.join(candidates)})")


def invoke_subscription_llm(prompt_text: str, harness: str = "auto", cwd: Path | None = None, timeout_sec: int = 90) -> str:
    resolved_name, base_cmd = _resolve_subscription_harness(harness)
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_API_KEY_VARS}
    cmd = [*base_cmd, prompt_text]
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
        creationflags=NO_WINDOW,
    )
    if res.returncode != 0:
        raise RuntimeError(f"{resolved_name} exited {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
    return res.stdout


def route_with_llm(
    prompt: str,
    root: Path | None = None,
    harness: str = "auto",
    llm_runner: Callable[[str, int], str | dict] | None = None,
) -> dict:
    packet = build_menu_packet(prompt, root=root)
    safe_root = Path(packet["repo_facts"]["root"]) if packet["repo_facts"].get("has_root") else None
    runner = llm_runner or (lambda p, _r: invoke_subscription_llm(p, harness=harness, cwd=safe_root))

    raw_r1 = runner(packet["llm_router_prompt"], 1)
    dec_r1 = raw_r1 if isinstance(raw_r1, dict) else _extract_json_object(str(raw_r1))
    ver_r1 = verify_decision(dec_r1, prompt=packet["prompt"], root=safe_root, critic_round=1)
    rounds = [{"round": 1, "decision": dec_r1, "verification": ver_r1}]

    if ver_r1["status"] == "APPROVED":
        return {
            "status": "APPROVED",
            "routing_engine": "llm-semantic",
            "rounds_used": 1,
            "locked_plan": ver_r1["locked_plan"],
            "rounds": rounds,
        }

    raw_r2 = runner(ver_r1["critic_prompt"], 2)
    dec_r2 = raw_r2 if isinstance(raw_r2, dict) else _extract_json_object(str(raw_r2))
    dec_r2["critic_reviewed"] = True
    ver_r2 = verify_decision(dec_r2, prompt=packet["prompt"], root=safe_root, critic_round=2)
    rounds.append({"round": 2, "decision": dec_r2, "verification": ver_r2})

    return {
        "status": ver_r2["status"],
        "routing_engine": "llm-semantic",
        "rounds_used": 2,
        "locked_plan": ver_r2["locked_plan"],
        "violations": ver_r2["violations"],
        "rounds": rounds,
    }


def evaluate_reroute(root: Path, current_mode: str, current_size: str, failed_attempts: int = 0, competing_shapes: int = 1) -> dict:
    repo_facts = gather_repo_facts(root)
    triggers: list[str] = []
    new_size = current_size
    add_techniques: list[str] = []
    add_principles: list[str] = []
    recommended_mode = current_mode

    size_rank = {"none": 0, "S": 1, "M": 2, "L": 3}
    diff_size = repo_facts.get("diff_size", "none")
    if size_rank.get(diff_size, 0) > size_rank.get(current_size, 0):
        triggers.append(f"diff grew from {current_size} to {diff_size} ({repo_facts['diff_files']} files)")
        new_size = diff_size

    if repo_facts.get("diff_sensitive_paths"):
        triggers.append(f"diff touched sensitive path(s): {repo_facts['diff_sensitive_paths'][:3]}")
        if new_size in ("none", "S"):
            new_size = "M"
        add_techniques.extend(["security-audit", "self-grill"])

    if failed_attempts >= 2:
        triggers.append(f"{failed_attempts} failed attempts sharing a premise -> pause and apply attack-the-premise")
        add_techniques.append("self-grill")
        add_principles.append("attack-the-premise")
        if current_mode in ("bug-fix", "feature"):
            recommended_mode = "investigation"

    if competing_shapes >= 2:
        triggers.append(f"{competing_shapes} competing design shapes -> sketch with architect or arena")
        add_techniques.append("architect" if competing_shapes == 2 else "arena")

    if repo_facts.get("diff_added_comments", 0) > 0:
        triggers.append(f"diff added {repo_facts['diff_added_comments']} code comment(s) -> run no-comments")
        add_techniques.append("no-comments")
    if repo_facts.get("diff_workaround_smells", 0) > 0:
        triggers.append(f"diff added {repo_facts['diff_workaround_smells']} workaround smell(s) -> run self-grill")
        add_techniques.append("self-grill")

    return {
        "reroute_needed": bool(triggers),
        "current_mode": current_mode,
        "recommended_mode": recommended_mode,
        "current_size": current_size,
        "recommended_size": new_size,
        "add_techniques": sorted(set(add_techniques)),
        "add_principles": sorted(set(add_principles)),
        "triggers": triggers,
        "repo_facts": repo_facts,
    }


def cmd_route(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.stdin else (args.prompt or "")
    root = Path(args.root) if args.root else None
    res = route_with_llm(raw, root=root, harness=args.harness)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        plan = res.get("locked_plan") or {}
        print(
            f"autoroute ({res['routing_engine']}, rounds={res['rounds_used']}): {res['status']} "
            f"mode={plan.get('primary_mode')} file={plan.get('route_file')} size={plan.get('size')}"
        )
    return 0 if res["status"] == "APPROVED" else 2


def cmd_menu(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.stdin else (args.prompt or "")
    root = Path(args.root) if args.root else None
    packet = build_menu_packet(raw, root=root)
    if args.json:
        print(json.dumps(packet, indent=2))
    else:
        print(packet["llm_router_prompt"])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    if args.strict and not (args.prompt or "").strip():
        raise SystemExit("verify --strict requires a non-empty --prompt")
    raw_dec = sys.stdin.read() if args.decision_stdin else Path(args.decision_file).read_text(encoding="utf-8")
    try:
        decision = json.loads(raw_dec)
    except ValueError as err:
        raise SystemExit(f"invalid decision JSON: {err}") from err
    root = Path(args.root) if args.root else None
    res = verify_decision(decision, prompt=args.prompt or "", root=root, critic_round=args.critic_round)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"autoroute: {res['status']} violations={len(res['violations'])} critic_reasons={len(res['critic_reasons'])}")
    if args.strict and res["status"] != "APPROVED":
        return 2
    return 0


def cmd_reroute(args: argparse.Namespace) -> int:
    res = evaluate_reroute(
        Path(args.root),
        current_mode=args.current_mode,
        current_size=args.current_size,
        failed_attempts=args.failed_attempts,
        competing_shapes=args.competing_shapes,
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(
            f"reroute_needed={res['reroute_needed']} mode={res['current_mode']}->{res['recommended_mode']} "
            f"size={res['current_size']}->{res['recommended_size']} add={res['add_techniques']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pure LLM semantic auto-routing loop with checks and balances.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rt = sub.add_parser("route", help="Semantically route a user prompt using the subscription LLM + 2-round verifier.")
    p_rt.add_argument("--stdin", action="store_true")
    p_rt.add_argument("--prompt", default="")
    p_rt.add_argument("--root", default=None)
    p_rt.add_argument("--harness", choices=("auto", "agy", "claude", "codex"), default="auto")
    p_rt.add_argument("--json", action="store_true")
    p_rt.set_defaults(func=cmd_route)

    p_menu = sub.add_parser("menu", help="Build live disk catalog menu and repo facts packet for the LLM router.")
    p_menu.add_argument("--stdin", action="store_true")
    p_menu.add_argument("--prompt", default="")
    p_menu.add_argument("--root", default=None)
    p_menu.add_argument("--json", action="store_true")
    p_menu.set_defaults(func=cmd_menu)

    p_ver = sub.add_parser("verify", help="Verify an LLM route decision against checks and balances.")
    p_ver.add_argument("--root", default=None)
    p_ver.add_argument("--prompt", default="")
    dec_group = p_ver.add_mutually_exclusive_group(required=True)
    dec_group.add_argument("--decision-stdin", action="store_true")
    dec_group.add_argument("--decision-file", default=None)
    p_ver.add_argument("--critic-round", type=int, choices=(1, 2), default=1)
    p_ver.add_argument("--strict", action="store_true")
    p_ver.add_argument("--json", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    p_re = sub.add_parser("reroute", help="Evaluate mid-flight re-route triggers from live repo state.")
    p_re.add_argument("--root", required=True)
    p_re.add_argument("--current-mode", required=True)
    p_re.add_argument("--current-size", choices=("S", "M", "L", "none"), required=True)
    p_re.add_argument("--failed-attempts", type=int, default=0)
    p_re.add_argument("--competing-shapes", type=int, default=1)
    p_re.add_argument("--json", action="store_true")
    p_re.set_defaults(func=cmd_reroute)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
