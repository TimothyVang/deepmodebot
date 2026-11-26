#!/usr/bin/env python3
"""Prompt reviewer/full-scope upgrader and repo gap/overclaim prompt suggester for deepmodebot.

    python prompt_tools.py upgrade --stdin [--root <repo>] [--json] <<'EOF'
    python prompt_tools.py suggest --root <repo> [--limit 8] [--json]
"""
import argparse
import importlib.util
import json
import os
import re
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
    "venv", "dist", "build", ".next", "target", ".pytest_cache",
}

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

    return {
        "original_prompt": raw_prompt.strip(),
        "hardcore_mode": hardcore_mode,
        "promoted_optional_hardcore": promoted_hardcore,
        "decoded_deliverables": deliverables,
        "weaknesses": weaknesses,
        "needs_upgrade": bool(weaknesses),
        "route": route,
        "verify_skills": verify_skills,
        "upgraded_prompt": "\n".join(upgraded_lines),
    }


def _scan_docs_for_overclaims_and_broken_links(root: Path) -> tuple[list[dict], list[dict]]:
    overclaims: list[dict] = []
    broken_links: list[dict] = []
    seen_md: set[Path] = set()
    candidates: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()
        ]
        base = Path(dirpath)
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            p = base / name
            if p.is_symlink():
                continue
            resolved_p = p.resolve()
            if resolved_p not in seen_md:
                seen_md.add(resolved_p)
                candidates.append(p)

    resolved_root = root.resolve()
    for md in candidates:
        rel = md.relative_to(root).as_posix()
        skill_dir = next(
            (p for p in md.parents if (p / "SKILL.md").is_file() and (p == root or root in p.parents)),
            None,
        )
        sibling_skills = [p.parent for p in skill_dir.parent.glob("*/SKILL.md")] if skill_dir is not None else []
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        fence_len = 0
        for idx, line in enumerate(lines, 1):
            stripped = line.lstrip()
            m_fence = re.match(r"^(`{3,}|~{3,})", stripped)
            if m_fence:
                ticks = len(m_fence.group(1))
                if fence_len == 0:
                    fence_len = ticks
                elif ticks >= fence_len:
                    fence_len = 0
                continue
            if fence_len > 0:
                continue
            prose_only = re.sub(r"`[^`]+`", " ", line)
            if not re.search(r"\bkeep\s+100%\s+of\s+scope\b|\b100%\s+vs\b", prose_only, re.I):
                for kind, pat in OVERCLAIM_PATTERNS:
                    m = pat.search(prose_only)
                    if m:
                        overclaims.append(
                            {
                                "path": rel,
                                "line": idx,
                                "kind": kind,
                                "match": m.group(0),
                                "excerpt": line.strip()[:140],
                            }
                        )
                        break
            is_template_doc = md.name.endswith(".template.md")
            for raw_target in MD_LINK_RE.findall(prose_only):
                target = raw_target.strip("<>").split("#", 1)[0].split("?", 1)[0].strip()
                if not target or target.startswith("#") or URI_SCHEME_RE.match(target) or target.startswith("mailto:"):
                    continue
                if "{{" in target or "}}" in target or (is_template_doc and target.startswith("../")):
                    continue
                bases = [md.parent, root]
                if skill_dir is not None:
                    bases.extend([skill_dir, *sibling_skills])
                found_link = False
                for base_dir in bases:
                    cand = (base_dir / target.lstrip("/")).resolve()
                    try:
                        cand.relative_to(resolved_root)
                    except ValueError:
                        continue
                    if cand.exists():
                        found_link = True
                        break
                if not found_link:
                    broken_links.append(
                        {
                            "path": rel,
                            "line": idx,
                            "target": target,
                        }
                    )
    return overclaims, broken_links


