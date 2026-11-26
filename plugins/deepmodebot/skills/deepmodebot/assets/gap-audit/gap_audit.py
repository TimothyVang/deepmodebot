#!/usr/bin/env python3
"""Deterministic repo gap/drift scanner and adversarial research ledger verifier for deepmodebot.

    python -B gap_audit.py [scan] [--root <repo>] [--fail-on-p1] [--json]
    python -B gap_audit.py init-research --root <repo> --slug <slug> --question <q> [--sources a,b] [--force] [--json]
    python -B gap_audit.py record-claim --dir <dir> --id <id> --claim <text> --evidence-tier <tier> --primary-receipt <ref> --disconfirmation-probe <probe> --disconfirmation-result <survived|qualified|refuted> [--caveat <text>] [--json]
    python -B gap_audit.py record-gap --dir <dir> --id <id> --capability <text> --source-ref <ref> --repo-state <missing|partial|stubbed|divergent|parity> --repo-evidence <ref> --priority <P0|P1|P2> --leverage <text> [--json]
    python -B gap_audit.py verify-research --dir <dir> [--strict] [--require-gap-matrix] [--render <out.md>] [--json]
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

SKIP_DIRS = frozenset({
    ".git", ".scratch", ".worktrees", "__pycache__", "node_modules",
    ".venv", "venv", "target", "dist", "build", ".next", ".pytest_cache", ".lake",
})

TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?/|spec/|__tests__/|evals/|corpus/|fixtures/)"
    r"|(?:^|/)(?:test_[^/]+|[^/]+(?:_test|\.test|\.spec)\.[^/]+)$",
    re.I,
)

DOC_SKIP_PREFIXES = ("docs/evidence/", "docs/research/", "evals/", "trending/")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JS_EXTS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})
SCAN_TEXT_EXTS = frozenset({
    ".md", ".py", ".mjs", ".cjs", ".js", ".ts", ".tsx", ".jsx",
    ".sh", ".rs", ".go", ".json", ".yml", ".yaml", ".toml",
})

EVIDENCE_TIERS = ("code-verified", "spec-rfc", "measured", "docs-only", "unverified")
DISCONFIRM_RESULTS = ("survived", "qualified", "refuted")
REPO_STATES = ("missing", "partial", "stubbed", "divergent", "parity")
PRIORITIES = ("P0", "P1", "P2")

UNIVERSAL_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:100%|always\s+works|never\s+fails|zero\s+(?:bugs|errors|failures|gaps)"
    r"|completely\s+bug[- ]free|supports?\s+all|handles?\s+every|guaranteed\s+to)(?![A-Za-z0-9_])",
    re.I,
)

ADVERSARIAL_SIGNAL_RE = re.compile(
    r"\b(?:issues?|bugs?|changelog|breaking|cve|advisor(?:y|ies)|source|code|line|repro|cmd:|test|benchmark"
    r"|edge|limit|timeout|race|contradict|mismatch|falsif|counterexample|fail|regression)\b",
    re.I,
)

TRIVIAL_PROBE_RE = re.compile(r"^(?:ok|yes|checked|done|none|n/a|na|verified|looks\s+good|true)\.?$", re.I)

ADD_ARG_CALL_RE = re.compile(r"\.add_argument\s*\((.*?)\)", re.S)
LONG_FLAG_LIT_RE = re.compile(r"""['"](--[a-zA-Z0-9][a-zA-Z0-9-]*)['"]""")
SCRIPT_INVOCATION_RE = re.compile(r"""(?:^|[\s"'`/\\])([a-z0-9_]+\.py)\b([^`|;&\n)]*)""")
PASSING_FLAG_RE = re.compile(r"""(?<=\s)(--[a-z][a-z0-9-]*)(?=\s|$|=|`|"|')""")

DMB_GATE_DOC_RE = re.compile(r"""(?<![/.\w-])(?:dmb-gate|deepmodebot\s+gate)\s+([a-z][a-z0-9|-]*)""")
DMB_NET_DOC_RE = re.compile(r"""(?<![/.\w-])dmb-net\s+([a-z][a-z0-9|-]*)""")

REPLACES_COMMENT_RE = re.compile(
    r"""(?://|#)\s*[^\n]*?\breplaces\s+([A-Za-z0-9_./-]+\.(?:py|rs|go|ts|js|mjs|sh))\b""",
    re.I,
)

JS_EMPTY_CATCH_RE = re.compile(
    r"""\.catch\s*\(\s*(?:\(\s*[A-Za-z0-9_$]*\s*\)|[A-Za-z0-9_$]+|function\s*\(\s*[A-Za-z0-9_$]*\s*\))\s*(?:=>)?\s*\{\s*\}\s*\)"""
)
JS_STUB_THROW_RE = re.compile(
    r"""\bthrow\s+new\s+Error\s*\(\s*['"](?:not\s+implemented|todo\b|unimplemented)[^'"]*['"]\s*\)""",
    re.I,
)
RUST_STUB_MACRO_RE = re.compile(r"""(?<![A-Za-z0-9_])(?:todo|unimplemented)!\s*\(""")

