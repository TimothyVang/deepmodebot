#!/usr/bin/env python3
"""Anti-reward-hacking scanner, contract hash lock, provenance receipt, and independent judge gate.

    python -B reward_guard.py [scan] [--root <repo>] [--base <ref>] [--staged] [--files a,b] [--allow-primitives] [--advisory] [--json]
    python -B reward_guard.py lock-contract --root <repo> --slug <slug> [--gates g1,g2] [--references r1,r2] [--thresholds k=v] [--required-producers p1,p2] [--artifacts a1,a2] [--force] [--json]
    python -B reward_guard.py record-provenance --root <repo> --slug <slug> --artifact <rel> --producer <name> --job-id <id> [--raw-sha256 <hex>] [--inputs r1,r2] [--notes <text>] [--json]
    python -B reward_guard.py record-judge --root <repo> --slug <slug> --artifact <rel> --judge-model <model> --independent-context --verdict <approve|reject> [--open-p0-p1 <n>] --goal-match-notes <text> --shortcut-audit <text> [--compared-references r1,r2] [--json]
    python -B reward_guard.py verdict --root <repo> --slug <slug> [--strict] [--json]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FLOAT_PAT = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
MIN_FLOOR_EPSILON = 1e-6

TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:tests?/|spec/|__tests__/|evals/)|(?:^|/)(?:test_[^/]+|[^/]+(?:_test|\.test|\.spec))\.[^/]+$",
    re.I,
)
GATE_OR_EVAL_FILE_RE = re.compile(
    r"(?:^|/)(?:gates?/|evals?/|bench(?:marks?)?/|validators?/)|(?:gate|eval|bench|validator|fidelity|metric|scorer)\.[^/]+$",
    re.I,
)
SCANNER_META_RE = re.compile(
    r"""(?:re\.compile\s*\(|Regex::new|THRESHOLD_ZERO_RE|SKIP_GATE_RE|PRIMITIVE_STANDIN_RE|HARDCODED_PASS_RE|TEST_SKIP_RE|REWARD_RULES|"rule"\s*:|rule:\s*"|Zeroed quality threshold|Goodhart / Anti-Reward-Hacking|`--min-)"""
)

BARE_LOWER_METRICS = (
    "iou|ssim|psnr|clip_score|dice|f1|auc|bleu|rouge|accuracy|"
    "precision|recall|fidelity|similarity|coverage|pass_rate|win_rate|score|confidence|protrusion|symmetry"
)
QUAL_LOWER_METRICS = f"{BARE_LOWER_METRICS}|clip|acc|ap|map"
CLI_LOWER_METRICS = "|".join(m.replace("_", "-") for m in QUAL_LOWER_METRICS.split("|"))

BARE_UPPER_METRICS = (
    "mse|mae|rmse|lpips|chamfer|hausdorff|drift|tolerance|holes|non_manifold"
)
QUAL_UPPER_METRICS = f"{BARE_UPPER_METRICS}|err|error|loss|tol|epsilon|eps"
CLI_UPPER_METRICS = "|".join(m.replace("_", "-") for m in QUAL_UPPER_METRICS.split("|"))

CLI_MIN_VAL_RE = re.compile(
    rf"(?<![A-Za-z0-9_])--min-(?:{CLI_LOWER_METRICS})(?:\s+|=)['\"]?({FLOAT_PAT})['\"]?(?![A-Za-z0-9_.])",
    re.I,
)
KWARG_MIN_VAL_RE = re.compile(
    rf"\b(?:min|minimum)_(?:{QUAL_LOWER_METRICS})\s*[:=]\s*['\"]?({FLOAT_PAT})['\"]?(?![A-Za-z0-9_.])",
    re.I,
)
SKIP_GATE_FLAG_RE = re.compile(
    r"(?<![A-Za-z0-9_])--(?:skip-gates?|skip-verify|skip-validation|skip-reference|skip-fidelity|bypass-gate|pass-if-no-tests|passWithNoTests)\b"
    r"|\bgit\s+commit\b[^\n]*\s--no-verify\b"
    r"|\b(?:skip_reference|skip_validation|skip_fidelity|bypass_gate)\s*[:=]\s*(?:True|true|1)\b"
    r"|\b(?:check_reference|verify_reference|enforce_provenance)\s*[:=]\s*(?:False|false|0)\b"
)
TEST_SKIP_DECORATOR_RE = re.compile(
    r"^\s*(?:@(?:pytest\.mark|unittest)\.skip\b(?!If|Unless)|#\s*\[\s*ignore\b|(?:it|test|describe)\.skip\s*\(\s*(?:['\"`)]|$))"
)
TOP_PYTEST_SKIP_RE = re.compile(r"^ {0,4}(?:pytest|unittest)\.skip\s*\(")
PRIMITIVE_STANDIN_RE = re.compile(
    r"\b(?:bpy\.ops\.mesh\.primitive_(?:cube|cone|cylinder|uv_sphere|ico_sphere|torus|monkey|plane|grid)_add"
    r"|trimesh\.creation\.(?:box|cone|cylinder|icosphere|uv_sphere|capsule|annulus)\s*\("
    r"|create_(?:cube|cone|cylinder|uv_sphere|icosphere)\s*\()"
)
HARDCODED_PASS_RE = re.compile(
    r"""\breturn\s*\{\s*['"](?:pass|passed|ok|verdict)['"]\s*:\s*(?:True|true|['"]PASS['"])\s*,\s*['"](?:iou|ssim|psnr|score|fidelity)['"]\s*:\s*1\.0\b"""
)
QUAL_LOWER_BOUND_RE = re.compile(
    rf"\b((?:min_|minimum_)(?:{QUAL_LOWER_METRICS})|(?:{QUAL_LOWER_METRICS})(?:_threshold|_min|_floor))\s*(>=|>|=|:)\s*({FLOAT_PAT})"
    rf"|--(min-(?:{CLI_LOWER_METRICS}))(?:\s+|=)['\"]?({FLOAT_PAT})['\"]?",
    re.I,
)
BARE_LOWER_INEQ_RE = re.compile(
    rf"(?<![.\w])({BARE_LOWER_METRICS})\s*(>=|>)\s*({FLOAT_PAT})",
    re.I,
)
BARE_LOWER_ASSIGN_RE = re.compile(
    rf"(?<![.\w])({BARE_LOWER_METRICS})\s*(=|:)\s*({FLOAT_PAT})",
    re.I,
)
QUAL_UPPER_BOUND_RE = re.compile(
    rf"\b((?:max_|maximum_)(?:{QUAL_UPPER_METRICS})|(?:{QUAL_UPPER_METRICS})(?:_threshold|_max|_ceiling|_limit)|tolerance)\s*(<=|<|=|:)\s*({FLOAT_PAT})"
    rf"|--(max-(?:{CLI_UPPER_METRICS})|tolerance)(?:\s+|=)['\"]?({FLOAT_PAT})['\"]?",
    re.I,
)
BARE_UPPER_INEQ_RE = re.compile(
    rf"(?<![.\w])({BARE_UPPER_METRICS})\s*(<=|<)\s*({FLOAT_PAT})",
    re.I,
)
BARE_UPPER_ASSIGN_RE = re.compile(
    rf"(?<![.\w])({BARE_UPPER_METRICS})\s*(=|:)\s*({FLOAT_PAT})",
    re.I,
)
FAKE_PRODUCER_NAMES = frozenset({
    "local", "mock", "fake", "stub", "none", "todo", "manual",
    "primitive", "primitives", "blender-primitives", "synthetic-box",
})
FAKE_JOB_IDS = frozenset({"none", "null", "local", "mock", "fake", "todo", "stub", "n/a", "na", "0", "test"})
SELF_JUDGE_NAMES = frozenset({"self", "builder", "author", "same", "inline", "none", "mock", "fake"})


def _norm_rel(raw: str) -> str:
    s = raw.strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def reject_unsafe_root(root_arg: Path) -> Path:
    if root_arg.is_symlink():
        raise ValueError(f"project root cannot be a symlink: {root_arg}")
    resolved = root_arg.resolve()
    if not resolved.is_dir():
        raise ValueError(f"project root does not exist: {resolved}")
    if resolved.parent == resolved:
        raise ValueError(f"refusing filesystem root as project root: {resolved}")
    forbidden = {Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
    for extra in ("/tmp", "/var/tmp", "/private/tmp"):
        p = Path(extra)
        if p.exists():
            forbidden.add(p.resolve())
    if resolved in forbidden:
        raise ValueError(f"refusing home or system temp directory as project root: {resolved}")
    return resolved


def ensure_contained(target: Path, root: Path) -> Path:
    safe_root = reject_unsafe_root(root)
    if target.is_symlink():
        raise ValueError(f"refusing symlink path: {target}")
    resolved = target.resolve()
    if not resolved.is_relative_to(safe_root):
        raise ValueError(f"path {resolved} escapes project root {safe_root}")
    probe = safe_root
    for part in resolved.relative_to(safe_root).parts:
        probe = probe / part
        if probe.is_symlink():
            raise ValueError(f"refusing symlink component inside root: {probe}")
    return resolved


def _hash_repo_file(root: Path, rel_raw: str) -> tuple[str, str, int]:
    safe_root = reject_unsafe_root(root)
    norm = _norm_rel(rel_raw)
    if not norm or Path(rel_raw).is_absolute():
        raise ValueError(f"path must be repo-relative: {rel_raw!r}")
    target = ensure_contained(safe_root / norm, safe_root)
    if not target.is_file():
        raise ValueError(f"file not found inside root: {norm}")
    size = target.stat().st_size
    if size <= 0:
        raise ValueError(f"file is empty (0 bytes): {norm}")
    h = hashlib.sha256()
    with target.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return target.relative_to(safe_root).as_posix(), h.hexdigest(), size


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=NO_WINDOW,
    )


def _changed_files(root: Path, staged: bool, explicit_files: list[str] | None, base: str | None = None) -> list[str]:
    if explicit_files:
        return sorted({_norm_rel(f) for f in explicit_files if _norm_rel(f)})
    found: set[str] = set()
    has_head = _git(root, "rev-parse", "--verify", "HEAD").returncode == 0
    if staged:
        r = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
        if r.returncode == 0:
            found.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    else:
        if base:
            r = _git(root, "diff", base, "--name-only", "--diff-filter=ACMR")
            if r.returncode == 0:
                found.update(x.strip() for x in r.stdout.splitlines() if x.strip())
        elif has_head:
            r = _git(root, "diff", "HEAD", "--name-only", "--diff-filter=ACMR")
            if r.returncode == 0:
                found.update(x.strip() for x in r.stdout.splitlines() if x.strip())
        u = _git(root, "ls-files", "--others", "--exclude-standard")
        if u.returncode == 0:
            found.update(x.strip() for x in u.stdout.splitlines() if x.strip())
    return sorted(f for f in found if not f.startswith((".scratch/", ".worktrees/")))


def _parse_unified_diff(
    patch_text: str,
    out: dict[str, tuple[dict[int, str], list[tuple[list[str], list[tuple[int, str]]]]]],
) -> None:
    cur_file: str | None = None
    cur_ln = 0
    cur_rem: list[str] = []
    cur_add: list[tuple[int, str]] = []
    for raw in patch_text.splitlines():
        if raw.startswith("diff --git "):
            if cur_file and (cur_rem or cur_add):
                out.setdefault(cur_file, ({}, []))[1].append((cur_rem, cur_add))
            cur_file, cur_rem, cur_add = None, [], []
            continue
        if raw.startswith("+++ "):
            hp = raw[4:].strip().strip('"')
            cur_file = None if hp == "/dev/null" else _norm_rel(hp[2:] if hp.startswith("b/") else hp)
            if cur_file:
                out.setdefault(cur_file, ({}, []))
            continue
        if not cur_file:
            continue
        if raw.startswith("@@ "):
            if cur_rem or cur_add:
                out[cur_file][1].append((cur_rem, cur_add))
                cur_rem, cur_add = [], []
            m = re.search(r"\+(\d+)", raw)
            cur_ln = int(m.group(1)) if m else 0
        elif raw.startswith("-") and not raw.startswith("---"):
            cur_rem.append(raw[1:])
        elif raw.startswith("+") and not raw.startswith("+++"):
            out[cur_file][0][cur_ln] = raw[1:]
            cur_add.append((cur_ln, raw[1:]))
            cur_ln += 1
    if cur_file and (cur_rem or cur_add):
        out.setdefault(cur_file, ({}, []))[1].append((cur_rem, cur_add))


def _batch_diffs_for_files(
    root: Path, files: list[str], staged: bool, base: str | None = None
) -> dict[str, tuple[dict[int, str], list[tuple[list[str], list[tuple[int, str]]]]]]:
    if not files:
        return {}
    valid = [f for f in files if (root / f).is_file() and not (root / f).is_symlink() and (root / f).stat().st_size <= 1_048_576]
    if not valid:
        return {}
    has_head = _git(root, "rev-parse", "--verify", "HEAD").returncode == 0
    untracked: set[str] = set()
    if not staged:
        u = _git(root, "ls-files", "--others", "--exclude-standard")
        if u.returncode == 0:
            untracked = {_norm_rel(x) for x in u.stdout.splitlines() if x.strip()}
    out: dict[str, tuple[dict[int, str], list[tuple[list[str], list[tuple[int, str]]]]]] = {}
    tracked_list: list[str] = []
    for rel in valid:
        if (not has_head or rel in untracked) and not staged:
            lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
            added = {i: ln for i, ln in enumerate(lines, 1)}
            out[rel] = (added, [([], list(added.items()))])
        else:
            tracked_list.append(rel)
    if not tracked_list:
        return out
    cmd = ["diff", "--relative", "--cached", "-U0", "--", *tracked_list] if staged else (
        ["diff", "--relative", base, "-U0", "--", *tracked_list] if base else ["diff", "--relative", "HEAD", "-U0", "--", *tracked_list]
    )
    r = _git(root, *cmd)
    if r.returncode == 0:
        _parse_unified_diff(r.stdout, out)
    return out


def _diff_for_file(root: Path, rel: str, staged: bool, base: str | None = None) -> tuple[dict[int, str], list[tuple[list[str], list[tuple[int, str]]]]]:
    return _batch_diffs_for_files(root, [rel], staged=staged, base=base).get(rel, ({}, []))


def _is_comment_or_scanner_line(ext: str, line: str) -> bool:
    s = line.strip()
    if not s or ext == ".md" or SCANNER_META_RE.search(line):
        return True
    if ext in (".py", ".sh", ".yml", ".yaml", ".toml") and s.startswith("#") and not s.startswith("#["):
        return True
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".rs", ".go") and s.startswith("//"):
        return True
    return False


