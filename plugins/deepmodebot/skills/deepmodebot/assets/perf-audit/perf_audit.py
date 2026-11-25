#!/usr/bin/env python3
"""Deterministic static audit for high-scale backend & data-structure anti-patterns.

Checks source files for high-confidence performance traps distilled from
`high-scale-server-optimization.md` and `data-structures-and-cache-optimization.md`,
plus universal backend hot-path killers (N+1 queries, await-in-loop waterfalls,
sync-in-async event-loop blocking, missing HTTP timeouts, per-request DB pools,
unbounded fan-out, and SQL OFFSET scans).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.dont_write_bytecode = True

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
    ".pytest_cache",
}

SCAN_EXTS = {
    ".py",
    ".go",
    ".rs",
    ".cs",
    ".fs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".java",
    ".kt",
    ".c",
    ".cc",
    ".cxx",
    ".cpp",
    ".h",
    ".hpp",
    ".zig",
    ".sql",
}

TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:tests?/|__tests__/|spec/|test_[^/]+|[^/]+(?:_test|\.test|\.spec)\.[^/]+$)",
    re.I,
)


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
        rule_id="PERF-DB-002",
        severity="medium",
        exts=(".sql", ".rs", ".go", ".py", ".cs", ".fs", ".ts", ".js", ".java", ".kt"),
        pattern=re.compile(r"\bSELECT\b.{0,160}\bLIMIT\s+\S+\s+OFFSET\s+(?:\$\d+|\?|\d+|:[A-Za-z_]\w*)", re.IGNORECASE),
        message="SQL OFFSET pagination scans and discards skipped rows O(N); prefer keyset/cursor pagination WHERE (col, id) < ($1, $2).",
        ref="backend-system-design.md",
    ),
    Rule(
        rule_id="PERF-PY-002",
        severity="medium",
        exts=(".py",),
        pattern=re.compile(r"@app\.(get|post|put|delete)\("),
        message="FastAPI APIRoute Pydantic/DI wrapper adds ~40% CPU overhead on hot routes; consider Starlette Route + orjson.",
        ref="high-scale-server-optimization.md#88",
    ),
    Rule(
        rule_id="PERF-CPP-001",
        severity="medium",
        exts=(".cpp", ".cc", ".cxx", ".hpp", ".h"),
        pattern=re.compile(r"\bstd::unordered_map\s*<"),
        message="std::unordered_map allocates a heap node per entry and chases pointers; prefer flat hash maps or sorted vectors on hot paths.",
        ref="data-structures-and-cache-optimization.md#11",
    ),
    Rule(
        rule_id="PERF-CPP-002",
        severity="medium",
        exts=(".cpp", ".cc", ".cxx"),
        pattern=re.compile(r"\bstd::endl\b"),
        message="std::endl forces an unbuffered stream flush every line; use '\\n' in hot logging/output paths.",
        ref="high-scale-server-optimization.md#135",
    ),
    Rule(
        rule_id="PERF-GO-002",
        severity="medium",
        exts=(".go",),
        pattern=re.compile(r"\bdb\.(?:Query|Exec|QueryRow)Context\("),
        message="database/sql *Context() spawns a watcher goroutine per query (4-30% CPU); evaluate pgx/batching on hot paths.",
        ref="high-scale-server-optimization.md#85",
    ),
    Rule(
        rule_id="PERF-NET-002",
        severity="medium",
        exts=(".cs", ".fs"),
        pattern=re.compile(r"Host=[^;]+;.*Database=", re.IGNORECASE),
        message="Npgsql connection string without NoResetOnClose=true incurs extra RESET ALL round trips per checkout.",
        ref="high-scale-server-optimization.md#45",
        anti_pattern=re.compile(r"NoResetOnClose\s*=\s*true", re.IGNORECASE),
    ),
)

PY_DB_METHODS = frozenset({
    "execute", "executemany", "fetch", "fetchrow", "fetchval",
    "find_one", "find_unique", "scalar", "scalars",
})
PY_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "request"})
PY_BLOCKING_CALLS = frozenset({
    "time.sleep",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "subprocess.check_call",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "requests.patch",
    "requests.request",
    "urllib.request.urlopen",
})
PY_POOL_CALLS = frozenset({
    "create_engine",
    "create_async_engine",
    "asyncpg.create_pool",
    "psycopg_pool.ConnectionPool",
    "psycopg_pool.AsyncConnectionPool",
})

JS_LOOP_OPEN_RE = re.compile(r"\b(?:for|while)\s*\(")
JS_ASYNC_FN_RE = re.compile(r"\basync\s+(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*\()")
JS_AWAIT_RE = re.compile(r"\bawait\s+")
JS_DB_CALL_RE = re.compile(
    r"\.\s*(?:query|execute|findUnique|findFirst|findMany|findOne|findById|updateOne|insertOne)\s*\("
)
JS_SYNC_BLOCK_RE = re.compile(
    r"\b(?:fs\.)?(?:readFileSync|writeFileSync|appendFileSync|readdirSync|statSync|execSync|execFileSync|spawnSync|pbkdf2Sync|scryptSync)\s*\("
    r"|\bbcrypt\.hashSync\s*\(|\bbcrypt\.compareSync\s*\("
)
JS_UNBOUNDED_PROMISE_ALL_RE = re.compile(r"\bPromise\.all\s*\(\s*[A-Za-z_$][\w$.]*\.map\s*\(")
JS_POOL_NEW_RE = re.compile(r"\bnew\s+(?:Pool|PrismaClient|MongoClient|Redis)\s*\(")
JS_HANDLER_RE = re.compile(
    r"(?:app|router)\s*\.\s*(?:get|post|put|delete|patch|use)\s*\("
    r"|\bexport\s+(?:default\s+)?async\s+function\s+(?:GET|POST|PUT|DELETE|PATCH|handler)\b"
)


def _call_dotted_name(node: ast.Call) -> str:
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _is_route_or_handler_fn(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        dotted = ""
        cur = target
        parts: list[str] = []
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        dotted = ".".join(reversed(parts)).lower()
        if any(seg in dotted for seg in ("route", "get", "post", "put", "delete", "patch", "websocket", "api_view")):
            return True
    return fn.name.startswith(("handle_", " endpoint_", "get_", "post_", "list_", "create_", "update_", "delete_"))


def _scan_python_ast(text: str, rel: str) -> list[Finding]:
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []

    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()

    def emit(rule_id: str, severity: str, line: int, message: str, ref: str) -> None:
        key = (rule_id, line)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(rule_id=rule_id, severity=severity, file=rel, line=line, message=message, ref=ref))

    def walk_scope(
        node: ast.AST,
        in_async: bool = False,
        in_loop: bool = False,
        in_handler: bool = False,
        has_semaphore: bool = False,
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_async = isinstance(child, ast.AsyncFunctionDef)
                child_handler = _is_route_or_handler_fn(child)
                child_sem = any(
                    (isinstance(n, ast.Name) and n.id in ("Semaphore", "BoundedSemaphore"))
                    or (isinstance(n, ast.Attribute) and n.attr in ("Semaphore", "BoundedSemaphore"))
                    for n in ast.walk(child)
                )
                walk_scope(
                    child,
                    in_async=child_async,
                    in_loop=False,
                    in_handler=child_handler,
                    has_semaphore=child_sem,
                )
                continue

            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                walk_scope(child, in_async=in_async, in_loop=True, in_handler=in_handler, has_semaphore=has_semaphore)
                continue

            if isinstance(child, ast.Await) and in_loop:
                if isinstance(child.value, ast.Call):
                    cname = _call_dotted_name(child.value)
                    leaf = cname.rsplit(".", 1)[-1]
                    if leaf not in ("sleep", "wait_closed", "drain", "aclose", "close"):
                        emit(
                            "PERF-ASYNC-001",
                            "high",
                            child.lineno,
                            "Serial await inside loop causes N+1 latency waterfall; batch IDs or gather with asyncio.Semaphore.",
                            "backend-system-design.md",
                        )

            if isinstance(child, ast.Call):
                cname = _call_dotted_name(child)
                leaf = cname.rsplit(".", 1)[-1]

                if in_async and cname in PY_BLOCKING_CALLS:
                    emit(
                        "PERF-ASYNC-002",
                        "high",
                        child.lineno,
                        f"Blocking call '{cname}()' inside async function stalls the entire event loop; use async client or asyncio.to_thread.",
                        "high-scale-server-optimization.md",
                    )

                if in_loop and leaf in PY_DB_METHODS and "." in cname:
                    prefix = cname.split(".", 1)[0].lower()
                    if prefix in {"db", "conn", "cursor", "cur", "session", "pool", "prisma", "collection", "objects", "repo"} or cname.endswith(".objects.get") or cname.endswith(".objects.filter"):
                        emit(
                            "PERF-DB-001",
                            "high",
                            child.lineno,
                            f"Database/ORM query '{cname}()' inside loop triggers N+1 round trips; batch with WHERE id = ANY($1) or IN (...).",
                            "backend-system-design.md",
                        )

                if cname.startswith(("requests.", "httpx.")) and leaf in PY_HTTP_METHODS:
                    has_timeout = any(kw.arg == "timeout" for kw in child.keywords)
                    if not has_timeout:
                        emit(
                            "PERF-HTTP-001",
                            "high",
                            child.lineno,
                            f"Outbound HTTP call '{cname}()' has no timeout=... argument and can hang workers indefinitely.",
                            "backend-infrastructure.md",
                        )

                if (in_handler or in_loop) and (cname in PY_POOL_CALLS or leaf in {"create_engine", "create_async_engine", "create_pool"}):
                    emit(
                        "PERF-POOL-001",
                        "high",
                        child.lineno,
                        f"Pool/engine '{cname}()' created inside handler or loop; initialize once at process startup and reuse.",
                        "high-scale-server-optimization.md",
                    )

                if cname.endswith("gather") and not has_semaphore:
                    for arg in child.args:
                        if isinstance(arg, ast.Starred) and isinstance(arg.value, (ast.ListComp, ast.GeneratorExp)):
                            emit(
                                "PERF-FANOUT-001",
                                "medium",
                                child.lineno,
                                "Unbounded asyncio.gather(*[...]) fan-out can exhaust DB pools and sockets; guard with asyncio.Semaphore.",
                                "backend-infrastructure.md",
                            )

            walk_scope(child, in_async=in_async, in_loop=in_loop, in_handler=in_handler, has_semaphore=has_semaphore)

    walk_scope(tree)
    return findings


def _scan_js_ts_scopes(lines: list[str], rel: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    brace_depth = 0
    loop_depths: list[int] = []
    async_depths: list[int] = []
    handler_depths: list[int] = []
    full_text = "\n".join(lines)
    has_limiter = bool(re.search(r"\bpLimit\b|\bp-limit\b|\bSemaphore\b|\b Bottleneck\b", full_text))

    def emit(rule_id: str, severity: str, line: int, message: str, ref: str) -> None:
        key = (rule_id, line)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(rule_id=rule_id, severity=severity, file=rel, line=line, message=message, ref=ref))

    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue

        in_loop = bool(loop_depths)
        in_async = bool(async_depths)
        in_handler = bool(handler_depths)

        if in_loop and JS_AWAIT_RE.search(stripped):
            emit(
                "PERF-ASYNC-001",
                "high",
                lineno,
                "Serial await inside loop causes N+1 latency waterfall; batch queries or bound concurrency with p-limit.",
                "backend-system-design.md",
            )
        if in_loop and JS_DB_CALL_RE.search(stripped):
            emit(
                "PERF-DB-001",
                "high",
                lineno,
                "Database/ORM query inside loop triggers N+1 round trips; batch with WHERE id IN / ANY($1) or DataLoader.",
                "backend-system-design.md",
            )
        if (in_async or in_handler) and JS_SYNC_BLOCK_RE.search(stripped):
            emit(
                "PERF-ASYNC-002",
                "high",
                lineno,
                "Synchronous *Sync() call inside async/request scope blocks the Node/Bun event loop for all concurrent requests.",
                "high-scale-server-optimization.md",
            )
        if (in_handler or in_loop) and JS_POOL_NEW_RE.search(stripped):
            emit(
                "PERF-POOL-001",
                "high",
                lineno,
                "Database/cache client pool instantiated inside request handler or loop; share a singleton pool across requests.",
                "high-scale-server-optimization.md",
            )
        if not has_limiter and JS_UNBOUNDED_PROMISE_ALL_RE.search(stripped):
            emit(
                "PERF-FANOUT-001",
                "medium",
                lineno,
                "Unbounded Promise.all(items.map(...)) fan-out risks exhausting DB connections/file descriptors; cap concurrency with p-limit.",
                "backend-infrastructure.md",
            )

        opens = stripped.count("{")
        closes = stripped.count("}")
        if JS_LOOP_OPEN_RE.search(stripped) and opens > 0:
            loop_depths.append(brace_depth + 1)
        if JS_ASYNC_FN_RE.search(stripped) and opens > 0:
            async_depths.append(brace_depth + 1)
        if JS_HANDLER_RE.search(stripped) and opens > 0:
            handler_depths.append(brace_depth + 1)

        brace_depth = max(0, brace_depth + opens - closes)
        while loop_depths and brace_depth < loop_depths[-1]:
            loop_depths.pop()
        while async_depths and brace_depth < async_depths[-1]:
            async_depths.pop()
        while handler_depths and brace_depth < handler_depths[-1]:
            handler_depths.pop()

    return findings


def iter_target_files(root: Path, explicit_files: list[str] | None, include_tests: bool = False) -> list[Path]:
    if explicit_files:
        out: list[Path] = []
        for raw in explicit_files:
            p = (root / raw) if not Path(raw).is_absolute() else Path(raw)
            if p.is_file() and p.suffix.lower() in SCAN_EXTS:
                out.append(p)
        return sorted(out)
    files: list[Path] = []
    for p in root.rglob("*"):
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if p.is_file() and p.suffix.lower() in SCAN_EXTS:
            rel_posix = p.relative_to(root).as_posix()
            if not include_tests and TEST_FILE_RE.search(rel_posix):
                continue
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
    lines = text.splitlines()
    findings: list[Finding] = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith(("#", "//", "--", "/*", "*", "message=")) or "re.compile(" in line:
            continue
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
    if ext == ".py":
        findings.extend(_scan_python_ast(text, rel))
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs"}:
        findings.extend(_scan_js_ts_scopes(lines, rel))
    return findings


def scan_paths(root: Path, explicit_files: list[str] | None = None) -> dict:
    resolved = root.resolve()
    files = iter_target_files(resolved, explicit_files)
    findings: list[Finding] = []
    for f in files:
        findings.extend(scan_file(f, resolved))
    return {
        "scanned_files": len(files),
        "findings": [asdict(x) for x in findings],
        "high_count": sum(1 for x in findings if x.severity == "high"),
    }


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
            print(f"[{x.severity.upper()}] {x.rule_id} {x.file}:{x.line} - {x.message} ({x.ref})")

    if args.fail_on_high and any(x.severity == "high" for x in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