UI_RULE_EQUIV = {
    "ui-100vw-overflow": "no-100vw-overflow",
    "ui-sticky-overflow-x-hidden": "sticky-overflow-x-hidden",
    "ui-circular-checkbox": "checkbox-not-circular",
    "ui-ease-in": "no-ease-in-ui",
    "ui-fake-live-pulse": "no-fake-live-pulse",
    "ui-heavy-rgba-shadow": "oklch-ambient-shadow",
    "ui-icon-button-unlabeled": "icon-button-label",
    "ui-img-missing-alt": "img-alt",
    "ui-layout-transition": "no-layout-transition",
    "ui-missing-focus-visible": "focus-visible",
    "ui-missing-html-lang": "html-lang",
    "ui-missing-reduced-motion": "reduced-motion",
    "ui-missing-viewport": "meta-viewport",
    "ui-no-paste-block": "no-paste-block",
    "ui-no-zoom-disable": "no-zoom-disable",
    "ui-pure-black-surface": "no-pure-black-surface",
    "ui-raw-hex-without-tokens": "semantic-color-tokens",
    "ui-scale-zero": "no-scale-zero-entry",
    "ui-transition-all": "no-transition-all",
}


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
    safe_root = reject_unsafe_root(root)
    if target.is_symlink():
        raise SystemExit(f"refusing symlink path: {target}")
    resolved = target.resolve()
    try:
        resolved.relative_to(safe_root)
    except ValueError as exc:
        raise SystemExit(f"path escapes project root ({safe_root}): {target}") from exc
    return resolved


def scrub_c_like_line(line: str, keep_string_contents: bool = False) -> str:
    out: list[str] = []
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                out.append(line[i : i + 2] if keep_string_contents else "  ")
                i += 2
                continue
            if ch == quote:
                out.append(ch)
                quote = None
            else:
                out.append(ch if keep_string_contents else " ")
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if ch == "/" and i + 1 < n and line[i + 1] == "*":
            end = line.find("*/", i + 2)
            if end < 0:
                break
            out.append(" " * (end + 2 - i))
            i = end + 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _is_pass_or_ellipsis(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def _is_not_implemented_raise(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Raise) or stmt.exc is None:
        return False
    exc = stmt.exc
    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
        return True
    if isinstance(exc, ast.Call):
        fn = exc.func
        if isinstance(fn, ast.Name) and fn.id == "NotImplementedError":
            return True
    return False


def _is_broad_except(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"):
        return True
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in ("Exception", "BaseException")
            for elt in handler.type.elts
        )
    return False


def _scan_python_ast_gaps(rel: str, text: str) -> list[dict]:
    findings: list[dict] = []
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return findings

    abstract_classes: set[int] = set()
    parent_class: dict[int, ast.ClassDef] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    base_names.append(b.id)
                elif isinstance(b, ast.Attribute):
                    base_names.append(b.attr)
            if any(bn in ("ABC", "Protocol") for bn in base_names):
                abstract_classes.add(id(node))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parent_class[id(child)] = node

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            if len(node.body) == 1 and _is_pass_or_ellipsis(node.body[0]):
                findings.append({
                    "severity": "P1",
                    "rule": "swallowed-exception",
                    "file": rel,
                    "line": node.lineno,
                    "message": "Bare `except: pass` silently swallows all errors including KeyboardInterrupt/SystemExit.",
                    "fix": "Catch a narrow exception type and handle, log, or re-raise it.",
                })

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cls = parent_class.get(id(node))
            in_abstract = cls is not None and id(cls) in abstract_classes
            decs = []
            for d in node.decorator_list:
                if isinstance(d, ast.Name):
                    decs.append(d.id)
                elif isinstance(d, ast.Attribute):
                    decs.append(d.attr)
            is_abstract_or_overload = in_abstract or any(
                "abstract" in d or d == "overload" for d in decs
            )
            is_exempt_name = (
                (node.name.startswith("__") and node.name.endswith("__"))
                or node.name in ("log_message", "noop", "_noop")
            )
            body = _strip_docstring(node.body)
            if not is_abstract_or_overload and not is_exempt_name:
                if len(body) == 1 and _is_pass_or_ellipsis(body[0]):
                    findings.append({
                        "severity": "P1",
                        "rule": "hollow-stub-body",
                        "file": rel,
                        "line": node.lineno,
                        "message": f"Function `{node.name}` has a hollow no-op body (`pass`/`...`).",
                        "fix": "Implement real behavior, mark `@abstractmethod` on a Protocol/ABC, or delete dead scaffolding.",
                    })
                elif len(body) == 1 and _is_not_implemented_raise(body[0]):
                    findings.append({
                        "severity": "P1",
                        "rule": "hollow-stub-body",
                        "file": rel,
                        "line": node.lineno,
                        "message": f"Function `{node.name}` raises `NotImplementedError` outside an ABC/Protocol.",
                        "fix": "Implement the function or move the interface contract onto an explicit `ABC`/`Protocol`.",
                    })

            if len(body) == 1 and isinstance(body[0], ast.Try):
                try_stmt = body[0]
                if (
                    not try_stmt.orelse
                    and not try_stmt.finalbody
                    and try_stmt.handlers
                    and all(
                        _is_broad_except(h)
                        and h.type is not None
                        and len(h.body) == 1
                        and _is_pass_or_ellipsis(h.body[0])
                        for h in try_stmt.handlers
                    )
                ):
                    findings.append({
                        "severity": "P1",
                        "rule": "swallowed-exception",
                        "file": rel,
                        "line": try_stmt.handlers[0].lineno,
                        "message": f"Function `{node.name}` wraps its entire body in broad `except Exception: pass`.",
                        "fix": "Catch narrow expected errors or surface/return structured failure state.",
                    })
    return findings


def _discover_cli_subcommands(root: Path) -> tuple[set[str], set[str]]:
    gate_subs: set[str] = set()
    net_subs: set[str] = set()

    main_rs = root / "native" / "dmb-gate" / "src" / "main.rs"
    if main_rs.is_file():
        txt = main_rs.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"([a-z][a-z0-9-]*)"\s*=>', txt):
            gate_subs.add(m.group(1))

    cli_mjs = root / "bin" / "deepmodebot.mjs"
    if cli_mjs.is_file():
        txt = cli_mjs.read_text(encoding="utf-8", errors="replace")
        m_map = re.search(r"const\s+map\s*=\s*\{(.*?)\};", txt, re.S)
        if m_map:
            for m in re.finditer(r"\b([a-z][a-z0-9-]*)\s*:", m_map.group(1)):
                gate_subs.add(m.group(1))

    main_go = root / "native" / "dmb-net" / "main.go"
    if main_go.is_file():
        txt = main_go.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'case\s+"([a-z][a-z0-9-]*)":', txt):
            net_subs.add(m.group(1))

    return gate_subs, net_subs


