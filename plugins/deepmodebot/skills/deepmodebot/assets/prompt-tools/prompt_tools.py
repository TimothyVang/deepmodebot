#!/usr/bin/env python3
"""Prompt reviewer/full-scope upgrader and repo gap/overclaim prompt suggester for deepmodebot.

    python prompt_tools.py upgrade --stdin [--root <repo>] [--json] <<'EOF'
    python prompt_tools.py suggest --root <repo> [--limit 0] [--ui] [--json]
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ASSETS_DIR = Path(__file__).resolve().parent.parent


def _load_sibling(name: str, rel_path: str):
    path = ASSETS_DIR / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SKIP_DIRS = {
    ".git", ".scratch", ".worktrees", "__pycache__", "node_modules", ".venv",
    "venv", "dist", "build", ".next", "target", ".pytest_cache", ".lake",
    ".playwright-mcp", ".turbo", "coverage", ".cache", "out", ".nuxt", ".svelte-kit",
}

AUX_SURFACE_PREFIXES = ("docs/assets/", "docs/evidence/", "docs/research/", "examples/", "evals/", "trending/")
UNCHECKED_TASK_RE = re.compile(r"^\s*[-*]\s+\[\s\]\s+(.{6,200})$")
AGENT_SDK_SIGNAL_RE = re.compile(
    r"\b(?:openai|anthropic|@google/genai|langchain|langgraph|@modelcontextprotocol|generateText|streamText|McpServer)\b"
)
HTTP_ROUTE_SIGNAL_RE = re.compile(
    r"\b(?:FastAPI|APIRouter|Hono|express\s*\(|axum::Router|NextResponse|createServer)\b|@(?:app|router)\.(?:post|put|delete|patch)\b"
)
RESILIENCE_SIGNAL_RE = re.compile(
    r"\b(?:idempoten|rate[_-]?limit|ratelimit|zod|pydantic|BaseModel|AbortSignal\.timeout|retry)\b",
    re.I,
)

ORACLE_HINT_RE = re.compile(
    r"\b(?:unittest|pytest|vitest|jest|playwright|cypress|npm\s+test|cargo\s+test|go\s+test"
    r"|failing\s+test|regression\s+test|verify\s+on|prove\s+(?:it|on)|benchmark|eval|exit\s+0|screenshot|repro|assert)\b",
    re.I,
)

GAP_OVERCLAIM_HINT_RE = re.compile(
    r"\b(?:overclaim|overclaims|gaps?|blind\s*spots?|unverified|false\s+positive|audit\s+claims)\b",
    re.I,
)

TYPO_FRAGMENT_RE = re.compile(
    r"\b(?:naetc|als[oy]|wehres|revuew|optimzie|misintepet|plz|pls|idk|w\/e|etc|stuff|things)\b",
    re.I,
)

OPTIONAL_HARDCORE_RE = re.compile(
    r"(?:\(\s*optional\s+hardcore(?:\s+mode)?[^)]*\)|\boptional\s+hardcore(?:\s+mode)?\b"
    r"|\bbonus\s+(?:hardcore|tier|goal)\b|\bbasic\s+mvp\b|\bsimple\s+placeholder\b"
    r"|\bquick\s+hack\b|\bstub\s+for\s+now\b|\bminimal\s+toy\b)",
    re.I,
)

LEADING_OPTIONAL_HARDCORE_RE = re.compile(
    r"^(?:\(\s*optional\s+hardcore(?:\s+mode)?\s*\)|optional\s+hardcore(?:\s+mode)?\b|bonus(?:\s+hardcore)?(?:\s+tier)?\b)\s*[:\-–—]?\s*",
    re.I,
)

INLINE_OPTIONAL_HARDCORE_RE = re.compile(
    r"\(\s*optional\s+hardcore(?:\s+mode)?(?:\s*[:\-–—]\s*([^)]+))?\s*\)",
    re.I,
)

WORD_COMPOUND_SPLIT_RE = re.compile(
    r"\s+(?:and\s+also|also|as\s+well\s+as)\s+",
    re.I,
)

BACKEND_SIGNAL_RE = re.compile(
    r"\b(?:backend|server|endpoint|route|api|fastapi|starlette|express|axum|tokio|go|postgres|sqlite|mysql"
    r"|database|sql|query|queries|orm|prisma|drizzle|sqlalchemy|pgx|asyncpg|npgsql|n\+1|pagination|cursor"
    r"|pool|latency|p9[59]|throughput|rps|cache|redis|serialization|orjson|gzip|simd|memory\s+layout)\b",
    re.I,
)

IMPORT_REF_RE = re.compile(
    r"(?:^\s*(?:from|import)\s+([A-Za-z0-9_.]+)"
    r"|\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)"
    r"|\bfrom\s+['\"]([^'\"]+)['\"]"
    r"|['\"]([A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|mjs|go|rs|cs))['\"])",
    re.M,
)

OVERCLAIM_PATTERNS = (
    (
        "universal-guarantee",
        re.compile(
            r"(?<![A-Za-z0-9_])100%(?![A-Za-z0-9_])"
            r"|\b(?:always\s+works|never\s+fails|zero\s+(?:bugs|errors|failures)|guaranteed\s+to|completely\s+bug[- ]free)\b",
            re.I,
        ),
    ),
    ("unbounded-coverage", re.compile(r"\b(?:supports?\s+all|handles?\s+every|works?\s+everywhere|fully\s+automated|production[- ]ready)\b", re.I)),
    ("unbacked-pass-claim", re.compile(r"\b(?:all\s+tests\s+pass|every\s+check\s+passes|fully\s+verified)\b", re.I)),
)

MD_LINK_RE = re.compile(r"\[[^\]]+\]\((<[^>]+>|[^)\s]+)\)")
URI_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
DEBT_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)")
DEFECT_WORD_RE = re.compile(r"\b(?:bug|broken|crash|error|fail|failing|fix|regression|leak|hang)\b", re.I)

NO_CLARIFY_OVERRIDE_RE = re.compile(
    r"\b(?:don'?t\s+ask|no\s+questions|just\s+do\s+it|do\s+everything\s+on\s+your\s+own|autonomous(?:ly)?|decide\s+yourself)\b",
    re.I,
)
CONCRETE_TARGET_RE = re.compile(
    r"(?:[A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs|rs|go|luau|lean|tla|md|json|yml|yaml|toml|sql|sh)\b"
    r"|https?://\S+|\borgs/[A-Za-z0-9_.-]+|#\d+\b|\bPR\s*#?\d+\b|`[^`]+`"
    r"|\b(?:postgres|sqlite|redis|stripe|oauth|jwt|cloudflare|vercel|workers|nextjs|react|tailwind|rust|golang|dmb-gate|dmb-net|gap_audit|slop_gate)\b)",
    re.I,
)
VAGUE_GOAL_RE = re.compile(
    r"^(?:please\s+|plz\s+|can\s+you\s+)?(?:improve|fix|upgrade|clean(?:\s+up)?|refactor|build|make|update|check|help(?:\s+with)?)"
    r"(?:\s+(?:it|this|things|stuff|everything|something|the\s+(?:app|repo|code|project|system)|an?\s+(?:app|tool|website|saas)))?"
    r"(?:\s+(?:better|faster|cleaner|good|now|please|plz))*[?!.]*$",
    re.I,
)
HUMAN_FORK_RE = re.compile(
    r"\b(?:not\s+sure\s+(?:whether|if)|should\s+(?:i|we)\b[^?!.]{1,80}\bor\b|either\b[^?!.]{1,60}\bor\b.*\bwhich\b)\b",
    re.I,
)
IRREVERSIBLE_GATE_RE = re.compile(
    r"\b(?:deploy\s+to\s+prod(?:uction)?|publish\s+(?:to\s+)?(?:npm|pypi|crates)|drop\s+table|delete\s+prod(?:uction)?|force[- ]push)\b",
    re.I,
)
HARNESS_QUESTION_TOOLS = {
    "agy": "ask_question",
    "claude": "AskUserQuestion",
    "omp": "ask",
    "codex": "request_user_input",
}


def analyze_ambiguity(raw_prompt: str, root: Path | None = None) -> dict:
    stripped = re.sub(r"^\s*(?:/(?:deepmodebot:)?deep\b|\$deepmodebot:(?:deepmodebot|deep)\b)\s*", "", raw_prompt or "", flags=re.I)
    cleaned = " ".join(stripped.strip().split())
    signals: list[str] = []
    questions: list[dict] = []

    if cleaned and not NO_CLARIFY_OVERRIDE_RE.search(cleaned):
        has_anchor = bool(CONCRETE_TARGET_RE.search(cleaned))
        word_count = len(re.findall(r"[A-Za-z0-9_]+", cleaned))
        if not has_anchor and (word_count <= 4 or VAGUE_GOAL_RE.match(cleaned)):
            signals.append("underspecified_scope")
            questions.append({
                "question": "What outcome should /deep prioritize in this run?",
                "options": [
                    "(Recommended) Full repo gap, drift & bug audit followed by Hardcore Mode fixes and verification",
                    "Build a new end-to-end feature or subsystem (specify target workflow)",
                    "Optimize performance, reliability, and test coverage across core modules",
                ],
            })
        if HUMAN_FORK_RE.search(cleaned):
            signals.append("explicit_human_choice_fork")
            questions.append({
                "question": "Which direction should /deep lock in before full-scope execution?",
                "options": [
                    "(Recommended) Prototype/benchmark the leading first-principles architecture and ship the winner",
                    "Keep the smallest backwards-compatible change in the existing module layout",
                ],
            })
        if IRREVERSIBLE_GATE_RE.search(cleaned):
            signals.append("irreversible_or_external_action")
            questions.append({
                "question": "This prompt touches an external/irreversible boundary; how far should /deep proceed?",
                "options": [
                    "(Recommended) Build, test, and prove everything locally/on a branch, pausing right before external publish/deploy",
                    "Execute the external publish/deploy step in this run as well",
                ],
            })

    return {
        "needs_clarification": bool(signals),
        "signals": signals,
        "max_rounds": 1 if signals else 0,
        "never_ask_repo_or_doc_facts": True,
        "headless_fallback": "select_recommended_and_log",
        "harness_question_tools": HARNESS_QUESTION_TOOLS,
        "questions": questions[:3],
    }

def _has_verify_skill(root: Path) -> list[str]:
    found = []
    for base in (".omp/skills", ".claude/skills", ".agents/skills"):
        d = root / base
        if d.is_dir():
            for child in sorted(d.glob("verify-*/SKILL.md")):
                found.append(child.relative_to(root).as_posix())
    return found


def _split_outside_code(text: str) -> list[str]:
    spans: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        idx = len(spans)
        spans.append(match.group(0))
        return f"\x00SPAN{idx}\x00"

    masked_ticks = re.sub(r"`[^`]+`", _stash, text)
    masked = []
    paren_depth = 0
    cur_paren: list[str] = []
    for ch in masked_ticks:
        if ch == "(":
            paren_depth += 1
            cur_paren.append(ch)
        elif ch == ")" and paren_depth > 0:
            cur_paren.append(ch)
            paren_depth -= 1
            if paren_depth == 0:
                idx = len(spans)
                spans.append("".join(cur_paren))
                cur_paren = []
                masked.append(f"\x00SPAN{idx}\x00")
        elif paren_depth > 0:
            cur_paren.append(ch)
        elif ch == ";":
            masked.append("\x1f")
        else:
            masked.append(ch)
    if cur_paren:
        masked.append("".join(cur_paren))

    def _restore(chunk: str) -> str:
        out = chunk
        for _ in range(3):
            if "\x00SPAN" not in out:
                break
            out = re.sub(r"\x00SPAN(\d+)\x00", lambda m: spans[int(m.group(1))], out)
        return out.strip()

    chunks: list[str] = []
    for semi_part in "".join(masked).split("\x1f"):
        s = semi_part.strip()
        if not s:
            continue
        for part in WORD_COMPOUND_SPLIT_RE.split(s):
            restored = _restore(part)
            if restored:
                chunks.append(restored)
    return chunks

def _extract_deliverables(raw_prompt: str) -> list[str]:
    text = raw_prompt.strip()
    if not text:
        return []
    has_list = bool(re.search(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+", text))
    raw_parts: list[str] = []
    if has_list:
        line_blocks = re.split(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+", text)
        lead = " ".join(line_blocks[0].split()).strip()
        if lead and not lead.endswith(":"):
            raw_parts.extend(_split_outside_code(lead))
        for block in line_blocks[1:]:
            norm = " ".join(block.split()).strip()
            if norm:
                raw_parts.extend(_split_outside_code(norm))
    else:
        raw_parts.extend(_split_outside_code(" ".join(text.split())))

    deduped: list[str] = []
    for raw_part in raw_parts:
        part = re.sub(r"^\d+[.)]\s+", "", raw_part).strip(" ,;.-")
        if len(part) < 3:
            continue
        if part.lower() not in {d.lower() for d in deduped}:
            deduped.append(part)
    return deduped if deduped else [" ".join(text.split())]


def _promote_optional_hardcore_item(item: str) -> tuple[str, bool]:
    if LEADING_OPTIONAL_HARDCORE_RE.search(item):
        stripped = LEADING_OPTIONAL_HARDCORE_RE.sub("", item).strip()
        return f"[Hardcore mandatory] {stripped or item}", True
    m = INLINE_OPTIONAL_HARDCORE_RE.search(item)
    if m:
        inner = (m.group(1) or "").strip()
        replacement = f"[Hardcore mandatory: {inner}]" if inner else "[Hardcore mandatory]"
        rewritten = INLINE_OPTIONAL_HARDCORE_RE.sub(replacement, item).strip()
        return rewritten, True
    return item, False


def upgrade_prompt(raw_prompt: str, root: Path | None = None) -> dict:
    tournament = _load_sibling("deepmode_tournament_mod", "tournament/tournament.py")
    self_grill = _load_sibling("deepmode_self_grill_mod", "self-grill/self_grill.py")
    autoroute = _load_sibling("deepmode_autoroute_mod", "autoroute/autoroute.py")

    cleaned = " ".join(raw_prompt.strip().split())
    if not cleaned:
        raise SystemExit("prompt cannot be empty")

    has_factory = False
    empty_dir = False
    verify_skills: list[str] = []
    diff_summary = None
    if root is not None:
        safe_root = self_grill.reject_unsafe_root(root)
        has_factory = (safe_root / "factory.json").is_file()
        entries = [
            p.name for p in safe_root.iterdir()
            if p.name not in {".git", ".scratch", ".worktrees", ".DS_Store"}
        ]
        empty_dir = len(entries) == 0
        verify_skills = _has_verify_skill(safe_root)
        if self_grill._is_git_root_or_worktree(safe_root):
            diff_summary = self_grill.inspect_diff(safe_root)

    route = dict(tournament.classify_prompt(cleaned, has_factory=has_factory, empty_dir=empty_dir))
    deliverables = _extract_deliverables(raw_prompt)
    hardcore_mode = not autoroute.has_minimal_opt_out(cleaned)
    hardcore_system = bool(autoroute.HARDCORE_SYSTEM_RE.search(cleaned))
    is_sensitive = bool(autoroute.SENSITIVE_RE.search(cleaned)) or bool(diff_summary and diff_summary["sensitive_paths"])

    promoted_hardcore = False
    normalized_deliverables: list[str] = []
    for item in deliverables:
        rewritten, changed = _promote_optional_hardcore_item(item) if hardcore_mode else (item, False)
        if changed:
            promoted_hardcore = True
        normalized_deliverables.append(rewritten)
    deliverables = normalized_deliverables

    if hardcore_mode and hardcore_system and route["mode"] == "bug-fix" and not DEFECT_WORD_RE.search(cleaned):
        route["mode"] = "phased-build" if len(deliverables) >= 2 else "feature"
    if route["mode"] not in autoroute.READ_ONLY_MODES and route["mode"] not in autoroute.FLEXIBLE_SIZE_MODES:
        size_rank = {"none": 0, "S": 1, "M": 2, "L": 3}
        floor_size = route["size"]
        if hardcore_mode and (hardcore_system or len(deliverables) >= 3):
            floor_size = "L"
        elif len(deliverables) >= 2 or is_sensitive:
            floor_size = "M" if size_rank.get(floor_size, 1) < 2 else floor_size
        if diff_summary and size_rank.get(diff_summary["measured_size"], 0) > size_rank.get(floor_size, 0):
            floor_size = diff_summary["measured_size"]
        route["size"] = floor_size
        if floor_size == "L" or is_sensitive:
            route["self_grill"] = "both"
            route["model_tier"] = "L"
            route["effort"] = "xhigh" if floor_size == "L" else "high"
        elif floor_size == "M" and route["self_grill"] == "none":
            route["self_grill"] = "checks"

    weaknesses: list[str] = []
    words = cleaned.split()
    if len(words) < 8 or route["anchors"] == 0:
        weaknesses.append("shorthand_or_vague")
    if len(deliverables) > 1 and not re.search(r"(?:^|\s)1[.)]\s", raw_prompt):
        weaknesses.append("multi_part_unnumbered")
    if not ORACLE_HINT_RE.search(cleaned):
        weaknesses.append("missing_acceptance_oracle")
    if not GAP_OVERCLAIM_HINT_RE.search(cleaned):
        weaknesses.append("missing_gap_overclaim_check")
    if TYPO_FRAGMENT_RE.search(cleaned):
        weaknesses.append("contains_typos_or_fragments")
    if hardcore_mode and (promoted_hardcore or OPTIONAL_HARDCORE_RE.search(cleaned)):
        weaknesses.append("watered_down_or_optional_hardcore")

    deliverable_lines = "\n".join(f"{idx}. {item}" for idx, item in enumerate(deliverables, 1))
    verify_hint = (
        f"Reuse existing verify skill ({', '.join(verify_skills)}) plus real tests/commands."
        if verify_skills
        else "Prove every behavior change on the real CLI/app/test path after the final edit with raw exit code 0."
    )
    diff_note = ""
    if diff_summary and diff_summary["file_count"] > 0:
        diff_note = (
            f"- Active repo diff: {diff_summary['file_count']} file(s), "
            f"+{diff_summary['lines_added']}/-{diff_summary['lines_deleted']} lines "
            f"(size={diff_summary['measured_size']}, comments_added={diff_summary['added_comment_count']}, "
            f"workaround_smells={diff_summary['workaround_smell_count']})."
        )

    hardcore_label = "HARDCORE MODE ON" if hardcore_mode else "minimal-scope opt-out"
    upgraded_lines = [
        f"/deep Execute the following full-scope request [{hardcore_label}] (advisory prior: {route['mode']}, "
        f"size: {route['size']}, self_grill: {route['self_grill']}, tier: {route['model_tier']}/{route['effort']}; "
        f"confirm via autoroute.py):",
        "",
        "Deliverables (keep 100% of scope; do not drop or demote any item):",
        deliverable_lines,
        "",
        "Required execution & quality gates:",
        "- Hardcore Mode by default (references/principles/hardcore-mode.md): aim straight for the first-principles architectural ceiling (batch query plans, bounded async concurrency, cache-friendly flat data structures, real solvers/algorithms, crisp native representations, full integration); never ship toy MVPs, stubs, or defer real craft to '(optional hardcore mode)'."
        if hardcore_mode
        else "- Respect explicit minimal-scope opt-out while preserving correctness and real-artifact proof.",
        "- Ground in real repo files and git state first; resolve reversible ambiguity from evidence and state assumptions.",
        *(
            [
                "- Backend & systems hot-path optimization: load skill://domain-rules/references/high-scale-server-optimization.md + data-structures-and-cache-optimization.md, run assets/perf-audit/perf_audit.py --fail-on-high, and eliminate N+1/await-in-loop waterfalls, sync-in-async blocking, missing timeouts, per-request pools, OFFSET scans, and cache stampedes."
            ]
            if BACKEND_SIGNAL_RE.search(cleaned) or route["mode"] in ("perf-issue", "hillclimb")
            else []
        ),
        "- Audit for gaps and overclaims: verify every claim, count, link, and 'passes/works' statement against current files or fresh runs; fix or downgrade any unbacked claim.",
        f"- Verification: {verify_hint}",
        "- Self-grill & hygiene: run self_grill.py check-diff (including hardcore-craft-depth), eliminate lying/narration comments (no-comments) and workaround smells, and keep all writes inside the project root.",
        "- Report concise observed results, exact receipts, remaining risks, and any real blockers.",
    ]
    if diff_note:
        upgraded_lines.insert(6, diff_note)

    clarification = analyze_ambiguity(raw_prompt, root=root)
    return {
        "original_prompt": raw_prompt.strip(),
        "hardcore_mode": hardcore_mode,
        "promoted_optional_hardcore": promoted_hardcore,
        "decoded_deliverables": deliverables,
        "weaknesses": weaknesses,
        "needs_upgrade": bool(weaknesses),
        "clarification": clarification,
        "route": route,
        "verify_skills": verify_skills,
        "upgraded_prompt": "\n".join(upgraded_lines),
    }


def _subsystem_of(rel: str) -> str:
    norm = rel.replace("\\", "/").strip("/")
    if "/assets/" in norm and norm.startswith("plugins/"):
        after = norm.split("/assets/", 1)[1]
        if "/" in after:
            seg = after.split("/", 1)[0]
            if seg:
                return f"assets/{seg}"
    parts = norm.split("/")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"src", "lib", "packages", "apps", "services", "native", "plugins", "docs", "skills"} and len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _is_aux_surface(rel: str) -> bool:
    return rel.replace("\\", "/").startswith(AUX_SURFACE_PREFIXES)


def _filter_bulk_untracked_dumps(tracked: list[str], untracked: list[str]) -> list[str]:
    if not tracked or len(untracked) < 400:
        return untracked
    code_suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go", ".cs", ".java", ".kt", ".luau"}
    by_bucket: dict[str, list[str]] = {}
    for rel in untracked:
        parts = rel.split("/")
        key = f"{parts[0]}/{parts[1]}" if len(parts) >= 3 else parts[0]
        by_bucket.setdefault(key, []).append(rel)
    kept: list[str] = []
    for items in by_bucket.values():
        if len(items) > 250:
            code_cnt = sum(1 for r in items if posixpath.splitext(r)[1].lower() in code_suffixes)
            if code_cnt < max(10, int(len(items) * 0.15)):
                continue
        kept.extend(items)
    return kept


def _collect_repo_files(root: Path) -> tuple[list[str], set[str], set[str]]:
    rel_files: list[str] = []
    all_known_files: list[str] = []
    git_used = False
    if (root / ".git").exists():
        try:
            rc = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--cached"],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=8,
            )
            ro = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=8,
            )
            if rc.returncode == 0 and ro.returncode == 0:
                git_used = True

                def _decode_list(blob: bytes) -> list[str]:
                    out: list[str] = []
                    for raw in blob.split(b"\x00"):
                        if not raw:
                            continue
                        rel = raw.decode("utf-8", errors="replace").replace("\\", "/").strip("/")
                        if rel and not any(seg in SKIP_DIRS for seg in rel.split("/")):
                            out.append(rel)
                    return out

                tracked = _decode_list(rc.stdout)
                untracked = _decode_list(ro.stdout)
                all_known_files = sorted(set(tracked) | set(untracked))
                kept = sorted(set(tracked) | set(_filter_bulk_untracked_dumps(tracked, untracked)))
                rel_files = [r for r in kept if (root / r).is_file() and not (root / r).is_symlink()]
        except (OSError, subprocess.SubprocessError):
            git_used = False
    if not git_used:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in sorted(dirnames)
                if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()
            ]
            base = Path(dirpath)
            for name in sorted(filenames):
                p = base / name
                if not p.is_symlink() and p.is_file():
                    rel_files.append(p.relative_to(root).as_posix())
        all_known_files = rel_files
    existing_files = set(all_known_files)
    existing_dirs: set[str] = {""}
    for rel in all_known_files:
        idx = rel.rfind("/")
        while idx > 0:
            parent = rel[:idx]
            if parent in existing_dirs:
                break
            existing_dirs.add(parent)
            idx = parent.rfind("/")
    return rel_files, existing_files, existing_dirs

def _recent_subsystem_churn(root: Path) -> dict[str, int]:
    churn: dict[str, int] = {}
    if not (root / ".git").exists():
        return churn
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "log", "-n", "30", "--format=", "--name-only"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                rel = line.strip().replace("\\", "/")
                if rel:
                    sub = _subsystem_of(rel)
                    churn[sub] = churn.get(sub, 0) + 1
    except (OSError, subprocess.SubprocessError):
        pass
    return churn


def _resolve_doc_link_in_repo(
    target: str, md_parent_rel: str, skill_rel: str | None, sibling_skill_rels: list[str], existing_all: set[str]
) -> bool:
    clean = target.lstrip("/")
    bases = [md_parent_rel, ""]
    if skill_rel is not None:
        bases.append(skill_rel)
        bases.extend(sibling_skill_rels)
    for base_rel in bases:
        joined = f"{base_rel}/{clean}" if base_rel else clean
        norm = posixpath.normpath(joined)
        if norm == ".":
            norm = ""
        if norm.startswith("..") or norm.startswith("/"):
            continue
        if norm in existing_all:
            return True
    return False


def _scan_single_markdown(
    root: Path,
    rel: str,
    skill_rel: str | None,
    sibling_rels: list[str],
    existing_all: set[str],
    overclaims: list[dict],
    broken_links: list[dict],
    roadmap_items: list[dict],
) -> None:
    p = root / rel
    try:
        if p.stat().st_size > 512_000:
            return
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    is_template_doc = p.name.endswith(".template.md")
    can_have_roadmap = (
        not is_template_doc
        and not _is_aux_surface(rel)
        and "/references/" not in f"/{rel}"
        and p.name.upper() != "CHANGELOG.MD"
    )
    md_parent_rel = posixpath.dirname(rel)
    fence_len = 0
    for idx, line in enumerate(lines, 1):
        m_fence = re.match(r"^(`{3,}|~{3,})", line.lstrip())
        if m_fence:
            ticks = len(m_fence.group(1))
            fence_len = ticks if fence_len == 0 else (0 if ticks >= fence_len else fence_len)
            continue
        if fence_len > 0:
            continue
        if can_have_roadmap and len(roadmap_items) < 60:
            m_task = UNCHECKED_TASK_RE.match(line)
            if m_task and "<" not in m_task.group(1):
                roadmap_items.append({"path": rel, "line": idx, "task": m_task.group(1).strip()})
        prose_only = re.sub(r"`[^`]+`", " ", line)
        if not re.search(r"\bkeep\s+100%\s+of\s+scope\b|\b100%\s+vs\b", prose_only, re.I):
            for kind, pat in OVERCLAIM_PATTERNS:
                m = pat.search(prose_only)
                if m:
                    overclaims.append({"path": rel, "line": idx, "kind": kind, "match": m.group(0), "excerpt": line.strip()[:140]})
                    break
        for raw_target in MD_LINK_RE.findall(prose_only):
            target = raw_target.strip("<>").split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith("#") or URI_SCHEME_RE.match(target) or target.startswith("mailto:"):
                continue
            if "{{" in target or "}}" in target or (is_template_doc and target.startswith("../")):
                continue
            if not _resolve_doc_link_in_repo(target, md_parent_rel, skill_rel, sibling_rels, existing_all):
                broken_links.append({"path": rel, "line": idx, "target": target})


def _scan_docs_for_overclaims_and_broken_links(
    root: Path, rel_files: list[str] | None = None, existing_all: set[str] | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    if rel_files is None or existing_all is None:
        rel_files, ef, ed = _collect_repo_files(root)
        existing_all = ef | ed
    skill_dirs = sorted({posixpath.dirname(r) for r in rel_files if r.endswith("/SKILL.md") or r == "SKILL.md"})
    skill_set = set(skill_dirs)
    siblings_by_parent: dict[str, list[str]] = {}
    for sd in skill_dirs:
        par = posixpath.dirname(sd)
        siblings_by_parent.setdefault(par, []).append(sd)
    overclaims: list[dict] = []
    broken_links: list[dict] = []
    roadmap_items: list[dict] = []
    for rel in rel_files:
        if not rel.lower().endswith(".md"):
            continue
        cur = posixpath.dirname(rel)
        skill_rel: str | None = None
        while True:
            if cur in skill_set:
                skill_rel = cur
                break
            if not cur:
                break
            cur = posixpath.dirname(cur)
        sibs = siblings_by_parent.get(posixpath.dirname(skill_rel), []) if skill_rel is not None else []
        _scan_single_markdown(root, rel, skill_rel, sibs, existing_all, overclaims, broken_links, roadmap_items)
    return overclaims, broken_links, roadmap_items


def _extract_imported_stems(joined_text: str) -> set[str]:
    stems: set[str] = set()
    for m_imp in IMPORT_REF_RE.finditer(joined_text):
        raw_imp = next((g for g in m_imp.groups() if g), "")
        clean_imp = raw_imp.replace("\\", "/").rstrip("/")
        leaf = Path(clean_imp.split(".")[-1] if "/" not in clean_imp else clean_imp).stem.lower()
        if len(leaf) >= 3:
            stems.add(leaf)
    for m_from in re.finditer(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\s+([A-Za-z0-9_,\s]+)", joined_text, re.M):
        for part in m_from.group(1).split("."):
            if len(part) >= 3:
                stems.add(part.lower())
    return stems


def _scan_code_debt_and_tests(
    root: Path,
    code_exts: set[str],
    test_re: re.Pattern[str],
    comment_body_fn,
    smell_patterns,
    rel_files: list[str] | None = None,
) -> dict:
    if rel_files is None:
        rel_files, _, _ = _collect_repo_files(root)
    debt: list[dict] = []
    repo_smells: list[dict] = []
    code_dirs: dict[str, set[str]] = {}
    tested_dirs: set[str] = set()
    test_contents_stems: set[str] = set()
    stem_to_subsystems: dict[str, set[str]] = {}
    imported_stem_counts: dict[str, int] = {}
    code_file_count = 0
    core_modules: list[tuple[str, int]] = []
    ui_component_files: list[str] = []
    agent_sdk_files: list[str] = []
    http_route_files: list[str] = []
    has_resilience_guard = False
    has_eval_suite = any("eval" in r.lower() or "bench" in r.lower() for r in rel_files)
    has_browser_e2e = any("playwright" in r.lower() or "cypress" in r.lower() or ".e2e." in r.lower() for r in rel_files)

    for rel in rel_files:
        p = root / rel
        ext = p.suffix.lower()
        if ext not in code_exts:
            continue
        code_file_count += 1
        parent_rel = posixpath.dirname(rel) or "."
        try:
            if p.stat().st_size > 512_000:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        if test_re.search(rel):
            tested_dirs.add(parent_rel)
            par_name = Path(parent_rel).name.lower()
            if par_name in {"tests", "test", "__tests__", "spec"} and "/" in parent_rel:
                tested_dirs.add(posixpath.dirname(parent_rel))
            test_contents_stems.update(_extract_imported_stems(text))
            continue

        subsys = _subsystem_of(rel)
        stem_low = p.stem.lower()
        if stem_low not in {"__init__", "index", "main", "types", "mod", "util", "utils"}:
            stem_to_subsystems.setdefault(stem_low, set()).add(subsys)
        for imp_stem in _extract_imported_stems(text):
            imported_stem_counts[imp_stem] = imported_stem_counts.get(imp_stem, 0) + 1
        if ext in {".tsx", ".vue", ".svelte"} and not _is_aux_surface(rel):
            ui_component_files.append(rel)
        if not _is_aux_surface(rel) and AGENT_SDK_SIGNAL_RE.search(text):
            agent_sdk_files.append(rel)
        if not _is_aux_surface(rel) and HTTP_ROUTE_SIGNAL_RE.search(text):
            http_route_files.append(rel)
        if RESILIENCE_SIGNAL_RE.search(text):
            has_resilience_guard = True
        code_dirs.setdefault(parent_rel, set()).add(stem_low)
        if len([ln for ln in lines if ln.strip()]) >= 2 and p.name != "__init__.py":
            core_modules.append((rel, len(lines)))
        for idx, line in enumerate(lines, 1):
            body = comment_body_fn(rel, line)
            if body is not None:
                m = DEBT_MARKER_RE.search(body)
                if m and len(debt) < 80:
                    debt.append({"path": rel, "line": idx, "marker": m.group(1), "excerpt": line.strip()[:120]})
            elif "re.compile(" not in line and len(repo_smells) < 80:
                for kind, pat, _ in smell_patterns:
                    if pat.search(line):
                        repo_smells.append({"path": rel, "line": idx, "kind": kind})
                        break

    subsystem_fan_in: dict[str, int] = {}
    for stem_k, subs in stem_to_subsystems.items():
        hits = imported_stem_counts.get(stem_k, 0)
        if hits:
            for s_name in subs:
                subsystem_fan_in[s_name] = subsystem_fan_in.get(s_name, 0) + hits

    core_modules.sort(key=lambda item: (_is_aux_surface(item[0]), -(item[1] * (1.0 + 0.08 * subsystem_fan_in.get(_subsystem_of(item[0]), 0))), item[0]))
    untested_dirs = [
        d for d, stems in sorted(code_dirs.items())
        if d not in tested_dirs and not ({s for s in stems if s not in {"__init__", "index", "main", "types"}} & test_contents_stems)
    ]
    return {
        "debt": debt,
        "untested_dirs": untested_dirs,
        "code_file_count": code_file_count,
        "core_modules": core_modules[:25],
        "repo_smells": repo_smells,
        "subsystem_fan_in": subsystem_fan_in,
        "ui_component_files": ui_component_files,
        "agent_sdk_files": agent_sdk_files,
        "http_route_files": http_route_files,
        "has_resilience_guard": has_resilience_guard,
        "has_eval_suite": has_eval_suite,
        "has_browser_e2e": has_browser_e2e,
    }


def _native_dmb_gate_bin() -> Path | None:
    repo_root = ASSETS_DIR.parents[4] if len(ASSETS_DIR.parents) > 4 else ASSETS_DIR
    exe_name = "dmb-gate.exe" if os.name == "nt" else "dmb-gate"
    cand = repo_root / "native" / "dmb-gate" / "target" / "release" / exe_name
    return cand if cand.is_file() else None


def _run_fast_perf_and_gap(safe_root: Path) -> tuple[list[dict], list[dict]]:
    gate_bin = _native_dmb_gate_bin()
    if gate_bin is not None:
        def _call_gate(sub: str) -> list[dict] | None:
            try:
                r = subprocess.run(
                    [str(gate_bin), sub, "--root", str(safe_root), "--json"],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                )
                if r.stdout.strip():
                    return json.loads(r.stdout).get("findings", [])
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_perf = pool.submit(_call_gate, "perf")
            f_gap = pool.submit(_call_gate, "gap")
            p_res, g_res = f_perf.result(), f_gap.result()
        if p_res is not None and g_res is not None:
            return p_res, g_res

    perf_findings: list[dict] = []
    if (ASSETS_DIR / "perf-audit" / "perf_audit.py").is_file():
        perf_audit = _load_sibling("deepmode_perf_audit_mod", "perf-audit/perf_audit.py")
        perf_findings = perf_audit.scan_paths(safe_root).get("findings", [])
    gap_findings: list[dict] = []
    if (ASSETS_DIR / "gap-audit" / "gap_audit.py").is_file():
        gap_audit = _load_sibling("deepmode_gap_audit_mod", "gap-audit/gap_audit.py")
        gap_findings = gap_audit.scan_repo(safe_root).get("findings", [])
    return perf_findings, gap_findings


def _group_by_subsystem(items: list[dict], path_key: str) -> list[tuple[str, list[dict]]]:
    buckets: dict[str, list[dict]] = {}
    for it in items:
        sub = _subsystem_of(it[path_key])
        buckets.setdefault(sub, []).append(it)
    return sorted(buckets.items(), key=lambda kv: (all(_is_aux_surface(x[path_key]) for x in kv[1]), -len(kv[1]), kv[0]))


def _compute_leverage_score(priority: str, subsys: str, count: int, fan_in: dict[str, int], churn: dict[str, int], aux: bool) -> int:
    base = {"P0": 88, "P1": 68, "P2": 44}.get(priority, 40)
    score = base + min(8, fan_in.get(subsys, 0) * 2) + min(6, churn.get(subsys, 0)) + min(6, count)
    score += -14 if aux else 4
    return max(10, min(99, score))


def _emit_capability_and_roadmap_tasks(
    add_fn, roadmap_items: list[dict], code_info: dict, verify_skills: list[str]
) -> None:
    if roadmap_items:
        for subsys, items in _group_by_subsystem(roadmap_items, "path"):
            refs = [f"{r['path']}:{r['line']} ({r['task'][:70]})" for r in items]
            add_fn(
                "P1", "capability", f"[{subsys}] Ship {len(items)} unchecked roadmap/spec deliverable(s)",
                refs, subsys, False,
                f"/deep [HARDCORE MODE] Full-scope delivery of {len(items)} unchecked roadmap/spec deliverable(s) in `{subsys}` "
                f"({', '.join(refs[:5])}): 1. Implement every listed deliverable end-to-end with production data models and error handling. "
                f"2. Check off verified items only after real behavioral tests and runtime proof pass. 3. Run self-grill.",
            )
    if code_info["agent_sdk_files"] and not code_info["has_eval_suite"]:
        refs = code_info["agent_sdk_files"][:8]
        sub = _subsystem_of(refs[0])
        add_fn(
            "P1", "capability", f"[{sub}] Build deterministic offline + adversarial eval harness for LLM/agent workflows",
            refs, sub, False,
            f"/deep [HARDCORE MODE] Full-scope LLM/agent evaluation & regression harness for `{sub}` ({', '.join(refs[:4])}): "
            f"1. Build a deterministic golden + adversarial evaluation suite covering tool calls, failure recovery, prompt injection, and output invariants. "
            f"2. Wire baseline pass-rate and latency metrics into local CI gates. 3. Prove the eval runner exits 0 and run self-grill.",
        )
    if code_info["http_route_files"] and not code_info["has_resilience_guard"]:
        refs = code_info["http_route_files"][:8]
        sub = _subsystem_of(refs[0])
        add_fn(
            "P1", "capability", f"[{sub}] Add schema validation, idempotency, timeouts, and rate-limit guards to HTTP/RPC boundaries",
            refs, sub, False,
            f"/deep [HARDCORE MODE] Full-scope API & boundary hardening for `{sub}` ({', '.join(refs[:4])}): "
            f"1. Enforce strict input schema validation, explicit upstream timeouts, idempotency keys on mutating routes, and rate-limit protection. "
            f"2. Add hostile/malformed payload and retry regression tests. 3. Prove all gates exit 0 and run self-grill.",
        )
    if len(code_info["ui_component_files"]) >= 3 and not code_info["has_browser_e2e"] and not verify_skills:
        refs = code_info["ui_component_files"][:8]
        sub = _subsystem_of(refs[0])
        add_fn(
            "P1", "verification", f"[{sub}] Add real-browser Desktop + Mobile visual E2E, motion, and a11y verification",
            refs, sub, False,
            f"/deep [HARDCORE MODE] Full-scope real-browser E2E & UI gate for `{sub}` ({', '.join(refs[:4])}): "
            f"1. Build automated Desktop (1440x900) and Mobile (390x844) browser journeys exercising real user flows, keyboard focus, and OKLCH/layout tokens. "
            f"2. Pass deepmodebot gate ui and capture reproducible runtime proof. 3. Run self-grill.",
        )


def _emit_core_module_tasks(add_fn, core_modules: list[tuple[str, int]]) -> None:
    if not core_modules:
        return
    seen_subs: set[str] = set()
    grouped: list[tuple[str, list[tuple[str, int]]]] = []
    for path, n_lines in core_modules:
        if _is_aux_surface(path) and any(not _is_aux_surface(p) for p, _ in core_modules):
            continue
        sub = _subsystem_of(path)
        if n_lines < 220 and grouped:
            continue
        if sub not in seen_subs:
            seen_subs.add(sub)
            sub_mods = [(p, nl) for p, nl in core_modules if _subsystem_of(p) == sub and (nl >= 220 or not grouped)][:4]
            grouped.append((sub, sub_mods))
    for idx, (sub, mods) in enumerate(grouped):
        refs = [f"{p} ({nl} lines)" for p, nl in mods]
        paths_csv = ", ".join(p for p, _ in mods)
        prefix = f"[{sub}] " if len(grouped) > 1 or idx > 0 else ""
        add_fn(
            "P1", "hardcore", f"{prefix}Hardcore Mode architectural ceiling upgrade on core source modules",
            refs, sub, all(_is_aux_surface(p) for p, _ in mods),
            f"/deep [HARDCORE MODE] First-principles architectural ceiling upgrade for `{sub}` core module(s) ({paths_csv}): "
            f"1. Inspect {paths_csv} and identify every flat approximation, single-threaded bottleneck, shallow pass-through seam, "
            f"or naive algorithm holding back the system ceiling. "
            f"2. Upgrade straight to the true first-principles architecture (batch query plans, bounded async concurrency, "
            f"cache-friendly data structures, crisp native representations, and full integration). "
            f"3. Prove end-to-end behavior and measured gains on the real artifact, and run self_grill.py check-diff.",
        )


def _emit_p0_and_diff_tasks(
    add_fn, broken_links: list[dict], overclaims: list[dict], gap_findings: list[dict], diff: dict
) -> None:
    if broken_links:
        refs = [f"{b['path']}:{b['line']} -> {b['target']}" for b in broken_links]
        add_fn(
            "P0", "overclaim", "Fix broken documentation links and audit referenced paths",
            refs, "docs", False,
            f"/deep Full-scope doc link and accuracy audit: 1. Inspect and fix all {len(broken_links)} broken local doc link(s) "
            f"({', '.join(refs[:5])}). 2. Audit every doc file for stale paths, missing files, and unbacked claims. "
            f"3. Prove every remaining link resolves on disk and run repo checks + self-grill before reporting.",
        )
    if overclaims:
        non_aux_oc = [o for o in overclaims if not _is_aux_surface(o["path"])] or overclaims
        refs = [f"{o['path']}:{o['line']} ({o['match']})" for o in non_aux_oc]
        add_fn(
            "P0", "overclaim", "Audit documentation for overclaims and back or downgrade every guarantee",
            refs, "docs", len(non_aux_oc) != len(overclaims) and all(_is_aux_surface(o["path"]) for o in non_aux_oc),
            f"/deep Full-scope gap and overclaim audit across docs: 1. Inspect all {len(non_aux_oc)} flagged guarantee/coverage claim(s) "
            f"({', '.join(refs[:5])}). 2. For each claim, either prove it with a real command/test receipt or rewrite it to state exact tested bounds and limits. "
            f"3. Run doc/repo checks and self-grill, and report each claim's verdict with file:line evidence.",
        )
    drift_gaps = [
        g for g in gap_findings
        if g["rule"] in ("doc-script-flag-drift", "doc-cli-subcommand-drift", "stale-replaces-claim", "cross-lang-gate-drift")
    ]
    for subsys, items in _group_by_subsystem(drift_gaps, "file"):
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in items]
        add_fn(
            "P0", "gap", f"[{subsys}] Eliminate doc-to-CLI flag drift, stale replacement claims, and cross-language gate drift",
            refs, subsys, all(_is_aux_surface(g["file"]) for g in items),
            f"/deep Full-scope spec-to-code and cross-language parity fix in `{subsys}` across {len(items)} drift finding(s) "
            f"({', '.join(refs[:5])}): 1. Reconcile every documented CLI flag/subcommand, stale replacement comment, and Python-vs-Rust gate rule mismatch at the root. "
            f"2. Add regression tests asserting 1:1 parity across docs, Python scripts, and native binaries. "
            f"3. Prove gap_audit.py scan --root . exits 0 and run self-grill.",
        )
    if diff["sensitive_paths"]:
        refs = list(diff["sensitive_paths"])
        add_fn(
            "P0", "checks", "Self-grill and security-audit sensitive paths in the current diff",
            refs, _subsystem_of(refs[0]), False,
            f"/deep Full-scope security and self-grill audit on active diff touching sensitive path(s) ({', '.join(refs[:5])}): "
            f"1. Run self_grill.py check-diff and verify fail-closed handling on missing, malformed, and hostile inputs. "
            f"2. Add failing-without-fix regression tests for every trust boundary touched. "
            f"3. Run a cross-family skeptic review, prove all checks exit 0 on the current tree, and report gaps or blockers.",
        )
    if diff["code_paths"] and not diff["test_paths"]:
        refs = list(diff["code_paths"])
        add_fn(
            "P1", "gap", "Add failing-without-fix regression tests for changed code files",
            refs, _subsystem_of(refs[0]), False,
            f"/deep Full-scope test coverage for active diff: 1. Inspect changed code ({', '.join(refs[:5])}) that currently has zero test edits. "
            f"2. Write behavioral tests (no tautological mocks) proven to fail if each change is reverted. "
            f"3. Run the full test suite and self_grill.py check-diff to verify PASS with raw exit code 0.",
        )
    if diff["added_comment_count"] > 0:
        refs = [f"{c['path']}:{c['line']}" for c in diff["added_comments"]]
        add_fn(
            "P1", "checks", "Run comment-sicko / no-comments on added code comments in diff",
            refs, _subsystem_of(diff["added_comments"][0]["path"]), False,
            f"/deep Full-scope no-comments cleanup: 1. Inspect all {diff['added_comment_count']} added code comment(s) "
            f"({', '.join(refs[:5])}) because stale comments rot and mislead agents into reading comments instead of code. "
            f"2. Delete narration, banners, workarounds, and unsafe suppressions; encode real constraints in types, names, or tests. "
            f"3. Re-run tests and self_grill.py check-diff to confirm clean diff.",
        )


def _emit_subsystem_and_hygiene_tasks(
    add_fn, safe_root: Path, gap_findings: list[dict], perf_findings: list[dict], diff: dict, code_info: dict, verify_skills: list[str]
) -> None:
    silent_gaps = [g for g in gap_findings if g["rule"] in ("hollow-stub-body", "swallowed-exception")]
    for subsys, items in _group_by_subsystem(silent_gaps, "file"):
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in items]
        add_fn(
            "P1", "gap", f"[{subsys}] Replace hollow stub functions and silent swallowed exceptions with real behavior",
            refs, subsys, all(_is_aux_surface(g["file"]) for g in items),
            f"/deep [HARDCORE MODE] Full-scope elimination of {len(items)} hollow stub / silent error black-hole(s) in `{subsys}` "
            f"({', '.join(refs[:5])}): 1. Replace every hollow no-op `pass` or empty function body with a complete production implementation or explicit ABC/Protocol contract. "
            f"2. Replace broad `except Exception: pass` and `.catch(() => {{}})` black-holes with narrow error handling and observable failure states. "
            f"3. Prove gap_audit.py scan --root . exits 0, add failure-path tests, and run self-grill.",
        )
    for subsys, items in _group_by_subsystem(perf_findings, "file"):
        refs = [f"{f['file']}:{f['line']} ({f.get('rule_id') or f.get('rule', 'perf')})" for f in items]
        add_fn(
            "P1", "perf", f"[{subsys}] Eliminate backend hot-path, database N+1, and high-scale server bottlenecks",
            refs, subsys, all(_is_aux_surface(f["file"]) for f in items),
            f"/deep [HARDCORE MODE] Full-scope backend & systems performance optimization in `{subsys}` across {len(items)} "
            f"perf_audit finding(s) ({', '.join(refs[:5])}): "
            f"1. Load skill://domain-rules/references/high-scale-server-optimization.md and data-structures-and-cache-optimization.md, "
            f"and capture baseline p50/p95/p99 latency + query counts via bench_harness.py or EXPLAIN ANALYZE. "
            f"2. Fix every N+1/await-in-loop waterfall, sync-in-async block, missing timeout, per-request pool, OFFSET scan, "
            f"and framework/serialization bottleneck at the root. "
            f"3. Prove perf_audit.py --fail-on-high exits 0, verify before/after delta on the real harness, and run self-grill.",
        )
    smell_items = diff["workaround_smells"] or code_info["repo_smells"]
    for subsys, items in _group_by_subsystem(smell_items, "path"):
        refs = [f"{s['path']}:{s['line']}({s['kind']})" for s in items]
        add_fn(
            "P1", "gardening", f"[{subsys}] Replace imperative-timer, raw useEffect, or unsafe cast workarounds at the root",
            refs, subsys, all(_is_aux_surface(s["path"]) for s in items),
            f"/deep Full-scope root-cause cleanup in `{subsys}` for {len(items)} workaround smell(s) ({', '.join(refs[:5])}): "
            f"1. Eliminate each imperative timer, raw useEffect, or unsafe type cast at the root cause. "
            f"2. Add a deterministic lint or type check so the pattern cannot return. "
            f"3. Prove behavior with tests and self_grill.py check-diff.",
        )
    if not verify_skills and code_info["code_file_count"] >= 3:
        add_fn(
            "P1", "verification", "Create a project-local verify-<app> skill with control CLI and full feature map",
            [f"code_files={code_info['code_file_count']}", "verify_skills=0"], "root", False,
            "/deep Full-scope verification setup: 1. Interview this repo and generate a project-local verify-<app> skill "
            "with a single control CLI (launch, doctor, inspect, drive, cleanup) and complete user-POV feature map across every route/command. "
            "2. Prove the skill end-to-end on the real app and confirm evidence survives cleanup. "
            "3. Wire it into repo instructions and audit for gaps or unverified steps.",
        )
    untested_by_sub: dict[str, list[str]] = {}
    for d in code_info["untested_dirs"]:
        untested_by_sub.setdefault(_subsystem_of(f"{d}/x"), []).append(d)
    for subsys, dirs in sorted(untested_by_sub.items(), key=lambda kv: (all(_is_aux_surface(f"{x}/") for x in kv[1]), -len(kv[1]), kv[0])):
        aux_u = all(_is_aux_surface(f"{x}/") for x in dirs)
        add_fn(
            "P2" if aux_u else "P1", "gap", f"[{subsys}] Close missing test coverage in code directories with no sibling tests",
            dirs, subsys, aux_u,
            f"/deep Full-scope gap audit and test hardening for `{subsys}`: 1. Inspect untested code directories ({', '.join(dirs[:6])}) "
            f"and prioritize highest-risk public contracts and failure paths. "
            f"2. Add real behavioral tests (never tautological mocks) covering happy paths and edge failures. "
            f"3. Run all checks and self-grill to confirm zero regressions.",
        )
    _emit_core_module_tasks(add_fn, code_info["core_modules"])
    unwired_gaps = [g for g in gap_findings if g["rule"] == "unwired-script-asset"]
    for subsys, items in _group_by_subsystem(unwired_gaps, "file"):
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in items]
        add_fn(
            "P2", "gap", f"[{subsys}] Wire orphaned skill/tool scripts into active workflows or prune dead assets",
            refs, subsys, False,
            f"/deep Full-scope dead-seam audit in `{subsys}` for {len(items)} unwired script asset(s) ({', '.join(refs[:5])}): "
            f"1. Inspect each unreferenced script and either wire it into its owning SKILL.md / CLI dispatcher with end-to-end tests or delete dead code. "
            f"2. Prove gap_audit.py scan --root . reports 0 unwired assets and run self-grill.",
        )
    for subsys, items in _group_by_subsystem(code_info["debt"], "path"):
        refs = [f"{d['path']}:{d['line']} ({d['marker']})" for d in items]
        add_fn(
            "P2", "gardening", f"[{subsys}] Triage and resolve TODO/FIXME/HACK markers via codebase gardening",
            refs, subsys, all(_is_aux_surface(d["path"]) for d in items),
            f"/deep Full-scope codebase gardening in `{subsys}` for {len(items)} TODO/FIXME/HACK marker(s) ({', '.join(refs[:5])}): "
            f"1. Group markers by shared root cause into a pattern buffer instead of patching one by one. "
            f"2. Fix valid items, delete obsolete markers/workarounds, and encode recurring rules as lints/types/tests. "
            f"3. Prove all tests pass and run self-grill.",
        )
    if code_info["code_file_count"] >= 10 and not (safe_root / "GLOSSARY.md").is_file() and not (safe_root / "docs" / "adr").is_dir():
        add_fn(
            "P2", "gardening", "Establish domain glossary and architecture decision records",
            [f"code_files={code_info['code_file_count']}", "GLOSSARY.md=missing", "docs/adr=missing"], "docs", False,
            "/deep Full-scope domain modeling and architecture baseline: 1. Audit core domain terms and high-churn modules "
            "across the repo. 2. Create GLOSSARY.md and initial docs/adr/ records for non-obvious architectural choices. "
            "3. Verify every entry cites real code paths with zero fabricated claims.",
        )


def suggest_prompts(root: Path, limit: int = 0) -> dict:
    self_grill = _load_sibling("deepmode_self_grill_mod", "self-grill/self_grill.py")
    safe_root = self_grill.reject_unsafe_root(root)
    rel_files, existing_files, existing_dirs = _collect_repo_files(safe_root)
    existing_all = existing_files | existing_dirs
    verify_skills = _has_verify_skill(safe_root)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        f_churn = pool.submit(_recent_subsystem_churn, safe_root)
        f_diff = pool.submit(self_grill.inspect_diff, safe_root)
        f_docs = pool.submit(_scan_docs_for_overclaims_and_broken_links, safe_root, rel_files, existing_all)
        f_code = pool.submit(
            _scan_code_debt_and_tests,
            safe_root,
            self_grill.CODE_EXTS,
            self_grill.TEST_PATH_RE,
            self_grill._comment_body,
            self_grill.WORKAROUND_SMELL_PATTERNS,
            rel_files,
        )
        f_gates = pool.submit(_run_fast_perf_and_gap, safe_root)
        churn = f_churn.result()
        diff = f_diff.result()
        overclaims, broken_links, roadmap_items = f_docs.result()
        code_info = f_code.result()
        perf_findings, gap_findings = f_gates.result()

    fan_in = code_info["subsystem_fan_in"]
    all_suggestions: list[dict] = []
    wave_for = {"P0": 1, "P1": 2, "P2": 3}

    def add(priority: str, kind: str, title: str, evidence: list[str], subsys: str, aux: bool, prompt: str) -> None:
        score = _compute_leverage_score(priority, subsys, len(evidence), fan_in, churn, aux)
        all_suggestions.append({
            "priority": priority,
            "wave": wave_for.get(priority, 3),
            "leverage_score": score,
            "subsystem": subsys,
            "kind": kind,
            "title": title,
            "evidence": evidence,
            "prompt": prompt,
        })

    _emit_p0_and_diff_tasks(add, broken_links, overclaims, gap_findings, diff)
    _emit_capability_and_roadmap_tasks(add, roadmap_items, code_info, verify_skills)
    _emit_subsystem_and_hygiene_tasks(add, safe_root, gap_findings, perf_findings, diff, code_info, verify_skills)

    rank = {"P0": 0, "P1": 1, "P2": 2}
    all_suggestions.sort(key=lambda s: (rank.get(s["priority"], 9), -s["leverage_score"], s["title"]))
    total_count = len(all_suggestions)
    suggestions = all_suggestions[:limit] if limit and limit > 0 else all_suggestions
    subsystems_mapped = sorted({s["subsystem"] for s in all_suggestions})

    return {
        "root": str(safe_root),
        "hardcore_mode": True,
        "full_scope": not (limit and limit > 0),
        "total_leverage_tasks": total_count,
        "truncated": len(suggestions) < total_count,
        "subsystems_mapped": subsystems_mapped,
        "code_file_count": code_info["code_file_count"],
        "core_modules": [{"path": p, "lines": n, "subsystem": _subsystem_of(p)} for p, n in code_info["core_modules"]],
        "verify_skills": verify_skills,
        "diff_size": diff["measured_size"],
        "overclaim_hits": len(overclaims),
        "broken_link_hits": len(broken_links),
        "roadmap_unchecked_hits": len(roadmap_items),
        "debt_marker_hits": len(code_info["debt"]),
        "perf_audit_hits": len(perf_findings),
        "gap_audit_hits": len(gap_findings),
        "suggestions": suggestions,
    }


def cmd_upgrade(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.stdin else (args.prompt or "")
    root = Path(args.root) if args.root else None
    result = upgrade_prompt(raw, root=root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["upgraded_prompt"])
    return 0


def cmd_clarify(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.stdin else (args.prompt or "")
    root = Path(args.root) if args.root else None
    res = analyze_ambiguity(raw, root=root)
    if args.json:
        print(json.dumps(res, indent=2))
    elif res["needs_clarification"]:
        print(f"clarify [ASK_ONCE_UPFRONT]: {', '.join(res['signals'])}")
        for idx, q in enumerate(res["questions"], 1):
            print(f"  Q{idx}: {q['question']} -> {'; '.join(q['options'])}")
    else:
        print("clarify [CLEAR_RUN_AUTONOMOUSLY]: 0 questions needed")
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    result = suggest_prompts(Path(args.root), limit=args.limit)
    if getattr(args, "ui", False) or getattr(args, "open", False):
        gen_ui = _load_sibling("deepmode_gen_ui_mod", "gen-ui/gen_ui.py")
        ui_out = gen_ui.generate_from_suggest(
            Path(result["root"]),
            slug="suggest",
            limit=args.limit,
            open_browser=bool(getattr(args, "open", False)),
            precomputed=result,
        )
        result["ui_surface"] = ui_out["ui_surface"]
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"High-Leverage Project Map ({len(result['suggestions'])}/{result['total_leverage_tasks']} task(s) across "
            f"{len(result['subsystems_mapped'])} subsystem(s)):"
        )
        for idx, item in enumerate(result["suggestions"], 1):
            print(
                f"{idx}. [W{item['wave']} {item['priority']}/{item['kind']} · score={item['leverage_score']}] {item['title']}"
            )
            print(f"   evidence ({len(item['evidence'])}): {', '.join(item['evidence'][:8])}")
            print(f"   prompt: {item['prompt']}")
        if "ui_surface" in result:
            print(f"   a2ui: {result['ui_surface']['a2ui_path']}")
            print(f"   cockpit: {result['ui_surface']['html_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt reviewer/upgrader and repo gap/overclaim prompt suggester.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("upgrade", help="Review a raw user prompt and compile a full-scope deepmodebot prompt.")
    p_up.add_argument("--stdin", action="store_true")
    p_up.add_argument("--prompt", default="")
    p_up.add_argument("--root", default=None)
    p_up.add_argument("--json", action="store_true")
    p_up.set_defaults(func=cmd_upgrade)

    p_cl = sub.add_parser("clarify", help="Check whether /deep should ask 1 upfront clarification round or run immediately.")
    p_cl.add_argument("--stdin", action="store_true")
    p_cl.add_argument("--prompt", default="")
    p_cl.add_argument("--root", default=None)
    p_cl.add_argument("--json", action="store_true")
    p_cl.set_defaults(func=cmd_clarify)

    p_sug = sub.add_parser("suggest", help="Scan a repo for gaps and overclaims and suggest full-scope /deep prompts.")
    p_sug.add_argument("--root", required=True)
    p_sug.add_argument("--limit", type=int, default=0, help="Max tasks to return (0 = full un-truncated scope, default).")
    p_sug.add_argument("--ui", action="store_true", help="Also emit an A2UI v1.0 surface and interactive HTML cockpit.")
    p_sug.add_argument("--open", action="store_true", help="Open the interactive HTML cockpit in the default browser.")
    p_sug.add_argument("--json", action="store_true")
    p_sug.set_defaults(func=cmd_suggest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
