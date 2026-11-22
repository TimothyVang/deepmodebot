#!/usr/bin/env python3
"""Deterministic weekly-quota & subagent-multiplication guard for deepmodebot.

Prevents the 4 compounding quota killers observed in multi-agent runs:
1. Stacking outer orchestrators (/teamwork, /swarm) with nested multi-seat review/panel waves.
2. Defaulting read-only scouts, mechanical helpers, and heartbeats to top-tier 'inherit' models.
3. Spawning 4 separate cold-cache pr-review lens agents + 1 Prosecutor + 3 panel verifiers per round.
4. Re-running full 3-agent waves on minor fixes or re-reading 10k+ LOC cold after 429 resets.

    python quota_guard.py plan --root <repo> --size S|M|L|none [--mode <mode>] [--diff-lines <n>] [--sensitive] [--outer-harness auto|none|teamwork|swarm|subagent] [--lean] [--json]
    python quota_guard.py checkpoint save --root <repo> --slug <slug> [--done <step>...] [--finding <item>...] [--anchor <file:lines>...] [--cmd-ok <cmd>...] [--json]
    python quota_guard.py checkpoint load --root <repo> --slug <slug> [--json]
    python quota_guard.py audit-transcripts --brain-dir <path> [--conv-id <uuid>] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent

OUTER_HARNESS_ENV_KEYS = (
    ("teamwork", ("TEAMWORK_RUN_ID", "TEAMWORK_ROLE", "TEAMWORK_ORCHESTRATOR")),
    ("swarm", ("SWARM_ID", "AGY_SWARM_MEMBER", "SWARM_WORKER")),
    ("subagent", ("DEEPMODEBOT_SUBAGENT_DEPTH", "AGY_PARENT_CONVERSATION_ID")),
)


def _load_self_grill():
    path = ASSETS_DIR / "self-grill" / "self_grill.py"
    spec = importlib.util.spec_from_file_location("qg_self_grill", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def detect_outer_harness(root: Path | None = None, explicit: str = "auto") -> str:
    choice = (explicit or "auto").strip().lower()
    if choice in {"none", "teamwork", "swarm", "subagent"}:
        return choice
    for kind, keys in OUTER_HARNESS_ENV_KEYS:
        for k in keys:
            val = os.environ.get(k, "").strip()
            if val and val != "0":
                return kind
    cwd_norm = Path.cwd().as_posix().lower()
    if "/.agents/teamwork/" in cwd_norm or "/teamwork_worker" in cwd_norm:
        return "teamwork"
    if root is not None:
        root_norm = root.as_posix().lower()
        if "/.agents/teamwork/" in root_norm:
            return "teamwork"
    return "none"


def compute_quota_plan(
    size: str,
    mode: str = "feature",
    diff_lines: int = 0,
    is_sensitive: bool = False,
    outer_harness: str = "none",
    lean_mode: bool = False,
    is_merge_gate: bool = False,
) -> dict:
    norm_size = size if size in ("S", "M", "L", "none") else "M"
    nested = outer_harness in {"teamwork", "swarm", "subagent"}

    subagent_models = {
        "scout": "flash_lite",
        "comment-sicko": "flash",
        "mechanical": "flash",
        "slice_worker": "flash" if (norm_size in ("S", "M") or lean_mode) else "inherit",
        "reviewer": "inherit",
        "security-reviewer": "inherit",
    }

    if nested:
        return {
            "budget_mode": "nested-single-pass",
            "outer_harness": outer_harness,
            "nested_anti_stacking": True,
            "max_subagents_per_task": 0,
            "max_review_subagents": 0,
            "panel_seats": 0,
            "max_review_rounds": 1,
            "max_parallel_worktrees": 1,
            "review_strategy": "inline-4-lens-plus-deterministic-scripts",
            "rereview_strategy": "delta-only-inline",
            "subagent_models": subagent_models,
            "rationale": (
                f"Outer orchestrator '{outer_harness}' already owns multi-agent verification waves; "
                "suppressing nested subagent fan-out prevents the 20-30x multiplier."
            ),
        }

    if norm_size in ("none", "S"):
        return {
            "budget_mode": "inline-zero-spawn",
            "outer_harness": "none",
            "nested_anti_stacking": False,
            "max_subagents_per_task": 0 if norm_size == "S" else 1,
            "max_review_subagents": 0,
            "panel_seats": 1 if (norm_size == "S" and is_merge_gate) else 0,
            "max_review_rounds": 1,
            "max_parallel_worktrees": 1,
            "review_strategy": "author-inline-checklist",
            "rereview_strategy": "delta-only-inline",
            "subagent_models": subagent_models,
            "rationale": "Size S / discovery tasks run inline with deterministic scripts and zero cold-cache subagent overhead.",
        }

    if lean_mode or (norm_size == "M" and not is_sensitive and diff_lines <= 500):
        return {
            "budget_mode": "lean-single-bundle",
            "outer_harness": "none",
            "nested_anti_stacking": False,
            "max_subagents_per_task": 1,
            "max_review_subagents": 1,
            "panel_seats": 1 if is_merge_gate else 0,
            "max_review_rounds": 2,
            "max_parallel_worktrees": 1 if lean_mode else 2,
            "review_strategy": "single-prosecutor-bundle-all-4-lenses",
            "rereview_strategy": "delta-only-reuse-warm-reviewer",
            "subagent_models": subagent_models,
            "rationale": (
                "Pack 1 prosecutor-bundle.md and run at most 1 read-only reviewer covering all 4 lenses + Hotspot Sieve "
                "(replaces 4 separate cold-cache lens subagents + 3-seat mid-flight panels; ~85% lower token burn)."
            ),
        }

    max_rev = 2 if (is_sensitive or diff_lines > 800) else 1
    return {
        "budget_mode": "capped-hardcore-l",
        "outer_harness": "none",
        "nested_anti_stacking": False,
        "max_subagents_per_task": 3 if not is_merge_gate else 5,
        "max_review_subagents": max_rev,
        "panel_seats": 3 if is_merge_gate else 0,
        "max_review_rounds": 2,
        "max_parallel_worktrees": 2,
        "review_strategy": "bundle-prosecutor-plus-security-split" if max_rev == 2 else "single-prosecutor-bundle-all-4-lenses",
        "rereview_strategy": "delta-only-1-verifier-on-new-hunks",
        "subagent_models": subagent_models,
        "rationale": (
            "Hardcore L cap: scouts pinned to flash_lite, review consolidated into 1-2 bundle passes (never 4 cold diff reads), "
            "3-seat panel reserved strictly for final green merge SHA, Round 2+ restricted to git diff <last_sha>..HEAD, "
            "and parallel worktrees capped at 2 to prevent 429 respawn storms."
        ),
    }


def save_checkpoint(
    root: Path,
    slug: str,
    done_steps: list[str],
    open_findings: list[str],
    anchors: list[str],
    verified_cmds: list[str],
) -> dict:
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    if not sg.SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug {slug!r}: use lowercase kebab-case")
    out_dir = sg.ensure_contained(safe_root / ".scratch" / "quota-guard", safe_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / f"{slug}-checkpoint.json"
    head_res = sg._run_git(safe_root, ["rev-parse", "--short", "HEAD"]) if sg._is_git_root_or_worktree(safe_root) else None
    head_sha = head_res.stdout.strip() if (head_res and head_res.returncode == 0) else None
    payload = {
        "slug": slug,
        "head_sha": head_sha,
        "tree_digest": sg.compute_tree_digest(safe_root),
        "updated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "done_steps": list(done_steps),
        "open_findings": list(open_findings),
        "hotspot_anchors": list(anchors),
        "verified_commands": list(verified_cmds),
    }
    sg.atomic_write_text(ckpt_path, json.dumps(payload, indent=2) + "\n", safe_root)
    payload["checkpoint_path"] = str(ckpt_path)
    return payload


def load_checkpoint(root: Path, slug: str) -> dict:
    sg = _load_self_grill()
    safe_root = sg.reject_unsafe_root(root)
    if not sg.SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug {slug!r}: use lowercase kebab-case")
    ckpt_path = sg.ensure_contained(safe_root / ".scratch" / "quota-guard" / f"{slug}-checkpoint.json", safe_root)
    if not ckpt_path.is_file():
        raise SystemExit(f"checkpoint not found: {ckpt_path}")
    data = json.loads(ckpt_path.read_text(encoding="utf-8"))
    live_digest = sg.compute_tree_digest(safe_root)
    data["stale_tree"] = (data.get("tree_digest") != live_digest)
    data["live_tree_digest"] = live_digest
    data["checkpoint_path"] = str(ckpt_path)
    return data


def audit_transcripts(brain_dir: Path, root_conv_id: str | None = None) -> dict:
    resolved = brain_dir.resolve()
    if not resolved.is_dir():
        raise SystemExit(f"brain directory not found: {resolved}")

    uuid_re = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    if root_conv_id and (resolved / root_conv_id).is_dir():
        seen_ids = {root_conv_id.lower()}
        queue = [resolved / root_conv_id]
        target_dirs: list[Path] = []
        while queue:
            cur = queue.pop(0)
            target_dirs.append(cur)
            tpath = cur / ".system_generated" / "logs" / "transcript.jsonl"
            if not tpath.is_file():
                continue
            try:
                raw_txt = tpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for cid in uuid_re.findall(raw_txt):
                cid_low = cid.lower()
                if cid_low not in seen_ids and (resolved / cid).is_dir():
                    seen_ids.add(cid_low)
                    queue.append(resolved / cid)
    else:
        target_dirs = [d for d in sorted(resolved.iterdir()) if d.is_dir()]
    conv_count = 0
    total_steps = 0
    total_bytes = 0
    subagent_spawns = 0
    inherit_spawns = 0
    light_spawns = 0
    coding_spawns = 0
    overhead_spawns = 0
    respawn_suffix_hits = 0

    overhead_role_re = re.compile(
        r"(?<![A-Za-z0-9])(?:orchestrator|explorer|scout|reviewer|challenger|auditor|verifier|judge|sentinel|interviewer|monitor|heartbeat)(?![A-Za-z0-9])",
        re.I,
    )
    respawn_re = re.compile(r"(?:_[rR][2-9](?![A-Za-z0-9])|(?<![A-Za-z0-9])round\s*[2-9](?![A-Za-z0-9]))", re.I)

    for d in target_dirs:
        tfile = d / ".system_generated" / "logs" / "transcript.jsonl"
        if not tfile.is_file():
            continue
        conv_count += 1
        try:
            total_bytes += tfile.stat().st_size
            lines = tfile.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        total_steps += len(lines)
        for line in lines:
            if '"invoke_subagent"' not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            for tc in obj.get("tool_calls") or []:
                if tc.get("name") != "invoke_subagent":
                    continue
                subagent_spawns += 1
                args = tc.get("args") or {}
                model = str(args.get("Model") or "inherit").strip().strip('"').lower() or "inherit"
                role = str(args.get("Role") or "").strip().strip('"')
                tname = str(args.get("TypeName") or "").strip().strip('"').lower()
                if model in {"flash", "flash_lite"}:
                    light_spawns += 1
                else:
                    inherit_spawns += 1
                if overhead_role_re.search(role) or tname in {"scout", "reviewer", "security-reviewer", "research", "teamwork"}:
                    overhead_spawns += 1
                else:
                    coding_spawns += 1
                if respawn_re.search(role):
                    respawn_suffix_hits += 1

    overhead_pct = round((overhead_spawns / subagent_spawns) * 100.0, 1) if subagent_spawns else 0.0
    inherit_pct = round((inherit_spawns / subagent_spawns) * 100.0, 1) if subagent_spawns else 0.0
    warnings: list[str] = []
    if subagent_spawns > 12:
        warnings.append(f"HIGH_SUBAGENT_MULTIPLIER: {subagent_spawns} subagents spawned; enable lean/single-bundle mode and avoid /teamwork + deepmodebot stacking.")
    if subagent_spawns >= 4 and overhead_pct > 75.0:
        warnings.append(f"OVERHEAD_DOMINATED: {overhead_pct}% ({overhead_spawns}/{subagent_spawns}) of spawns are orchestrator/scout/review overhead rather than coding workers.")
    if subagent_spawns >= 3 and inherit_pct > 70.0:
        warnings.append(f"HEAVY_MODEL_INHERITANCE: {inherit_pct}% ({inherit_spawns}/{subagent_spawns}) of subagents inherited the primary model; pin scouts/mechanical helpers to flash_lite/flash.")
    if respawn_suffix_hits > 0:
        warnings.append(f"RESPAWN_TAX: {respawn_suffix_hits} _r2/_r3 retry/recovery spawns detected; write .scratch/quota-guard checkpoints and cap parallel worktrees at <=2.")

    return {
        "conversations_scanned": conv_count,
        "total_steps": total_steps,
        "transcript_mb": round(total_bytes / (1024 * 1024), 2),
        "subagent_spawns": subagent_spawns,
        "coding_spawns": coding_spawns,
        "overhead_spawns": overhead_spawns,
        "overhead_pct": overhead_pct,
        "inherit_model_spawns": inherit_spawns,
        "light_model_spawns": light_spawns,
        "inherit_pct": inherit_pct,
        "respawn_hits": respawn_suffix_hits,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Weekly-quota and subagent-budget guard for deepmodebot.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Compute hard subagent, model-tier, and review-round budget for a task.")
    p_plan.add_argument("--root", default=None)
    p_plan.add_argument("--size", default="M", choices=("S", "M", "L", "none"))
    p_plan.add_argument("--mode", default="feature")
    p_plan.add_argument("--diff-lines", type=int, default=0)
    p_plan.add_argument("--sensitive", action="store_true")
    p_plan.add_argument("--outer-harness", default="auto", choices=("auto", "none", "teamwork", "swarm", "subagent"))
    p_plan.add_argument("--lean", action="store_true")
    p_plan.add_argument("--merge-gate", action="store_true")
    p_plan.add_argument("--json", action="store_true")

    p_ckpt = sub.add_parser("checkpoint", help="Save or load <2KB 429/compaction recovery state.")
    ckpt_sub = p_ckpt.add_subparsers(dest="ckpt_cmd", required=True)

    c_save = ckpt_sub.add_parser("save")
    c_save.add_argument("--root", required=True)
    c_save.add_argument("--slug", required=True)
    c_save.add_argument("--done", nargs="*", default=[])
    c_save.add_argument("--finding", nargs="*", default=[])
    c_save.add_argument("--anchor", nargs="*", default=[])
    c_save.add_argument("--cmd-ok", nargs="*", default=[])
    c_save.add_argument("--json", action="store_true")

    c_load = ckpt_sub.add_parser("load")
    c_load.add_argument("--root", required=True)
    c_load.add_argument("--slug", required=True)
    c_load.add_argument("--json", action="store_true")

    p_aud = sub.add_parser("audit-transcripts", help="Measure subagent multiplier, model inheritance, and overhead % across transcripts.")
    p_aud.add_argument("--brain-dir", required=True)
    p_aud.add_argument("--conv-id", default=None)
    p_aud.add_argument("--json", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "plan":
        root_p = Path(args.root).resolve() if args.root else None
        outer = detect_outer_harness(root=root_p, explicit=args.outer_harness)
        plan = compute_quota_plan(
            size=args.size,
            mode=args.mode,
            diff_lines=args.diff_lines,
            is_sensitive=args.sensitive,
            outer_harness=outer,
            lean_mode=args.lean,
            is_merge_gate=args.merge_gate,
        )
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(
                f"quota_plan [{plan['budget_mode']}]: max_subagents={plan['max_subagents_per_task']} "
                f"review={plan['review_strategy']} panel_seats={plan['panel_seats']} "
                f"worktrees<={plan['max_parallel_worktrees']}"
            )
        return 0

    if args.cmd == "checkpoint":
        if args.ckpt_cmd == "save":
            res = save_checkpoint(
                Path(args.root),
                slug=args.slug,
                done_steps=args.done,
                open_findings=args.finding,
                anchors=args.anchor,
                verified_cmds=args.cmd_ok,
            )
        else:
            res = load_checkpoint(Path(args.root), slug=args.slug)
        print(json.dumps(res, indent=2) if args.json else f"checkpoint: {res['checkpoint_path']} (digest={res['tree_digest']})")
        return 0

    res = audit_transcripts(Path(args.brain_dir), root_conv_id=args.conv_id)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(
            f"transcript_audit: convs={res['conversations_scanned']} steps={res['total_steps']} "
            f"mb={res['transcript_mb']} spawns={res['subagent_spawns']} "
            f"overhead={res['overhead_pct']}% inherit={res['inherit_pct']}%"
        )
        for w in res["warnings"]:
            print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