def _check_cross_lang_gate_parity(root: Path) -> list[dict]:
    findings: list[dict] = []
    perf_py = root / "plugins" / "deepmodebot" / "skills" / "deepmodebot" / "assets" / "perf-audit" / "perf_audit.py"
    perf_rs = root / "native" / "dmb-gate" / "src" / "perf.rs"
    if perf_py.is_file() and perf_rs.is_file():
        py_rules = set(re.findall(r'"([a-z0-9]+-(?:n-plus-one|sync-in-async|missing-timeout|unbounded-[a-z-]+|offset-pagination|pool-per-request|json-in-loop|regex-in-loop)[a-z0-9-]*)"', perf_py.read_text(encoding="utf-8", errors="replace")))
        rs_rules = set(re.findall(r'rule:\s*"([a-z0-9-]+)"', perf_rs.read_text(encoding="utf-8", errors="replace")))
        for missing in sorted(py_rules - rs_rules):
            findings.append({
                "severity": "P1",
                "rule": "cross-lang-gate-drift",
                "file": "native/dmb-gate/src/perf.rs",
                "line": 1,
                "message": f"Rule `{missing}` exists in perf_audit.py but is missing in native/dmb-gate/src/perf.rs.",
                "fix": "Implement 1:1 rule parity across Python and Rust gates.",
            })

    ui_py = root / "plugins" / "deepmodebot" / "skills" / "frontend-ui" / "scripts" / "ui_audit.py"
    ui_rs = root / "native" / "dmb-gate" / "src" / "ui.rs"
    if ui_py.is_file() and ui_rs.is_file():
        py_txt = ui_py.read_text(encoding="utf-8", errors="replace")
        rs_txt = ui_rs.read_text(encoding="utf-8", errors="replace")
        py_rules = set(re.findall(r'Finding\(\s*"[P012]"\s*,\s*"([a-z0-9-]+)"', py_txt))
        rs_raw = set(re.findall(r'rule:\s*"([a-z0-9-]+)"', rs_txt))
        rs_mapped = {UI_RULE_EQUIV.get(r, r.removeprefix("ui-")) for r in rs_raw}
        blocking_ui = {
            "no-transition-all", "no-layout-transition", "no-scale-zero-entry", "no-ease-in-ui",
            "checkbox-not-circular", "icon-button-label", "no-pure-black-surface", "no-100vw-overflow",
            "sticky-overflow-x-hidden", "no-zoom-disable", "no-paste-block", "no-fake-live-pulse",
        }
        for missing in sorted((py_rules & blocking_ui) - rs_mapped):
            findings.append({
                "severity": "P1",
                "rule": "cross-lang-gate-drift",
                "file": "native/dmb-gate/src/ui.rs",
                "line": 1,
                "message": f"Blocking UI rule `{missing}` in ui_audit.py has no Rust counterpart in native/dmb-gate/src/ui.rs.",
                "fix": "Add matching rule coverage in native/dmb-gate/src/ui.rs.",
            })

    gap_py = root / "plugins" / "deepmodebot" / "skills" / "deepmodebot" / "assets" / "gap-audit" / "gap_audit.py"
    gap_rs = root / "native" / "dmb-gate" / "src" / "gap.rs"
    if gap_py.is_file() and gap_rs.is_file():
        expected_gap_rules = {
            "doc-script-flag-drift", "doc-cli-subcommand-drift", "stale-replaces-claim",
            "hollow-stub-body", "swallowed-exception", "cross-lang-gate-drift", "unwired-script-asset",
        }
        rs_gap_rules = set(re.findall(r'rule:\s*"([a-z0-9-]+)"', gap_rs.read_text(encoding="utf-8", errors="replace")))
        for missing in sorted(expected_gap_rules - rs_gap_rules):
            findings.append({
                "severity": "P1",
                "rule": "cross-lang-gate-drift",
                "file": "native/dmb-gate/src/gap.rs",
                "line": 1,
                "message": f"Gap rule `{missing}` in gap_audit.py is missing from native/dmb-gate/src/gap.rs.",
                "fix": "Keep gap_audit.py and native/dmb-gate/src/gap.rs rule sets identical.",
            })

    return findings


