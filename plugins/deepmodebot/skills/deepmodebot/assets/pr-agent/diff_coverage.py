#!/usr/bin/env python3
"""Deterministic pre-review file selection, rule-batch grouping, and coverage/line-position verification.

    python -B diff_coverage.py plan [<repo>] [--base <ref>] [--head <ref>] [--include-untracked] [--json]
    python -B diff_coverage.py verify <plan.json> [--reviewed <path>...] [--skipped <path=reason>...] [--findings <file.json>] [--json]

Zero external dependencies (Python 3 stdlib only). Keeps large PR reviews complete and line-accurate without
requiring an external review binary.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

LOCKFILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock",
    "poetry.lock", "uv.lock", "gemfile.lock", "composer.lock", "go.sum",
})
MINIFIED_RE = re.compile(r"\.min\.(?:js|css|mjs)$", re.I)
SECURITY_RE = re.compile(
    r"(?:^|/)(?:\.env|auth|login|password|secret|credential|token|permission|security|rbac|oauth|crypto|migration)",
    re.I,
)
CONFIG_CI_RE = re.compile(
    r"(?:^|/)(?:\.github/|\.gitlab-ci\.yml|jenkinsfile|dockerfile|docker-compose|pyproject\.toml|"
    r"package\.json|tsconfig\.json|cargo\.toml|go\.mod|hooks\.json|mcp_config\.json)",
    re.I,
)
TEST_RE = re.compile(r"(?:^|/)(?:tests?/|__tests__/|spec/|test_[^/]+|[^/]+(?:\.test|_test|\.spec)\.[^/]+$)", re.I)
DOCS_RE = re.compile(r"\.(?:md|mdx|rst|txt|adoc)$", re.I)
UI_RE = re.compile(r"\.(?:tsx|jsx|vue|svelte|css|scss|html|svg)$", re.I)
GENERATED_RE = re.compile(
    r"(?:^|/)(?:__snapshots__/|generated/|gen/)|(?:\.snap|\.(?:pb\.go|g\.dart|generated\.[A-Za-z0-9]+))$",
    re.I,
)
THEMATIC_GROUP_ORDER = ("auth_security", "backend_core", "ui", "config_ci", "docs", "tests")
GUIDE_TITLES = {
    "auth_security": "Security, auth & trust boundaries",
    "backend_core": "Core domain & backend logic",
    "ui": "UI, interaction & styling",
    "config_ci": "Build, CI & configuration",
    "docs": "Documentation & specifications",
    "tests": "Verification & test suites",
}
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), "--no-pager", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )


def git_root(path: Path) -> Path:
    res = run_git(path, "rev-parse", "--show-toplevel")
    if res.returncode != 0 or not res.stdout.strip():
        raise SystemExit(f"not inside a git repository: {path}")
    return Path(res.stdout.strip())


def classify_rule_group(rel_path: str) -> str:
    if SECURITY_RE.search(rel_path):
        return "auth_security"
    if TEST_RE.search(rel_path):
        return "tests"
    if CONFIG_CI_RE.search(rel_path):
        return "config_ci"
    if DOCS_RE.search(rel_path):
        return "docs"
    if UI_RE.search(rel_path):
        return "ui"
    return "backend_core"


def why_excluded(rel_path: str, status: str, added: int, deleted: int, is_binary: bool, max_file_lines: int) -> str | None:
    if status.startswith("D"):
        return "deleted"
    if is_binary:
        return "binary"
    name = Path(rel_path).name.lower()
    if name in LOCKFILES:
        return "lockfile"
    if MINIFIED_RE.search(rel_path):
        return "minified"
    if max_file_lines > 0 and (added + deleted) > max_file_lines:
        return f"oversized ({added + deleted} > {max_file_lines} changed lines)"
    return None


def collect_changes(repo: Path, base: str | None, head: str | None, include_untracked: bool) -> list[dict]:
    diff_flags = ["--no-ext-diff", "--no-textconv", "--no-color"]
    if base and head:
        range_args = [f"{base}...{head}"]
    elif base:
        range_args = [base]
    else:
        range_args = ["HEAD"] if run_git(repo, "rev-parse", "--verify", "HEAD").returncode == 0 else []

    records: dict[str, dict] = {}
    if range_args:
        status_res = run_git(repo, "diff", *diff_flags, "--name-status", "-z", *range_args)
        if status_res.returncode != 0:
            raise SystemExit(f"git diff --name-status failed: {status_res.stderr.strip()}")
        tokens = [t for t in status_res.stdout.split("\0") if t]
        idx = 0
        while idx < len(tokens):
            st = tokens[idx]
            idx += 1
            if st.startswith(("R", "C")) and idx + 1 < len(tokens):
                _old = tokens[idx]
                rel = tokens[idx + 1]
                idx += 2
            elif idx < len(tokens):
                rel = tokens[idx]
                idx += 1
            else:
                break
            records[rel] = {"path": rel, "status": st[0], "added": 0, "deleted": 0, "binary": False}

        num_res = run_git(repo, "diff", *diff_flags, "--numstat", "-z", *range_args)
        if num_res.returncode == 0:
            ntokens = num_res.stdout.split("\0")
            i = 0
            while i < len(ntokens):
                entry = ntokens[i]
                i += 1
                if not entry:
                    continue
                parts = entry.split("\t", 2)
                if len(parts) < 3:
                    continue
                add_s, del_s, path_part = parts
                if path_part == "" and i + 1 < len(ntokens):
                    # Rename in -z numstat: "\t\t" followed by old\0new\0
                    _old = ntokens[i]
                    path_part = ntokens[i + 1]
                    i += 2
                rec = records.setdefault(path_part, {"path": path_part, "status": "M", "added": 0, "deleted": 0, "binary": False})
                if add_s == "-" or del_s == "-":
                    rec["binary"] = True
                else:
                    rec["added"] = int(add_s)
                    rec["deleted"] = int(del_s)

    if include_untracked:
        untracked = run_git(repo, "ls-files", "--others", "--exclude-standard", "-z")
        if untracked.returncode == 0:
            for rel in untracked.stdout.split("\0"):
                if not rel or rel in records:
                    continue
                full = repo / rel
                is_bin = False
                lines = 0
                if full.is_file():
                    raw = full.read_bytes()
                    is_bin = b"\0" in raw[:8192]
                    lines = 0 if is_bin else len(raw.decode("utf-8", errors="replace").splitlines())
                records[rel] = {"path": rel, "status": "?", "added": lines, "deleted": 0, "binary": is_bin}

    return [records[k] for k in sorted(records)]


def is_meaningful_code(rec: dict) -> bool:
    if rec.get("binary") or rec.get("status", "").startswith("D"):
        return False
    rel_path = rec["path"]
    name = Path(rel_path).name.lower()
    if name in LOCKFILES or MINIFIED_RE.search(rel_path) or GENERATED_RE.search(rel_path):
        return False
    if TEST_RE.search(rel_path) or DOCS_RE.search(rel_path):
        return False
    return True


def summarize_loc(changes: list[dict]) -> dict:
    total_added = sum(int(r.get("added", 0)) for r in changes if not r.get("binary"))
    total_deleted = sum(int(r.get("deleted", 0)) for r in changes if not r.get("binary"))
    meaningful_added = sum(int(r.get("added", 0)) for r in changes if is_meaningful_code(r))
    meaningful_deleted = sum(int(r.get("deleted", 0)) for r in changes if is_meaningful_code(r))
    return {
        "meaningful_added": meaningful_added,
        "meaningful_deleted": meaningful_deleted,
        "meaningful_lines": meaningful_added + meaningful_deleted,
        "total_added": total_added,
        "total_deleted": total_deleted,
        "total_lines": total_added + total_deleted,
        "badge": f"Meaningful code +{meaningful_added} -{meaningful_deleted} · Total +{total_added} -{total_deleted}",
    }


def build_batches(reviewable: list[dict], max_files: int, max_lines: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in reviewable:
        grouped.setdefault(item["rule_group"], []).append(item)

    ordered_groups = [g for g in THEMATIC_GROUP_ORDER if g in grouped] + sorted(
        g for g in grouped if g not in THEMATIC_GROUP_ORDER
    )
    batches: list[dict] = []
    for group in ordered_groups:
        cur_items: list[dict] = []
        cur_lines = 0
        for item in grouped[group]:
            item_lines = item["added"] + item["deleted"]
            if cur_items and (len(cur_items) >= max_files or (max_lines > 0 and cur_lines + item_lines > max_lines)):
                batches.append({
                    "batch_id": len(batches) + 1,
                    "rule_group": group,
                    "guide_title": GUIDE_TITLES.get(group, group),
                    "files": [x["path"] for x in cur_items],
                    "indices": [x["index"] for x in cur_items],
                    "changed_lines": cur_lines,
                })
                cur_items, cur_lines = [], 0
            cur_items.append(item)
            cur_lines += item_lines
        if cur_items:
            batches.append({
                "batch_id": len(batches) + 1,
                "rule_group": group,
                "guide_title": GUIDE_TITLES.get(group, group),
                "files": [x["path"] for x in cur_items],
                "indices": [x["index"] for x in cur_items],
                "changed_lines": cur_lines,
            })
    total_b = len(batches)
    for b in batches:
        b["guide_step"] = f"{b['batch_id']} of {total_b}"
    return batches


def _apply_patch_line(rec: dict, line: str) -> None:
    if line.startswith("Binary files "):
        rec["binary"] = True
    elif line.startswith("new file mode"):
        rec["status"] = "A"
    elif line.startswith("deleted file mode"):
        rec["status"] = "D"
    elif line.startswith("+") and not line.startswith("+++"):
        rec["added"] += 1
    elif line.startswith("-") and not line.startswith("---"):
        rec["deleted"] += 1


def collect_changes_from_patch(patch_path: Path) -> list[dict]:
    records: dict[str, dict] = {}
    cur_path: str | None = None
    for line in patch_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            cur_path = parts[1].strip() if len(parts) == 2 else None
            if cur_path and cur_path not in records:
                records[cur_path] = {"path": cur_path, "status": "M", "added": 0, "deleted": 0, "binary": False}
            continue
        if cur_path:
            _apply_patch_line(records[cur_path], line)
    return [records[k] for k in sorted(records)]

def cmd_plan(args: argparse.Namespace) -> int:
    repo_arg = args.repo_flag or args.repo
    repo = git_root(Path(repo_arg).resolve())
    changes = (
        collect_changes_from_patch(Path(args.diff))
        if args.diff
        else collect_changes(repo, args.base, args.head, args.include_untracked)
    )
    reviewable: list[dict] = []
    excluded: list[dict] = []
    for rec in changes:
        reason = why_excluded(rec["path"], rec["status"], rec["added"], rec["deleted"], rec["binary"], args.max_file_lines)
        if reason:
            excluded.append({**rec, "reason": reason})
        else:
            reviewable.append({
                **rec,
                "index": len(reviewable) + 1,
                "rule_group": classify_rule_group(rec["path"]),
                "meaningful_code": is_meaningful_code(rec),
            })

    batches = build_batches(reviewable, max(1, args.max_batch_files), max(0, args.max_batch_lines))
    loc = summarize_loc(changes)
    payload = {
        "repo": str(repo),
        "base": args.base,
        "head": args.head,
        "total_changed": len(changes),
        "reviewable_count": len(reviewable),
        "excluded_count": len(excluded),
        "loc_summary": loc,
        "reviewable": reviewable,
        "excluded": excluded,
        "batches": batches,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"diff-plan: {len(reviewable)} reviewable, {len(excluded)} excluded, {len(batches)} guide section(s) — {loc['badge']}")
        for b in batches:
            print(
                f"  guide {b['guide_step']} [{b['rule_group']}: {b['guide_title']}] "
                f"({len(b['files'])} files, {b['changed_lines']} lines): {', '.join(b['files'])}"
            )
        for ex in excluded:
            print(f"  excluded: {ex['path']} ({ex['reason']})")
    return 0


def verify_positions(repo: Path, findings_path: Path) -> list[str]:
    data = json.loads(findings_path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("findings", [])
    errors: list[str] = []
    line_cache: dict[str, int | None] = {}
    for idx, item in enumerate(items, 1):
        rel = str(item.get("path", "")).strip()
        if not rel:
            errors.append(f"finding #{idx}: missing path")
            continue
        if rel not in line_cache:
            target = repo / rel
            if not target.is_file():
                line_cache[rel] = None
            else:
                line_cache[rel] = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        max_lines = line_cache[rel]
        if max_lines is None:
            errors.append(f"finding #{idx}: file does not exist in repo: {rel}")
            continue
        for key in ("line", "start_line", "end_line"):
            val = item.get(key)
            if val is None or val == 0:
                continue
            if not isinstance(val, int) or val < 1 or val > max_lines:
                errors.append(f"finding #{idx}: {rel}:{val} out of range (1..{max_lines})")
        start_l = item.get("start_line")
        end_l = item.get("end_line")
        if isinstance(start_l, int) and isinstance(end_l, int) and start_l > 0 and end_l > 0 and end_l < start_l:
            errors.append(f"finding #{idx}: {rel}:{start_l}-{end_l} has end_line < start_line")
    return errors


def cmd_verify(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    repo = Path(args.repo).resolve() if args.repo else Path(plan["repo"])
    expected = [item["path"] for item in plan.get("reviewable", [])]

    reviewed = set(args.reviewed or [])
    skipped: dict[str, str] = {}
    for entry in args.skipped or []:
        if "=" not in entry:
            raise SystemExit(f"--skipped expects <path>=<reason>, got: {entry}")
        path_s, reason = entry.split("=", 1)
        if not reason.strip():
            raise SystemExit(f"--skipped requires a non-empty reason for {path_s}")
        skipped[path_s] = reason.strip()

    if args.all_reviewed:
        for p in expected:
            if p not in skipped:
                reviewed.add(p)

    missing = [p for p in expected if p not in reviewed and p not in skipped]
    pos_errors = verify_positions(repo, Path(args.findings)) if args.findings else []

    total = len(expected)
    rev_count = sum(1 for p in expected if p in reviewed)
    skip_count = sum(1 for p in expected if p in skipped and p not in reviewed)
    coverage_rate = round((rev_count / total), 4) if total else 1.0
    ok = (len(missing) == 0) and (len(pos_errors) == 0)

    result = {
        "ok": ok,
        "total_files": total,
        "reviewed_files": rev_count,
        "skipped_files": skip_count,
        "excluded_files": plan.get("excluded_count", 0),
        "coverage_rate": coverage_rate,
        "missing_files": missing,
        "skipped": skipped,
        "position_errors": pos_errors,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"coverage: {rev_count}/{total} reviewable files "
            f"({plan.get('excluded_count', 0)} excluded, {skip_count} skipped, rate={coverage_rate:.0%})"
        )
        for p in missing:
            print(f"  MISSING: {p}")
        for err in pos_errors:
            print(f"  POSITION: {err}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Classify and batch changed/untracked files before review")
    p_plan.add_argument("repo", nargs="?", default=".")
    p_plan.add_argument("--repo", dest="repo_flag", default=None)
    p_plan.add_argument("--diff", default=None, help="Read unified diff from file instead of git")
    p_plan.add_argument("--base")
    p_plan.add_argument("--head")
    p_plan.add_argument("--include-untracked", action="store_true")
    p_plan.add_argument("--max-batch-files", type=int, default=10)
    p_plan.add_argument("--max-batch-lines", type=int, default=400)
    p_plan.add_argument("--max-file-lines", type=int, default=1500)
    p_plan.add_argument("--out")
    p_plan.add_argument("--json", action="store_true")

    p_verify = sub.add_parser("verify", help="Verify 100%% reviewable-file accounting and finding line positions")
    p_verify.add_argument("plan")
    p_verify.add_argument("--repo")
    p_verify.add_argument("--reviewed", nargs="*")
    p_verify.add_argument("--skipped", nargs="*")
    p_verify.add_argument("--all-reviewed", action="store_true")
    p_verify.add_argument("--findings")
    p_verify.add_argument("--json", action="store_true")

    opts = parser.parse_args()
    if opts.cmd == "plan":
        return cmd_plan(opts)
    return cmd_verify(opts)


if __name__ == "__main__":
    sys.exit(main())