def _scan_code_debt_and_tests(
    root: Path, code_exts: set[str], test_re: re.Pattern[str], comment_body_fn, smell_patterns
) -> tuple[list[dict], list[str], int, list[tuple[str, int]], list[dict]]:
    debt: list[dict] = []
    repo_smells: list[dict] = []
    code_dirs: dict[str, set[str]] = {}
    tested_dirs: set[str] = set()
    test_contents_stems: set[str] = set()
    code_file_count = 0
    core_modules: list[tuple[str, int]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()
        ]
        base = Path(dirpath)
        for name in sorted(filenames):
            p = base / name
            if p.is_symlink() or p.suffix.lower() not in code_exts:
                continue
            rel = p.relative_to(root).as_posix()
            code_file_count += 1
            parent_rel = p.parent.relative_to(root).as_posix()
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            if test_re.search(rel):
                tested_dirs.add(parent_rel)
                if p.parent.name.lower() in {"tests", "test", "__tests__", "spec"} and p.parent.parent != root:
                    tested_dirs.add(p.parent.parent.relative_to(root).as_posix())
                joined_test = "\n".join(lines)
                for m_imp in IMPORT_REF_RE.finditer(joined_test):
                    raw_imp = next((g for g in m_imp.groups() if g), "")
                    clean_imp = raw_imp.replace("\\", "/").rstrip("/")
                    leaf = Path(clean_imp.split(".")[-1] if "/" not in clean_imp else clean_imp).stem.lower()
                    if len(leaf) >= 3:
                        test_contents_stems.add(leaf)
                for m_from in re.finditer(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\s+([A-Za-z0-9_,\s]+)", joined_test, re.M):
                    for part in m_from.group(1).split("."):
                        if len(part) >= 3:
                            test_contents_stems.add(part.lower())
                continue

            code_dirs.setdefault(parent_rel, set()).add(p.stem.lower())
            if len([ln for ln in lines if ln.strip()]) >= 2 and p.name != "__init__.py":
                core_modules.append((rel, len(lines)))
            for idx, line in enumerate(lines, 1):
                body = comment_body_fn(rel, line)
                if body is not None:
                    m = DEBT_MARKER_RE.search(body)
                    if m and len(debt) < 30:
                        debt.append(
                            {
                                "path": rel,
                                "line": idx,
                                "marker": m.group(1),
                                "excerpt": line.strip()[:120],
                            }
                        )
                elif "re.compile(" not in line and len(repo_smells) < 30:
                    for kind, pat, _ in smell_patterns:
                        if pat.search(line):
                            repo_smells.append({"path": rel, "line": idx, "kind": kind})
                            break

    core_modules.sort(key=lambda item: (-item[1], item[0]))
    untested_dirs: list[str] = []
    for d, stems in sorted(code_dirs.items()):
        non_trivial = {s for s in stems if s not in {"__init__", "index", "main", "types"}}
        if d in tested_dirs:
            continue
        if non_trivial and (non_trivial & test_contents_stems):
            continue
        untested_dirs.append(d)
    return debt, untested_dirs, code_file_count, core_modules[:5], repo_smells


def suggest_prompts(root: Path, limit: int = 8) -> dict:
    self_grill = _load_sibling("deepmode_self_grill_mod", "self-grill/self_grill.py")
    safe_root = self_grill.reject_unsafe_root(root)
    diff = self_grill.inspect_diff(safe_root)
    verify_skills = _has_verify_skill(safe_root)
    overclaims, broken_links = _scan_docs_for_overclaims_and_broken_links(safe_root)
    debt, untested_dirs, code_file_count, core_modules, repo_smells = _scan_code_debt_and_tests(
        safe_root,
        self_grill.CODE_EXTS,
        self_grill.TEST_PATH_RE,
        self_grill._comment_body,
        self_grill.WORKAROUND_SMELL_PATTERNS,
    )
    perf_findings: list[dict] = []
    if (ASSETS_DIR / "perf-audit" / "perf_audit.py").is_file():
        perf_audit = _load_sibling("deepmode_perf_audit_mod", "perf-audit/perf_audit.py")
        perf_findings = perf_audit.scan_paths(safe_root).get("findings", [])
    gap_findings: list[dict] = []
    if (ASSETS_DIR / "gap-audit" / "gap_audit.py").is_file():
        gap_audit = _load_sibling("deepmode_gap_audit_mod", "gap-audit/gap_audit.py")
        gap_findings = gap_audit.scan_repo(safe_root).get("findings", [])
    suggestions: list[dict] = []

    def add(priority: str, kind: str, title: str, evidence: list[str], prompt: str) -> None:
        suggestions.append(
            {
                "priority": priority,
                "kind": kind,
                "title": title,
                "evidence": evidence,
                "prompt": prompt,
            }
        )

    if broken_links:
        refs = [f"{b['path']}:{b['line']} -> {b['target']}" for b in broken_links[:5]]
        add(
            "P0",
            "overclaim",
            "Fix broken documentation links and audit referenced paths",
            refs,
            f"/deep Full-scope doc link and accuracy audit: 1. Inspect and fix all {len(broken_links)} broken local doc link(s) "
            f"({', '.join(refs[:3])}). 2. Audit every doc file for stale paths, missing files, and unbacked claims. "
            f"3. Prove every remaining link resolves on disk and run repo checks + self-grill before reporting.",
        )

    if overclaims:
        refs = [f"{o['path']}:{o['line']} ({o['match']})" for o in overclaims[:5]]
        add(
            "P0",
            "overclaim",
            "Audit documentation for overclaims and back or downgrade every guarantee",
            refs,
            f"/deep Full-scope gap and overclaim audit across docs: 1. Inspect all {len(overclaims)} flagged guarantee/coverage claim(s) "
            f"({', '.join(refs[:3])}). 2. For each claim, either prove it with a real command/test receipt or rewrite it to state exact tested bounds and limits. "
            f"3. Run doc/repo checks and self-grill, and report each claim's verdict with file:line evidence.",
        )

    drift_gaps = [
        g for g in gap_findings
        if g["rule"] in ("doc-script-flag-drift", "doc-cli-subcommand-drift", "stale-replaces-claim", "cross-lang-gate-drift")
    ]
    if drift_gaps:
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in drift_gaps[:5]]
        add(
            "P0",
            "gap",
            "Eliminate doc-to-CLI flag drift, stale replacement claims, and cross-language gate drift",
            refs,
            f"/deep Full-scope spec-to-code and cross-language parity fix across {len(drift_gaps)} drift finding(s) "
            f"({', '.join(refs[:4])}): "
            f"1. Reconcile every documented CLI flag/subcommand, stale replacement comment, and Python-vs-Rust gate rule mismatch at the root. "
            f"2. Add regression tests asserting 1:1 parity across docs, Python scripts, and native binaries. "
            f"3. Prove gap_audit.py scan --root . exits 0 and run self-grill.",
        )

    silent_gaps = [g for g in gap_findings if g["rule"] in ("hollow-stub-body", "swallowed-exception")]
    if silent_gaps:
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in silent_gaps[:5]]
        add(
            "P1",
            "gap",
            "Replace hollow stub functions and silent swallowed exceptions with real behavior",
            refs,
            f"/deep [HARDCORE MODE] Full-scope elimination of {len(silent_gaps)} hollow stub / silent error black-hole(s) "
            f"({', '.join(refs[:4])}): "
            f"1. Replace every no-op `pass`/`NotImplementedError`/`todo!()` stub with a complete production implementation or explicit ABC/Protocol contract. "
            f"2. Replace broad `except Exception: pass` and `.catch(() => {{}})` black-holes with narrow error handling and observable failure states. "
            f"3. Prove gap_audit.py scan --root . exits 0, add failure-path tests, and run self-grill.",
        )

    unwired_gaps = [g for g in gap_findings if g["rule"] == "unwired-script-asset"]
    if unwired_gaps:
        refs = [f"{g['file']}:{g['line']} ({g['rule']})" for g in unwired_gaps[:5]]
        add(
            "P2",
            "gap",
            "Wire orphaned skill/tool scripts into active workflows or prune dead assets",
            refs,
            f"/deep Full-scope dead-seam audit for {len(unwired_gaps)} unwired script asset(s) ({', '.join(refs[:4])}): "
            f"1. Inspect each unreferenced script and either wire it into its owning SKILL.md / CLI dispatcher with end-to-end tests or delete dead code. "
            f"2. Prove gap_audit.py scan --root . reports 0 unwired assets and run self-grill.",
        )

    if diff["sensitive_paths"]:
        refs = diff["sensitive_paths"][:5]
        add(
            "P0",
            "checks",
            "Self-grill and security-audit sensitive paths in the current diff",
            refs,
            f"/deep Full-scope security and self-grill audit on active diff touching sensitive path(s) ({', '.join(refs)}): "
            f"1. Run self_grill.py check-diff and verify fail-closed handling on missing, malformed, and hostile inputs. "
            f"2. Add failing-without-fix regression tests for every trust boundary touched. "
            f"3. Run a cross-family skeptic review, prove all checks exit 0 on the current tree, and report gaps or blockers.",
        )

    if diff["code_paths"] and not diff["test_paths"]:
        refs = diff["code_paths"][:5]
        add(
            "P1",
            "gap",
            "Add failing-without-fix regression tests for changed code files",
            refs,
            f"/deep Full-scope test coverage for active diff: 1. Inspect changed code ({', '.join(refs)}) that currently has zero test edits. "
            f"2. Write behavioral tests (no tautological mocks) proven to fail if each change is reverted. "
            f"3. Run the full test suite and self_grill.py check-diff to verify PASS with raw exit code 0.",
        )

    if diff["added_comment_count"] > 0:
        refs = [f"{c['path']}:{c['line']}" for c in diff["added_comments"][:5]]
        add(
            "P1",
            "checks",
            "Run comment-sicko / no-comments on added code comments in diff",
            refs,
            f"/deep Full-scope no-comments cleanup: 1. Inspect all {diff['added_comment_count']} added code comment(s) "
            f"({', '.join(refs[:4])}) because stale comments rot and mislead agents into reading comments instead of code. "
            f"2. Delete narration, banners, workarounds, and unsafe suppressions; encode real constraints in types, names, or tests. "
            f"3. Re-run tests and self_grill.py check-diff to confirm clean diff.",
        )

    if perf_findings:
        refs = [f"{f['file']}:{f['line']} ({f['rule_id']})" for f in perf_findings[:5]]
        add(
            "P1",
            "perf",
            "Eliminate backend hot-path, database N+1, and high-scale server bottlenecks",
            refs,
            f"/deep [HARDCORE MODE] Full-scope backend & systems performance optimization across {len(perf_findings)} "
            f"perf_audit finding(s) ({', '.join(refs[:4])}): "
            f"1. Load skill://domain-rules/references/high-scale-server-optimization.md and data-structures-and-cache-optimization.md, "
            f"and capture baseline p50/p95/p99 latency + query counts via bench_harness.py or EXPLAIN ANALYZE. "
            f"2. Fix every N+1/await-in-loop waterfall, sync-in-async block, missing timeout, per-request pool, OFFSET scan, "
            f"and framework/serialization bottleneck at the root. "
            f"3. Prove perf_audit.py --fail-on-high exits 0, verify before/after delta on the real harness, and run self-grill.",
        )

    smell_items = diff["workaround_smells"] or repo_smells
    if smell_items:
        refs = [f"{s['path']}:{s['line']}({s['kind']})" for s in smell_items[:5]]
        add(
            "P1",
            "gardening",
            "Replace imperative-timer, raw useEffect, or unsafe cast workarounds at the root",
            refs,
            f"/deep Full-scope root-cause cleanup for {len(smell_items)} workaround smell(s) ({', '.join(refs[:4])}): "
            f"1. Eliminate each imperative timer, raw useEffect, or unsafe type cast at the root cause. "
            f"2. Add a deterministic lint or type check so the pattern cannot return. "
            f"3. Prove behavior with tests and self_grill.py check-diff.",
        )

    if not verify_skills and code_file_count >= 3:
        add(
            "P1",
            "verification",
            "Create a project-local verify-<app> skill with control CLI and feature map",
            [f"code_files={code_file_count}", "verify_skills=0"],
            "/deep Full-scope verification setup: 1. Interview this repo and generate a project-local verify-<app> skill "
            "with a single control CLI (launch, doctor, inspect, drive, cleanup) and user-POV feature map. "
            "2. Prove the skill end-to-end on the real app and confirm evidence survives cleanup. "
            "3. Wire it into repo instructions and audit for gaps or unverified steps.",
        )

    if untested_dirs:
        refs = untested_dirs[:5]
        add(
            "P1",
            "gap",
            "Close missing test coverage in code directories with no sibling tests",
            refs,
            f"/deep Full-scope gap audit and test hardening: 1. Inspect untested code directories ({', '.join(refs)}) "
            f"and prioritize highest-risk public contracts and failure paths. "
            f"2. Add real behavioral tests (never tautological mocks) covering happy paths and edge failures. "
            f"3. Run all checks and self-grill to confirm zero regressions.",
        )

    if core_modules:
        top_refs = [f"{path} ({n} lines)" for path, n in core_modules[:3]]
        top_paths = ", ".join(path for path, _ in core_modules[:3])
        add(
            "P1",
            "hardcore",
            "Hardcore Mode architectural ceiling upgrade on core source modules",
            top_refs,
            f"/deep [HARDCORE MODE] First-principles architectural ceiling upgrade for core module(s) ({top_paths}): "
            f"1. Inspect {top_paths} and identify every flat approximation, single-threaded bottleneck, naive solver/algorithm, "
            f"or deferred stub holding back the system ceiling. "
            f"2. Upgrade straight to the true first-principles architecture (batch query plans, bounded async concurrency, "
            f"cache-friendly flat data structures, real algorithms/solvers, crisp native representations, and full integration — "
            f"never bury the best tier under '(Optional hardcore mode)'). "
            f"3. Prove end-to-end behavior and measured gains on the real artifact, run self_grill.py check-diff "
            f"(hardcore-craft-depth + no-comments), and report exact receipts and any verified platform limits.",
        )

    if debt:
        refs = [f"{d['path']}:{d['line']} ({d['marker']})" for d in debt[:5]]
        add(
            "P2",
            "gardening",
            "Triage and resolve TODO/FIXME/HACK markers via codebase gardening",
            refs,
            f"/deep Full-scope codebase gardening for {len(debt)} TODO/FIXME/HACK marker(s) ({', '.join(refs[:4])}): "
            f"1. Group markers by shared root cause into a pattern buffer instead of patching one by one. "
            f"2. Fix valid items, delete obsolete markers/workarounds, and encode recurring rules as lints/types/tests. "
            f"3. Prove all tests pass and run self-grill.",
        )

    if code_file_count >= 10 and not (safe_root / "GLOSSARY.md").is_file() and not (safe_root / "docs" / "adr").is_dir():
        add(
            "P2",
            "gardening",
            "Establish domain glossary and architecture decision records",
            [f"code_files={code_file_count}", "GLOSSARY.md=missing", "docs/adr=missing"],
            "/deep Full-scope domain modeling and architecture baseline: 1. Audit core domain terms and high-churn modules "
            "across the repo. 2. Create GLOSSARY.md and initial docs/adr/ records for non-obvious architectural choices. "
            "3. Verify every entry cites real code paths with zero fabricated claims.",
        )

    rank = {"P0": 0, "P1": 1, "P2": 2}
    suggestions.sort(key=lambda s: rank.get(s["priority"], 9))
    suggestions = suggestions[: max(1, limit)]

    return {
        "root": str(safe_root),
        "hardcore_mode": True,
        "code_file_count": code_file_count,
        "core_modules": [{"path": p, "lines": n} for p, n in core_modules],
        "verify_skills": verify_skills,
        "diff_size": diff["measured_size"],
        "overclaim_hits": len(overclaims),
        "broken_link_hits": len(broken_links),
        "debt_marker_hits": len(debt),
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
        for idx, item in enumerate(result["suggestions"], 1):
            print(f"{idx}. [{item['priority']}/{item['kind']}] {item['title']}")
            print(f"   evidence: {', '.join(item['evidence'])}")
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

    p_sug = sub.add_parser("suggest", help="Scan a repo for gaps and overclaims and suggest full-scope /deep prompts.")
    p_sug.add_argument("--root", required=True)
    p_sug.add_argument("--limit", type=int, default=8)
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