def _extract_script_flags(txt: str) -> set[str]:
    if ".add_argument(" not in txt:
        return set()
    if any(tok in txt for tok in ("parse_known_args", "REMAINDER", "parse_intermixed_args")):
        return set()
    flags = {fl_m.group(1) for call_m in ADD_ARG_CALL_RE.finditer(txt) for fl_m in LONG_FLAG_LIT_RE.finditer(call_m.group(1))}
    return (flags | {"--help"}) if flags else set()


def _collect_repo_inventory(safe_root: Path) -> tuple[dict[str, str], set[str], set[str], dict[str, list[tuple[str, set[str]]]], list[str]]:
    all_files: dict[str, str] = {}
    live_paths: set[str] = set()
    live_basenames: set[str] = set()
    argparse_by_name: dict[str, list[tuple[str, set[str]]]] = {}
    asset_scripts: list[str] = []

    for dirpath, dirnames, filenames in os.walk(safe_root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()]
        base = Path(dirpath)
        for name in sorted(filenames):
            p = base / name
            if p.is_symlink() or not p.is_file():
                continue
            try:
                if p.stat().st_size > 2_097_152:
                    continue
            except OSError:
                continue
            rel = p.relative_to(safe_root).as_posix()
            suffix = p.suffix.lower()
            is_test = bool(TEST_PATH_RE.search(rel))
            if not is_test:
                live_paths.add(rel)
                live_basenames.add(name)
            if suffix not in SCAN_TEXT_EXTS:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            all_files[rel] = txt
            if suffix == ".py" and not is_test:
                if re.match(r"plugins/[^/]+/skills/[^/]+/(?:assets/[^/]+|scripts)/[a-z0-9_]+\.py$", rel) and name != "__init__.py":
                    asset_scripts.append(rel)
                flags = _extract_script_flags(txt)
                if flags:
                    argparse_by_name.setdefault(name, []).append((rel, flags))
    return all_files, live_paths, live_basenames, argparse_by_name, asset_scripts


def _scan_markdown_line(
    rel: str,
    idx: int,
    line: str,
    argparse_by_name: dict[str, list[tuple[str, set[str]]]],
    gate_subs: set[str],
    net_subs: set[str],
) -> list[dict]:
    out: list[dict] = []
    for m in SCRIPT_INVOCATION_RE.finditer(line):
        entries = argparse_by_name.get(m.group(1))
        tail = m.group(2)
        if not entries or len(entries) != 1 or "--<" in tail or "--{" in tail:
            continue
        srel, valid_flags = entries[0]
        for fm in PASSING_FLAG_RE.finditer(tail):
            flg = fm.group(1)
            if flg not in valid_flags:
                out.append({
                    "severity": "P1",
                    "rule": "doc-script-flag-drift",
                    "file": rel,
                    "line": idx,
                    "message": f"Doc passes `{flg}` to `{srel}`, which does not define that flag.",
                    "fix": f"Update `{rel}` or add `{flg}` to `{srel}`'s argparse definition.",
                })
    for pat, subs, label, fix in (
        (DMB_GATE_DOC_RE, gate_subs, "dmb-gate", "Update the documented gate subcommand or wire it into dmb-gate and bin/deepmodebot.mjs."),
        (DMB_NET_DOC_RE, net_subs, "dmb-net", "Update the documented dmb-net subcommand or add it to native/dmb-net/main.go."),
    ):
        if not subs:
            continue
        for cm in pat.finditer(line):
            for token in cm.group(1).split("|"):
                if token and token != "help" and token not in subs:
                    out.append({
                        "severity": "P1",
                        "rule": "doc-cli-subcommand-drift",
                        "file": rel,
                        "line": idx,
                        "message": f"Doc references unknown {label} subcommand `{token}`.",
                        "fix": fix,
                    })
    return out


