#!/usr/bin/env python3
"""Zero-token diff-only anti-slop, secret, test-theater, linter, boundary & budget CI gate.

    python -B slop_gate.py [--root <repo>] [--staged] [--files a,b] [--allow-config-change] [--no-linters] [--record-memory] [--json]

Runs deterministically on changed files/lines only (0 LLM tokens, <1s typical):
- Reuses loop.py (scan_text_slop + diff_new_slop + discover_guardrail_configs), perf_audit.py, and ui_audit.py.
- Scans added lines for secrets/keys/PEMs, unpinned Actions, unsafe sinks, workarounds, Rust .unwrap(), Go `_ = err`.
- AST-checks changed Python tests for 0-assertion/tautological test theater and new functions for god-function bloat.
- Auto-dispatches installed fast linters (ruff, shellcheck, node --check, oxlint, biome) on changed files only.
- Enforces .deepmodebot/policy.xml <boundaries> (import layer rules) and <budgets> (file byte/line ceilings).
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ASSETS_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = ASSETS_DIR.parent.parent
DEFAULT_MAX_FUNC_LINES = 120
DEFAULT_MAX_NESTING = 5

SECRET_PATTERNS = (
    ("secret-aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "Remove hardcoded AWS key; inject via OIDC or vault."),
    ("secret-github-pat", re.compile(r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})\b"), "Revoke and remove GitHub PAT; inject via env/gh auth."),
    ("secret-anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "Remove Anthropic API key; use subscription login or broker."),
    ("secret-openai-key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"), "Remove OpenAI key; use subscription login or broker."),
    ("secret-google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Remove Google API key; inject from vault."),
    ("secret-stripe-live", re.compile(r"\bsk_live_[0-9A-Za-z]{20,}\b"), "Remove live Stripe key; rotate immediately."),
    ("secret-private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"), "Remove private key material from repository."),
)

UNPINNED_ACTION_RE = re.compile(r"^\s*-?\s*uses:\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@(?:main|master)\b")
TS_CAST_SLOP_RE = re.compile(r"\bas\s+(?:any|unknown\s+as)\b")
UNSAFE_WEB_SINK_RE = re.compile(r"(?:\.innerHTML\s*=|\bdangerouslySetInnerHTML\b|\beval\s*\()")
CLIENT_ENV_SECRET_RE = re.compile(
    r"\b(?:NEXT_PUBLIC|VITE|EXPO_PUBLIC|NUXT_PUBLIC)_[A-Z0-9_]*(?:SECRET|PRIVATE_KEY|SERVICE_ROLE|DATABASE_URL|WEBHOOK_SECRET)[A-Z0-9_]*\b"
)
LLM_BROWSER_KEY_RE = re.compile(r"\bdangerouslyAllowBrowser\s*:\s*true\b")
WORKERS_LEGACY_DO_RE = re.compile(r"\bclass\s+[A-Za-z_$][\w$]*\s+implements\s+DurableObject\b")
WORKERS_CTX_DESTRUCTURE_RE = re.compile(r"\b(?:const|let|var)\s*\{\s*waitUntil\b[^}]*\}\s*=\s*ctx\b")
RUST_UNWRAP_RE = re.compile(r"""(?<!['"`])\.unwrap\s*\(\s*\)(?!['"`])""")
GO_IGNORED_ERR_RE = re.compile(r"\b_\s*=\s*err\b")
JS_IMPORT_RE = re.compile(r"""(?:import\s+(?:[^'"]+?\s+from\s+)?|require\s*\(\s*)['"]([^'"]+)['"]""")

CODE_EXTS = frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".rs", ".go", ".sh", ".css", ".html", ".svelte"})
UI_EXTS = frozenset({".html", ".htm", ".css", ".scss", ".jsx", ".tsx", ".vue", ".svelte"})
TEST_FILE_RE = re.compile(r"(?:^|/)(?:tests?/|spec/|__tests__/)|(?:^|/)(?:test_[^/]+|[^/]+(?:_test|\.test|\.spec))\.[^/]+$", re.I)
GUARDRAIL_EXTRA = (".deepmodebot/ci.yml", ".deepmodebot/policy.xml", ".github/dependabot.yml")


