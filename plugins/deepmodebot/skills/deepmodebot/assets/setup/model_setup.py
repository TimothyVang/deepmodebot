#!/usr/bin/env python3
"""Deterministic per-role model & reasoning-budget configurator (.deepmodebot/models.json).

    python -B model_setup.py inspect [--root <repo>] [--json]
    python -B model_setup.py plan [--root <repo>] [--budget large|medium|small] [--available s1,s2,...] [--json]
    python -B model_setup.py write [--root <repo>] [--budget large|medium|small] [--available s1,s2,...] [--set role=val] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

DEFAULTS_VERSION = 3
LADDER = ("low", "medium", "high", "xhigh")
BUDGET_DROP = {"large": 0, "medium": 1, "small": 2}
BUDGET_LABEL = {"large": "large (xhigh)", "medium": "medium (high)", "small": "small (medium)"}
ALIASES = frozenset({"inherit-parent", "auto"})

RETIRED_ROLES = frozenset({
    "hardest tasks", "hardest_tasks",
    "architect runners", "architect_runners",
    "reflect tooling", "reflect_tooling",
    "why investigators", "why_investigators",
})

PANEL_ROLES = frozenset({"arena_runners", "arena_cross_judge_pool", "interrogate_reviewers"})

DEFAULT_ROLES: dict[str, str | list[str]] = {
    "feature_refactoring": "claude-opus-5-5-xhigh-fast",
    "bug_fix": "claude-opus-5-5-xhigh-fast",
    "perf_issue": "claude-opus-5-5-xhigh-fast",
    "hillclimb": "claude-opus-5-5-xhigh-fast",
    "judgment_and_prose": "claude-opus-5-5-xhigh-fast",
    "arena_runners": [
        "claude-fable-5-2-high",
        "claude-opus-5-5-high-fast",
        "gemini-4-neon-xhigh",
    ],
    "arena_cross_judge_pool": [
        "claude-opus-5-5-high-fast",
        "gemini-4-neon-xhigh",
    ],
    "swarm_workers": "claude-opus-5-5-high-fast",
    "interrogate_reviewers": [
        "claude-fable-5-2-high",
        "claude-opus-5-5-high-fast",
        "gemini-4-neon-xhigh",
    ],
}

ROLE_ALIASES = {
    "feature, refactoring": "feature_refactoring",
    "bug-fix": "bug_fix",
    "perf-issue": "perf_issue",
    "judgment and prose": "judgment_and_prose",
    "arena runners": "arena_runners",
    "arena cross-judge pool": "arena_cross_judge_pool",
    "swarm workers": "swarm_workers",
    "interrogate reviewers": "interrogate_reviewers",
}


def canonical_role(name: str) -> str:
    clean = name.strip()
    return ROLE_ALIASES.get(clean, clean)


def vendor_of(slug: str) -> str:
    s = slug.lower()
    if s.startswith("claude-"):
        return "anthropic"
    if s.startswith("gemini-"):
        return "google"
    if s.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
        return "openai"
    return s.split("-", 1)[0]


def parse_effort(slug: str) -> tuple[str, str | None, bool]:
    if slug in ALIASES:
        return slug, None, False
    fast = slug.endswith("-fast")
    stem = slug[:-5] if fast else slug
    parts = stem.rsplit("-", 1)
    if len(parts) == 2 and parts[1] in (*LADDER, "max", "ultrafast"):
        return parts[0], parts[1], fast
    return stem, None, fast


def format_slug(family: str, effort: str | None, fast: bool) -> str:
    if effort is None:
        return family
    if family.startswith("claude-opus-5-5"):
        fast = True
    elif family.startswith(("claude-fable-", "gemini-")):
        fast = False
    return f"{family}-{effort}{'-fast' if fast else ''}"


def shift_slug_for_budget(slug: str, budget: str, available: set[str] | None = None) -> tuple[str, bool]:
    if slug in ALIASES:
        return slug, True
    family, effort, fast = parse_effort(slug)
    if effort is None:
        ok = available is None or slug in available
        return slug, ok
    base_idx = LADDER.index("xhigh") if effort in ("max", "ultrafast") else LADDER.index(effort)
    target_idx = max(0, base_idx - BUDGET_DROP[budget])
    candidate = format_slug(family, LADDER[target_idx], fast)
    if available is None or candidate in available:
        return candidate, True
    for idx in range(target_idx - 1, -1, -1):
        fallback = format_slug(family, LADDER[idx], fast)
        if fallback in available:
            return fallback, True
    return candidate, False


def migrate_state(raw: dict) -> tuple[dict, list[str], list[str]]:
    replaced: list[str] = []
    dropped: list[str] = []
    version = int(raw.get("defaults_version") or 0)
    budget = str(raw.get("budget") or "large").split()[0].lower()
    if budget == "unlimited" or budget not in BUDGET_DROP:
        if raw.get("budget"):
            replaced.append(f"budget: {raw.get('budget')} -> large")
        budget = "large"

    in_roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    roles: dict[str, str | list[str]] = {}
    for k, v in in_roles.items():
        if k in RETIRED_ROLES or canonical_role(k) in RETIRED_ROLES:
            dropped.append(k)
            continue
        rk = canonical_role(k)
        if rk not in DEFAULT_ROLES:
            dropped.append(k)
            continue
        roles[rk] = list(v) if isinstance(v, list) else str(v)

    for rk in PANEL_ROLES:
        if rk in roles and isinstance(roles[rk], list):
            new_list = []
            for entry in roles[rk]:
                if entry == "gemini-4-neon-high" or (entry.startswith("gemini-4-") and not entry.startswith("gemini-4-neon-")):
                    replaced.append(f"{rk}: {entry} -> gemini-4-neon-xhigh")
                    new_list.append("gemini-4-neon-xhigh")
                else:
                    new_list.append(entry)
            roles[rk] = new_list

    if version < 3:
        pool = roles.get("arena_cross_judge_pool")
        if isinstance(pool, list) and len(pool) == 3:
            fable = [x for x in pool if x.startswith("claude-fable-")]
            opus = [x for x in pool if x.startswith("claude-opus-")]
            gem = [x for x in pool if x.startswith("gemini-")]
            if len(fable) == 1 and len(opus) == 1 and len(gem) == 1:
                replaced.append("arena_cross_judge_pool: collapsed single-vendor Claude pair to default cross-vendor pool")
                roles["arena_cross_judge_pool"] = list(DEFAULT_ROLES["arena_cross_judge_pool"])
        if version < 2:
            code_roles = ("feature_refactoring", "bug_fix", "perf_issue", "hillclimb", "swarm_workers")
            for rk, val in list(roles.items()):
                if isinstance(val, str) and val.startswith("grok-") and rk in code_roles:
                    replaced.append(f"{rk}: {val} -> {DEFAULT_ROLES[rk]}")
                    roles[rk] = DEFAULT_ROLES[rk]
                elif isinstance(val, list) and rk in PANEL_ROLES:
                    if len(val) == 2 and any(x.startswith("claude-opus-") for x in val) and any(x.startswith("grok-") for x in val):
                        replaced.append(f"{rk}: {val} -> {DEFAULT_ROLES[rk]}")
                        roles[rk] = list(DEFAULT_ROLES[rk])
                    else:
                        roles[rk] = ["claude-opus-5-5-high-fast" if x.startswith("grok-") else x for x in val]

    merged: dict[str, str | list[str]] = {}
    for rk, default_val in DEFAULT_ROLES.items():
        if rk in roles:
            merged[rk] = roles[rk]
        else:
            merged[rk] = list(default_val) if isinstance(default_val, list) else default_val

    return {"defaults_version": DEFAULTS_VERSION, "budget": budget, "roles": merged}, replaced, dropped


def build_plan(
    root: Path,
    budget: str | None = None,
    available: set[str] | None = None,
    overrides: dict[str, str | list[str]] | None = None,
) -> dict:
    cfg_path = root / ".deepmodebot" / "models.json"
    existing = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    migrated, replaced, dropped = migrate_state(existing)
    chosen_budget = budget or migrated["budget"]
    if chosen_budget not in BUDGET_DROP:
        raise ValueError(f"budget must be one of {tuple(BUDGET_DROP)}, got {chosen_budget!r}")

    planned_roles: dict[str, str | list[str]] = {}
    needs_choice: list[str] = []
    errors: list[str] = []

    for rk, default_val in DEFAULT_ROLES.items():
        cur_val = (overrides or {}).get(rk, migrated["roles"][rk])
        is_user_override = overrides is not None and rk in overrides
        if isinstance(default_val, list):
            items = cur_val if isinstance(cur_val, list) else [s.strip() for s in str(cur_val).split(",") if s.strip()]
            out_items: list[str] = []
            for idx, item in enumerate(items):
                if is_user_override or item in ALIASES or (rk in existing.get("roles", {}) and item not in default_val):
                    mapped, ok = item, (item in ALIASES or available is None or item in available)
                else:
                    base_slug = default_val[idx] if idx < len(default_val) else item
                    mapped, ok = shift_slug_for_budget(base_slug, chosen_budget, available)
                out_items.append(mapped)
                if not ok:
                    needs_choice.append(f"{rk}[{idx}]={mapped}")
            planned_roles[rk] = out_items
        else:
            item = str(cur_val).strip()
            if is_user_override or item in ALIASES or (rk in existing.get("roles", {}) and item != default_val):
                mapped, ok = item, (item in ALIASES or available is None or item in available)
            else:
                mapped, ok = shift_slug_for_budget(default_val, chosen_budget, available)
            planned_roles[rk] = mapped
            if not ok:
                needs_choice.append(f"{rk}={mapped}")

    for rk, val in planned_roles.items():
        entries = val if isinstance(val, list) else [val]
        if rk == "arena_cross_judge_pool":
            if any(e in ALIASES for e in entries):
                errors.append("arena_cross_judge_pool cannot contain inherit-parent or auto")
            vendors = {vendor_of(e) for e in entries if e not in ALIASES}
            if len(vendors) < 2 and len(entries) >= 2:
                errors.append("arena_cross_judge_pool should span at least two model vendors")
        for e in entries:
            if e in ALIASES:
                continue
            _, eff, _ = parse_effort(e)
            if eff in ("max", "ultrafast"):
                errors.append(f"{rk}: {e} exceeds xhigh reasoning cap")
            if available is not None and e not in available:
                errors.append(f"{rk}: {e} is not in detected available models")

    has_verify = any((root / base).glob("verify-*/SKILL.md") for base in (".omp/skills", ".claude/skills", ".agents/skills"))
    return {
        "path": str(cfg_path),
        "defaults_version": DEFAULTS_VERSION,
        "budget": chosen_budget,
        "budget_label": BUDGET_LABEL[chosen_budget],
        "roles": planned_roles,
        "replaced_defaults": replaced,
        "dropped_roles": dropped,
        "needs_choice": needs_choice,
        "errors": errors,
        "has_verify_skill": has_verify,
    }


def write_config(plan: dict) -> Path:
    if plan["errors"]:
        raise ValueError("; ".join(plan["errors"]))
    path = Path(plan["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "defaults_version": plan["defaults_version"],
        "budget": plan["budget"],
        "budget_label": plan["budget_label"],
        "roles": plan["roles"],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def _parse_overrides(pairs: list[str] | None) -> dict[str, str | list[str]]:
    out: dict[str, str | list[str]] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"expected role=value, got {pair!r}")
        k, v = pair.split("=", 1)
        rk = canonical_role(k)
        if rk not in DEFAULT_ROLES:
            raise ValueError(f"unknown role {k!r}")
        if isinstance(DEFAULT_ROLES[rk], list):
            out[rk] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            out[rk] = v.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "plan", "write"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--json", action="store_true")
        if name in ("plan", "write"):
            p.add_argument("--budget", choices=tuple(BUDGET_DROP))
            p.add_argument("--available", help="Comma-separated available model slugs")
            p.add_argument("--set", action="append", default=[], help="Override role=slug (or role=s1,s2)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    avail = {s.strip() for s in args.available.split(",") if s.strip()} if getattr(args, "available", None) else None
    try:
        overrides = _parse_overrides(getattr(args, "set", None))
        plan = build_plan(root, getattr(args, "budget", None), avail, overrides or None)
        if args.cmd == "write":
            write_config(plan)
    except ValueError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json or args.cmd in ("inspect", "plan"):
        print(json.dumps({"ok": not plan["errors"], **plan}, indent=2))
    else:
        print(f"wrote {plan['path']} (budget={plan['budget_label']})")
    return 0 if not plan["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