def _find_rs_cfg_test_mod_line(full_text: str) -> int | None:
    lines = full_text.splitlines()
    n = len(lines)
    for i, raw in enumerate(lines):
        if raw.strip().startswith("#[cfg(test)]"):
            j = i + 1
            while j < n:
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("//") or nxt.startswith("#["):
                    j += 1
                    continue
                if nxt.startswith("mod ") or nxt.startswith("pub mod ") or nxt.startswith("pub(crate) mod "):
                    return i + 1
                break
    return None


def _extract_bounds_for_file(lines: list[str], *, upper: bool, is_test_or_gate: bool) -> dict[str, float]:
    bounds: dict[str, float] = {}
    qual_re = QUAL_UPPER_BOUND_RE if upper else QUAL_LOWER_BOUND_RE
    ineq_re = BARE_UPPER_INEQ_RE if upper else BARE_LOWER_INEQ_RE
    assign_re = BARE_UPPER_ASSIGN_RE if upper else BARE_LOWER_ASSIGN_RE
    for line in lines:
        if SCANNER_META_RE.search(line):
            continue
        norm = _normalized_arg_pairs(line)
        for m in qual_re.finditer(norm):
            key = (m.group(1) or m.group(4) or "").lower().replace("-", "_")
            val_s = m.group(3) if m.group(1) else m.group(5)
            try:
                bounds[key] = float(val_s)
            except (TypeError, ValueError):
                continue
        for m in ineq_re.finditer(norm):
            try:
                bounds.setdefault(m.group(1).lower(), float(m.group(3)))
            except (TypeError, ValueError):
                continue
        if is_test_or_gate:
            for m in assign_re.finditer(norm):
                try:
                    bounds.setdefault(m.group(1).lower(), float(m.group(3)))
                except (TypeError, ValueError):
                    continue
    return bounds