def _load_mod(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, creationflags=NO_WINDOW,
    )


def _changed_files(root: Path, staged: bool, explicit_files: list[str] | None) -> list[str]:
    if explicit_files:
        return sorted({f.replace("\\", "/").lstrip("./") for f in explicit_files if f.strip()})
    has_head = _git(root, "rev-parse", "--verify", "HEAD").returncode == 0
    found: set[str] = set()
    if staged:
        r = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
        if r.returncode == 0:
            found.update(l.strip() for l in r.stdout.splitlines() if l.strip())
    else:
        if has_head:
            r = _git(root, "diff", "HEAD", "--name-only", "--diff-filter=ACMR")
            if r.returncode == 0:
                found.update(l.strip() for l in r.stdout.splitlines() if l.strip())
        else:
            r = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
            if r.returncode == 0:
                found.update(l.strip() for l in r.stdout.splitlines() if l.strip())
        u = _git(root, "ls-files", "--others", "--exclude-standard")
        if u.returncode == 0:
            found.update(l.strip() for l in u.stdout.splitlines() if l.strip())
    return sorted(found)


def _added_lines_for_file(root: Path, rel: str, staged: bool) -> dict[int, str]:
    full = root / rel
    if not full.is_file() or full.is_symlink():
        return {}
    has_head = _git(root, "rev-parse", "--verify", "HEAD").returncode == 0
    if not has_head and not staged:
        return {i: l for i, l in enumerate(full.read_text(encoding="utf-8", errors="replace").splitlines(), 1)}
    tracked = _git(root, "ls-files", "--error-unmatch", "--", rel).returncode == 0
    if not tracked and not staged:
        return {i: l for i, l in enumerate(full.read_text(encoding="utf-8", errors="replace").splitlines(), 1)}
    cmd = ["diff", "--cached", "-U0", "--", rel] if staged else ["diff", "HEAD", "-U0", "--", rel]
    diff = _git(root, *cmd)
    if diff.returncode != 0:
        return {}
    added: dict[int, str] = {}
    cur_line = 0
    for raw in diff.stdout.splitlines():
        if raw.startswith("@@ "):
            m = re.search(r"\+(\d+)", raw)
            if m:
                cur_line = int(m.group(1))
        elif raw.startswith("+") and not raw.startswith("+++"):
            added[cur_line] = raw[1:]
            cur_line += 1
    return added


def _read_text_safe(root: Path, rel: str) -> str | None:
    p = root / rel
    if p.is_symlink() or not p.is_file():
        return None
    if not p.resolve().is_relative_to(root.resolve()):
        return None
    if p.stat().st_size > 1_048_576:
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _max_ast_nesting(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        inc = 1 if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)) else 0
        sub = _max_ast_nesting(child, depth + inc)
        if sub > best:
            best = sub
    return best