def _scan_source_file(rel: str, suffix: str, txt: str, live_paths: set[str], live_basenames: set[str]) -> list[dict]:
    out: list[dict] = []
    if suffix in (".py", ".rs", ".go", *JS_EXTS):
        for idx, line in enumerate(txt.splitlines(), 1):
            rm = REPLACES_COMMENT_RE.search(line)
            if not rm:
                continue
            target = rm.group(1).lstrip("./")
            still_live = (
                target in live_paths
                or ("/" not in target and Path(target).name in live_basenames)
                or any(p.endswith("/" + target) for p in live_paths)
            )
            if still_live:
                out.append({
                    "severity": "P1",
                    "rule": "stale-replaces-claim",
                    "file": rel,
                    "line": idx,
                    "message": f"Comment claims to replace `{target}`, which is still an active file in the repo.",
                    "fix": f"Migrate callers and delete `{target}`, or clarify how this module complements `{target}`.",
                })

    if suffix == ".py":
        out.extend(_scan_python_ast_gaps(rel, txt))
    elif suffix == ".rs":
        for idx, line in enumerate(txt.splitlines(), 1):
            if line.strip().startswith("#[cfg(test)]"):
                break
            if RUST_STUB_MACRO_RE.search(scrub_c_like_line(line, keep_string_contents=False)):
                out.append({
                    "severity": "P1",
                    "rule": "hollow-stub-body",
                    "file": rel,
                    "line": idx,
                    "message": "Production Rust code leaves `todo!()` / `unimplemented!()` stub.",
                    "fix": "Implement the code path before shipping.",
                })
    elif suffix in JS_EXTS and not rel.startswith("docs/assets/"):
        teardown_re = re.compile(r"\b(?:finished|unlink|rm|rmdir|close|abort|cancel|dispose)\b")
        for idx, line in enumerate(txt.splitlines(), 1):
            scrubbed_no_str = scrub_c_like_line(line, keep_string_contents=False)
            scrubbed_with_str = scrub_c_like_line(line, keep_string_contents=True)
            m_catch = JS_EMPTY_CATCH_RE.search(scrubbed_no_str)
            if m_catch and not teardown_re.search(scrubbed_no_str[: m_catch.start()]):
                out.append({
                    "severity": "P1",
                    "rule": "swallowed-exception",
                    "file": rel,
                    "line": idx,
                    "message": "Empty `.catch(() => {})` silently drops rejected Promises.",
                    "fix": "Log, propagate, or surface structured error state instead of swallowing rejections.",
                })
            if "throw new Error" in scrubbed_no_str and JS_STUB_THROW_RE.search(scrubbed_with_str):
                out.append({
                    "severity": "P1",
                    "rule": "hollow-stub-body",
                    "file": rel,
                    "line": idx,
                    "message": "Production JS/TS code throws a `not implemented` / `TODO` placeholder error.",
                    "fix": "Implement the real handler or remove the dead entrypoint.",
                })
    return out


def _scan_unwired_assets(asset_scripts: list[str], all_files: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for srel in asset_scripts:
        sname = Path(srel).name
        stem = Path(srel).stem
        sdir_prefix = str(Path(srel).parent.as_posix()) + "/"
        referenced = any(
            orel != srel
            and not (orel.startswith(sdir_prefix) and TEST_PATH_RE.search(orel))
            and (sname in otxt or (orel.startswith(sdir_prefix) and re.search(rf"\b{re.escape(stem)}\b", otxt)))
            for orel, otxt in all_files.items()
        )
        if not referenced:
            out.append({
                "severity": "P2",
                "rule": "unwired-script-asset",
                "file": srel,
                "line": 1,
                "message": f"Skill script `{srel}` is never referenced by any skill, command, CLI, or non-test module.",
                "fix": "Wire the script into its owning SKILL.md / reference workflow or remove dead code.",
            })
    return out


def scan_repo(root: Path) -> dict:
    safe_root = reject_unsafe_root(root)
    all_files, live_paths, live_basenames, argparse_by_name, asset_scripts = _collect_repo_inventory(safe_root)
    gate_subs, net_subs = _discover_cli_subcommands(safe_root)
    findings: list[dict] = []

    for rel, txt in sorted(all_files.items()):
        suffix = Path(rel).suffix.lower()
        if suffix == ".md":
            if rel.startswith(DOC_SKIP_PREFIXES) or Path(rel).name.upper().startswith("CHANGELOG"):
                continue
            for idx, line in enumerate(txt.splitlines(), 1):
                findings.extend(_scan_markdown_line(rel, idx, line, argparse_by_name, gate_subs, net_subs))
        elif not TEST_PATH_RE.search(rel):
            findings.extend(_scan_source_file(rel, suffix, txt, live_paths, live_basenames))

    findings.extend(_check_cross_lang_gate_parity(safe_root))
    findings.extend(_scan_unwired_assets(asset_scripts, all_files))

    rank = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda f: (rank.get(f["severity"], 9), f["file"], f["line"], f["rule"]))
    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in ("P0", "P1", "P2")}
    code_files_scanned = sum(
        1 for rel in all_files
        if Path(rel).suffix.lower() in {".py", ".rs", ".go", ".sh", *JS_EXTS}
        and not TEST_PATH_RE.search(rel)
    )
    return {
        "ok": counts["P0"] == 0 and counts["P1"] == 0,
        "engine": "python-ast",
        "files_checked": len(all_files),
        "code_files_checked": code_files_scanned,
        "counts": counts,
        "findings": findings,
    }

