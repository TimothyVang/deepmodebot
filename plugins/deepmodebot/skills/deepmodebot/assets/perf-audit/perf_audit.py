#!/usr/bin/env python3
"""Deterministic static audit for high-scale backend & data-structure anti-patterns.

Checks source files for high-confidence performance traps distilled from
`high-scale-server-optimization.md` and `data-structures-and-cache-optimization.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".worktrees",
    ".scratch",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
}

SCAN_EXTS = {
    ".py",
    ".go",
    ".rs",
    ".cs",
    ".fs",
    ".ts",
    ".js",
    ".java",
    ".kt",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".zig",
    ".sql",
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    ref: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    exts: tuple[str, ...]
    pattern: re.Pattern[str]
    message: str
    ref: str
    anti_pattern: re.Pattern[str] | None = None


RULES: tuple[Rule, ...] = (
    Rule(
        rule_id="PERF-GO-001",
        severity="high",
        exts=(".go",),
        pattern=re.compile(r"gin-contrib/gzip|gzip\.Gzip\("),
        message="gin-contrib/gzip allocates ~1 MB flate writer before DB wait; prefer gzhttp at write time.",
        ref="high-scale-server-optimization.md#66",
    ),
    Rule(
        rule_id="PERF-PY-001",
        severity="high",
        exts=(".py",),
        pattern=re.compile(r"statement_cache_size\s*=\s*0"),
        message="asyncpg statement_cache_size=0 forces unnamed prepared statements and re-planning unless named.",
        ref="high-scale-server-optimization.md#44",
        anti_pattern=re.compile(r"prepare\([^)]*name\s*="),
    ),
    Rule(
        rule_id="PERF-NET-001",
        severity="high",
        exts=(".cs", ".fs"),
        pattern=re.compile(r"new\s+GZipStream\s*\("),
        message="GZipStream without leaveOpen: true closes the backing MemoryStream and causes 500s under gzip.",
        ref="high-scale-server-optimization.md#67",
        anti_pattern=re.compile(r"leaveOpen\s*:\s*true|true\s*\)\s*;?"),
    ),
    Rule(
        rule_id="PERF-SQLITE-001",
        severity="high",
        exts=(".c", ".cc", ".cpp", ".rs", ".go", ".py", ".cs", ".fs", ".ts", ".js", ".sql"),
        pattern=re.compile(r"PRAGMA\s+mmap_size\s*=\s*[1-9]\d*", re.IGNORECASE),
        message="SQLite mmap_size > 0 adds WAL-index probe and MemPage re-parse overhead; prefer mmap_size=0.",
        ref="high-scale-server-optimization.md#111",
    ),
    Rule(
        rule_id="PERF-SQLITE-002",
        severity="medium",
        exts=(".c", ".cc", ".cpp", ".rs", ".go", ".py", ".cs", ".fs", ".ts", ".js", ".sql"),
        pattern=re.compile(r"PRAGMA\s+synchronous\s*=\s*FULL", re.IGNORECASE),
        message="SQLite synchronous=FULL fsyncs every commit on the loop; use synchronous=NORMAL in WAL mode.",
        ref="high-scale-server-optimization.md#111",
    ),
    Rule(
        rule_id="PERF-SQL-001",
        severity="medium",
        exts=(".sql", ".rs", ".go", ".py", ".cs", ".fs", ".ts", ".js", ".java", ".kt", ".c", ".cpp"),
        pattern=re.compile(r"\bLIMIT\s+\$\d+\b", re.IGNORECASE),
        message="Parameterized LIMIT $1 can trigger per-execution re-planning in Postgres; keep static limits literal.",
        ref="high-scale-server-optimization.md#40",
    ),
    Rule(
        rule_id="PERF-PY-002",
        severity="medium",
        exts=(".py",),
        pattern=re.compile(r"@app\.(get|post|put|delete)\("),
        message="FastAPI APIRoute Pydantic/DI wrapper adds ~40% CPU overhead on hot routes; consider Starlette Route + orjson.",
        ref="high-scale-server-optimization.md#88",
    ),
)


def iter_target_files(root: Path, explicit_files: list[str] | None) -> list[Path]:
    if explicit_files:
        out: list[Path] = []
        for raw in explicit_files:
            p = (root / raw) if not Path(raw).is_absolute() else Path(raw)
            if p.is_file() and p.suffix.lower() in SCAN_EXTS:
                out.append(p)
        return sorted(out)
    files: list[Path] = []
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file() and p.suffix.lower() in SCAN_EXTS:
            files.append(p)
    return sorted(files)


def scan_file(path: Path, root: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    ext = path.suffix.lower()
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    rel = rel.replace("\\", "/")
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule in RULES:
            if ext not in rule.exts:
                continue
            if not rule.pattern.search(line):
                continue
            if rule.anti_pattern and rule.anti_pattern.search(line):
                continue
            findings.append(
                Finding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    file=rel,
                    line=lineno,
                    message=rule.message,
                    ref=rule.ref,
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit code for high-scale performance traps.")
    parser.add_argument("--path", default=".", help="Repository or directory root to scan.")
    parser.add_argument("--files", nargs="*", help="Optional explicit file paths to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--fail-on-high", action="store_true", help="Exit 1 if any high-severity finding exists.")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    files = iter_target_files(root, args.files)
    findings: list[Finding] = []
    for f in files:
        findings.extend(scan_file(f, root))

    if args.json:
        print(json.dumps({"scanned_files": len(files), "findings": [asdict(x) for x in findings]}, indent=2))
    else:
        print(f"perf_audit: scanned {len(files)} files, {len(findings)} findings")
        for x in findings:
            print(f"[{x.severity.upper()}] {x.rule_id} {x.file}:{x.line} — {x.message} ({x.ref})")

    if args.fail_on_high and any(x.severity == "high" for x in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
