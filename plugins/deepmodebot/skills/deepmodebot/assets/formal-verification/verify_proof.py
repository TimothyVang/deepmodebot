#!/usr/bin/env python3
"""Deterministic formal & mathematical proof verifier, Comparator-style statement guard,
able-to-fail mutation runner, and Prove2Me/Siege claim-DAG ledger for deepmodebot.

    python verify_proof.py audit-static --path <file-or-dir> [--challenge <Challenge.lean>] [--solution <Solution.lean>] [--formalization <formalization.yaml>] [--json]
    python verify_proof.py able-to-fail --root <repo> --slug <slug> (--script <verify.py> | --cmd <clean_cmd> --mutate-cmd <bad_cmd>) [--covered <file>...] [--json]
    python verify_proof.py dag init --root <repo> --slug <slug> --goal <statement> [--nodes-json <file>] [--json]
    python verify_proof.py dag update --root <repo> --slug <slug> --node <id> --status <status> [--statement <text>] [--depends-on <ids>] [--receipt <ref>] [--auditor <id>] [--json]
    python verify_proof.py dag status --root <repo> --slug <slug> [--strict] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.dont_write_bytecode = True

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ASSETS_DIR = Path(__file__).resolve().parent.parent

PROOF_EXTS = {".lean", ".v", ".thy", ".tla", ".smt2", ".tex"}
SKIP_DIRS = {".git", ".scratch", ".worktrees", "__pycache__", "node_modules", ".lake", "build", "target", ".venv", "venv"}
STANDARD_LEAN_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
VALID_NODE_STATUSES = (
    "open",
    "falsified",
    "sorry_stub",
    "proved_single",
    "proved_dual_verified",
    "kernel_verified",
)

LEAN_ESCAPE_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("PROOF-LEAN-SORRY", "high", re.compile(r"\bsorry\b"), "Unproved 'sorry' placeholder remains in Lean file."),
    ("PROOF-LEAN-ADMIT", "high", re.compile(r"\badmit\b"), "Unproved 'admit' tactic remains in Lean file."),
    ("PROOF-LEAN-AXIOM", "high", re.compile(r"^\s*axiom\s+([A-Za-z0-9_'.]+)"), "Custom 'axiom' declaration bypasses Lean kernel proof obligations."),
    ("PROOF-LEAN-NATIVE", "high", re.compile(r"\bnative_decide\b|Lean\.ofReduceBool\b"), "'native_decide' / ofReduceBool trusts unverified native compiler evaluation outside the kernel."),
    ("PROOF-LEAN-EXTERN", "high", re.compile(r"@\[(?:implemented_by|extern)\b|^\s*unsafe\s+"), "Unsafe/@[extern]/@[implemented_by] attribute can violate logical soundness."),
)

COQ_ESCAPE_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("PROOF-COQ-ADMITTED", "high", re.compile(r"\b(?:Admitted|admit)\s*\."), "Incomplete Coq/Rocq proof ('Admitted.' or 'admit.')."),
    ("PROOF-COQ-AXIOM", "high", re.compile(r"^\s*(?:Axiom|Parameter|Conjecture|Hypothesis)\s+"), "Unproved Coq/Rocq Axiom/Parameter assumption."),
)

ISABELLE_ESCAPE_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("PROOF-ISA-SORRY", "high", re.compile(r"\b(?:sorry|oops)\b"), "Incomplete Isabelle proof ('sorry' or 'oops')."),
    ("PROOF-ISA-AXIOM", "high", re.compile(r"^\s*axiomatization\b"), "Unchecked Isabelle 'axiomatization' block."),
)

TLA_ESCAPE_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("PROOF-TLA-OMITTED", "high", re.compile(r"\bOMITTED\b"), "Omitted TLA+/TLAPS proof obligation ('OMITTED')."),
)

LEAN_DECL_RE = re.compile(
    r"^\s*(?:noncomputable\s+|protected\s+|private\s+)*(theorem|lemma|def|abbrev)\s+([A-Za-z0-9_'.]+)\s*(.*?)(?::=\s*by\b|:=\s*sorry\b|:=|\bwhere\b)",
    re.S | re.M,
)


@dataclass(frozen=True)
class ProofFinding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str


def _load_self_grill():
    path = ASSETS_DIR / "self-grill" / "self_grill.py"
    spec = importlib.util.spec_from_file_location("fv_self_grill", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def strip_proof_comments(text: str, ext: str) -> str:
    if ext == ".lean":
        out: list[str] = []
        i = 0
        depth = 0
        in_str = False
        n = len(text)
        while i < n:
            if depth == 0 and not in_str and text[i : i + 2] == "/-":
                depth = 1
                out.append("  ")
                i += 2
                continue
            if depth > 0:
                if text[i : i + 2] == "/-":
                    depth += 1
                    out.append("  ")
                    i += 2
                elif text[i : i + 2] == "-/":
                    depth -= 1
                    out.append("  ")
                    i += 2
                else:
                    out.append("\n" if text[i] == "\n" else " ")
                    i += 1
                continue
            if text[i] == '"' and (i == 0 or text[i - 1] != "\\"):
                in_str = not in_str
                out.append(text[i])
                i += 1
                continue
            if not in_str and text[i : i + 2] == "--":
                while i < n and text[i] != "\n":
                    out.append(" ")
                    i += 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)
    if ext == ".v":
        cleaned = re.sub(r"\(\*.*?\*\)", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        return cleaned
    if ext == ".tla":
        cleaned = re.sub(r"\(\*.*?\*\)", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        return "\n".join(line.split("\\*", 1)[0] for line in cleaned.splitlines())
    if ext == ".smt2":
        return "\n".join(line.split(";", 1)[0] for line in text.splitlines())
    if ext == ".tex":
        return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines())
    return text


def scan_proof_file(path: Path, base_root: Path | None = None) -> list[ProofFinding]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    ext = path.suffix.lower()
    if ext not in PROOF_EXTS:
        return []
    rel = path.relative_to(base_root).as_posix() if (base_root and path.is_relative_to(base_root)) else path.as_posix()
    stripped = strip_proof_comments(raw, ext)
    rules = (
        LEAN_ESCAPE_RULES if ext == ".lean"
        else COQ_ESCAPE_RULES if ext == ".v"
        else ISABELLE_ESCAPE_RULES if ext == ".thy"
        else TLA_ESCAPE_RULES if ext == ".tla"
        else ()
    )
    findings: list[ProofFinding] = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        for rule_id, sev, pat, msg in rules:
            if pat.search(line):
                findings.append(ProofFinding(rule_id=rule_id, severity=sev, file=rel, line=lineno, message=msg))
    return findings


def extract_lean_declarations(text: str) -> dict[str, tuple[str, str]]:
    clean = strip_proof_comments(text, ".lean")
    decls: dict[str, tuple[str, str]] = {}
    for m in LEAN_DECL_RE.finditer(clean):
        kind, name, sig = m.group(1), m.group(2), m.group(3)
        norm_sig = " ".join(sig.split())
        decls[name] = (kind, norm_sig)
    return decls


def compare_lean_challenge_solution(challenge_path: Path, solution_path: Path) -> list[str]:
    errors: list[str] = []
    if not challenge_path.is_file():
        return [f"challenge file not found: {challenge_path}"]
    if not solution_path.is_file():
        return [f"solution file not found: {solution_path}"]
    ch_text = challenge_path.read_text(encoding="utf-8", errors="replace")
    sol_text = solution_path.read_text(encoding="utf-8", errors="replace")
    ch_decls = extract_lean_declarations(ch_text)
    sol_decls = extract_lean_declarations(sol_text)
    if not ch_decls:
        errors.append(f"no theorem/lemma/def declarations found in challenge file {challenge_path.name}")
    for name, (ch_kind, ch_sig) in ch_decls.items():
        if name not in sol_decls:
            errors.append(f"missing challenge declaration '{name}' ({ch_kind}) in {solution_path.name}")
            continue
        sol_kind, sol_sig = sol_decls[name]
        if ch_sig != sol_sig:
            errors.append(
                f"statement mismatch on '{name}': challenge has '{ch_kind} {name} {ch_sig}' "
                f"but solution has '{sol_kind} {name} {sol_sig}'"
            )
    sol_escapes = scan_proof_file(solution_path)
    for esc in sol_escapes:
        errors.append(f"{solution_path.name}:{esc.line}: [{esc.rule_id}] {esc.message}")
    return errors


def check_formalization_alignment(formalization_path: Path, challenge_decls: dict[str, tuple[str, str]]) -> list[str]:
    if not formalization_path.is_file():
        return [f"formalization manifest not found: {formalization_path}"]
    txt = formalization_path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    for name in challenge_decls:
        if not re.search(rf"\b{re.escape(name)}\b", txt):
            errors.append(f"challenge declaration '{name}' is undocumented in {formalization_path.name} (missing NL-to-formal alignment)")
    if not re.search(r"\b(?:nl_statement|natural_language|paper_ref|source_claim)\s*:", txt):
        errors.append(f"{formalization_path.name} must record nl_statement/source_claim provenance for statement alignment")
    return errors


def audit_static(
    target: Path,
    challenge: Path | None = None,
    solution: Path | None = None,
    formalization: Path | None = None,
) -> dict:
    resolved = target.resolve()
    files: list[Path] = []
    if resolved.is_file():
        files = [resolved]
        base = resolved.parent
    elif resolved.is_dir():
        base = resolved
        for p in sorted(resolved.rglob("*")):
            if any(part in SKIP_DIRS for part in p.relative_to(resolved).parts):
                continue
            if p.is_file() and p.suffix.lower() in PROOF_EXTS:
                if challenge and p.resolve() == challenge.resolve():
                    continue
                files.append(p)
    else:
        return {"valid": False, "scanned_files": 0, "findings": [], "comparator_errors": [f"path not found: {target}"]}

    findings: list[ProofFinding] = []
    for f in files:
        findings.extend(scan_proof_file(f, base_root=base))

    comp_errors: list[str] = []
    if challenge and solution:
        comp_errors.extend(compare_lean_challenge_solution(challenge, solution))
        if formalization:
            ch_decls = extract_lean_declarations(challenge.read_text(encoding="utf-8", errors="replace"))
            comp_errors.extend(check_formalization_alignment(formalization, ch_decls))

    valid = len(findings) == 0 and len(comp_errors) == 0
    return {
        "valid": valid,
        "scanned_files": len(files),
        "findings": [asdict(x) for x in findings],
        "comparator_errors": comp_errors,
    }


def _run_cmd(argv: list[str], cwd: Path, timeout_s: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
        creationflags=NO_WINDOW,
    )
    combined = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return proc.returncode, combined[:4000]


def run_able_to_fail(
    root: Path,
    slug: str,
    script: Path | None = None,
    clean_cmd: str | None = None,
    mutate_cmd: str | None = None,
    mutate_arg: str | None = None,
    covered_files: list[str] | None = None,
) -> dict:
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    if not sg.SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug {slug!r}: use lowercase kebab-case")

    if script is not None:
        script_path = (safe_root / script) if not script.is_absolute() else script
        clean_argv = [sys.executable, "-B", str(script_path)]
        mut_argv = [sys.executable, "-B", str(script_path), "--mutate", *([mutate_arg] if mutate_arg else [])]
    elif clean_cmd and mutate_cmd:
        clean_argv = shlex.split(clean_cmd, posix=(os.name != "nt"))
        mut_argv = shlex.split(mutate_cmd, posix=(os.name != "nt"))
    else:
        raise SystemExit("provide either --script <verify.py> or both --cmd and --mutate-cmd")

    clean_rc, clean_out = _run_cmd(clean_argv, cwd=safe_root)
    mut_rc, mut_out = _run_cmd(mut_argv, cwd=safe_root)

    head_res = sg._run_git(safe_root, ["rev-parse", "--short", "HEAD"]) if sg._is_git_root_or_worktree(safe_root) else None
    sync_sha = head_res.stdout.strip() if (head_res and head_res.returncode == 0) else sg.compute_tree_digest(safe_root)

    cli_usage_err = (
        mut_rc == 2
        and bool(re.search(r"\b(?:unrecognized arguments|expected one argument|invalid choice)\b|^usage:", mut_out, re.I | re.M))
    )
    proven = (clean_rc == 0) and (mut_rc != 0) and not cli_usage_err
    errors: list[str] = []
    if clean_rc != 0:
        errors.append(f"clean verification command failed with exit {clean_rc}")
    if mut_rc == 0:
        errors.append("VACUOUS_CHECK: mutated command exited 0 (check is not proven able to fail)")
    if cli_usage_err:
        errors.append("CLI_USAGE_ERROR: mutated command exited 2 with an argument-parser usage error rather than a real invariant failure")
    out_dir = sg.ensure_contained(safe_root / ".scratch" / "formal-verification", safe_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / f"{slug}-receipt.json"
    payload = {
        "slug": slug,
        "able_to_fail_proven": proven,
        "clean_exit": clean_rc,
        "mutate_exit": mut_rc,
        "clean_output_excerpt": clean_out[:800],
        "mutate_output_excerpt": mut_out[:800],
        "covered_files": list(covered_files or ([str(script)] if script else [])),
        "sync_sha": sync_sha,
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "errors": errors,
    }
    sg.atomic_write_text(receipt_path, json.dumps(payload, indent=2) + "\n", safe_root)
    payload["receipt_path"] = str(receipt_path)
    return payload


def _dag_paths(safe_root: Path, slug: str, sg) -> tuple[Path, Path]:
    if not sg.SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug {slug!r}: use lowercase kebab-case")
    base = sg.ensure_contained(safe_root / ".scratch" / "formal-verification", safe_root)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{slug}-dag.json", base / f"{slug}-ledger.md"


def _detect_dag_cycle(nodes: dict[str, dict]) -> list[str]:
    state: dict[str, int] = {}
    cycle_Errors: list[str] = []

    def dfs(nid: str) -> None:
        state[nid] = 1
        for dep in nodes.get(nid, {}).get("depends_on", []):
            if dep not in nodes:
                cycle_Errors.append(f"node '{nid}' depends on unknown node '{dep}'")
                continue
            st = state.get(dep, 0)
            if st == 1:
                cycle_Errors.append(f"dependency cycle detected: '{nid}' -> '{dep}'")
            elif st == 0:
                dfs(dep)
        state[nid] = 2

    for k in nodes:
        if state.get(k, 0) == 0:
            dfs(k)
    return cycle_Errors


def _compute_dag_status(dag: dict) -> dict:
    nodes: dict[str, dict] = dag.get("nodes", {})
    errors = _detect_dag_cycle(nodes)
    proved_states = {"proved_dual_verified", "kernel_verified"}
    ready_leaves: list[str] = []
    falsified: list[str] = []
    pending_dual_audit: list[str] = []
    sorry_stubs: list[str] = []

    for nid, info in sorted(nodes.items()):
        st = info.get("status", "open")
        deps = info.get("depends_on", [])
        if st == "falsified":
            falsified.append(nid)
        elif st == "sorry_stub":
            sorry_stubs.append(nid)
        elif st == "proved_single":
            pending_dual_audit.append(nid)
        if st in {"open", "sorry_stub"} and all(nodes.get(d, {}).get("status") in proved_states for d in deps):
            ready_leaves.append(nid)

    theorem_proved = bool(nodes) and not errors and all(n.get("status") in proved_states for n in nodes.values())
    return {
        "slug": dag.get("slug", ""),
        "goal": dag.get("goal", ""),
        "theorem_proved": theorem_proved,
        "node_count": len(nodes),
        "ready_leaves": ready_leaves,
        "sorry_stubs": sorry_stubs,
        "pending_dual_audit": pending_dual_audit,
        "falsified": falsified,
        "errors": errors,
    }


def _render_dag_ledger(dag: dict, summary: dict) -> str:
    lines = [
        f"# Proof & Invariant Claim-DAG Ledger (`{dag['slug']}`)",
        "",
        f"- **Goal:** {dag['goal']}",
        f"- **Overall Verdict:** `{'THEOREM_PROVED' if summary['theorem_proved'] else 'IN_PROGRESS'}`",
        f"- **Tractable Ready Leaves (prove next):** `{summary['ready_leaves']}`",
        f"- **Awaiting 2nd Independent Audit (`Siege` dual-audit gate):** `{summary['pending_dual_audit']}`",
        f"- **Active `sorry` Stubs:** `{summary['sorry_stubs']}`",
        f"- **Falsified / Counterexample Found:** `{summary['falsified']}`",
        "",
        "| Node | Status | Depends On | Auditors | Receipt | Statement |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for nid, n in sorted(dag.get("nodes", {}).items()):
        deps = ", ".join(n.get("depends_on") or []) or "-"
        auds = ", ".join(n.get("auditors") or []) or "-"
        rec = n.get("receipt") or "-"
        lines.append(f"| `{nid}` | `{n['status']}` | {deps} | {auds} | `{rec}` | {n['statement']} |")
    return "\n".join(lines) + "\n"


def dag_init(root: Path, slug: str, goal: str, initial_nodes: list[dict] | None = None) -> dict:
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    dag_path, ledger_path = _dag_paths(safe_root, slug, sg)
    nodes: dict[str, dict] = {}
    for raw in initial_nodes or []:
        nid = str(raw["id"]).strip()
        st = str(raw.get("status") or "open")
        if st not in VALID_NODE_STATUSES:
            raise SystemExit(f"invalid status {st!r}")
        nodes[nid] = {
            "id": nid,
            "statement": str(raw.get("statement") or nid),
            "depends_on": list(raw.get("depends_on") or []),
            "status": st,
            "auditors": list(raw.get("auditors") or []),
            "receipt": str(raw.get("receipt") or ""),
        }
    if not nodes:
        nodes["root_goal"] = {
            "id": "root_goal",
            "statement": goal,
            "depends_on": [],
            "status": "open",
            "auditors": [],
            "receipt": "",
        }
    dag = {"slug": slug, "goal": goal, "nodes": nodes}
    summary = _compute_dag_status(dag)
    if summary["errors"]:
        raise SystemExit(f"invalid claim DAG: {summary['errors']}")
    sg.atomic_write_text(dag_path, json.dumps(dag, indent=2) + "\n", safe_root)
    sg.atomic_write_text(ledger_path, _render_dag_ledger(dag, summary), safe_root)
    summary["dag_path"] = str(dag_path)
    summary["ledger_path"] = str(ledger_path)
    return summary


def dag_update(
    root: Path,
    slug: str,
    node_id: str,
    status: str,
    statement: str | None = None,
    depends_on: list[str] | None = None,
    receipt: str = "",
    auditor: str = "",
) -> dict:
    if status not in VALID_NODE_STATUSES:
        raise SystemExit(f"invalid status {status!r}; choose from {VALID_NODE_STATUSES}")
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    dag_path, ledger_path = _dag_paths(safe_root, slug, sg)
    if not dag_path.is_file():
        raise SystemExit(f"claim DAG not initialized: {dag_path}")
    dag = json.loads(dag_path.read_text(encoding="utf-8"))
    nodes = dag.setdefault("nodes", {})
    entry = nodes.get(node_id, {
        "id": node_id,
        "statement": statement or node_id,
        "depends_on": [],
        "status": "open",
        "auditors": [],
        "receipt": "",
    })
    if statement:
        entry["statement"] = statement
    if depends_on is not None:
        entry["depends_on"] = depends_on
    if receipt:
        entry["receipt"] = receipt
    auditors = list(entry.get("auditors") or [])
    if auditor and auditor not in auditors:
        auditors.append(auditor)
    entry["auditors"] = auditors
    if status == "proved_dual_verified" and len(auditors) < 2:
        raise SystemExit(
            f"node '{node_id}' cannot be marked 'proved_dual_verified' with {len(auditors)} auditor(s); "
            "Siege dual-audit gate requires >=2 distinct independent auditors (or use 'kernel_verified' with Lean/TLC/Z3 receipt)"
        )
    if status in {"proved_single", "proved_dual_verified", "kernel_verified"} and not entry.get("receipt"):
        raise SystemExit(f"node '{node_id}' status '{status}' requires a non-empty --receipt")
    entry["status"] = status
    nodes[node_id] = entry
    summary = _compute_dag_status(dag)
    if summary["errors"]:
        raise SystemExit(f"invalid DAG update: {summary['errors']}")
    sg.atomic_write_text(dag_path, json.dumps(dag, indent=2) + "\n", safe_root)
    sg.atomic_write_text(ledger_path, _render_dag_ledger(dag, summary), safe_root)
    summary["dag_path"] = str(dag_path)
    summary["ledger_path"] = str(ledger_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deterministic formal & mathematical proof verification runner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_aud = sub.add_parser("audit-static", help="Scan proof files for sorry/axiom/native_decide escapes and Comparator statement drift.")
    p_aud.add_argument("--path", default=".")
    p_aud.add_argument("--challenge", default=None)
    p_aud.add_argument("--solution", default=None)
    p_aud.add_argument("--formalization", default=None)
    p_aud.add_argument("--json", action="store_true")

    p_atf = sub.add_parser("able-to-fail", help="Prove a verification script passes clean and fails under mutation.")
    p_atf.add_argument("--root", required=True)
    p_atf.add_argument("--slug", required=True)
    p_atf.add_argument("--script", default=None)
    p_atf.add_argument("--mutate-arg", default=None)
    p_atf.add_argument("--cmd", dest="clean_cmd", default=None)
    p_atf.add_argument("--mutate-cmd", default=None)
    p_atf.add_argument("--covered", nargs="*", default=[])
    p_atf.add_argument("--json", action="store_true")

    p_dag = sub.add_parser("dag", help="Manage Prove2Me/Siege claim-DAG decomposition and dual-audit proof ledger.")
    dag_sub = p_dag.add_subparsers(dest="dag_cmd", required=True)

    d_init = dag_sub.add_parser("init")
    d_init.add_argument("--root", required=True)
    d_init.add_argument("--slug", required=True)
    d_init.add_argument("--goal", required=True)
    d_init.add_argument("--nodes-json", default=None)
    d_init.add_argument("--json", action="store_true")

    d_up = dag_sub.add_parser("update")
    d_up.add_argument("--root", required=True)
    d_up.add_argument("--slug", required=True)
    d_up.add_argument("--node", required=True)
    d_up.add_argument("--status", required=True, choices=VALID_NODE_STATUSES)
    d_up.add_argument("--statement", default=None)
    d_up.add_argument("--depends-on", nargs="*", default=None)
    d_up.add_argument("--receipt", default="")
    d_up.add_argument("--auditor", default="")
    d_up.add_argument("--json", action="store_true")

    d_st = dag_sub.add_parser("status")
    d_st.add_argument("--root", required=True)
    d_st.add_argument("--slug", required=True)
    d_st.add_argument("--strict", action="store_true")
    d_st.add_argument("--json", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "audit-static":
        res = audit_static(
            Path(args.path),
            challenge=Path(args.challenge) if args.challenge else None,
            solution=Path(args.solution) if args.solution else None,
            formalization=Path(args.formalization) if args.formalization else None,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"audit-static: valid={res['valid']} scanned={res['scanned_files']} findings={len(res['findings'])} comparator_errors={len(res['comparator_errors'])}")
            for f in res["findings"]:
                print(f"  [{f['severity'].upper()}] {f['rule_id']} {f['file']}:{f['line']} - {f['message']}")
            for e in res["comparator_errors"]:
                print(f"  [COMPARATOR] {e}")
        return 0 if res["valid"] else 1

    if args.cmd == "able-to-fail":
        res = run_able_to_fail(
            Path(args.root),
            slug=args.slug,
            script=Path(args.script) if args.script else None,
            clean_cmd=args.clean_cmd,
            mutate_cmd=args.mutate_cmd,
            mutate_arg=args.mutate_arg,
            covered_files=args.covered,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"able-to-fail: proven={res['able_to_fail_proven']} clean={res['clean_exit']} mutate={res['mutate_exit']} receipt={res['receipt_path']}")
        return 0 if res["able_to_fail_proven"] else 1

    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(Path(args.root))
    if args.dag_cmd == "init":
        nodes_list = json.loads(Path(args.nodes_json).read_text(encoding="utf-8")) if args.nodes_json else None
        res = dag_init(safe_root, slug=args.slug, goal=args.goal, initial_nodes=nodes_list)
        print(json.dumps(res, indent=2) if args.json else f"dag init: {res['ledger_path']} (ready_leaves={res['ready_leaves']})")
        return 0
    if args.dag_cmd == "update":
        res = dag_update(
            safe_root,
            slug=args.slug,
            node_id=args.node,
            status=args.status,
            statement=args.statement,
            depends_on=args.depends_on,
            receipt=args.receipt,
            auditor=args.auditor,
        )
        print(json.dumps(res, indent=2) if args.json else f"dag update: proved={res['theorem_proved']} ready_leaves={res['ready_leaves']}")
        return 0
    dag_path, _ = _dag_paths(safe_root, args.slug, sg)
    if not dag_path.is_file():
        raise SystemExit(f"claim DAG not found: {dag_path}")
    dag = json.loads(dag_path.read_text(encoding="utf-8"))
    res = _compute_dag_status(dag)
    print(json.dumps(res, indent=2) if args.json else f"dag status: proved={res['theorem_proved']} ready={res['ready_leaves']}")
    if args.strict and not res["theorem_proved"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