def _scan_hunk_weakening(rel: str, hunks: list[tuple[list[str], list[tuple[int, str]]]], *, is_test_or_gate: bool) -> list[dict]:
    findings: list[dict] = []
    for rem_lines, add_pairs in hunks:
        if not rem_lines or not add_pairs:
            continue
        first_ln = add_pairs[0][0]
        add_lines = [t for _, t in add_pairs]
        old_low = _extract_bounds_for_file(rem_lines, upper=False, is_test_or_gate=is_test_or_gate)
        new_low = _extract_bounds_for_file(add_lines, upper=False, is_test_or_gate=is_test_or_gate)
        for key, old_v in old_low.items():
            if key in new_low and old_v > 0 and new_low[key] < old_v:
                findings.append({
                    "severity": "P0",
                    "rule": "reward-hack-assertion-weakened",
                    "file": rel,
                    "line": first_ln,
                    "message": f"Quality/fidelity lower bound `{key}` weakened from `{old_v}` to `{new_low[key]}`.",
                    "fix": "Restore the original acceptance threshold and fix the implementation to meet it.",
                })
        old_up = _extract_bounds_for_file(rem_lines, upper=True, is_test_or_gate=is_test_or_gate)
        new_up = _extract_bounds_for_file(add_lines, upper=True, is_test_or_gate=is_test_or_gate)
        for key, old_v in old_up.items():
            if key in new_up and new_up[key] > old_v:
                findings.append({
                    "severity": "P0",
                    "rule": "reward-hack-assertion-weakened",
                    "file": rel,
                    "line": first_ln,
                    "message": f"Error/defect upper bound `{key}` relaxed from `{old_v}` to `{new_up[key]}`.",
                    "fix": "Keep the stricter defect/tolerance bound and fix the underlying output.",
                })
    return findings


