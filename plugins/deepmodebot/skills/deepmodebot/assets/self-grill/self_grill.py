#!/usr/bin/env python3
"""Deterministic diff-aware self-grill and Adaptive Hotspot Prosecutor engine for deepmodebot.

    python self_grill.py check-diff --root <repo> [--base <ref>] [--staged] [--json]
    python self_grill.py init --root <repo> --slug <slug> [--phase plan|checks|both] [--base <ref>] [--staged] [--force] [--refresh] [--json]
    python self_grill.py answer --dir <dir> --id <qid> --status proven|na|failed|blocked --answer <text> [--receipt <ref>] [--json]
    python self_grill.py verdict --dir <dir> [--strict] [--allow-stale] [--json]
    python self_grill.py bundle --root <repo> [--slug <slug>] [--claims-stdin | --claims-file <path>] [--confession <text>] [--json]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True

SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

SENSITIVE_PATH_RE = re.compile(
    r"(?:^|/)(?:\.github/workflows/|hooks\.json$|mcp_config\.json$|AGENTS\.md$|CLAUDE\.md$|migrations?/|contain/)"
    r"|(?:^|/|.)\.env(?:\.|$)"
    r"|(?:^|[/._-])(?:auth|oauth|jwt|password|passwords|login|sso|mfa|session|token|tokens|secret|secrets"
    r"|credential|credentials|cred|rbac|acl|permission|permissions|policy|security|guard|sanitize|sanitizer"
    r"|crypto|signature|billing|stripe|payment|payments)(?:$|[/._-])",
    re.I,
)

TEST_PATH_RE = re.compile(
    r"(^|/)(?:tests?/|spec/|__tests__/|evals/)|(?:^|/)(?:test_[^/]+|[^/]+(?:_test|\.test|\.spec)\.[^/]+)$",
    re.I,
)

CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".java", ".cs", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".lua", ".luau",
}

SHELL_OR_SCRIPT_EXTS = {".sh", ".bash", ".zsh", ".ps1", ".cmd", ".bat", ".py", ".mjs", ".cjs", ".ts", ".js"}

SCHEMA_OR_CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".sql", ".ini", ".cfg"}

PROOF_EXTS = {".lean", ".v", ".thy", ".tla", ".smt2", ".tex"}
NON_GIT_SKIP_DIRS = {
    ".git", ".scratch", ".worktrees", "__pycache__", "node_modules",
    ".venv", "venv", "target", "dist", "build", ".pytest_cache", ".lake",
}
SKILL_OR_PROMPT_RE = re.compile(
    r"(^|/)(?:SKILL\.md$|commands/|references/|agents/|prompts?/|\.claude-plugin/|\.antigravity-plugin/|\.omp-plugin/)",
    re.I,
)

HASH_COMMENT_EXTS = {".py", ".rb", ".sh", ".bash", ".zsh", ".ps1"}
import ast
import importlib.util

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BACKEND_EXTS = {".py", ".go", ".rs", ".cs", ".fs", ".ts", ".js", ".mjs", ".java", ".kt", ".sql", ".c", ".cc", ".cpp"}
SLASH_COMMENT_EXTS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".java", ".cs", ".php", ".c", ".cc", ".cpp", ".h", ".hpp",
}
DASH_COMMENT_EXTS = {".lua", ".luau", ".sql"}
COMMENT_SCAN_EXTS = CODE_EXTS | HASH_COMMENT_EXTS | DASH_COMMENT_EXTS

LUAU_DIRECTIVE_RE = re.compile(r"^!(?:strict|nonstrict|nocheck|native|optimize)\b", re.I)

COMMENT_KEEP_RE = re.compile(
    r"(?:spdx-license-identifier|copyright\b|prettier-ignore|https?://\S+)",
    re.I,
)
COMMENT_SCENT_RE = re.compile(
    r"(?:eslint-disable|@ts-ignore|@ts-expect-error|\bnoqa\b|type:\s*ignore|\btodo\b|\bfixme\b"
    r"|\bimportant\b|\bdo\s+not\s+remove\b|\btoo\s+risky\b|\bfine\s+for\s+now\b|\bworkaround\b|\bhack\b)",
    re.I,
)
WORKAROUND_SMELL_PATTERNS = (
    ("imperative-timer", re.compile(r"\b(?:setTimeout|requestAnimationFrame|requestIdleCallback)\s*\("), False),
    ("raw-use-effect", re.compile(r"\buseEffect\s*\("), False),
    ("unsafe-type-escape", re.compile(r"\bas\s+any\b|\bas\s+unknown\s+as\b"), True),
)
TOY_SHORTCUT_PATTERNS = (
    (
        "not-implemented-stub",
        re.compile(r"\b(?:NotImplementedError|unimplemented!\s*\(|todo!\s*\(|throw\s+new\s+Error\s*\(\s*['\"]not\s+implemented)", re.I),
        True,
    ),
    (
        "placeholder-shortcut",
        re.compile(
            r"\b(?:placeholder\s+(?:impl|implementation|stub|logic|value|return|data|code|solver|mesh|fallback)"
            r"|stub\s+for\s+now|simplified\s+fallback|fake_data|mock_data|optional\s+hardcore)\b",
            re.I,
        ),
        True,
    ),
    (
        "deferred-real-impl",
        re.compile(r"\b(?:TODO|FIXME)\b.{0,40}\b(?:later|hardcore|real\s+impl|future|upgrade|placeholder)\b", re.I),
        True,
    ),
)

CMD_RECEIPT_RE = re.compile(r"^cmd:\s*\S+.*(?:\bexit\s+0\b|\bok\b|\bpass(?:ed)?\b)", re.I)
URL_RECEIPT_RE = re.compile(r"^https?://\S+$", re.I)
FILE_LINE_TOKEN_RE = re.compile(r"([A-Za-z0-9_./\\-]+?\.[A-Za-z0-9]{1,10})(?::(\d+))?")

CLAIM_OVERCLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:100%|always\s+works|never\s+fails|zero\s+(?:bugs|errors|failures|gaps)"
    r"|completely\s+bug[- ]free|supports?\s+all|handles?\s+every|guaranteed\s+to)(?![A-Za-z0-9_])",
    re.I,
)


def reject_unsafe_root(root_arg: Path) -> Path:
    if root_arg.is_symlink():
        raise SystemExit(f"project root cannot be a symlink: {root_arg}")
    resolved = root_arg.resolve()
    if not resolved.is_dir():
        raise SystemExit(f"project root does not exist: {resolved}")
    if resolved.parent == resolved:
        raise SystemExit(f"refusing filesystem root as project root: {resolved}")
    forbidden = {Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
    for extra in ("/tmp", "/var/tmp", "/private/tmp"):
        p = Path(extra)
        if p.exists():
            forbidden.add(p.resolve())
    if resolved in forbidden:
        raise SystemExit(f"refusing home or system temp directory as project root: {resolved}")
    return resolved


def ensure_contained(target: Path, root: Path) -> Path:
    resolved_root = reject_unsafe_root(root)
    if target.is_symlink():
        raise SystemExit(f"refusing symlink path: {target}")
    resolved_target = target.resolve()
    try:
        rel_parts = resolved_target.relative_to(resolved_root).parts
    except ValueError as err:
        raise SystemExit(f"path {resolved_target} escapes project root {resolved_root}") from err
    probe = resolved_root
    for part in rel_parts:
        probe = probe / part
        if probe.is_symlink():
            raise SystemExit(f"refusing symlink component inside root: {probe}")
    return resolved_target


def atomic_write_text(target: Path, content: str, root: Path) -> None:
    safe_target = ensure_contained(target, root)
    safe_parent = ensure_contained(safe_target.parent, root)
    safe_parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{safe_target.name}.", suffix=".tmp", dir=str(safe_parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        last_err = None
        for attempt in range(5):
            try:
                os.replace(str(tmp_path), str(safe_target))
                last_err = None
                break
            except PermissionError as err:
                last_err = err
                time.sleep(0.05 * (attempt + 1))
        if last_err is not None:
            raise last_err
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        creationflags=NO_WINDOW,
    )


def _is_git_root_or_worktree(root: Path) -> bool:
    if (root / ".git").exists():
        return True
    res = _run_git(root, ["rev-parse", "--show-toplevel"])
    if res.returncode != 0:
        return False
    try:
        return Path(res.stdout.strip()).resolve() == root.resolve()
    except OSError:
        return False


def _iter_non_git_files(safe_root: Path, cap: int = 200) -> list[str]:
    found: list[str] = []
    for cur_root, dirnames, filenames in os.walk(safe_root):
        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in NON_GIT_SKIP_DIRS and not (Path(cur_root) / d).is_symlink()
        ]
        base = Path(cur_root)
        for fn in sorted(filenames):
            p = base / fn
            if p.is_symlink():
                continue
            ext = p.suffix.lower()
            if ext in (CODE_EXTS | PROOF_EXTS | SCHEMA_OR_CONFIG_EXTS | {".md"}):
                found.append(p.relative_to(safe_root).as_posix())
                if len(found) >= cap:
                    return found
    return found


def compute_tree_digest(root: Path) -> str:
    safe_root = reject_unsafe_root(root)
    h = hashlib.sha256()
    if _is_git_root_or_worktree(safe_root):
        head = _run_git(safe_root, ["rev-parse", "HEAD"])
        h.update(f"HEAD:{head.stdout.strip()}\n".encode("utf-8"))
        status = _run_git(safe_root, ["status", "--porcelain=v1", "-uno"])
        for line in sorted(status.stdout.splitlines()):
            norm = line.replace("\\", "/")
            if "/.scratch/" in norm or norm.endswith(" .scratch") or ".worktrees/" in norm:
                continue
            h.update((norm + "\n").encode("utf-8"))
        diff = _run_git(safe_root, ["diff", "--relative", "HEAD"])
        h.update(diff.stdout.encode("utf-8", errors="replace"))
        untracked = _run_git(safe_root, ["ls-files", "--others", "--exclude-standard"])
        for rel in sorted(untracked.stdout.splitlines()):
            norm = rel.strip().replace("\\", "/")
            if not norm or norm.startswith((".scratch/", ".worktrees/", "__pycache__/")):
                continue
            p = safe_root / norm
            if p.is_file() and not p.is_symlink():
                try:
                    h.update(f"U:{norm}:{hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode("utf-8"))
                except OSError:
                    pass
    else:
        for rel in _iter_non_git_files(safe_root, cap=200):
            p = safe_root / rel
            if p.is_file() and not p.is_symlink():
                try:
                    h.update(f"NG:{rel}:{hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode("utf-8"))
                except OSError:
                    pass
    return h.hexdigest()[:24]

def _parse_numstat(output: str) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add_raw, del_raw, raw_path = parts[0], parts[1], parts[2]
        if " => " in raw_path:
            raw_path = re.sub(r"\{[^{}]* => ([^{}]*)\}", r"\1", raw_path)
            if " => " in raw_path:
                raw_path = raw_path.split(" => ", 1)[1]
        path_norm = raw_path.strip().strip('"').replace("\\", "/")
        if not path_norm or path_norm.startswith((".scratch/", ".worktrees/")):
            continue
        added = int(add_raw) if add_raw.isdigit() else 0
        deleted = int(del_raw) if del_raw.isdigit() else 0
        prev_a, prev_d = stats.get(path_norm, (0, 0))
        stats[path_norm] = (prev_a + added, prev_d + deleted)
    return stats


def _count_file_lines(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if b"\x00" in data[:8192] or not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _find_inline_marker(line: str, marker: str) -> int:
    in_single = False
    in_double = False
    escaped = False
    mlen = len(marker)
    limit = len(line) - mlen + 1
    i = 0
    while i < limit:
        ch = line[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\" and (in_single or in_double):
            escaped = True
            i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and line.startswith(marker, i):
            if marker == "//" and i > 0 and line[i - 1] == ":":
                i += 1
                continue
            return i
        i += 1
    return -1


def _comment_body(path: str, line: str) -> str | None:
    ext = Path(path).suffix.lower()
    stripped = line.lstrip()
    if ext in HASH_COMMENT_EXTS:
        if stripped.startswith("#!"):
            return None
        if stripped.startswith("#"):
            return stripped[1:].strip()
        idx = _find_inline_marker(line, "#")
        if idx >= 0:
            return line[idx + 1 :].strip()
    elif ext in SLASH_COMMENT_EXTS:
        if stripped.startswith("//"):
            return stripped[2:].strip()
        if stripped.startswith("/*") and not stripped.startswith("/**"):
            body = stripped[2:]
            if body.endswith("*/"):
                body = body[: -2]
            return body.strip(" *")
        idx = _find_inline_marker(line, "//")
        if idx >= 0:
            return line[idx + 2 :].strip()
    elif ext in DASH_COMMENT_EXTS:
        if stripped.startswith("--"):
            body = stripped[2:].strip()
            if ext in (".lua", ".luau") and LUAU_DIRECTIVE_RE.match(body):
                return None
            return body
        idx = _find_inline_marker(line, "--")
        if idx >= 0:
            body = line[idx + 2 :].strip()
            if ext in (".lua", ".luau") and LUAU_DIRECTIVE_RE.match(body):
                return None
            return body
    return None


def _should_keep_comment(body: str) -> bool:
    if not body:
        return True
    if COMMENT_SCENT_RE.search(body):
        return False
    return bool(COMMENT_KEEP_RE.search(body))


def _collect_diff_patches(root: Path, paths: list[str], base: str | None, staged: bool, head_sha: str | None) -> list[str]:
    if not paths:
        return []
    outputs: list[str] = []
    if base:
        res = _run_git(root, ["diff", "--relative", "-U0", base, "--", *paths])
        if res.returncode == 0:
            outputs.append(res.stdout)
    elif staged:
        res = _run_git(root, ["diff", "--relative", "--cached", "-U0", "--", *paths])
        if res.returncode == 0:
            outputs.append(res.stdout)
    elif head_sha:
        res = _run_git(root, ["diff", "--relative", "-U0", "HEAD", "--", *paths])
        if res.returncode == 0:
            outputs.append(res.stdout)
    else:
        cached = _run_git(root, ["diff", "--relative", "--cached", "-U0", "--", *paths])
        if cached.returncode == 0 and cached.stdout:
            outputs.append(cached.stdout)
        unstaged = _run_git(root, ["diff", "--relative", "-U0", "--", *paths])
        if unstaged.returncode == 0 and unstaged.stdout:
            outputs.append(unstaged.stdout)
    return outputs


def _iter_added_lines(
    root: Path, target_paths: set[str], base: str | None, staged: bool, head_sha: str | None
):
    if not target_paths:
        return
    seen_in_diff: set[str] = set()
    seen_pairs: set[tuple[str, int]] = set()
    patches = _collect_diff_patches(root, sorted(target_paths), base, staged, head_sha)
    for patch in patches:
        cur_file = None
        cur_line = 0
        for raw in patch.splitlines():
            if raw.startswith("diff --git "):
                cur_file = None
            elif raw.startswith("+++ "):
                header_path = raw[4:].strip().strip('"')
                if header_path == "/dev/null":
                    cur_file = None
                else:
                    if header_path.startswith("b/"):
                        header_path = header_path[2:]
                    cur_file = header_path.replace("\\", "/")
                    seen_in_diff.add(cur_file)
            elif raw.startswith("@@ "):
                m = re.search(r"\+(\d+)", raw)
                cur_line = int(m.group(1)) if m else 0
            elif cur_file and cur_file in target_paths and raw.startswith("+") and not raw.startswith("+++"):
                key = (cur_file, cur_line)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    yield cur_file, cur_line, raw[1:]
                cur_line += 1

    if not staged:
        for rel in sorted(target_paths - seen_in_diff):
            target = root / rel
            if not target.is_file() or target.is_symlink():
                continue
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for idx, line in enumerate(lines, 1):
                yield rel, idx, line


def _scan_added_comments(root: Path, files: list[str], base: str | None, staged: bool, head_sha: str | None) -> list[dict]:
    scan_set = {p for p in files if Path(p).suffix.lower() in COMMENT_SCAN_EXTS}
    found: list[dict] = []
    for rel, line_no, text in _iter_added_lines(root, scan_set, base, staged, head_sha):
        body = _comment_body(rel, text)
        if body is not None and not _should_keep_comment(body):
            found.append(
                {
                    "path": rel,
                    "line": line_no,
                    "text": body[:120],
                    "high_scent": bool(COMMENT_SCENT_RE.search(body)),
                }
            )
    return found


def _python_regex_or_template_lines(root: Path, rel: str) -> set[int]:
    if not rel.lower().endswith(".py"):
        return set()
    target = root / rel
    try:
        src = target.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=rel)
    except (OSError, SyntaxError):
        return set()
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            is_re_compile = (
                isinstance(fn, ast.Attribute)
                and fn.attr in {"compile", "search", "match", "fullmatch", "sub", "findall", "finditer"}
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "re"
            )
            if is_re_compile and hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                skip.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if ("/deep " in val or "Hardcore Mode" in val or "hardcore-craft-depth" in val or "(optional hardcore mode)" in val.lower()) and hasattr(node, "lineno"):
                skip.update(range(node.lineno, (getattr(node, "end_lineno", None) or node.lineno) + 1))
    return skip


def _scan_workaround_smells(root: Path, files: list[str], base: str | None, staged: bool, head_sha: str | None) -> list[dict]:
    code_set = {p for p in files if Path(p).suffix.lower() in CODE_EXTS and not TEST_PATH_RE.search(p)}
    skip_cache: dict[str, set[int]] = {}
    found: list[dict] = []
    for rel, line_no, text in _iter_added_lines(root, code_set, base, staged, head_sha):
        stripped = text.lstrip()
        if stripped.startswith(("#", "//", "--", "/*", "*")) or "re.compile(" in text:
            continue
        if rel not in skip_cache:
            skip_cache[rel] = _python_regex_or_template_lines(root, rel)
        if line_no in skip_cache[rel]:
            continue
        for kind, pat, is_critical in WORKAROUND_SMELL_PATTERNS:
            if pat.search(text):
                found.append(
                    {
                        "path": rel,
                        "line": line_no,
                        "kind": kind,
                        "critical": is_critical,
                        "text": text.strip()[:120],
                    }
                )
    return found


def _scan_toy_shortcuts(root: Path, files: list[str], base: str | None, staged: bool, head_sha: str | None) -> list[dict]:
    code_set = {p for p in files if Path(p).suffix.lower() in CODE_EXTS and not TEST_PATH_RE.search(p)}
    skip_cache: dict[str, set[int]] = {}
    found: list[dict] = []
    for rel, line_no, text in _iter_added_lines(root, code_set, base, staged, head_sha):
        if "re.compile(" in text:
            continue
        if rel not in skip_cache:
            skip_cache[rel] = _python_regex_or_template_lines(root, rel)
        if line_no in skip_cache[rel]:
            continue
        cbody = _comment_body(rel, text)
        if cbody is not None and re.search(r"\b(?:placeholder|stub|simplified\s+fallback|optional\s+hardcore)\b", cbody, re.I):
            found.append(
                {
                    "path": rel,
                    "line": line_no,
                    "kind": "comment-placeholder-shortcut",
                    "critical": True,
                    "text": text.strip()[:120],
                }
            )
            continue
        for kind, pat, is_critical in TOY_SHORTCUT_PATTERNS:
            if pat.search(text):
                found.append(
                    {
                        "path": rel,
                        "line": line_no,
                        "kind": kind,
                        "critical": is_critical,
                        "text": text.strip()[:120],
                    }
                )
                break
    return found


def _scan_backend_perf_traps(root: Path, files: list[str]) -> list[dict]:
    perf_script = Path(__file__).resolve().parent.parent / "perf-audit" / "perf_audit.py"
    if not perf_script.is_file():
        return []
    cand_files = [
        f for f in files
        if Path(f).suffix.lower() in BACKEND_EXTS
        and not TEST_PATH_RE.search(f)
        and (root / f).is_file()
    ]
    if not cand_files:
        return []
    try:
        spec = importlib.util.spec_from_file_location("self_grill_perf_audit", perf_script)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        res = mod.scan_paths(root, explicit_files=cand_files)
        return list(res.get("findings") or [])
    except Exception:
        return []


def _auto_merge_base(root: Path) -> str | None:
    branch_res = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_res.stdout.strip() if branch_res.returncode == 0 else ""
    if not branch or branch in ("main", "master", "HEAD"):
        return None
    for candidate in ("origin/main", "origin/master", "main", "master"):
        mb = _run_git(root, ["merge-base", "HEAD", candidate])
        if mb.returncode == 0:
            sha = mb.stdout.strip()
            head = _run_git(root, ["rev-parse", "HEAD"]).stdout.strip()
            if sha and sha != head:
                return sha
    return None



def _scan_proof_escapes(root: Path, files: list[str]) -> list[dict]:
    vp_script = Path(__file__).resolve().parent.parent / "formal-verification" / "verify_proof.py"
    if not vp_script.is_file():
        return []
    cand_files = [
        f for f in files
        if Path(f).suffix.lower() in PROOF_EXTS
        and not TEST_PATH_RE.search(f)
        and (root / f).is_file()
    ]
    if not cand_files:
        return []
    try:
        spec = importlib.util.spec_from_file_location("self_grill_verify_proof", vp_script)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        out: list[dict] = []
        for rel in cand_files:
            for item in mod.scan_proof_file(root / rel, base_root=root):
                out.append({
                    "rule_id": item.rule_id,
                    "severity": item.severity,
                    "file": item.file,
                    "line": item.line,
                    "message": item.message,
                })
        return out
    except Exception:
        return []

def inspect_diff(
    root: Path,
    base: str | None = None,
    staged: bool = False,
    explicit_files: list[str] | None = None,
) -> dict:
    safe_root = reject_unsafe_root(root)
    stats: dict[str, tuple[int, int]] = {}
    head_sha = None
    effective_base = base
    in_git = _is_git_root_or_worktree(safe_root)
    if explicit_files:
        for raw in explicit_files:
            cand = ensure_contained((safe_root / raw) if not Path(raw).is_absolute() else Path(raw), safe_root)
            if cand.is_file():
                rel = cand.relative_to(safe_root).as_posix()
                stats[rel] = (_count_file_lines(cand), 0)
    elif in_git:
        head_res = _run_git(safe_root, ["rev-parse", "--short", "HEAD"])
        if head_res.returncode == 0:
            head_sha = head_res.stdout.strip() or None
        if effective_base:
            diff_res = _run_git(safe_root, ["diff", "--relative", "--numstat", effective_base])
            if diff_res.returncode != 0:
                diff_res = _run_git(safe_root, ["diff", "--relative", "--numstat", f"{effective_base}...HEAD"])
            stats.update(_parse_numstat(diff_res.stdout))
        elif staged:
            diff_res = _run_git(safe_root, ["diff", "--relative", "--cached", "--numstat"])
            stats.update(_parse_numstat(diff_res.stdout))
        else:
            if head_sha:
                diff_res = _run_git(safe_root, ["diff", "--relative", "--numstat", "HEAD"])
                stats.update(_parse_numstat(diff_res.stdout))
            else:
                cached_res = _run_git(safe_root, ["diff", "--relative", "--cached", "--numstat"])
                stats.update(_parse_numstat(cached_res.stdout))
                wt_res = _run_git(safe_root, ["diff", "--relative", "--numstat"])
                stats.update(_parse_numstat(wt_res.stdout))

        if not staged:
            untracked = _run_git(safe_root, ["ls-files", "--others", "--exclude-standard"])
            if untracked.returncode == 0:
                for rel in untracked.stdout.splitlines():
                    norm = rel.strip().replace("\\", "/")
                    if not norm or norm.startswith((".scratch/", ".worktrees/")):
                        continue
                    stats.setdefault(norm, (_count_file_lines(safe_root / norm), 0))

        if not stats and not effective_base and not staged and head_sha:
            mb = _auto_merge_base(safe_root)
            if mb:
                effective_base = mb
                mb_res = _run_git(safe_root, ["diff", "--relative", "--numstat", mb])
                stats.update(_parse_numstat(mb_res.stdout))

    else:
        for rel in _iter_non_git_files(safe_root, cap=150):
            stats[rel] = (_count_file_lines(safe_root / rel), 0)
    files = sorted(stats.keys())
    added = sum(v[0] for v in stats.values())
    deleted = sum(v[1] for v in stats.values())
    total_lines = added + deleted
    file_count = len(files)

    sensitive_paths = [p for p in files if SENSITIVE_PATH_RE.search(p)]
    test_paths = [p for p in files if TEST_PATH_RE.search(p)]
    code_paths = [p for p in files if Path(p).suffix.lower() in CODE_EXTS and p not in test_paths]
    proof_paths = [p for p in files if Path(p).suffix.lower() in PROOF_EXTS and p not in test_paths]
    shell_paths = [p for p in files if Path(p).suffix.lower() in SHELL_OR_SCRIPT_EXTS]
    schema_paths = [p for p in files if Path(p).suffix.lower() in SCHEMA_OR_CONFIG_EXTS]
    skill_paths = [p for p in files if SKILL_OR_PROMPT_RE.search(p)]

    if file_count == 0:
        measured_size = "none"
    elif total_lines <= 30 and file_count <= 2 and not sensitive_paths:
        measured_size = "S"
    elif total_lines > 250 or file_count > 8 or len(sensitive_paths) >= 2:
        measured_size = "L"
    else:
        measured_size = "M"

    added_comments = _scan_added_comments(safe_root, files, effective_base, staged, head_sha) if in_git else []
    workaround_smells = _scan_workaround_smells(safe_root, files, effective_base, staged, head_sha) if in_git else []
    toy_shortcuts = _scan_toy_shortcuts(safe_root, files, effective_base, staged, head_sha) if in_git else []
    backend_perf_findings = _scan_backend_perf_traps(safe_root, files)
    proof_escapes = _scan_proof_escapes(safe_root, files)
    questions = build_questions(
        phase="checks",
        files=files,
        total_lines=total_lines,
        file_count=file_count,
        sensitive_paths=sensitive_paths,
        code_paths=code_paths,
        test_paths=test_paths,
        shell_paths=shell_paths,
        schema_paths=schema_paths,
        skill_paths=skill_paths,
        added_comments=added_comments,
        workaround_smells=workaround_smells,
        toy_shortcuts=toy_shortcuts,
        backend_perf_findings=backend_perf_findings,
        proof_paths=proof_paths,
        proof_escapes=proof_escapes,
    )
    recommend_cross_family = measured_size == "L" or bool(sensitive_paths) or bool(proof_paths)
    tree_digest = compute_tree_digest(safe_root)
    return {
        "root": str(safe_root),
        "in_git": in_git,
        "head_sha": head_sha,
        "tree_digest": tree_digest,
        "base": effective_base,
        "staged": staged,
        "file_count": file_count,
        "lines_added": added,
        "lines_deleted": deleted,
        "total_lines": total_lines,
        "measured_size": measured_size,
        "files": files,
        "sensitive_paths": sensitive_paths,
        "code_paths": code_paths,
        "proof_paths": proof_paths,
        "test_paths": test_paths,
        "shell_paths": shell_paths,
        "schema_paths": schema_paths,
        "skill_paths": skill_paths,
        "added_comment_count": len(added_comments),
        "added_comments": added_comments[:25],
        "workaround_smell_count": len(workaround_smells),
        "workaround_smells": workaround_smells[:25],
        "toy_shortcut_count": len(toy_shortcuts),
        "toy_shortcuts": toy_shortcuts[:25],
        "backend_perf_count": len(backend_perf_findings),
        "backend_perf_findings": backend_perf_findings[:25],
        "proof_escape_count": len(proof_escapes),
        "proof_escapes": proof_escapes[:25],
        "recommend_cross_family_skeptic": recommend_cross_family,
        "questions": questions,
    }


def build_questions(
    phase: str,
    files: list[str],
    total_lines: int,
    file_count: int,
    sensitive_paths: list[str],
    code_paths: list[str],
    test_paths: list[str],
    shell_paths: list[str],
    schema_paths: list[str],
    skill_paths: list[str],
    added_comments: list[dict] | None = None,
    workaround_smells: list[dict] | None = None,
    toy_shortcuts: list[dict] | None = None,
    added_comment_total: int | None = None,
    workaround_smell_total: int | None = None,
    toy_shortcut_total: int | None = None,
    backend_perf_findings: list[dict] | None = None,
    proof_paths: list[str] | None = None,
    proof_escapes: list[dict] | None = None,
) -> list[dict]:
    items: list[dict] = []
    comment_count = added_comment_total if added_comment_total is not None else len(added_comments or [])
    smell_count = workaround_smell_total if workaround_smell_total is not None else len(workaround_smells or [])
    shortcut_count = toy_shortcut_total if toy_shortcut_total is not None else len(toy_shortcuts or [])
    perf_list = list(backend_perf_findings or [])
    p_paths = list(proof_paths or [])
    p_escapes = list(proof_escapes or [])
    def add(qid: str, severity: str, category: str, prompt: str, trigger: str) -> None:
        items.append(
            {
                "id": qid,
                "severity": severity,
                "category": category,
                "prompt": prompt,
                "trigger": trigger,
                "status": "open",
                "answer": "",
                "receipt": "",
            }
        )

    if phase in ("plan", "both"):
        add(
            "premise-check",
            "critical",
            "plan",
            "What assumption in this plan could be wrong or an XY proxy, and what repo/runtime fact proves the premise holds?",
            "always-plan",
        )
        add(
            "irreversible-and-scope",
            "critical",
            "plan",
            "Are all user deliverables accounted for in the scope ledger, and does any step cross a hard stop or outside-root write?",
            "always-plan",
        )
        add(
            "oracle-before-code",
            "advisory",
            "plan",
            "What exact real-artifact command or failing-without-fix test will prove this change works before reporting done?",
            "always-plan",
        )
        add(
            "hardcore-ceiling",
            "critical",
            "hardcore",
            "Hardcore Mode check: does this plan aim straight for the first-principles architectural ceiling (real algorithms, parallelism, solvers, native representations/LODs) instead of sandbagging into a toy MVP or hiding the best tier under '(Optional hardcore mode)'?",
            "always-plan",
        )

    if phase in ("checks", "both"):
        add(
            "real-artifact-proof",
            "critical",
            "checks",
            "Did you run the real command, app, or test suite AFTER your final edit with raw exit code 0 (never masked behind | head or | tail)?",
            "always-checks",
        )
        add(
            "scope-completeness",
            "critical",
            "checks",
            "Does every deliverable requested by the user map to a verified change or an explicit blocker with unblock path?",
            "always-checks",
        )
        if code_paths and not test_paths:
            add(
                "missing-regression-test",
                "critical",
                "checks",
                f"Code changed ({', '.join(code_paths[:4])}) without test edits: what failing-without-fix test or live check proves the behavior cannot silently regress?",
                "code-without-tests",
            )
        if test_paths:
            add(
                "no-check-theater",
                "critical",
                "checks",
                "Would the new or touched tests fail if your production fix were reverted, and do they avoid mocking out the behavior under test?",
                "tests-touched",
            )
        if sensitive_paths:
            add(
                "trust-boundary-fail-closed",
                "critical",
                "security",
                f"Sensitive paths touched ({', '.join(sensitive_paths[:4])}): how do missing, malformed, or hostile inputs fail closed without leaking secrets or escaping root?",
                "sensitive-paths",
            )
        if shell_paths:
            add(
                "exit-code-and-platform",
                "advisory",
                "platform",
                "Do shell/script changes handle Windows paths, CRLF line endings, spaces in paths, and non-zero exit codes safely?",
                "scripts-touched",
            )
        if skill_paths:
            add(
                "skill-and-link-validation",
                "critical",
                "skills",
                "Did check_skill.py (and repo structural checks, byte budgets, and routing tests) pass after the final skill or prompt edit?",
                "skills-touched",
            )
        if schema_paths:
            add(
                "schema-backcompat",
                "advisory",
                "data",
                "Are config, JSON, or schema edits backwards-compatible and idempotent for existing callers and stored state?",
                "schema-touched",
            )
        if total_lines > 200 or file_count > 6:
            add(
                "blast-radius-and-split",
                "advisory",
                "architecture",
                f"Diff touches {total_lines} lines across {file_count} files: what indirect callers could break, and should any independent unit split out?",
                "large-diff",
            )
        if added_comments:
            high_scent = [c for c in added_comments if c.get("high_scent")]
            locs = ", ".join(f"{c['path']}:{c['line']}" for c in added_comments[:4])
            sev = "critical" if (high_scent or comment_count >= 3) else "advisory"
            add(
                "no-lying-comments",
                sev,
                "comments",
                f"Diff adds {comment_count} code comment(s) ({locs}): comments rot and lie, and AI agents read comments instead of code. Delete narration/workaround/suppression comments via no-comments or prove each matches a strict keep exception.",
                "added-comments",
            )
        if workaround_smells:
            has_crit = any(s.get("critical") for s in workaround_smells)
            locs = ", ".join(f"{s['path']}:{s['line']}({s['kind']})" for s in workaround_smells[:4])
            sev = "critical" if (has_crit or smell_count >= 2) else "advisory"
            add(
                "no-workaround-smells",
                sev,
                "architecture",
                f"Diff introduces {smell_count} workaround/foot-gun smell(s) ({locs}): eliminate the root cause or use a supported framework API/type instead of imperative timers, raw useEffect, or unsafe type casts.",
                "workaround-smells",
            )
        if perf_list:
            locs = ", ".join(f"{p['file']}:{p['line']}({p['rule_id']})" for p in perf_list[:4])
            has_high = any(p.get("severity") == "high" for p in perf_list)
            add(
                "backend-systems-hygiene",
                "critical" if has_high else "advisory",
                "performance",
                f"Diff triggers {len(perf_list)} backend/systems hot-path trap(s) ({locs}): eliminate N+1/await-in-loop waterfalls, sync-in-async blocking, missing HTTP timeouts, per-request pools, OFFSET scans, or cache/serialization bottlenecks per high-scale-server-optimization.md.",
                "backend-perf-traps",
            )
        if p_escapes or p_paths:
            esc_note = (
                f" Static proof escapes found: {', '.join(f'{e['file']}:{e['line']}({e['rule_id']})' for e in p_escapes[:4])}."
                if p_escapes else ""
            )
            add(
                "proof-and-math-soundness",
                "critical",
                "formal",
                f"Formal & mathematical proof soundness ({', '.join(p_paths[:4] or ['proofs'])}):{esc_note} "
                "Verify zero sorry/admit/custom axiom/native_decide escapes via verify_proof.py audit-static, "
                "check NL-to-formal statement alignment (quantifier order forall-exists vs exists-forall, n=0/1 boundaries, strict vs weak inequalities), "
                "prove checks are able-to-fail (--mutate), and run two independent line-by-line audits on any non-kernel-certified step.",
                "proof-touched",
            )
        if toy_shortcuts:
            locs = ", ".join(f"{s['path']}:{s['line']}({s['kind']})" for s in toy_shortcuts[:4])
            add(
                "hardcore-craft-depth",
                "critical",
                "hardcore",
                f"Hardcore Mode violation: diff introduces {shortcut_count} stub/toy shortcut(s) ({locs}). Replace placeholders/stubs/deferred TODOs with the real first-principles implementation and prove it on the real artifact.",
                "toy-shortcuts",
            )
        elif code_paths and (total_lines > 30 or file_count > 2):
            add(
                "hardcore-craft-depth",
                "critical",
                "hardcore",
                "Hardcore Mode audit: does this implementation ship the true first-principles architecture/algorithm rather than a watered-down approximation, single-threaded shortcut, or deferred '(optional hardcore mode)' compromise?",
                "hardcore-code-change",
            )
        add(
            "gaps-and-overclaims",
            "critical",
            "honesty",
            "Audit your work and final report for gaps and overclaims: does every claim, count, link, and 'passes/works' statement match an observed file or fresh run on this tree, with every remaining gap or limit named explicitly?",
            "always-checks",
        )
        add(
            "deletion-test",
            "advisory",
            "simplicity",
            "Apply the deletion test: what newly added wrapper, flag, comment, or prose block can be deleted without losing required behavior?",
            "always-checks",
        )
    return items


def is_valid_receipt(receipt_text: str, root: Path | None = None) -> bool:
    text = receipt_text.strip()
    if len(text) < 4:
        return False
    if CMD_RECEIPT_RE.search(text) or URL_RECEIPT_RE.match(text):
        return True
    for raw_path, line_str in FILE_LINE_TOKEN_RE.findall(text):
        if raw_path.lower() in {"e.g", "i.e", "etc.py"}:
            continue
        if root is not None:
            cand = (root / raw_path).resolve()
            try:
                cand.relative_to(root.resolve())
            except ValueError:
                continue
            if cand.is_file():
                if line_str:
                    line_no = int(line_str)
                    total = _count_file_lines(cand)
                    if 1 <= line_no <= max(1, total):
                        return True
                else:
                    return True
        elif line_str and int(line_str) >= 1:
            return True
    return False


def _ensure_scratch_gitignore(root: Path) -> None:
    scratch_dir = ensure_contained(root / ".scratch", root)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    gi = scratch_dir / ".gitignore"
    if not gi.exists():
        atomic_write_text(gi, "*\n!.gitignore\n", root)


def cmd_check_diff(args: argparse.Namespace) -> int:
    report = inspect_diff(Path(args.root), base=args.base, staged=args.staged, explicit_files=args.files)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"size={report['measured_size']} files={report['file_count']} "
            f"lines=+{report['lines_added']}/-{report['lines_deleted']} "
            f"sensitive={len(report['sensitive_paths'])} "
            f"cross_family={report['recommend_cross_family_skeptic']}"
        )
        for q in report["questions"]:
            print(f"- [{q['severity']}] {q['id']}: {q['prompt']}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    if not SLUG_RE.fullmatch(args.slug):
        raise SystemExit(f"invalid slug {args.slug!r}: use lowercase kebab-case")
    root = reject_unsafe_root(Path(args.root))
    _ensure_scratch_gitignore(root)
    gdir = ensure_contained(root / ".scratch" / "self-grill" / args.slug, root)
    state_path = gdir / "grill.json"
    existing_answers: dict[str, dict] = {}
    if state_path.exists():
        if args.refresh:
            old_data = json.loads(state_path.read_text(encoding="utf-8"))
            for q in old_data.get("questions", []):
                if q.get("category") in ("plan", "hardcore") and q.get("trigger") == "always-plan" and q.get("status") != "open":
                    existing_answers[q["id"]] = q
        elif not args.force:
            raise SystemExit(f"self-grill session already exists at {gdir}; pass --refresh or --force")

    diff_info = inspect_diff(root, base=args.base, staged=args.staged, explicit_files=args.files)
    questions = build_questions(
        phase=args.phase,
        files=diff_info["files"],
        total_lines=diff_info["total_lines"],
        file_count=diff_info["file_count"],
        sensitive_paths=diff_info["sensitive_paths"],
        code_paths=diff_info["code_paths"],
        test_paths=diff_info["test_paths"],
        shell_paths=diff_info["shell_paths"],
        schema_paths=diff_info["schema_paths"],
        skill_paths=diff_info["skill_paths"],
        added_comments=diff_info["added_comments"],
        workaround_smells=diff_info["workaround_smells"],
        toy_shortcuts=diff_info["toy_shortcuts"],
        added_comment_total=diff_info["added_comment_count"],
        workaround_smell_total=diff_info["workaround_smell_count"],
        toy_shortcut_total=diff_info["toy_shortcut_count"],
        backend_perf_findings=diff_info["backend_perf_findings"],
        proof_paths=diff_info["proof_paths"],
        proof_escapes=diff_info["proof_escapes"],
    )
    for q in questions:
        if q["id"] in existing_answers:
            prev = existing_answers[q["id"]]
            q["status"] = prev["status"]
            q["answer"] = prev["answer"]
            q["receipt"] = prev["receipt"]

    payload = {
        "slug": args.slug,
        "phase": args.phase,
        "root": str(root),
        "head_sha": diff_info["head_sha"],
        "tree_digest": diff_info["tree_digest"],
        "base": diff_info["base"],
        "staged": args.staged,
        "measured_size": diff_info["measured_size"],
        "file_count": diff_info["file_count"],
        "total_lines": diff_info["total_lines"],
        "sensitive_paths": diff_info["sensitive_paths"],
        "toy_shortcuts": diff_info["toy_shortcuts"],
        "recommend_cross_family_skeptic": diff_info["recommend_cross_family_skeptic"],
        "questions": questions,
    }
    atomic_write_text(state_path, json.dumps(payload, indent=2) + "\n", root)
    out = {"dir": str(gdir), "state": str(state_path), **payload}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"initialized {gdir} ({len(questions)} questions, size={payload['measured_size']})")
    return 0


def _load_state(gdir: Path) -> tuple[Path, Path, dict]:
    state_path = gdir / "grill.json"
    if not state_path.is_file():
        raise SystemExit(f"missing grill.json in {gdir}")
    data = json.loads(state_path.read_text(encoding="utf-8"))
    root = reject_unsafe_root(Path(data["root"]))
    ensure_contained(state_path, root)
    return root, state_path, data


def cmd_answer(args: argparse.Namespace) -> int:
    gdir = Path(args.dir)
    root, state_path, data = _load_state(gdir)
    answer_text = args.answer.strip()
    receipt_text = (args.receipt or "").strip()
    if not answer_text:
        raise SystemExit("--answer cannot be empty")
    if args.status == "proven":
        if not receipt_text or not is_valid_receipt(receipt_text, root):
            raise SystemExit(
                "status 'proven' requires a verified --receipt (existing repo file:line, 'cmd:<cmd> -> exit 0', or URL)"
            )
    if args.status == "na" and len(answer_text) < 8:
        raise SystemExit("status 'na' requires a concrete reason in --answer")

    matched = None
    for q in data["questions"]:
        if q["id"] == args.id:
            q["status"] = args.status
            q["answer"] = answer_text
            q["receipt"] = receipt_text
            matched = q
            break
    if matched is None:
        raise SystemExit(f"unknown question id {args.id!r}")

    atomic_write_text(state_path, json.dumps(data, indent=2) + "\n", root)
    if args.json:
        print(json.dumps(matched, indent=2))
    else:
        print(f"recorded {matched['id']} -> {matched['status']}")
    return 0


def evaluate_verdict(data: dict, root: Path | None = None, allow_stale: bool = False) -> dict:
    blocked = [q["id"] for q in data["questions"] if q["status"] == "blocked"]
    failed = [q["id"] for q in data["questions"] if q["status"] == "failed"]
    open_critical = [
        q["id"]
        for q in data["questions"]
        if q["severity"] == "critical" and q["status"] not in ("proven", "na")
    ]
    missing_receipts = [
        q["id"]
        for q in data["questions"]
        if q["status"] == "proven" and not is_valid_receipt(q.get("receipt", ""), root)
    ]
    open_advisory = [
        q["id"]
        for q in data["questions"]
        if q["severity"] != "critical" and q["status"] == "open"
    ]
    stale_tree = False
    recorded_digest = data.get("tree_digest", "")
    live_digest = ""
    if root is not None and recorded_digest and data.get("phase") in ("checks", "both") and not allow_stale:
        if _is_git_root_or_worktree(root):
            live_digest = compute_tree_digest(root)
            if live_digest != recorded_digest:
                stale_tree = True

    if blocked:
        verdict = "BLOCKED"
    elif failed or open_critical or missing_receipts or stale_tree:
        verdict = "NEEDS_WORK"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "slug": data["slug"],
        "phase": data["phase"],
        "head_sha": data.get("head_sha"),
        "tree_digest": recorded_digest,
        "live_tree_digest": live_digest or recorded_digest,
        "stale_tree": stale_tree,
        "measured_size": data.get("measured_size"),
        "total_questions": len(data["questions"]),
        "open_critical": open_critical,
        "failed": failed,
        "blocked": blocked,
        "missing_receipts": missing_receipts,
        "open_advisory": open_advisory,
        "recommend_cross_family_skeptic": data.get("recommend_cross_family_skeptic", False),
    }


def cmd_verdict(args: argparse.Namespace) -> int:
    root, _, data = _load_state(Path(args.dir))
    summary = evaluate_verdict(data, root=root, allow_stale=args.allow_stale)
    if summary["verdict"] == "PASS":
        latest_path = ensure_contained(root / ".scratch" / "self-grill" / "latest-pass.json", root)
        atomic_write_text(
            latest_path,
            json.dumps(
                {
                    "status": "PASS",
                    "slug": summary["slug"],
                    "head_sha": summary["head_sha"],
                    "tree_digest": summary["live_tree_digest"],
                },
                indent=2,
            )
            + "\n",
            root,
        )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"self-grill: {summary['verdict']} (phase={summary['phase']}, "
            f"open_critical={len(summary['open_critical'])}, failed={len(summary['failed'])}, "
            f"blocked={len(summary['blocked'])}, stale_tree={summary['stale_tree']})"
        )
    if args.strict and summary["verdict"] != "PASS":
        return 2
    return 0


def build_prosecutor_bundle(
    root: Path,
    slug: str = "prosecutor",
    claims_text: str = "",
    confession_text: str = "",
    base: str | None = None,
    explicit_files: list[str] | None = None,
) -> dict:
    safe_root = reject_unsafe_root(root)
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug {slug!r}: use lowercase kebab-case")
    _ensure_scratch_gitignore(safe_root)
    diff_info = inspect_diff(safe_root, base=base, explicit_files=explicit_files)
    out_dir = ensure_contained(safe_root / ".scratch" / "self-grill" / slug, safe_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    claim_warnings = [m.group(0) for m in CLAIM_OVERCLAIM_RE.finditer(claims_text)] if claims_text else []
    sections: list[str] = [
        "# Adaptive Hotspot Prosecutor Bundle",
        f"- Project root: `{safe_root}`",
        f"- Measured diff size: `{diff_info['measured_size']}` ({diff_info['file_count']} files, +{diff_info['lines_added']}/-{diff_info['lines_deleted']} lines)",
        f"- Tree digest: `{diff_info['tree_digest']}`",
        f"- Sensitive paths: `{diff_info['sensitive_paths']}`",
        f"- Mechanical flags: comments={diff_info['added_comment_count']}, workaround_smells={diff_info['workaround_smell_count']}, toy_shortcuts={diff_info['toy_shortcut_count']}",
    ]
    if claims_text.strip():
        sections.append("\n## Draft Claims Under Audit\n" + claims_text.strip())
        if claim_warnings:
            sections.append(f"\nMechanical universal-claim triggers to verify strictly: {claim_warnings}")
    if confession_text.strip():
        sections.append("\n## Part B1 — Builder Confession (Known Shortcuts & Risks)\n" + confession_text.strip())

    sensitive_set = set(diff_info.get("sensitive_paths") or [])
    flagged_set = {
        x["path"]
        for bucket in ("workaround_smells", "toy_shortcuts", "added_comments")
        for x in (diff_info.get(bucket) or [])
        if "path" in x
    } | {x["file"] for x in (diff_info.get("backend_perf_findings") or []) if "file" in x} | {
        x["file"] for x in (diff_info.get("proof_escapes") or []) if "file" in x
    }

    def _bundle_priority(rel: str) -> tuple[int, int, int, int, str]:
        ext = Path(rel).suffix.lower()
        is_code = int((ext in CODE_EXTS or ext in PROOF_EXTS) and not TEST_PATH_RE.search(rel))
        is_sens = int(rel in sensitive_set)
        is_flag = int(rel in flagged_set)
        line_cnt = _count_file_lines(safe_root / rel)
        return (-is_sens, -is_flag, -is_code, -line_cnt, rel)

    ranked_files = sorted(diff_info["files"], key=_bundle_priority)
    selected_files = ranked_files[:25]
    omitted_files = ranked_files[25:]
    if omitted_files:
        sections.append(
            f"- Additional changed files outside top-25 bundle ({len(omitted_files)} — read directly if relevant): `{omitted_files[:30]}`"
        )

    for rel in selected_files:
        target = safe_root / rel
        if not target.is_file() or target.is_symlink():
            continue
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        max_whole_lines = 900 if Path(rel).suffix.lower() in PROOF_EXTS else 450
        if len(lines) <= max_whole_lines:
            numbered = "\n".join(f"{idx}: {line}" for idx, line in enumerate(lines, 1))
            sections.append(f"\n==================== FILE: {rel} ({len(lines)} lines) ====================\n{numbered}")
        else:
            patch_list = _collect_diff_patches(safe_root, [rel], diff_info["base"], False, diff_info["head_sha"]) if diff_info["in_git"] else []
            patch_preview = "\n".join(patch_list)[:18000].strip()
            if patch_preview:
                sections.append(
                    f"\n==================== FILE (HUNK WINDOW, {len(lines)} total lines — read full ranges if needed): {rel} ====================\n{patch_preview}"
                )
            else:
                head_part = "\n".join(f"{idx}: {line}" for idx, line in enumerate(lines[:220], 1))
                tail_start = max(221, len(lines) - 119)
                tail_part = "\n".join(f"{idx}: {line}" for idx, line in enumerate(lines[tail_start - 1:], tail_start))
                window_preview = f"{head_part}\n... [{tail_start - 221} lines elided; read {rel}:221-{tail_start - 1} on disk] ...\n{tail_part}"
                sections.append(
                    f"\n==================== FILE (UNTRACKED WINDOW, {len(lines)} total lines — read elided middle if needed): {rel} ====================\n{window_preview}"
                )
    prosecutor_prompt = (
        f"Read ONLY `{out_dir / 'prosecutor-bundle.md'}` first (read additional ranges in `{safe_root}` only for `[HUNK WINDOW]` files).\n"
        "Run the 3-step Adaptive Hotspot Prosecutor + Independent Sieve in a SINGLE pass:\n"
        "1. Adaptive Hotspot Map (5 lines): weight ~75% of probes on the highest-complexity code/regex/state/concurrency/security modules in the bundle and ~25% on Draft Claims & Docs vs literal code.\n"
        "2. Exhaustive Divergent Hunt: push past surface checks to brainstorm 50+ concrete candidate bugs, false positives, false negatives, edge cases, and overclaims (do NOT filter early).\n"
        "3. Independent Prosecutor Sieve: keep ONLY 100% code-provable P0/P1/P2 Gaps and text-vs-code Overclaims with exact `<file>:<line>`, concrete trigger input, and root-cause fix. Drop hypothetical '$90 trillion' filler."
    )
    bundle_path = out_dir / "prosecutor-bundle.md"
    atomic_write_text(bundle_path, "\n".join(sections) + "\n", safe_root)
    return {
        "bundle_path": str(bundle_path),
        "measured_size": diff_info["measured_size"],
        "file_count": diff_info["file_count"],
        "tree_digest": diff_info["tree_digest"],
        "claim_warnings": claim_warnings,
        "prosecutor_prompt": prosecutor_prompt,
    }


def cmd_bundle(args: argparse.Namespace) -> int:
    claims = sys.stdin.read() if args.claims_stdin else (Path(args.claims_file).read_text(encoding="utf-8") if args.claims_file else "")
    res = build_prosecutor_bundle(
        Path(args.root),
        slug=args.slug,
        claims_text=claims,
        confession_text=args.confession or "",
        base=args.base,
        explicit_files=args.files,
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(res["bundle_path"])
        print(res["prosecutor_prompt"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic diff-aware self-grill and Adaptive Prosecutor helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("check-diff", help="Inspect git diff and generate targeted self-grill questions.")
    p_diff.add_argument("--root", required=True)
    p_diff.add_argument("--base", default=None)
    p_diff.add_argument("--staged", action="store_true")
    p_diff.add_argument("--files", nargs="*", default=None)
    p_diff.add_argument("--json", action="store_true")
    p_diff.set_defaults(func=cmd_check_diff)

    p_init = sub.add_parser("init", help="Initialize or refresh a contained self-grill ledger under .scratch/self-grill/<slug>.")
    p_init.add_argument("--root", required=True)
    p_init.add_argument("--slug", required=True)
    p_init.add_argument("--phase", choices=("plan", "checks", "both"), default="checks")
    p_init.add_argument("--base", default=None)
    p_init.add_argument("--staged", action="store_true")
    p_init.add_argument("--files", nargs="*", default=None)
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--refresh", action="store_true")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_ans = sub.add_parser("answer", help="Record an evidence-backed answer for a self-grill question.")
    p_ans.add_argument("--dir", required=True)
    p_ans.add_argument("--id", required=True)
    p_ans.add_argument("--status", choices=("proven", "na", "failed", "blocked"), required=True)
    p_ans.add_argument("--answer", required=True)
    p_ans.add_argument("--receipt", default="")
    p_ans.add_argument("--json", action="store_true")
    p_ans.set_defaults(func=cmd_answer)

    p_ver = sub.add_parser("verdict", help="Compute PASS/NEEDS_WORK/BLOCKED gate verdict from recorded receipts.")
    p_ver.add_argument("--dir", required=True)
    p_ver.add_argument("--strict", action="store_true")
    p_ver.add_argument("--allow-stale", action="store_true")
    p_ver.add_argument("--json", action="store_true")
    p_ver.set_defaults(func=cmd_verdict)

    p_bun = sub.add_parser("bundle", help="Pack a single-file Adaptive Hotspot Prosecutor bundle on disk.")
    p_bun.add_argument("--root", required=True)
    p_bun.add_argument("--slug", default="prosecutor")
    p_bun.add_argument("--base", default=None)
    p_bun.add_argument("--files", nargs="*", default=None)
    p_bun.add_argument("--claims-stdin", action="store_true")
    p_bun.add_argument("--claims-file", default=None)
    p_bun.add_argument("--confession", default="")
    p_bun.add_argument("--json", action="store_true")
    p_bun.set_defaults(func=cmd_bundle)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