def _check_python_ast(rel: str, text: str, added_lines: dict[int, str], max_func_lines: int, max_nesting: int) -> list[dict]:
    findings: list[dict] = []
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return [{"severity": "P0", "rule": "py-syntax", "file": rel, "line": exc.lineno or 1,
                 "message": f"SyntaxError: {exc.msg}", "fix": "Fix Python syntax before continuing."}]

    is_test = bool(TEST_FILE_RE.search(rel))
    added_set = set(added_lines.keys())

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            touched = any(start <= ln <= end for ln in added_set)
            if not touched:
                continue
            if is_test and node.name.startswith("test_"):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                if not body or all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis) for s in body):
                    findings.append({"severity": "P1", "rule": "test-theater-empty", "file": rel, "line": start,
                                     "message": f"Empty test `{node.name}` proves nothing.",
                                     "fix": "Assert real observable behavior or delete the placeholder test."})
                    continue
                has_oracle = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        has_oracle = True
                        if isinstance(sub.test, ast.Constant) and sub.test.value is True:
                            findings.append({"severity": "P1", "rule": "test-theater-tautology", "file": rel, "line": sub.lineno,
                                             "message": f"`assert True` in `{node.name}` is a tautology.",
                                             "fix": "Assert a real output/state invariant that fails if the fix is reverted."})
                    elif isinstance(sub, ast.Call):
                        fn = sub.func
                        fname = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                        if fname.startswith("assert") or fname in ("fail", "raises", "verify", "check"):
                            has_oracle = True
                            if fname == "assertEqual" and len(sub.args) >= 2 and ast.dump(sub.args[0]) == ast.dump(sub.args[1]):
                                findings.append({"severity": "P1", "rule": "test-theater-tautology", "file": rel, "line": sub.lineno,
                                                 "message": f"`assertEqual(x, x)` in `{node.name}` always passes.",
                                                 "fix": "Compare actual computed output against expected value."})
                if not has_oracle:
                    findings.append({"severity": "P1", "rule": "test-theater-no-assert", "file": rel, "line": start,
                                     "message": f"Test `{node.name}` has zero assertions.",
                                     "fix": "Add concrete behavioral assertions or delete the dead test."})
            elif not is_test and start in added_set:
                span = end - start + 1
                if span > max_func_lines:
                    findings.append({"severity": "P2", "rule": "complexity-god-func", "file": rel, "line": start,
                                     "message": f"New function `{node.name}` is {span} lines (max {max_func_lines}).",
                                     "fix": "Split into cohesive single-responsibility helpers."})
                nest = _max_ast_nesting(node)
                if nest > max_nesting:
                    findings.append({"severity": "P2", "rule": "complexity-nesting", "file": rel, "line": start,
                                     "message": f"New function `{node.name}` nesting depth is {nest} (max {max_nesting}).",
                                     "fix": "Use guard clauses/early returns or extract inner loop."})

        if not is_test and isinstance(node, ast.Call) and node.lineno in added_set:
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "run" and isinstance(fn.value, ast.Name) and fn.value.id == "subprocess":
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                if not has_timeout:
                    findings.append({"severity": "P1", "rule": "safety-subprocess-timeout", "file": rel, "line": node.lineno,
                                     "message": "`subprocess.run()` called without `timeout=`.",
                                     "fix": "Pass an explicit `timeout=` bound so child commands cannot hang forever."})

    return findings