def _verify_local_or_external_receipt(receipt: str, root: Path) -> tuple[bool, str]:
    r = receipt.strip()
    if not r:
        return False, "empty receipt"
    if r.startswith(("https://", "http://")):
        return True, "url"
    if r.startswith("cmd:") and len(r) > 6:
        return True, "command"
    if r.startswith(("scan:", "missing:")):
        return True, "scan-state"
    if "@" in r and ":" in r:
        return True, "versioned-source"
    path_part = r.split(":", 1)[0].strip()
    line_part = r.split(":", 2)[1].split("-", 1)[0].strip() if ":" in r else ""
    cand = (root / path_part).resolve()
    try:
        cand.relative_to(root)
    except ValueError:
        return False, f"receipt path escapes root: {receipt}"
    if not cand.exists():
        return False, f"receipt path does not exist on disk: {path_part}"
    if line_part.isdigit() and cand.is_file():
        line_no = int(line_part)
        total = len(cand.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_no < 1 or (total > 0 and line_no > total):
            return False, f"receipt line {line_no} out of range (1..{total}) in {path_part}"
    return True, "local-file"


def init_research_ledger(root: Path, slug: str, question: str, sources: list[str], force: bool = False) -> dict:
    safe_root = reject_unsafe_root(root)
    if not SLUG_RE.match(slug):
        raise SystemExit(f"invalid kebab-case slug: {slug!r}")
    if not question.strip():
        raise SystemExit("research question cannot be empty")
    out_dir = ensure_contained(safe_root / ".scratch" / "research" / slug, safe_root)
    ledger_path = out_dir / "ledger.json"
    if ledger_path.exists() and not force:
        raise SystemExit(f"research ledger already exists at {ledger_path} (pass --force to overwrite)")
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch_gi = safe_root / ".scratch" / ".gitignore"
    if not scratch_gi.exists():
        scratch_gi.write_text("*\n", encoding="utf-8")

    gap_scan = scan_repo(safe_root)
    has_code_files = gap_scan.get("code_files_checked", 0) > 0

    ledger = {
        "schema_version": 1,
        "slug": slug,
        "root": str(safe_root),
        "question": question.strip(),
        "as_of": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "sources": [s.strip() for s in sources if s.strip()],
        "has_code_files": has_code_files,
        "repo_gap_baseline": {
            "files_checked": gap_scan["files_checked"],
            "counts": gap_scan["counts"],
            "top_findings": gap_scan["findings"][:10],
        },
        "claims": [],
        "gaps": [],
    }
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "dir": str(out_dir), "ledger_path": str(ledger_path), "repo_gap_counts": gap_scan["counts"]}


def _load_ledger(dir_arg: Path) -> tuple[Path, Path, dict]:
    ledger_dir = dir_arg.resolve()
    ledger_path = ledger_dir / "ledger.json"
    if not ledger_path.is_file():
        raise SystemExit(f"missing ledger.json in {ledger_dir}")
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    safe_root = reject_unsafe_root(Path(data["root"]))
    ensure_contained(ledger_dir, safe_root)
    return safe_root, ledger_path, data


def record_claim(
    dir_arg: Path,
    claim_id: str,
    claim: str,
    evidence_tier: str,
    primary_receipt: str,
    disconfirmation_probe: str,
    disconfirmation_result: str,
    caveat: str = "",
) -> dict:
    safe_root, ledger_path, data = _load_ledger(dir_arg)
    ok_rec, rec_detail = _verify_local_or_external_receipt(primary_receipt, safe_root)
    if not ok_rec:
        raise SystemExit(f"invalid primary receipt for {claim_id}: {rec_detail}")
    probe = disconfirmation_probe.strip()
    if len(probe) < 15 or TRIVIAL_PROBE_RE.match(probe):
        raise SystemExit(
            f"disconfirmation_probe for {claim_id} is too shallow; record the exact issue/code/repro/limit probe run"
        )
    effective_caveat = caveat.strip()
    if evidence_tier == "docs-only" and not effective_caveat:
        effective_caveat = "docs-claimed only; not yet corroborated against source code or runtime probe"

    entry = {
        "id": claim_id.strip(),
        "claim": claim.strip(),
        "evidence_tier": evidence_tier,
        "primary_receipt": primary_receipt.strip(),
        "receipt_kind": rec_detail,
        "disconfirmation_probe": probe,
        "disconfirmation_result": disconfirmation_result,
        "caveat": effective_caveat,
    }
    claims = [c for c in data.get("claims", []) if c.get("id") != entry["id"]]
    claims.append(entry)
    data["claims"] = claims
    ledger_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "recorded_claim": entry, "total_claims": len(claims)}


def record_gap(
    dir_arg: Path,
    gap_id: str,
    capability: str,
    source_ref: str,
    repo_state: str,
    repo_evidence: str,
    priority: str,
    leverage: str,
) -> dict:
    safe_root, ledger_path, data = _load_ledger(dir_arg)
    ok_src, src_detail = _verify_local_or_external_receipt(source_ref, safe_root)
    if not ok_src:
        raise SystemExit(f"invalid source_ref for {gap_id}: {src_detail}")
    ok_ev, ev_detail = _verify_local_or_external_receipt(repo_evidence, safe_root)
    if not ok_ev:
        raise SystemExit(f"invalid repo_evidence for {gap_id}: {ev_detail}")

    entry = {
        "id": gap_id.strip(),
        "capability": capability.strip(),
        "source_ref": source_ref.strip(),
        "repo_state": repo_state,
        "repo_evidence": repo_evidence.strip(),
        "priority": priority,
        "leverage": leverage.strip(),
    }
    gaps = [g for g in data.get("gaps", []) if g.get("id") != entry["id"]]
    gaps.append(entry)
    data["gaps"] = gaps
    ledger_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "recorded_gap": entry, "total_gaps": len(gaps)}


