#!/usr/bin/env python3
"""Contained disk & memory hygiene cleanup helper for deepmodebot repositories.

    python self_cleanup.py --root <repo> [--apply] [--max-age-hours 24] [--keep-surfaces 5] [--prune-captures] [--prune-worktrees] [--json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ASSETS_DIR = Path(__file__).resolve().parent.parent
_CANDIDATE_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ROOT = _CANDIDATE_REPO_ROOT if (_CANDIDATE_REPO_ROOT / ".git").exists() else Path.cwd()

BYTECODE_DIRS = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
})
PROTECTED_WALK_DIRS = frozenset({
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
})
KNOWN_SCRATCH_SUBDIRS = frozenset({
    "tmp",
    "gen-ui",
    "self-grill",
    "mobbin",
    "trending",
    "tournament",
    "arena",
    "evidence",
    "backup",
})


def _load_self_grill():
    path = ASSETS_DIR / "self-grill" / "self_grill.py"
    spec = importlib.util.spec_from_file_location("cleanup_self_grill", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def dir_bytes(path: Path) -> int:
    if not path.exists() or path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for fn in files:
            fp = Path(root) / fn
            if not fp.is_symlink():
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
    return total


def newest_mtime(path: Path) -> float:
    try:
        latest = path.stat().st_mtime
    except OSError:
        return 0.0
    if path.is_dir() and not path.is_symlink():
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
            for fn in files:
                fp = Path(root) / fn
                if not fp.is_symlink():
                    try:
                        latest = max(latest, fp.stat().st_mtime)
                    except OSError:
                        pass
    return latest


def _handle_remove_readonly(func, path, _exc_info) -> None:
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _safe_remove(target: Path, safe_root: Path, ensure_contained) -> int:
    import stat
    ensure_contained(target, safe_root)
    reclaimed = dir_bytes(target)
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target, onerror=_handle_remove_readonly)
    elif target.is_file() and not target.is_symlink():
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        target.unlink(missing_ok=True)
    return reclaimed


def _is_clean_worktree(wt_path: Path) -> bool:
    res = subprocess.run(
        ["git", "-C", str(wt_path), "--no-optional-locks", "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=NO_WINDOW,
    )
    return res.returncode == 0 and res.stdout.strip() == ""


def run_self_cleanup(
    root: Path,
    apply: bool = False,
    max_age_hours: float = 24.0,
    keep_surfaces: int = 5,
    prune_captures: bool = False,
    prune_worktrees: bool = False,
) -> dict:
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    now = time.time()
    cutoff = now - max(0.0, max_age_hours) * 3600.0

    scratch_dir = safe_root / ".scratch"
    scratch_before = dir_bytes(scratch_dir)
    planned: list[dict] = []
    protected_large: list[dict] = []

    for cur_root, dirs, _files in os.walk(safe_root):
        cur_path = Path(cur_root)
        next_dirs: list[str] = []
        for d in sorted(dirs):
            dp = cur_path / d
            if dp.is_symlink() or d in PROTECTED_WALK_DIRS:
                continue
            if d in BYTECODE_DIRS:
                sz = dir_bytes(dp)
                planned.append({"kind": "bytecode_cache", "path": dp.relative_to(safe_root).as_posix(), "bytes": sz, "_abs": dp})
                continue
            if dp != scratch_dir:
                next_dirs.append(d)
        dirs[:] = next_dirs

    if scratch_dir.is_dir() and not scratch_dir.is_symlink():
        tmp_dir = scratch_dir / "tmp"
        if tmp_dir.is_dir() and not tmp_dir.is_symlink():
            for child in sorted(tmp_dir.iterdir()):
                if child.is_symlink():
                    continue
                if newest_mtime(child) <= cutoff:
                    planned.append({"kind": "scratch_tmp", "path": child.relative_to(safe_root).as_posix(), "bytes": dir_bytes(child), "_abs": child})

        gen_dir = scratch_dir / "gen-ui"
        if gen_dir.is_dir() and not gen_dir.is_symlink():
            surfaces = [c for c in gen_dir.iterdir() if c.is_dir() and not c.is_symlink()]
            surfaces.sort(key=newest_mtime, reverse=True)
            for stale in surfaces[max(0, keep_surfaces):]:
                planned.append({"kind": "stale_gen_ui", "path": stale.relative_to(safe_root).as_posix(), "bytes": dir_bytes(stale), "_abs": stale})

        grill_dir = scratch_dir / "self-grill"
        if grill_dir.is_dir() and not grill_dir.is_symlink():
            ledgers = [c for c in grill_dir.iterdir() if c.is_dir() and not c.is_symlink()]
            ledgers.sort(key=newest_mtime, reverse=True)
            for idx, entry in enumerate(ledgers):
                if idx >= 3 and newest_mtime(entry) <= cutoff:
                    planned.append({"kind": "stale_self_grill", "path": entry.relative_to(safe_root).as_posix(), "bytes": dir_bytes(entry), "_abs": entry})

        if prune_captures:
            mobbin_dir = scratch_dir / "mobbin"
            if mobbin_dir.is_dir() and not mobbin_dir.is_symlink():
                for cap_name in ("captures", "live_sites"):
                    cap_path = mobbin_dir / cap_name
                    if cap_path.is_dir() and not cap_path.is_symlink():
                        planned.append({"kind": " transient_captures".strip(), "path": cap_path.relative_to(safe_root).as_posix(), "bytes": dir_bytes(cap_path), "_abs": cap_path})
            for bak in sorted(scratch_dir.glob("*.tar.gz")):
                if bak.is_file() and not bak.is_symlink() and newest_mtime(bak) <= cutoff:
                    planned.append({"kind": "stale_scratch_archive", "path": bak.relative_to(safe_root).as_posix(), "bytes": dir_bytes(bak), "_abs": bak})
            bak_dir = scratch_dir / "backup"
            if bak_dir.is_dir() and not bak_dir.is_symlink() and newest_mtime(bak_dir) <= cutoff:
                planned.append({"kind": "stale_scratch_backup", "path": bak_dir.relative_to(safe_root).as_posix(), "bytes": dir_bytes(bak_dir), "_abs": bak_dir})

        for top in sorted(scratch_dir.iterdir()):
            if top.name == ".gitignore" or top.name in KNOWN_SCRATCH_SUBDIRS or top.suffix == ".db":
                continue
            sz = dir_bytes(top)
            if sz >= 10 * 1024 * 1024:
                protected_large.append({
                    "path": top.relative_to(safe_root).as_posix(),
                    "bytes": sz,
                    "mb": round(sz / (1024 * 1024), 2),
                    "reason": "unrecognized large scratch folder preserved; confirm with user before deleting",
                })

    if prune_worktrees:
        wt_root = safe_root / ".worktrees"
        if wt_root.is_dir() and not wt_root.is_symlink():
            for wt in sorted(wt_root.iterdir()):
                if wt.is_dir() and not wt.is_symlink() and newest_mtime(wt) <= cutoff and _is_clean_worktree(wt):
                    planned.append({"kind": "clean_worktree", "path": wt.relative_to(safe_root).as_posix(), "bytes": dir_bytes(wt), "_abs": wt})

    bytes_freed = 0
    removed: list[dict] = []
    for item in planned:
        target = item.pop("_abs")
        if apply:
            if item["kind"] == "clean_worktree":
                subprocess.run(
                    ["git", "-C", str(safe_root), "worktree", "remove", "--force", str(target)],
                    capture_output=True,
                    check=False,
                    creationflags=NO_WINDOW,
                )
                if target.exists():
                    bytes_freed += _safe_remove(target, safe_root, sg.ensure_contained)
                else:
                    bytes_freed += item["bytes"]
            else:
                bytes_freed += _safe_remove(target, safe_root, sg.ensure_contained)
            removed.append(item)
        else:
            bytes_freed += item["bytes"]
            removed.append(item)

    scratch_after = dir_bytes(scratch_dir) if apply else max(0, scratch_before - sum(i["bytes"] for i in removed if i["path"].startswith(".scratch/")))
    return {
        "root": str(safe_root),
        "applied": apply,
        "items_count": len(removed),
        "bytes_freed": bytes_freed,
        "mb_freed": round(bytes_freed / (1024 * 1024), 2),
        "scratch_mb_before": round(scratch_before / (1024 * 1024), 2),
        "scratch_mb_after": round(scratch_after / (1024 * 1024), 2),
        "items": removed,
        "protected_large_scratch": protected_large,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Safe bounded disk and scratch cleanup for deepmodebot.")
    p.add_argument("--root", default=str(DEFAULT_ROOT), help="Repository root directory (defaults to enclosing repo root or cwd).")
    p.add_argument("--apply", action="store_true", help="Delete matched ephemeral items (default is dry-run preview).")
    p.add_argument("--max-age-hours", type=float, default=24.0, help="Minimum age in hours before pruning tmp/ledger artifacts.")
    p.add_argument("--keep-surfaces", type=int, default=5, help="Number of most recent .scratch/gen-ui surfaces to retain.")
    p.add_argument("--prune-captures", action="store_true", help="Also remove transient raw screenshot capture folders under .scratch/mobbin.")
    p.add_argument("--prune-worktrees", action="store_true", help="Also prune clean stale git worktrees under .worktrees/.")
    p.add_argument("--json", action="store_true", help="Emit JSON output.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    res = run_self_cleanup(
        Path(args.root),
        apply=args.apply,
        max_age_hours=args.max_age_hours,
        keep_surfaces=args.keep_surfaces,
        prune_captures=args.prune_captures,
        prune_worktrees=args.prune_worktrees,
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        mode = "APPLIED" if res["applied"] else "DRY-RUN"
        print(
            f"self_cleanup [{mode}]: {res['items_count']} item(s), "
            f"{res['mb_freed']} MB {'freed' if res['applied'] else 'reclaimable'} "
            f"(.scratch {res['scratch_mb_before']} MB -> {res['scratch_mb_after']} MB)"
        )
        for item in res["items"][:15]:
            print(f"  - [{item['kind']}] {item['path']} ({round(item['bytes'] / 1024, 1)} KB)")
        for prot in res["protected_large_scratch"]:
            print(f"  ! [preserved] {prot['path']} ({prot['mb']} MB): {prot['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