def _check_secrets_and_patterns(rel: str, added_lines: dict[int, str], full_text: str) -> list[dict]:
    findings: list[dict] = []
    ext = Path(rel).suffix.lower()
    is_test = bool(TEST_FILE_RE.search(rel))
    rs_cfg_test_line = None
    if ext == ".rs":
        for idx, fl in enumerate(full_text.splitlines(), 1):
            if fl.strip().startswith("#[cfg(test)]"):
                rs_cfg_test_line = idx
                break

    for ln, line in sorted(added_lines.items()):
        in_test_ctx = is_test or (rs_cfg_test_line is not None and ln >= rs_cfg_test_line)
        for rule_id, pat, fix in SECRET_PATTERNS:
            if rule_id == "secret-private-key" and in_test_ctx and ("compile(" in line or 'r"' in line or "r'" in line or '"-----BEGIN' in line or "'-----BEGIN" in line):
                continue
            if pat.search(line):
                findings.append({"severity": "P0", "rule": rule_id, "file": rel, "line": ln,
                                 "message": f"Potential hardcoded secret matched `{rule_id}`.", "fix": fix})
        if rel.startswith(".github/workflows/") and ext in (".yml", ".yaml") and UNPINNED_ACTION_RE.search(line):
            findings.append({"severity": "P1", "rule": "supply-chain-unpinned-action", "file": rel, "line": ln,
                             "message": "GitHub Action pinned to mutable `@main`/`@master` ref.",
                             "fix": "Pin to a full 40-char commit SHA or immutable tag."})
        if not in_test_ctx and ext in (".ts", ".tsx") and TS_CAST_SLOP_RE.search(line):
            findings.append({"severity": "P1", "rule": "ts-unsafe-cast", "file": rel, "line": ln,
                             "message": "Unsafe `as any` / `as unknown as` type escape.",
                             "fix": "Narrow with a proper type guard or schema parser."})
        if not in_test_ctx and CLIENT_ENV_SECRET_RE.search(line):
            findings.append({"severity": "P0", "rule": "client-env-secret", "file": rel, "line": ln,
                             "message": "Client-exposed env prefix (`NEXT_PUBLIC_`/`VITE_`/`EXPO_PUBLIC_`/`NUXT_PUBLIC_`) names a secret/private/DB credential.",
                             "fix": "Keep secrets in server-only env vars and access them behind a server route or Action."})
        if not in_test_ctx and ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".svelte", ".vue") and LLM_BROWSER_KEY_RE.search(line):
            findings.append({"severity": "P0", "rule": "llm-browser-key-exposure", "file": rel, "line": ln,
                             "message": "`dangerouslyAllowBrowser: true` exposes provider API keys in client bundles.",
                             "fix": "Move LLM SDK calls behind a server endpoint or Durable Object / Edge route."})
        if not in_test_ctx and ext in (".js", ".mjs", ".ts", ".tsx") and WORKERS_LEGACY_DO_RE.search(line):
            findings.append({"severity": "P1", "rule": "workers-legacy-implements-do", "file": rel, "line": ln,
                             "message": "Legacy `implements DurableObject` omits `this.ctx` and `this.env` bindings.",
                             "fix": "Import `DurableObject` from `cloudflare:workers` and use `extends DurableObject<Env>`."})
        if not in_test_ctx and ext in (".js", ".mjs", ".ts", ".tsx") and WORKERS_CTX_DESTRUCTURE_RE.search(line):
            findings.append({"severity": "P1", "rule": "workers-ctx-destructure", "file": rel, "line": ln,
                             "message": "Destructuring `const { waitUntil } = ctx` loses `ExecutionContext` `this` binding and throws `Illegal invocation`.",
                             "fix": "Call `ctx.waitUntil(...)` directly on `ctx`."})
        if not in_test_ctx and ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html") and UNSAFE_WEB_SINK_RE.search(line):
            findings.append({"severity": "P1", "rule": "security-unsafe-sink", "file": rel, "line": ln,
                             "message": "Unsafe dynamic sink (`eval`/`innerHTML`/`dangerouslySetInnerHTML`).",
                             "fix": "Use safe DOM nodes (`textContent`) or sanitized renderer."})
        if not in_test_ctx and ext == ".rs" and RUST_UNWRAP_RE.search(line):
            findings.append({"severity": "P1", "rule": "rust-prod-unwrap", "file": rel, "line": ln,
                             "message": "`.unwrap()` in non-test Rust code panics on unexpected input.",
                             "fix": "Propagate with `?` or handle error explicitly."})
        if not is_test and ext == ".go" and GO_IGNORED_ERR_RE.search(line):
            findings.append({"severity": "P1", "rule": "go-ignored-err", "file": rel, "line": ln,
                             "message": "Swallowed Go error (`_ = err`).",
                             "fix": "Check and return or explicitly handle `err`."})

    if rel == ".github/dependabot.yml" and "cooldown:" not in full_text:
        findings.append({"severity": "P2", "rule": "supply-chain-dependabot-cooldown", "file": rel, "line": 1,
                         "message": "`.github/dependabot.yml` has no `cooldown:` window.",
                         "fix": "Add `cooldown: { default-days: 7 }` to reduce zero-day supply-chain exposure."})
    return findings