def _normalized_arg_pairs(line: str) -> str:
    return re.sub(
        rf"""['"](--(?:min|max)-[A-Za-z0-9_-]+|--tolerance)['"]\s*,\s*['"]({FLOAT_PAT})['"]""",
        r"\1 \2",
        line,
    )


def _has_zero_or_sub_epsilon_threshold(norm_line: str) -> bool:
    for rx in (CLI_MIN_VAL_RE, KWARG_MIN_VAL_RE):
        for m in rx.finditer(norm_line):
            try:
                if float(m.group(1)) <= MIN_FLOOR_EPSILON:
                    return True
            except ValueError:
                continue
    return bool(SKIP_GATE_FLAG_RE.search(norm_line))


def _has_unconditional_test_skip(line: str) -> bool:
    s = line.lstrip()
    if s.startswith(('"', "'")):
        return False
    return bool(TEST_SKIP_DECORATOR_RE.search(line) or TOP_PYTEST_SKIP_RE.search(line))


def scan_added_lines_for_reward_hacks(
    rel: str,
    added_lines: dict[int, str],
    hunks: list[tuple[list[str], list[tuple[int, str]]]] | None = None,
    *,
    allow_primitives: bool = False,
    include_primitives: bool = True,
    full_text: str = "",
) -> list[dict]:
    norm_rel = _norm_rel(rel)
    ext = Path(norm_rel).suffix.lower()
    if ext == ".md" or norm_rel.endswith(("assets/reward-guard/reward_guard.py", "native/dmb-gate/src/reward.rs")):
        return []
    is_test = bool(TEST_FILE_RE.search(norm_rel))
    is_gate = bool(GATE_OR_EVAL_FILE_RE.search(norm_rel))
    rs_cfg_test_line = _find_rs_cfg_test_mod_line(full_text) if (ext == ".rs" and full_text) else None
    findings: list[dict] = []
    for ln, line in sorted(added_lines.items()):
        if _is_comment_or_scanner_line(ext, line):
            continue
        in_test_ctx = is_test or (rs_cfg_test_line is not None and ln >= rs_cfg_test_line)
        if in_test_ctx and _has_unconditional_test_skip(line):
            findings.append({
                "severity": "P1",
                "rule": "reward-hack-test-skip",
                "file": rel,
                "line": ln,
                "message": "Unconditional test skip added (`skip` / `#[ignore]`) silences a failing check.",
                "fix": "Fix the failing behavior instead of skipping the test.",
            })
        if in_test_ctx:
            continue
        norm_line = _normalized_arg_pairs(line)
        if _has_zero_or_sub_epsilon_threshold(norm_line):
            findings.append({
                "severity": "P0",
                "rule": "reward-hack-threshold-zero",
                "file": rel,
                "line": ln,
                "message": "Zero, negative, or near-zero quality threshold (`--min-iou 0` / `min_*<=1e-6`) or gate/reference skip flag bypasses real evaluation.",
                "fix": "Score directly against the reference artwork/contract with a positive threshold and remove skip flags.",
            })
        if include_primitives and not allow_primitives and PRIMITIVE_STANDIN_RE.search(line):
            findings.append({
                "severity": "P1",
                "rule": "reward-hack-primitive-standin",
                "file": rel,
                "line": ln,
                "message": "Local procedural primitive geometry (`cube`/`cone`/`sphere`/`cylinder`) added in production/pipeline code.",
                "fix": "Produce the asset via the real upstream generator/solver with a provenance receipt, or pass `--allow-primitives` for genuine CAD/procedural geometry.",
            })
        if HARDCODED_PASS_RE.search(line):
            findings.append({
                "severity": "P1",
                "rule": "reward-hack-hardcoded-pass",
                "file": rel,
                "line": ln,
                "message": "Hardcoded pass/perfect-metric return literal spoofs gate evaluation.",
                "fix": "Compute the metric from real rendered/runtime output against the reference input.",
            })
    if hunks:
        if rs_cfg_test_line is not None:
            pre_hunks = [(r, [(ln, t) for ln, t in a if ln < rs_cfg_test_line]) for r, a in hunks]
            findings.extend(_scan_hunk_weakening(rel, [(r, a) for r, a in pre_hunks if a], is_test_or_gate=is_test or is_gate))
        else:
            findings.extend(_scan_hunk_weakening(rel, hunks, is_test_or_gate=is_test or is_gate))
    return findings


