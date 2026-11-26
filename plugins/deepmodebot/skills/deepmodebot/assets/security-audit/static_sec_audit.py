#!/usr/bin/env python3
"""Cross-platform zero-dependency static security & GitHub Actions workflow scanner.

    python -B static_sec_audit.py [--root <repo>] [--json] [--strict]

Catches high-confidence sharp edges on Windows, macOS, and Linux in <1s without LLM calls:
- GitHub Actions: unpinned 3rd-party `uses:` tags, `pull_request_target` + PR checkout, `${{ ... }}` untrusted script injection
- Timing-unsafe secret/HMAC equality checks (`==` on hmac/signature/secret digests)
- Dangerous deserialization (`pickle.loads`, `yaml.load(` without SafeLoader), shell=True interpolation, and SQL f-strings
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SKIP_DIRS = frozenset({".git", "node_modules", ".scratch", ".worktrees", "__pycache__", "target", "dist", "build", "vendor"})
FIRST_PARTY_ACTION_OWNERS = frozenset({"actions", "github"})
UNTRUSTED_GH_EXPR_RE = re.compile(
    r"\$\{\{\s*github\.event\.(?:issue\.title|issue\.body|pull_request\.title|pull_request\.body"
    r"|pull_request\.head\.ref|pull_request\.head\.label|comment\.body|review\.body|commits\[[^\]]*\]\.message"
    r"|head_commit\.message|discussion\.title|discussion\.body)\s*\}\}",
    re.I,
)
USES_RE = re.compile(r"^\s*-?\s*uses:\s*(['\"]?)([^'\"#\s]+)\1")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.I)

CODE_RULES: tuple[tuple[str, str, set[str], re.Pattern[str], str], ...] = (
    (
        "unsafe-yaml-load",
        "error",
        {".py"},
        re.compile(r"\byaml\.load\s*\((?![^)]*Loader\s*=\s*(?:yaml\.)?(?:SafeLoader|CSafeLoader))"),
        "yaml.load() without SafeLoader executes arbitrary Python objects; use yaml.safe_load()",
    ),
    (
        "unsafe-pickle-loads",
        "warning",
        {".py"},
        re.compile(r"\bpickle\.loads?\s*\("),
        "pickle.load/loads executes arbitrary code on untrusted bytes; verify trust boundary",
    ),
    (
        "non-constant-time-secret-eq",
        "error",
        {".py", ".js", ".ts", ".mjs", ".cjs"},
        re.compile(r"\b(?:hmac_digest|expected_sig|expected_hmac|webhook_sig|signature_hex)\s*(?:==|===|!=|!==)\s*\w+"),
        "Comparing cryptographic MAC/signature digests with == leaks timing; use hmac.compare_digest / crypto.timingSafeEqual",
    ),
    (
        "sql-fstring-interpolation",
        "error",
        {".py"},
        re.compile(r"\b(?:cursor|conn|db|session)\.execute\s*\(\s*f['\"](?:SELECT|INSERT|UPDATE|DELETE|DROP)\b", re.I),
        "SQL query built via Python f-string inside .execute(); bind parameters instead",
    ),
    (
        "subprocess-shell-fstring",
        "warning",
        {".py"},
        re.compile(r"\bsubprocess\.(?:run|Popen|call|check_output|check_call)\s*\(\s*f['\"].*shell\s*=\s*True"),
        "subprocess call combines f-string command interpolation with shell=True; pass an argv list with shell=False",
    ),
)


def audit_workflow_yaml(path: Path, rel: str) -> list[dict]:
    findings: list[dict] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    full = "\n".join(lines)
    has_prt = bool(re.search(r"^\s*pull_request_target\s*:", full, re.M))
    if has_prt and re.search(r"github\.event\.pull_request\.head\.(?:sha|ref)", full):
        findings.append({
            "file": rel,
            "line": 1,
            "severity": "error",
            "rule": "gha-prt-untrusted-checkout",
            "message": "Workflow triggers on pull_request_target and checks out untrusted PR head code with base secrets",
        })

    in_run_block = False
    run_indent = 0
    for lineno, line in enumerate(lines, 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if in_run_block and stripped and not stripped.startswith("#") and indent <= run_indent:
            in_run_block = False

        m_uses = USES_RE.match(line)
        if m_uses:
            ref_spec = m_uses.group(2)
            if not ref_spec.startswith(("./", "docker://")) and "@" in ref_spec:
                action_path, ref = ref_spec.rsplit("@", 1)
                owner = action_path.split("/", 1)[0].lower()
                if owner not in FIRST_PARTY_ACTION_OWNERS and not SHA40_RE.fullmatch(ref):
                    findings.append({
                        "file": rel,
                        "line": lineno,
                        "severity": "warning",
                        "rule": "gha-unpinned-action",
                        "message": f"Third-party action {ref_spec!r} is not pinned to an immutable 40-char commit SHA",
                    })

        if re.match(r"^\s*-?\s*run\s*:", line):
            in_run_block = True
            run_indent = indent
            if UNTRUSTED_GH_EXPR_RE.search(line):
                findings.append({
                    "file": rel,
                    "line": lineno,
                    "severity": "error",
                    "rule": "gha-script-injection",
                    "message": "Untrusted GitHub event field interpolated directly into shell `run:`; pass via `env:` instead",
                })
        elif in_run_block and UNTRUSTED_GH_EXPR_RE.search(line):
            findings.append({
                "file": rel,
                "line": lineno,
                "severity": "error",
                "rule": "gha-script-injection",
                "message": "Untrusted GitHub event field interpolated inside multi-line `run:` block; pass via `env:` instead",
            })
    return findings


def _strip_comments_and_docstrings_py(text: str) -> dict[int, str]:
    """Blank out comments and plain non-f string literals in-place while preserving exact Python syntax and PEP 701 f-strings."""
    import io
    import tokenize
    lines = text.splitlines()
    chars = [list(ln) for ln in lines]
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                continue
            if tok.type == tokenize.STRING and re.match(r"^[fF]", tok.string):
                continue
            (sr, sc), (er, ec) = tok.start, tok.end
            for r in range(sr, er + 1):
                if not (1 <= r <= len(chars)):
                    continue
                row = chars[r - 1]
                c_start = sc if r == sr else 0
                c_end = ec if r == er else len(row)
                for c in range(c_start, min(c_end, len(row))):
                    row[c] = " "
    except (tokenize.TokenError, IndentationError):
        return {i: ln for i, ln in enumerate(lines, 1) if not ln.lstrip().startswith("#")}
    return {i: "".join(row) for i, row in enumerate(chars, 1) if "".join(row).strip()}


def scan_repo(root: Path) -> dict:
    findings: list[dict] = []
    files_scanned = 0
    wf_dir = root / ".github" / "workflows"
    if wf_dir.is_dir():
        for wf in sorted([*wf_dir.glob("*.yml"), *wf_dir.glob("*.yaml")]):
            files_scanned += 1
            findings.extend(audit_workflow_yaml(wf, wf.relative_to(root).as_posix()))

    code_exts = {".py", ".js", ".ts", ".mjs", ".cjs"}
    self_path = Path(__file__).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        base = Path(dirpath)
        for fname in sorted(filenames):
            if fname.startswith("test_") or fname.endswith((".test.ts", ".test.js", ".test.mjs", "_test.py")):
                continue
            p = base / fname
            if p.resolve() == self_path:
                continue
            ext = p.suffix.lower()
            if ext not in code_exts:
                continue
            files_scanned += 1
            rel = p.relative_to(root).as_posix()
            text = p.read_text(encoding="utf-8", errors="replace")
            line_map = (
                _strip_comments_and_docstrings_py(text)
                if ext == ".py"
                else {i: ln for i, ln in enumerate(text.splitlines(), 1) if not ln.lstrip().startswith("//")}
            )
            for lineno, line in sorted(line_map.items()):
                for rule_id, sev, exts, pat, msg in CODE_RULES:
                    if ext in exts and pat.search(line):
                        findings.append({"file": rel, "line": lineno, "severity": sev, "rule": rule_id, "message": msg})

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "ok": errors == 0,
        "files_scanned": files_scanned,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    rep = scan_repo(Path(args.root).resolve())
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        status = "OK" if rep["ok"] and not (args.strict and rep["warnings"]) else "FAIL"
        print(f"static-sec-audit [{status}]: {rep['files_scanned']} file(s), {rep['errors']} error(s), {rep['warnings']} warning(s)")
        for f in rep["findings"]:
            print(f"  [{f['severity'].upper()}] {f['file']}:{f['line']} ({f['rule']}): {f['message']}")
    return 1 if (not rep["ok"] or (args.strict and rep["warnings"])) else 0


if __name__ == "__main__":
    sys.exit(main())