def _check_policy_xml(root: Path, changed: list[str]) -> list[dict]:
    policy_path = root / ".deepmodebot" / "policy.xml"
    if not policy_path.is_file() or policy_path.is_symlink():
        return []
    findings: list[dict] = []
    try:
        xml_root = ET.fromstring(policy_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        return [{"severity": "P0", "rule": "policy-xml-invalid", "file": ".deepmodebot/policy.xml", "line": 1,
                 "message": f"Invalid policy.xml: {exc}", "fix": "Fix XML syntax in .deepmodebot/policy.xml."}]

    for b_el in xml_root.findall("./budgets/file"):
        rel = (b_el.attrib.get("path") or "").strip()
        if not rel:
            continue
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        raw = p.read_bytes()
        max_bytes = int(b_el.attrib["max-bytes"]) if "max-bytes" in b_el.attrib else None
        max_lines = int(b_el.attrib["max-lines"]) if "max-lines" in b_el.attrib else None
        if max_bytes is not None and len(raw) > max_bytes:
            findings.append({"severity": "P1", "rule": "budget-max-bytes", "file": rel, "line": 1,
                             "message": f"File size {len(raw)} B exceeds policy budget {max_bytes} B.",
                             "fix": "Trim bloat or progressively disclose reference detail into a sibling file."})
        if max_lines is not None:
            lcount = len(raw.decode("utf-8", errors="replace").splitlines())
            if lcount > max_lines:
                findings.append({"severity": "P1", "rule": "budget-max-lines", "file": rel, "line": 1,
                                 "message": f"File length {lcount} lines exceeds policy budget {max_lines} lines.",
                                 "fix": "Move non-essential prose out to referenced docs."})

    forbid_rules = [
        (el.attrib.get("from", ""), el.attrib.get("to", ""), el.attrib.get("reason", "forbidden layer import"))
        for el in xml_root.findall("./boundaries/forbid")
        if el.attrib.get("from") and el.attrib.get("to")
    ]
    if forbid_rules:
        for rel in changed:
            text = _read_text_safe(root, rel)
            if text is None:
                continue
            ext = Path(rel).suffix.lower()
            imports: list[tuple[int, str]] = []
            if ext == ".py":
                try:
                    tree = ast.parse(text, filename=rel)
                    for n in ast.walk(tree):
                        if isinstance(n, ast.Import):
                            for a in n.names:
                                imports.append((n.lineno, a.name.replace(".", "/")))
                        elif isinstance(n, ast.ImportFrom) and n.module:
                            imports.append((n.lineno, n.module.replace(".", "/")))
                except SyntaxError:
                    pass
            elif ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
                for idx, line in enumerate(text.splitlines(), 1):
                    for m in JS_IMPORT_RE.finditer(line):
                        imports.append((idx, m.group(1)))
            for from_pat, to_pat, reason in forbid_rules:
                if not fnmatch.fnmatch(rel, from_pat):
                    continue
                for ln, imp in imports:
                    norm_imp = imp.lstrip("./")
                    if fnmatch.fnmatch(norm_imp, to_pat) or fnmatch.fnmatch(imp, to_pat):
                        findings.append({"severity": "P0", "rule": "boundary-violation", "file": rel, "line": ln,
                                         "message": f"Forbidden import `{imp}` from `{rel}` ({reason}).",
                                         "fix": f"Invert dependency or route through an allowed interface outside `{to_pat}`."})
    return findings


def _run_polyglot_linters(root: Path, changed: list[str]) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    ran: list[str] = []
    py_files = [f for f in changed if f.endswith(".py") and (root / f).is_file()]
    js_files = [f for f in changed if Path(f).suffix.lower() in (".js", ".mjs", ".cjs") and (root / f).is_file()]
    sh_files = [f for f in changed if f.endswith(".sh") and (root / f).is_file()]

    ruff = shutil.which("ruff")
    if ruff and py_files:
        ran.append("ruff")
        r = subprocess.run(
            [ruff, "check", "--no-cache", "--select", "E9,F63,F7,F82,F401", "--output-format", "json", *py_files],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=NO_WINDOW,
        )
        if r.returncode != 0:
            try:
                items = json.loads(r.stdout or "[]")
                for it in items[:20]:
                    loc = it.get("location") or {}
                    fname = Path(it.get("filename", "")).resolve().relative_to(root.resolve()).as_posix() if it.get("filename") else "ruff"
                    findings.append({"severity": "P1", "rule": f"ruff-{it.get('code', 'ERR')}", "file": fname,
                                     "line": int(loc.get("row") or 1), "message": it.get("message", "ruff error"),
                                     "fix": "Fix the ruff diagnostic on the changed Python file."})
            except (ValueError, OSError):
                findings.append({"severity": "P1", "rule": "ruff", "file": py_files[0], "line": 1,
                                 "message": (r.stdout + r.stderr).strip()[-240:], "fix": "Run `ruff check` and fix errors."})

    node = shutil.which("node")
    if node and js_files:
        ran.append("node-check")
        for jf in js_files:
            r = subprocess.run(
                [node, "--check", jf], cwd=str(root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15, creationflags=NO_WINDOW,
            )
            if r.returncode != 0:
                findings.append({"severity": "P0", "rule": "node-syntax", "file": jf, "line": 1,
                                 "message": (r.stderr or r.stdout).strip().splitlines()[-1][:200],
                                 "fix": "Fix JS/ESM syntax error."})

    shellcheck = shutil.which("shellcheck")
    if shellcheck and sh_files:
        ran.append("shellcheck")
        r = subprocess.run(
            [shellcheck, "-S", "error", "-f", "json", *sh_files],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=NO_WINDOW,
        )
        if r.returncode != 0:
            try:
                for it in json.loads(r.stdout or "[]")[:15]:
                    findings.append({"severity": "P1", "rule": f"SC{it.get('code', '')}", "file": it.get("file", sh_files[0]),
                                     "line": int(it.get("line") or 1), "message": it.get("message", "shellcheck error"),
                                     "fix": "Fix the shellcheck error."})
            except ValueError:
                pass

    return findings, ran


def _record_gotcha_memory(root: Path, findings: list[dict]) -> None:
    mem_path = ASSETS_DIR / "memory" / "project_memory.py"
    if not mem_path.is_file() or not findings:
        return
    try:
        pm = _load_mod("dmb_slop_pm", mem_path)
        rules = sorted({f["rule"] for f in findings})[:6]
        sample = findings[0]
        pm.put_memory(
            root,
            key=f"slop-gotcha:{rules[0]}",
            kind="gotcha",
            priority=1,
            tags="slop-gate,ci",
            source=f"{sample['file']}:{sample['line']}",
            content=f"Slop gate blocked {len(findings)} issue(s) ({', '.join(rules)}): {sample['message']} -> {sample['fix']}",
        )
    except (OSError, ImportError, ValueError) as exc:
        print(f"warning: slop memory record skipped: {exc}", file=sys.stderr)

def run_slop_gate(
    root: Path,
    *,
    staged: bool = False,
    explicit_files: list[str] | None = None,
    allow_config_change: bool = False,
    run_linters: bool = True,
    record_memory: bool = False,
    max_func_lines: int = DEFAULT_MAX_FUNC_LINES,
    max_nesting: int = DEFAULT_MAX_NESTING,
) -> dict:
    resolved_root = root.resolve()
    changed = _changed_files(resolved_root, staged=staged, explicit_files=explicit_files)
    findings: list[dict] = []

    loop_mod = _load_mod("dmb_loop_slop", ASSETS_DIR / "loop" / "loop.py")
    guardrails = set(loop_mod.discover_guardrail_configs(str(resolved_root))) | set(GUARDRAIL_EXTRA)

    if not allow_config_change:
        for rel in changed:
            if rel in guardrails or Path(rel).name in guardrails:
                findings.append({"severity": "P0", "rule": "config-tamper-lock", "file": rel, "line": 1,
                                 "message": f"Guardrail config `{rel}` modified without explicit authorization.",
                                 "fix": "Revert guardrail weakening or re-run with `--allow-config-change` when intentional."})

    has_head = _git(resolved_root, "rev-parse", "--verify", "HEAD").returncode == 0
    for rel in changed:
        text = _read_text_safe(resolved_root, rel)
        if text is None:
            continue
        added = _added_lines_for_file(resolved_root, rel, staged=staged)
        if not added and explicit_files:
            added = {i: l for i, l in enumerate(text.splitlines(), 1)}

        cur_slop = loop_mod.scan_text_slop(rel, text)
        if cur_slop:
            base_findings = []
            if has_head:
                blob = _git(resolved_root, "show", f"HEAD:{rel}")
                if blob.returncode == 0:
                    base_findings = loop_mod.scan_text_slop(rel, blob.stdout)
            new_slop = loop_mod.diff_new_slop(cur_slop, loop_mod.slop_counts(base_findings))
            for _, ln, rule, _, msg in new_slop:
                findings.append({"severity": "P1", "rule": rule, "file": rel, "line": ln,
                                 "message": msg.split(": ", 1)[-1], "fix": "Fix the underlying issue instead of suppressing/stubbing."})

        findings.extend(_check_secrets_and_patterns(rel, added, text))

        if rel.endswith(".py"):
            findings.extend(_check_python_ast(rel, text, added, max_func_lines=max_func_lines, max_nesting=max_nesting))

    perf_path = ASSETS_DIR / "perf-audit" / "perf_audit.py"
    code_changed = [f for f in changed if Path(f).suffix.lower() in CODE_EXTS and not TEST_FILE_RE.search(f) and (resolved_root / f).is_file()]
    if perf_path.is_file() and code_changed:
        pa = _load_mod("dmb_perf_audit", perf_path)
        for rel in code_changed:
            for pf in pa.scan_file(resolved_root / rel, resolved_root):
                if getattr(pf, "severity", "") == "high":
                    findings.append({"severity": "P1", "rule": pf.rule_id, "file": rel, "line": pf.line,
                                     "message": pf.message, "fix": "Batch DB/async calls or move sync I/O off the hot loop."})

    ui_path = SKILLS_DIR / "frontend-ui" / "scripts" / "ui_audit.py"
    ui_changed = [f for f in changed if Path(f).suffix.lower() in UI_EXTS and (resolved_root / f).is_file()]
    if ui_path.is_file() and ui_changed:
        ua = _load_mod("dmb_ui_audit", ui_path)
        for rel in ui_changed:
            txt = _read_text_safe(resolved_root, rel)
            if txt is None:
                continue
            for uf in ua.audit_source(txt, rel, Path(rel).suffix.lower()):
                if uf["severity"] in ("P0", "P1"):
                    findings.append({"severity": uf["severity"], "rule": uf["rule"], "file": rel, "line": uf["line"],
                                     "message": uf["message"], "fix": "Fix UI token/a11y/motion violation per frontend-ui."})

    linters_ran: list[str] = []
    if run_linters and changed:
        l_findings, linters_ran = _run_polyglot_linters(resolved_root, changed)
        findings.extend(l_findings)

    findings.extend(_check_policy_xml(resolved_root, changed))

    counts = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    ok = counts["P0"] == 0 and counts["P1"] == 0

    if not ok and record_memory:
        _record_gotcha_memory(resolved_root, findings)

    return {
        "ok": ok,
        "root": str(resolved_root),
        "staged": staged,
        "files_checked": len(changed),
        "linters_ran": linters_ran,
        "counts": counts,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Zero-token diff-only anti-slop, secret, linter, boundary & budget CI gate.")
    p.add_argument("--root", default=".")
    p.add_argument("--staged", action="store_true", help="Scan staged git changes only (for pre-commit hooks).")
    p.add_argument("--files", default="", help="Optional comma-separated repo-relative file list.")
    p.add_argument("--allow-config-change", action="store_true", help="Allow edits to guardrail configs in this run.")
    p.add_argument("--no-linters", action="store_true", help="Skip external PATH linters (ruff/shellcheck/node).")
    p.add_argument("--record-memory", action="store_true", help="Record failing rules as P1 gotchas in deepmode-memory.db.")
    p.add_argument("--max-func-lines", type=int, default=DEFAULT_MAX_FUNC_LINES)
    p.add_argument("--max-nesting", type=int, default=DEFAULT_MAX_NESTING)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    explicit = [x.strip() for x in args.files.split(",") if x.strip()] if args.files else None
    res = run_slop_gate(
        Path(args.root).resolve(),
        staged=args.staged,
        explicit_files=explicit,
        allow_config_change=args.allow_config_change,
        run_linters=not args.no_linters,
        record_memory=args.record_memory,
        max_func_lines=args.max_func_lines,
        max_nesting=args.max_nesting,
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        c = res["counts"]
        status = "OK" if res["ok"] else "BLOCKED"
        print(f"slop-gate [{status}]: {res['files_checked']} file(s), linters={res['linters_ran']} — P0:{c['P0']} P1:{c['P1']} P2:{c['P2']}")
        for f in res["findings"]:
            print(f"  {f['file']}:{f['line']} [{f['severity']}:{f['rule']}] {f['message']} -> {f['fix']}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