def render_research_markdown(data: dict) -> str:
    lines = [
        f"# Research & Gap Brief: {data['question']}",
        "",
        f"As-of: `{data['as_of']}` | Slug: `{data['slug']}`",
        "",
        "## Verified Claims & Disconfirmation Receipts",
        "",
    ]
    for c in data.get("claims", []):
        badge = f"[{c['evidence_tier']} / {c['disconfirmation_result']}]"
        cav = f" (Bound: {c['caveat']})" if c.get("caveat") else ""
        lines.append(
            f"- **{c['id']}** {badge}: {c['claim']} — Source: `{c['primary_receipt']}`; "
            f"Disconfirmation probe: {c['disconfirmation_probe']}{cav}"
        )
    lines.extend([
        "",
        "## SOTA vs Target-Repo Differential Gap Matrix",
        "",
        "| ID | Priority | Capability / Invariant | Upstream Source | Repo State | Repo Evidence | Actionable Leverage |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for g in data.get("gaps", []):
        lines.append(
            f"| `{g['id']}` | `{g['priority']}` | {g['capability']} | `{g['source_ref']}` | "
            f"`{g['repo_state']}` | `{g['repo_evidence']}` | {g['leverage']} |"
        )
    baseline = data.get("repo_gap_baseline") or {}
    b_counts = baseline.get("counts") or {}
    lines.extend([
        "",
        "## Deterministic Repo Gap Baseline",
        "",
        f"- Scanned `{baseline.get('files_checked', 0)}` files: `P0={b_counts.get('P0', 0)}`, "
        f"`P1={b_counts.get('P1', 0)}`, `P2={b_counts.get('P2', 0)}`.",
        "",
    ])
    return "\n".join(lines)


def verify_research_ledger(
    dir_arg: Path,
    strict: bool = False,
    require_gap_matrix: bool = False,
    render_out: Path | None = None,
) -> dict:
    safe_root, _, data = _load_ledger(dir_arg)
    violations: list[str] = []
    claims = data.get("claims", [])
    gaps = data.get("gaps", [])

    if not claims:
        violations.append("zero claims recorded; record at least one primary-sourced claim")

    has_adversarial_probe = False
    has_non_docs_claim = False

    for c in claims:
        cid = c.get("id", "?")
        tier = c.get("evidence_tier", "")
        if tier not in EVIDENCE_TIERS:
            violations.append(f"claim {cid}: invalid evidence_tier {tier!r}")
        if tier in ("code-verified", "spec-rfc", "measured"):
            has_non_docs_claim = True
        ok_rec, rec_msg = _verify_local_or_external_receipt(c.get("primary_receipt", ""), safe_root)
        if not ok_rec:
            violations.append(f"claim {cid}: {rec_msg}")
        probe = c.get("disconfirmation_probe", "").strip()
        if len(probe) < 15 or TRIVIAL_PROBE_RE.match(probe):
            violations.append(f"claim {cid}: missing substantive disconfirmation_probe")
        if ADVERSARIAL_SIGNAL_RE.search(probe) or c.get("disconfirmation_result") in ("qualified", "refuted"):
            has_adversarial_probe = True
        if c.get("disconfirmation_result") == "qualified" and not c.get("caveat", "").strip():
            violations.append(f"claim {cid}: qualified claim requires a non-empty caveat")
        if tier in ("docs-only", "unverified") and UNIVERSAL_CLAIM_RE.search(c.get("claim", "")):
            violations.append(f"claim {cid}: universal guarantee language is forbidden on `{tier}` evidence")

    if claims and not has_adversarial_probe:
        violations.append("no adversarial disconfirmation signal found across probes (check issues, source code, changelogs, CVEs, or runtime repro)")

    if strict and claims and not has_non_docs_claim:
        violations.append("strict mode requires at least one claim corroborated at `code-verified`, `spec-rfc`, or `measured` tier (never 100% docs-only)")

    need_gaps = require_gap_matrix or bool(data.get("has_code_files"))
    if need_gaps and not gaps:
        violations.append("missing Differential Gap Matrix entries (`record-gap`); map external SOTA/spec against target repo state")

    for g in gaps:
        gid = g.get("id", "?")
        if g.get("repo_state") not in REPO_STATES:
            violations.append(f"gap {gid}: invalid repo_state {g.get('repo_state')!r}")
        if g.get("priority") not in PRIORITIES:
            violations.append(f"gap {gid}: invalid priority {g.get('priority')!r}")
        ok_s, s_msg = _verify_local_or_external_receipt(g.get("source_ref", ""), safe_root)
        if not ok_s:
            violations.append(f"gap {gid}: source_ref {s_msg}")
        ok_e, e_msg = _verify_local_or_external_receipt(g.get("repo_evidence", ""), safe_root)
        if not ok_e:
            violations.append(f"gap {gid}: repo_evidence {e_msg}")
        if not g.get("leverage", "").strip():
            violations.append(f"gap {gid}: missing actionable leverage description")

    rendered_path = None
    if render_out is not None and not violations:
        safe_out = ensure_contained(render_out, safe_root)
        safe_out.parent.mkdir(parents=True, exist_ok=True)
        safe_out.write_text(render_research_markdown(data), encoding="utf-8", newline="\n")
        rendered_path = str(safe_out)

    status = "PASS" if not violations else "NEEDS_WORK"
    return {
        "ok": not violations,
        "status": status,
        "claims_count": len(claims),
        "gaps_count": len(gaps),
        "violations": violations,
        "rendered_path": rendered_path,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deterministic repo gap/drift scanner and adversarial research ledger.")
    sub = p.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="Scan a repository for doc-code drift, hollow stubs, swallowed errors, and parity gaps.")
    p_scan.add_argument("--root", default=".")
    p_scan.add_argument("--fail-on-p1", action="store_true", help="Exit non-zero when P0 or P1 findings exist (default true).")
    p_scan.add_argument("--advisory", action="store_true", help="Exit 0 even when P1 findings exist.")
    p_scan.add_argument("--json", action="store_true")

    p_init = sub.add_parser("init-research", help="Initialize an adversarial research & differential gap ledger.")
    p_init.add_argument("--root", required=True)
    p_init.add_argument("--slug", required=True)
    p_init.add_argument("--question", required=True)
    p_init.add_argument("--sources", default="")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--json", action="store_true")

    p_claim = sub.add_parser("record-claim", help="Record a primary-sourced research claim and its disconfirmation probe.")
    p_claim.add_argument("--dir", required=True)
    p_claim.add_argument("--id", required=True)
    p_claim.add_argument("--claim", required=True)
    p_claim.add_argument("--evidence-tier", choices=EVIDENCE_TIERS, required=True)
    p_claim.add_argument("--primary-receipt", required=True)
    p_claim.add_argument("--disconfirmation-probe", required=True)
    p_claim.add_argument("--disconfirmation-result", choices=DISCONFIRM_RESULTS, required=True)
    p_claim.add_argument("--caveat", default="")
    p_claim.add_argument("--json", action="store_true")

    p_gap = sub.add_parser("record-gap", help="Record an entry in the SOTA-vs-Repo Differential Gap Matrix.")
    p_gap.add_argument("--dir", required=True)
    p_gap.add_argument("--id", required=True)
    p_gap.add_argument("--capability", required=True)
    p_gap.add_argument("--source-ref", required=True)
    p_gap.add_argument("--repo-state", choices=REPO_STATES, required=True)
    p_gap.add_argument("--repo-evidence", required=True)
    p_gap.add_argument("--priority", choices=PRIORITIES, required=True)
    p_gap.add_argument("--leverage", required=True)
    p_gap.add_argument("--json", action="store_true")

    p_ver = sub.add_parser("verify-research", help="Verify disconfirmation rigor, evidence tiers, and Gap Matrix completeness.")
    p_ver.add_argument("--dir", required=True)
    p_ver.add_argument("--strict", action="store_true")
    p_ver.add_argument("--require-gap-matrix", action="store_true")
    p_ver.add_argument("--render", default=None)
    p_ver.add_argument("--json", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    known_subs = {"scan", "init-research", "record-claim", "record-gap", "verify-research", "-h", "--help"}
    if not raw or raw[0] not in known_subs:
        raw = ["scan", *raw]
    args = build_parser().parse_args(raw)

    if args.cmd == "scan":
        res = scan_repo(Path(args.root))
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            status = "OK" if res["ok"] else "GAPS_FOUND"
            c = res["counts"]
            print(f"gap-audit [{status}]: {res['files_checked']} file(s) — P0:{c['P0']} P1:{c['P1']} P2:{c['P2']}")
            for f in res["findings"]:
                print(f"  {f['file']}:{f['line']} [{f['severity']}:{f['rule']}] {f['message']} -> {f['fix']}")
        if args.advisory:
            return 0
        return 0 if res["ok"] else 1

    if args.cmd == "init-research":
        srcs = [s for s in args.sources.split(",") if s.strip()]
        res = init_research_ledger(Path(args.root), args.slug, args.question, srcs, force=args.force)
        print(json.dumps(res, indent=2) if args.json else f"initialized: {res['ledger_path']}")
        return 0

    if args.cmd == "record-claim":
        res = record_claim(
            Path(args.dir),
            args.id,
            args.claim,
            args.evidence_tier,
            args.primary_receipt,
            args.disconfirmation_probe,
            args.disconfirmation_result,
            args.caveat,
        )
        print(json.dumps(res, indent=2) if args.json else f"recorded claim {args.id} ({res['total_claims']} total)")
        return 0

    if args.cmd == "record-gap":
        res = record_gap(
            Path(args.dir),
            args.id,
            args.capability,
            args.source_ref,
            args.repo_state,
            args.repo_evidence,
            args.priority,
            args.leverage,
        )
        print(json.dumps(res, indent=2) if args.json else f"recorded gap {args.id} ({res['total_gaps']} total)")
        return 0

    if args.cmd == "verify-research":
        render_path = Path(args.render) if args.render else None
        res = verify_research_ledger(
            Path(args.dir),
            strict=args.strict,
            require_gap_matrix=args.require_gap_matrix,
            render_out=render_path,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"research-verify [{res['status']}]: claims={res['claims_count']}, gaps={res['gaps_count']}")
            for v in res["violations"]:
                print(f"  VIOLATION: {v}")
        return 0 if res["ok"] else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