def _verify_hash_map(root: Path, slug: str, label: str, expected_map: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for rel_p, expected_sha in sorted(expected_map.items()):
        try:
            _, live_sha, _ = _hash_repo_file(root, rel_p)
        except ValueError:
            live_sha = "MISSING"
        if live_sha != expected_sha:
            out.append({
                "severity": "P0",
                "rule": "reward-hack-contract-tampered",
                "file": rel_p,
                "line": 1,
                "message": f"Locked {label} file `{rel_p}` in contract `{slug}` was modified or deleted (`{live_sha[:10]}` != `{expected_sha[:10]}`).",
                "fix": "Revert edits to locked gate/test/reference files so the builder never weakens its own oracle.",
            })
    return out


def _load_db_contract_maps(dbf: Path, slug: str) -> tuple[bool, dict[str, str], dict[str, str]]:
    if not dbf.is_file() or dbf.is_symlink():
        return False, {}, {}
    with _connect(dbf) as conn:
        row = conn.execute("SELECT gates_json, references_json FROM contracts WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return False, {}, {}
        return True, json.loads(row["gates_json"] or "{}"), json.loads(row["references_json"] or "{}")


def _check_locked_contracts(root: Path) -> list[dict]:
    rg_root = root / ".scratch" / "reward-guard"
    if not rg_root.is_dir() or rg_root.is_symlink():
        return []
    findings: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for slug_dir in sorted(p for p in rg_root.iterdir() if p.is_dir() and not p.is_symlink()):
        slug = slug_dir.name
        lock_file = slug_dir / "contract-lock.json"
        has_db_row, gates_map, refs_map = _load_db_contract_maps(slug_dir / "reward-guard.db", slug)
        if has_db_row and not lock_file.is_file():
            findings.append({
                "severity": "P0",
                "rule": "reward-hack-contract-tampered",
                "file": f".scratch/reward-guard/{slug}/contract-lock.json",
                "line": 1,
                "message": f"Contract lock file for `{slug}` was deleted while SQLite contract exists.",
                "fix": "Restore contract-lock.json or re-lock only with explicit operator --force.",
            })
        if lock_file.is_file() and not lock_file.is_symlink():
            try:
                lock = json.loads(lock_file.read_text(encoding="utf-8"))
                gates_map.update(lock.get("gates") or {})
                refs_map.update(lock.get("references") or {})
            except (OSError, ValueError):
                findings.append({
                    "severity": "P0",
                    "rule": "reward-hack-contract-tampered",
                    "file": f".scratch/reward-guard/{slug}/contract-lock.json",
                    "line": 1,
                    "message": f"Contract lock file for `{slug}` is corrupted.",
                    "fix": "Restore valid contract-lock.json.",
                })
        for f in _verify_hash_map(root, slug, "gate/test", gates_map) + _verify_hash_map(root, slug, "reference", refs_map):
            key = (slug, f["file"])
            if key not in seen_keys:
                seen_keys.add(key)
                findings.append(f)
    return findings


def scan_reward_hacking(
    root: Path,
    *,
    staged: bool = False,
    explicit_files: list[str] | None = None,
    base: str | None = None,
    allow_primitives: bool = False,
) -> dict:
    safe_root = reject_unsafe_root(root)
    changed = _changed_files(safe_root, staged=staged, explicit_files=explicit_files, base=base)
    findings: list[dict] = []
    batched = _batch_diffs_for_files(safe_root, changed, staged=staged, base=base)
    for rel in changed:
        added, hunks = batched.get(rel, ({}, []))
        full_txt = ""
        if (safe_root / rel).is_file() and not (safe_root / rel).is_symlink():
            full_txt = (safe_root / rel).read_text(encoding="utf-8", errors="replace")
            if not added and explicit_files:
                added = {i: ln for i, ln in enumerate(full_txt.splitlines(), 1)}
        if added or hunks:
            findings.extend(
                scan_added_lines_for_reward_hacks(rel, added, hunks, allow_primitives=allow_primitives, full_text=full_txt)
            )
    findings.extend(_check_locked_contracts(safe_root))
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {
        "ok": counts["P0"] == 0 and counts["P1"] == 0,
        "root": str(safe_root),
        "files_checked": len(changed),
        "counts": counts,
        "findings": findings,
    }


def _slug_dir(root: Path, slug: str) -> Path:
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"invalid slug {slug!r}: use lowercase kebab-case")
    safe_root = reject_unsafe_root(root)
    scratch = ensure_contained(safe_root / ".scratch", safe_root)
    scratch.mkdir(parents=True, exist_ok=True)
    gi = scratch / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n!.gitignore\n", encoding="utf-8", newline="\n")
    d = ensure_contained(scratch / "reward-guard" / slug, safe_root)
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextlib.contextmanager
def _connect(db_file: Path):
    conn = sqlite3.connect(str(db_file), timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                slug TEXT PRIMARY KEY,
                gates_json TEXT NOT NULL,
                references_json TEXT NOT NULL,
                thresholds_json TEXT NOT NULL,
                required_producers_json TEXT NOT NULL,
                required_artifacts_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provenance_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                artifact_bytes INTEGER NOT NULL,
                raw_sha256 TEXT NOT NULL,
                producer TEXT NOT NULL,
                job_id TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                UNIQUE(slug, artifact_path),
                FOREIGN KEY(slug) REFERENCES contracts(slug) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS judge_verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                judge_model TEXT NOT NULL,
                independent_context INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                open_p0_p1 INTEGER NOT NULL DEFAULT 0,
                compared_refs_json TEXT NOT NULL,
                goal_match_notes TEXT NOT NULL,
                shortcut_audit TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(slug, artifact_path),
                FOREIGN KEY(slug) REFERENCES contracts(slug) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


def _parse_thresholds(raw_items: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in raw_items:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(f"threshold must be key=value, got {part!r}")
            k, v = part.split("=", 1)
            key = k.strip().lower().replace("-", "_")
            val = float(v.strip())
            is_lower = key.startswith(("min_", "minimum_")) or key in {
                "iou", "ssim", "psnr", "clip", "clip_score", "fidelity", "score", "coverage", "accuracy", "protrusion"
            }
            if is_lower and val <= MIN_FLOOR_EPSILON:
                raise ValueError(f"refusing zero, negative, or sub-epsilon minimum threshold `{key}={val}` (reward-hacking guard)")
            out[key] = val
    return out


def lock_contract(
    root: Path,
    *,
    slug: str,
    gates: list[str] | None = None,
    references: list[str] | None = None,
    thresholds: list[str] | None = None,
    required_producers: list[str] | None = None,
    artifacts: list[str] | None = None,
    force: bool = False,
) -> dict:
    sdir = _slug_dir(root, slug)
    dbf = sdir / "reward-guard.db"
    lock_json = sdir / "contract-lock.json"
    gate_hashes = {rel: sha for raw in (gates or []) if raw.strip() for rel, sha, _ in [_hash_repo_file(root, raw)]}
    ref_hashes = {rel: sha for raw in (references or []) if raw.strip() for rel, sha, _ in [_hash_repo_file(root, raw)]}
    thresh_map = _parse_thresholds(thresholds or [])
    producers = sorted({p.strip() for p in (required_producers or []) if p.strip()})
    for prod in producers:
        if prod.lower() in FAKE_PRODUCER_NAMES:
            raise ValueError(f"required producer `{prod}` cannot be a mock/primitive placeholder")
    req_artifacts = sorted({_norm_rel(a) for a in (artifacts or []) if _norm_rel(a)})
    now = time.time()
    with _connect(dbf) as conn:
        existing = conn.execute("SELECT 1 FROM contracts WHERE slug = ?", (slug,)).fetchone()
        if (lock_json.exists() or existing is not None) and not force:
            raise ValueError(f"contract `{slug}` is already locked; pass --force only with operator approval")
        conn.execute(
            """INSERT INTO contracts(slug, gates_json, references_json, thresholds_json, required_producers_json, required_artifacts_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                   gates_json=excluded.gates_json,
                   references_json=excluded.references_json,
                   thresholds_json=excluded.thresholds_json,
                   required_producers_json=excluded.required_producers_json,
                   required_artifacts_json=excluded.required_artifacts_json,
                   created_at=excluded.created_at""",
            (slug, json.dumps(gate_hashes, ensure_ascii=False), json.dumps(ref_hashes, ensure_ascii=False), json.dumps(thresh_map), json.dumps(producers), json.dumps(req_artifacts, ensure_ascii=False), now),
        )
        conn.commit()
    lock_payload = {
        "slug": slug,
        "gates": gate_hashes,
        "references": ref_hashes,
        "thresholds": thresh_map,
        "required_producers": producers,
        "required_artifacts": req_artifacts,
        "locked_at": now,
    }
    lock_json.write_text(json.dumps(lock_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    md = render_reward_guard_md(root, slug)
    return {"slug": slug, "db": str(dbf), "lock_file": str(lock_json), "report_md": str(md), **lock_payload}


def record_provenance(
    root: Path,
    *,
    slug: str,
    artifact_rel: str,
    producer: str,
    job_id: str,
    raw_sha256: str = "",
    inputs: list[str] | None = None,
    notes: str = "",
) -> dict:
    sdir = _slug_dir(root, slug)
    dbf = sdir / "reward-guard.db"
    clean_prod = producer.strip()
    clean_job = job_id.strip()
    if not clean_prod or clean_prod.lower() in FAKE_PRODUCER_NAMES:
        raise ValueError(f"producer {producer!r} rejected: provenance requires a real generator/solver/service, not local primitives/mocks")
    if len(clean_job) < 4 or clean_job.lower() in FAKE_JOB_IDS:
        raise ValueError(f"job_id {job_id!r} rejected: supply the real upstream prompt_id/run_id/build receipt")
    norm_art, live_sha, size = _hash_repo_file(root, artifact_rel)
    clean_raw = raw_sha256.strip().lower() if raw_sha256.strip() else live_sha
    if not SHA256_RE.fullmatch(clean_raw):
        raise ValueError(f"raw_sha256 must be a 64-char hex SHA-256 digest, got {raw_sha256!r}")
    input_hashes = {rel: sha for raw in (inputs or []) if raw.strip() for rel, sha, _ in [_hash_repo_file(root, raw)]}
    with _connect(dbf) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise ValueError(f"contract `{slug}` not found; run lock-contract first")
        allowed_producers = json.loads(row["required_producers_json"])
        if allowed_producers and clean_prod not in allowed_producers:
            raise ValueError(f"producer `{clean_prod}` is not in contract required_producers {allowed_producers}")
        locked_refs = json.loads(row["references_json"])
        missing_refs = [r for r, sha in locked_refs.items() if input_hashes.get(r) != sha]
        if missing_refs:
            raise ValueError(f"provenance receipt skipped or mismatched locked reference inputs: {missing_refs}")
        conn.execute(
            """INSERT INTO provenance_receipts(slug, artifact_path, artifact_sha256, artifact_bytes, raw_sha256, producer, job_id, inputs_json, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug, artifact_path) DO UPDATE SET
                   artifact_sha256=excluded.artifact_sha256,
                   artifact_bytes=excluded.artifact_bytes,
                   raw_sha256=excluded.raw_sha256,
                   producer=excluded.producer,
                   job_id=excluded.job_id,
                   inputs_json=excluded.inputs_json,
                   notes=excluded.notes,
                   created_at=excluded.created_at""",
            (slug, norm_art, live_sha, size, clean_raw, clean_prod, clean_job, json.dumps(input_hashes, ensure_ascii=False), notes.strip(), time.time()),
        )
        conn.commit()
    render_reward_guard_md(root, slug)
    return {"slug": slug, "artifact": norm_art, "artifact_sha256": live_sha, "raw_sha256": clean_raw, "producer": clean_prod, "job_id": clean_job}


def record_judge(
    root: Path,
    *,
    slug: str,
    artifact_rel: str,
    judge_model: str,
    independent_context: bool,
    verdict: str,
    open_p0_p1: int = 0,
    goal_match_notes: str = "",
    shortcut_audit: str = "",
    compared_references: list[str] | None = None,
) -> dict:
    if not independent_context:
        raise ValueError("independent judge requires --independent-context (clean read-only critic, never builder self-grading)")
    clean_model = judge_model.strip()
    if not clean_model or clean_model.lower() in SELF_JUDGE_NAMES:
        raise ValueError(f"invalid judge_model {judge_model!r}: name the independent reviewer/vision model")
    if verdict not in ("approve", "reject"):
        raise ValueError("verdict must be 'approve' or 'reject'")
    if len(goal_match_notes.strip()) < 20:
        raise ValueError("goal_match_notes must be >= 20 chars describing side-by-side fidelity to the true goal/reference")
    if len(shortcut_audit.strip()) < 20:
        raise ValueError("shortcut_audit must be >= 20 chars explicitly auditing against primitive stand-ins and metric gaming")
    sdir = _slug_dir(root, slug)
    dbf = sdir / "reward-guard.db"
    norm_art, live_sha, _ = _hash_repo_file(root, artifact_rel)
    comp_hashes = {rel: sha for raw in (compared_references or []) if raw.strip() for rel, sha, _ in [_hash_repo_file(root, raw)]}
    with _connect(dbf) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise ValueError(f"contract `{slug}` not found; run lock-contract first")
        locked_refs = json.loads(row["references_json"])
        missing_refs = [r for r, sha in locked_refs.items() if comp_hashes.get(r) != sha]
        if missing_refs:
            raise ValueError(f"independent judge did not compare against locked reference(s): {missing_refs}")
        conn.execute(
            """INSERT INTO judge_verdicts(slug, artifact_path, artifact_sha256, judge_model, independent_context, verdict, open_p0_p1, compared_refs_json, goal_match_notes, shortcut_audit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug, artifact_path) DO UPDATE SET
                   artifact_sha256=excluded.artifact_sha256,
                   judge_model=excluded.judge_model,
                   independent_context=excluded.independent_context,
                   verdict=excluded.verdict,
                   open_p0_p1=excluded.open_p0_p1,
                   compared_refs_json=excluded.compared_refs_json,
                   goal_match_notes=excluded.goal_match_notes,
                   shortcut_audit=excluded.shortcut_audit,
                   created_at=excluded.created_at""",
            (slug, norm_art, live_sha, clean_model, 1, verdict, int(open_p0_p1), json.dumps(comp_hashes, ensure_ascii=False), goal_match_notes.strip(), shortcut_audit.strip(), time.time()),
        )
        conn.commit()
    render_reward_guard_md(root, slug)
    return evaluate_verdict(root, slug=slug)


def evaluate_verdict(root: Path, *, slug: str) -> dict:
    sdir = _slug_dir(root, slug)
    dbf = sdir / "reward-guard.db"
    lock_json = sdir / "contract-lock.json"
    if not dbf.is_file():
        return {"verdict": "REWARD_GUARD_BLOCKED", "slug": slug, "failed_gates": ["contract-not-locked"]}
    with _connect(dbf) as conn:
        contract = conn.execute("SELECT * FROM contracts WHERE slug = ?", (slug,)).fetchone()
        if contract is None:
            return {"verdict": "REWARD_GUARD_BLOCKED", "slug": slug, "failed_gates": ["contract-not-locked"]}
        prov_rows = {r["artifact_path"]: dict(r) for r in conn.execute("SELECT * FROM provenance_receipts WHERE slug = ?", (slug,)).fetchall()}
        judge_rows = {r["artifact_path"]: dict(r) for r in conn.execute("SELECT * FROM judge_verdicts WHERE slug = ?", (slug,)).fetchall()}

    failed: list[str] = []
    locked_gates = json.loads(contract["gates_json"] or "{}")
    locked_refs = json.loads(contract["references_json"] or "{}")
    db_tamper = _verify_hash_map(root, slug, "gate/test", locked_gates) + _verify_hash_map(root, slug, "reference", locked_refs)
    if not lock_json.is_file() or db_tamper:
        failed.append("contract-locked-and-intact")

    scan_res = scan_reward_hacking(root)
    if any(f["rule"] == "reward-hack-contract-tampered" for f in scan_res["findings"]):
        failed.append("contract-locked-and-intact")
    if not scan_res["ok"]:
        failed.append("zero-static-reward-hacks")

    req_artifacts = json.loads(contract["required_artifacts_json"])
    target_artifacts = req_artifacts or sorted(set(prov_rows.keys()) | set(judge_rows.keys()))
    allowed_producers = json.loads(contract["required_producers_json"])

    if not target_artifacts:
        failed.extend(["provenance-verified", "independent-judge-approved"])
    else:
        prov_ok = True
        judge_ok = True
        for art in target_artifacts:
            try:
                _, live_sha, _ = _hash_repo_file(root, art)
            except ValueError:
                prov_ok = False
                judge_ok = False
                continue
            pr = prov_rows.get(art)
            if not pr or pr["artifact_sha256"] != live_sha:
                prov_ok = False
            elif allowed_producers and pr["producer"] not in allowed_producers:
                prov_ok = False
            else:
                inp = json.loads(pr["inputs_json"])
                if any(inp.get(r) != sha for r, sha in locked_refs.items()):
                    prov_ok = False
            jv = judge_rows.get(art)
            if not jv or jv["artifact_sha256"] != live_sha or not jv["independent_context"] or jv["verdict"] != "approve" or int(jv["open_p0_p1"]) > 0:
                judge_ok = False
            else:
                crefs = json.loads(jv["compared_refs_json"])
                if any(crefs.get(r) != sha for r, sha in locked_refs.items()):
                    judge_ok = False
        if not prov_ok:
            failed.append("provenance-verified")
        if not judge_ok:
            failed.append("independent-judge-approved")

    dedup_failed = list(dict.fromkeys(failed))
    return {
        "verdict": "REWARD_GUARD_PASSED" if not dedup_failed else "REWARD_GUARD_BLOCKED",
        "slug": slug,
        "artifacts_checked": target_artifacts,
        "static_findings": len(scan_res["findings"]),
        "failed_gates": dedup_failed,
        "report_md": str(sdir / "REWARD_GUARD.md"),
    }


def render_reward_guard_md(root: Path, slug: str) -> Path:
    sdir = _slug_dir(root, slug)
    dbf = sdir / "reward-guard.db"
    out = sdir / "REWARD_GUARD.md"
    with _connect(dbf) as conn:
        contract = conn.execute("SELECT * FROM contracts WHERE slug = ?", (slug,)).fetchone()
        provs = conn.execute("SELECT * FROM provenance_receipts WHERE slug = ? ORDER BY artifact_path", (slug,)).fetchall()
        judges = conn.execute("SELECT * FROM judge_verdicts WHERE slug = ? ORDER BY artifact_path", (slug,)).fetchall()
    verdict = evaluate_verdict(root, slug=slug)
    gates = json.loads(contract["gates_json"]) if contract else {}
    refs = json.loads(contract["references_json"]) if contract else {}
    thresholds = json.loads(contract["thresholds_json"]) if contract else {}
    lines = [
        f"# Anti-Reward-Hacking Ledger (`{slug}`)",
        "",
        f"- **Verdict:** `{verdict['verdict']}`",
        f"- **Locked gates ({len(gates)}):** {', '.join(f'`{k}` (`{v[:10]}`)' for k, v in gates.items()) or '(none)'}",
        f"- **Locked references ({len(refs)}):** {', '.join(f'`{k}` (`{v[:10]}`)' for k, v in refs.items()) or '(none)'}",
        f"- **Locked thresholds:** `{json.dumps(thresholds, sort_keys=True)}`",
    ]
    if verdict["failed_gates"]:
        lines.append(f"- **Blocking gates:** {', '.join(verdict['failed_gates'])}")
    lines += [
        "",
        "## Provenance Receipts",
        "",
        "| Artifact | SHA-256 | Producer | Job / Prompt ID | Raw Output Hash |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in provs:
        lines.append(
            f"| `{p['artifact_path']}` | `{p['artifact_sha256'][:12]}` | `{p['producer']}` | `{p['job_id']}` | `{p['raw_sha256'][:12]}` |"
        )
    lines += [
        "",
        "## Independent Judge Verdicts",
        "",
        "| Artifact | SHA-256 | Judge Model | Verdict | Open P0/P1 | Goal Match & Anti-Shortcut Audit |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for j in judges:
        lines.append(
            f"| `{j['artifact_path']}` | `{j['artifact_sha256'][:12]}` | `{j['judge_model']}` | `{j['verdict']}` | {j['open_p0_p1']} | {j['goal_match_notes']} / {j['shortcut_audit']} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def _split_csv(raw_list: list[str] | None) -> list[str]:
    return [x.strip() for item in (raw_list or []) for x in item.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Anti-reward-hacking scanner, contract hash lock, provenance receipt & judge gate.")
    sub = p.add_subparsers(dest="cmd")

    sp_scan = sub.add_parser("scan")
    for target in (p, sp_scan):
        target.add_argument("--root", default=".")
        target.add_argument("--staged", action="store_true")
        target.add_argument("--base", default=None)
        target.add_argument("--files", nargs="*", default=None)
        target.add_argument("--allow-primitives", action="store_true")
        target.add_argument("--advisory", action="store_true")
        target.add_argument("--json", action="store_true")

    sp_lock = sub.add_parser("lock-contract")
    sp_lock.add_argument("--root", default=".")
    sp_lock.add_argument("--slug", required=True)
    sp_lock.add_argument("--gates", nargs="*", default=None)
    sp_lock.add_argument("--references", nargs="*", default=None)
    sp_lock.add_argument("--thresholds", nargs="*", default=None)
    sp_lock.add_argument("--required-producers", nargs="*", default=None)
    sp_lock.add_argument("--artifacts", nargs="*", default=None)
    sp_lock.add_argument("--force", action="store_true")
    sp_lock.add_argument("--json", action="store_true")

    sp_prov = sub.add_parser("record-provenance")
    sp_prov.add_argument("--root", default=".")
    sp_prov.add_argument("--slug", required=True)
    sp_prov.add_argument("--artifact", required=True)
    sp_prov.add_argument("--producer", required=True)
    sp_prov.add_argument("--job-id", required=True)
    sp_prov.add_argument("--raw-sha256", default="")
    sp_prov.add_argument("--inputs", nargs="*", default=None)
    sp_prov.add_argument("--notes", default="")
    sp_prov.add_argument("--json", action="store_true")

    sp_judge = sub.add_parser("record-judge")
    sp_judge.add_argument("--root", default=".")
    sp_judge.add_argument("--slug", required=True)
    sp_judge.add_argument("--artifact", required=True)
    sp_judge.add_argument("--judge-model", required=True)
    sp_judge.add_argument("--independent-context", action="store_true")
    sp_judge.add_argument("--verdict", required=True, choices=("approve", "reject"))
    sp_judge.add_argument("--open-p0-p1", type=int, default=0)
    sp_judge.add_argument("--goal-match-notes", required=True)
    sp_judge.add_argument("--shortcut-audit", required=True)
    sp_judge.add_argument("--compared-references", nargs="*", default=None)
    sp_judge.add_argument("--json", action="store_true")

    sp_ver = sub.add_parser("verdict")
    sp_ver.add_argument("--root", default=".")
    sp_ver.add_argument("--slug", required=True)
    sp_ver.add_argument("--strict", action="store_true")
    sp_ver.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.cmd or "scan"
    try:
        root = Path(args.root).resolve()
        if cmd == "scan":
            res = scan_reward_hacking(
                root,
                staged=args.staged,
                explicit_files=_split_csv(args.files) or None,
                base=args.base,
                allow_primitives=args.allow_primitives,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                c = res["counts"]
                print(f"reward-guard [{'OK' if res['ok'] else 'BLOCKED'}]: {res['files_checked']} file(s) — P0:{c['P0']} P1:{c['P1']} P2:{c['P2']}")
                for f in res["findings"]:
                    print(f"  {f['file']}:{f['line']} [{f['severity']}:{f['rule']}] {f['message']} -> {f['fix']}")
            return 0 if (res["ok"] or args.advisory) else 1
        if cmd == "lock-contract":
            res = lock_contract(
                root,
                slug=args.slug,
                gates=_split_csv(args.gates),
                references=_split_csv(args.references),
                thresholds=_split_csv(args.thresholds),
                required_producers=_split_csv(args.required_producers),
                artifacts=_split_csv(args.artifacts),
                force=args.force,
            )
            print(json.dumps(res, indent=2) if args.json else f"locked contract {res['slug']} ({len(res['gates'])} gate(s), {len(res['references'])} ref(s))")
            return 0
        if cmd == "record-provenance":
            res = record_provenance(
                root,
                slug=args.slug,
                artifact_rel=args.artifact,
                producer=args.producer,
                job_id=args.job_id,
                raw_sha256=args.raw_sha256,
                inputs=_split_csv(args.inputs),
                notes=args.notes,
            )
            print(json.dumps(res, indent=2) if args.json else f"recorded provenance for {res['artifact']} ({res['producer']}:{res['job_id']})")
            return 0
        if cmd == "record-judge":
            res = record_judge(
                root,
                slug=args.slug,
                artifact_rel=args.artifact,
                judge_model=args.judge_model,
                independent_context=args.independent_context,
                verdict=args.verdict,
                open_p0_p1=args.open_p0_p1,
                goal_match_notes=args.goal_match_notes,
                shortcut_audit=args.shortcut_audit,
                compared_references=_split_csv(args.compared_references),
            )
            print(json.dumps(res, indent=2) if args.json else f"{res['verdict']} (failed: {res['failed_gates']})")
            return 0 if res["verdict"] == "REWARD_GUARD_PASSED" else 1
        if cmd == "verdict":
            res = evaluate_verdict(root, slug=args.slug)
            print(json.dumps(res, indent=2) if args.json else f"{res['verdict']} (failed: {res['failed_gates']})")
            return 1 if (args.strict and res["verdict"] != "REWARD_GUARD_PASSED") else 0
    except ValueError as exc:
        print(f"reward-guard error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
