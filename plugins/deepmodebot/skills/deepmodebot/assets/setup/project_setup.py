#!/usr/bin/env python3
"""Automatic one-command deepmodebot project bootstrapper (CI, XML policy, memory DB, AGENTS.md/CLAUDE.md).

    python -B project_setup.py [--root <repo>] [--check] [--json]

Creates only what is missing and refreshes the managed deepmodebot block in AGENTS.md / CLAUDE.md
without overwriting user rules outside the markers:
- .deepmodebot/ci.yml       (GitHub-Actions-style local CI synthesized from detected repo checks)
- .deepmodebot/policy.xml   (compact XML governance contract)
- .scratch/deepmode-memory.db (SQLite WAL+mmap+FTS5 project memory seeded with P0 project invariants)
- AGENTS.md + CLAUDE.md     (managed block enforcing local CI, containment, and project memory)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.dont_write_bytecode = True

ASSETS_DIR = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    path = ASSETS_DIR / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _synthesize_ci_yml(repo_name: str, report: dict) -> str:
    layers = report.get("layers") or {}
    static = list(layers.get("static_checks") or [])
    tests = list(layers.get("test_checks") or [])
    lines = [
        f"name: {repo_name}-local-ci",
        "on: [local-edit, pre-pr, pre-merge]",
        "",
        "env:",
        '  PYTHONDONTWRITEBYTECODE: "1"',
        "",
        "jobs:",
    ]
    created_jobs: list[str] = []
    if static:
        created_jobs.append("checks")
        lines += ["  checks:", "    timeout-minutes: 3", "    steps:"]
        for i, cmd in enumerate(static, 1):
            lines += [f"      - name: static-check-{i}", f"        run: {json.dumps(cmd)}"]
    if tests:
        created_jobs.append("tests")
        lines += ["  tests:", "    timeout-minutes: 5", "    steps:"]
        for i, cmd in enumerate(tests, 1):
            lines += [f"      - name: test-suite-{i}", f"        run: {json.dumps(cmd)}"]
    if not created_jobs:
        created_jobs.append("sanity")
        lines += [
            "  sanity:",
            "    timeout-minutes: 2",
            "    steps:",
            "      - name: verify-git-tree",
            "        run: git status --short",
        ]
    created_jobs.append("anti-slop")
    slop_cmd = f"python -B {json.dumps(str(ASSETS_DIR / 'local-ci' / 'slop_gate.py'))} --root ."
    lines += [
        "  anti-slop:",
        "    timeout-minutes: 2",
        "    steps:",
        "      - name: zero-token-slop-gate",
        f"        run: {json.dumps(slop_cmd)}",
        "  gate:",
        f"    needs: [{', '.join(created_jobs)}]",
        "    timeout-minutes: 1",
        "    steps:",
        "      - name: local-ci-complete",
        '        run: python -B -c "print(\'local-ci: ok\')"',
        "",
    ]
    return "\n".join(lines)


def _synthesize_policy_xml(repo_name: str) -> str:
    safe_name = xml_escape(repo_name)
    return (
        f'<deepmode-policy version="1.0" repo="{safe_name}">\n'
        '  <enforcement>\n'
        '    <ci file=".deepmodebot/ci.yml" mode="local-only" required="true">\n'
        '      Run local CI (`local_ci.py run --cached`) before reporting done or opening a PR.\n'
        '    </ci>\n'
        '    <instructions source="AGENTS.md" claude="CLAUDE.md"/>\n'
        '    <ui-gate viewports="1440x900,390x844" rounds="2"/>\n'
        '  </enforcement>\n'
        '  <containment scratch=".scratch" temp=".scratch/tmp" worktrees=".worktrees" bytecode="off"/>\n'
        '  <memory engine="sqlite-wal-fts5" db=".scratch/deepmode-memory.db" max-records="500" recall-budget-tokens="800" format="xml"/>\n'
        '  <hard-stops>\n'
        '    <stop>force-push or history rewrite on shared/default branch</stop>\n'
        '    <stop>writes outside project root</stop>\n'
        '    <stop>billing API keys (use subscriptions only)</stop>\n'
        '  </hard-stops>\n'
        '</deepmode-policy>\n'
    )


def _synthesize_dependabot_yml(root: Path) -> str:
    ecosystems: list[str] = []
    if (root / "package.json").is_file():
        ecosystems.append("npm")
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        ecosystems.append("pip")
    if (root / "Cargo.toml").is_file():
        ecosystems.append("cargo")
    if (root / "go.mod").is_file():
        ecosystems.append("gomod")
    if (root / ".github" / "workflows").is_dir():
        ecosystems.append("github-actions")
    if not ecosystems:
        ecosystems.append("github-actions")
    lines = ["version: 2", "updates:"]
    for eco in ecosystems:
        lines += [
            f'  - package-ecosystem: "{eco}"',
            '    directory: "/"',
            "    schedule:",
            '      interval: "weekly"',
            '      day: "monday"',
            "    open-pull-requests-limit: 5",
            "    cooldown:",
            "      default-days: 7",
            "    groups:",
            f"      {eco}-minor-and-patch:",
            "        update-types:",
            '          - "minor"',
            '          - "patch"',
            '    labels: ["dependencies"]',
            "",
        ]
    return "\n".join(lines)


def check_setup(root: Path) -> dict:
    agents_mod = _load("dmb_agents_md", "agents-md/agents_md.py")
    mem_mod = _load("dmb_project_memory", "memory/project_memory.py")
    r = Path(agents_mod.project_root(str(root)))
    missing: list[str] = []
    if not (r / ".deepmodebot/ci.yml").is_file():
        missing.append(".deepmodebot/ci.yml")
    if not (r / ".deepmodebot/policy.xml").is_file():
        missing.append(".deepmodebot/policy.xml")
    if not mem_mod.db_path_for(r).is_file():
        missing.append(".scratch/deepmode-memory.db")
    plan = agents_mod.planned(str(r), False)
    for name, (_, cur, wanted) in plan.items():
        if cur != wanted:
            missing.append(name)
    return {"root": str(r), "initialized": not missing, "missing": missing}


def _install_pre_commit_hook(root: Path) -> str | None:
    if any((root / name).exists() for name in (".husky", ".pre-commit-config.yaml", "lefthook.yml")):
        return "skipped pre-commit hook (existing hook manager detected)"
    git_dir = root / ".git"
    if not git_dir.is_dir() or git_dir.is_symlink():
        return None
    hooks_path = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"], capture_output=True,
                                text=True, check=False, timeout=10).stdout.strip()
    if hooks_path:
        return (f"skipped .git/hooks/pre-commit: git runs hooks from core.hooksPath={hooks_path}, so add "
                f"`python3 -B {(ASSETS_DIR / 'rules' / 'rule_ledger.py').as_posix()} check --root . --staged` and "
                f"`python3 -B {(ASSETS_DIR / 'local-ci' / 'slop_gate.py').as_posix()} --root . --staged` to its pre-commit")
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    if hook.is_symlink():
        raise SystemExit(f"refusing symlinked hook: {hook}")
    if hook.is_file() and "deepmodebot:slop-gate" not in hook.read_text(encoding="utf-8", errors="replace"):
        return "skipped .git/hooks/pre-commit (custom hook already exists)"
    slop_py = (ASSETS_DIR / "local-ci" / "slop_gate.py").resolve().as_posix()
    rules_py = (ASSETS_DIR / "rules" / "rule_ledger.py").resolve().as_posix()
    native_bin = (ASSETS_DIR.parents[4] / "native" / "dmb-gate" / "target" / "release" / "dmb-gate").resolve().as_posix()
    script = (
        "#!/bin/sh\n"
        "# deepmodebot:slop-gate\n"
        "set -e\n"
        "rules_check() {\n"
        "  [ -f .deepmodebot/rules/ledger.json ] || git cat-file -e HEAD:.deepmodebot/rules/ledger.json 2>/dev/null || return 0\n"
        f'  if command -v py >/dev/null 2>&1; then py -3 -B "{rules_py}" check --root . --staged; '
        f'else python3 -B "{rules_py}" check --root . --staged; fi\n'
        "}\n"
        f'if [ -x "{native_bin}.exe" ]; then rules_check; exec "{native_bin}.exe" --root . --staged; fi\n'
        f'if [ -x "{native_bin}" ]; then rules_check; exec "{native_bin}" --root . --staged; fi\n'
        f'if command -v py >/dev/null 2>&1; then exec py -3 -B "{slop_py}" --root . --staged; fi\n'
        f'exec python3 -B "{slop_py}" --root . --staged\n'
    )
    hook.write_text(script, encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    return "installed .git/hooks/pre-commit"


def bootstrap_project(root: Path, *, with_dependabot: bool = False, install_hooks: bool = False) -> dict:
    agents_mod = _load("dmb_agents_md", "agents-md/agents_md.py")
    mem_mod = _load("dmb_project_memory", "memory/project_memory.py")
    r = Path(agents_mod.project_root(str(root)))
    report = agents_mod.audit_repo(str(r))
    dm_dir = r / ".deepmodebot"
    if dm_dir.is_symlink():
        raise SystemExit(f"refusing symlinked directory: {dm_dir}")
    dm_dir.mkdir(parents=True, exist_ok=True)

    actions: list[str] = []
    ci_path = dm_dir / "ci.yml"
    if ci_path.is_symlink():
        raise SystemExit(f"refusing symlinked file: {ci_path}")
    if not ci_path.is_file():
        ci_path.write_text(_synthesize_ci_yml(r.name, report), encoding="utf-8", newline="\n")
        actions.append("created .deepmodebot/ci.yml")

    pol_path = dm_dir / "policy.xml"
    if pol_path.is_symlink():
        raise SystemExit(f"refusing symlinked file: {pol_path}")
    if not pol_path.is_file():
        pol_path.write_text(_synthesize_policy_xml(r.name), encoding="utf-8", newline="\n")
        actions.append("created .deepmodebot/policy.xml")

    dbf = mem_mod.db_path_for(r)
    was_new_db = not dbf.is_file()
    mem_mod.put_memory(
        r,
        key="project:ci-gate",
        kind="convention",
        priority=0,
        tags="ci,setup,policy",
        source=".deepmodebot/ci.yml",
        content="Enforce local CI (.deepmodebot/ci.yml) via local_ci.py run --cached and keep all scratch/temp inside .scratch/.",
    )
    if was_new_db:
        actions.append("initialized .scratch/deepmode-memory.db")
    if with_dependabot:
        gh_dir = r / ".github"
        if gh_dir.is_symlink():
            raise SystemExit(f"refusing symlinked directory: {gh_dir}")
        gh_dir.mkdir(parents=True, exist_ok=True)
        dep_path = gh_dir / "dependabot.yml"
        if dep_path.is_symlink():
            raise SystemExit(f"refusing symlinked file: {dep_path}")
        if not dep_path.is_file():
            dep_path.write_text(_synthesize_dependabot_yml(r), encoding="utf-8", newline="\n")
            actions.append("created .github/dependabot.yml")
    if install_hooks:
        hook_note = _install_pre_commit_hook(r)
        if hook_note:
            actions.append(hook_note)

    plan = agents_mod.planned(str(r), False)
    rules_mod = _load("dmb_rule_ledger", "rules/rule_ledger.py")
    owner_approval = rules_mod.ledger_enabled(r)
    for name, (path, current, wanted) in plan.items():
        if wanted == current:
            continue
        if owner_approval:
            prop = rules_mod.propose(r, name, wanted.encode("utf-8"), "refresh the deepmodebot managed block", by="deepmodebot init")
            actions.append(f"proposed {name} as [{prop['id']}] for the owner (`deepmodebot rules approve {prop['id']}`)")
        else:
            agents_mod.write(path, wanted)
            actions.append(f"{'updated' if current else 'created'} {name}")

    return {"root": str(r), "ok": True, "actions": actions, "db": str(dbf)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Auto-bootstrap deepmodebot CI, XML policy, memory DB, and AGENTS/CLAUDE instructions.")
    p.add_argument("--root", default=".")
    p.add_argument("--check", action="store_true", help="Read-only check; exit 1 if project setup is incomplete.")
    p.add_argument("--dependabot", action="store_true", help="Also generate .github/dependabot.yml with grouped updates and 7-day cooldown.")
    p.add_argument("--install-hooks", action="store_true", help="Install lightweight .git/hooks/pre-commit running slop_gate --staged.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()

    if args.check:
        res = check_setup(root)
        print(json.dumps(res, indent=2) if args.json else ("ok" if res["initialized"] else "missing: " + ", ".join(res["missing"])))
        return 0 if res["initialized"] else 1
    res = bootstrap_project(root, with_dependabot=args.dependabot, install_hooks=args.install_hooks)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"deepmodebot init ({res['root']}): " + (", ".join(res["actions"]) if res["actions"] else "already up to date"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
