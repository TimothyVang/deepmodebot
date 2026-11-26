#!/usr/bin/env python3
"""Check or refresh pinned upstream skill inventories (cursor/plugins pstack & mattpocock/skills).

    python -B evals/workflows/sync_sources.py check-live [--json] [--out <file>] [--strict]
    python -B evals/workflows/sync_sources.py refresh
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE / "sources"
MATRIX_PATH = HERE / "matrix.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

UPSTREAMS = {
    "pstack": {"repository": "cursor/plugins", "branch": "main", "prefix": "pstack/"},
    "mattpocock": {"repository": "mattpocock/skills", "branch": "main", "prefix": ""},
}


def inventory_paths(files: list[dict]) -> set[str]:
    return {
        f["path"]
        for f in files
        if f["path"].endswith("/SKILL.md")
        or (f["path"].startswith("skills/poteto-mode/playbooks/") and f["path"].endswith(".md"))
        or f["path"] == "skills/poteto-mode/worker.md"
        or (f["path"].startswith("agents/") and f["path"].endswith(".md"))
        or f["path"] == "automations/benny/README.md"
    }


def gh_json(endpoint: str) -> dict:
    out = subprocess.check_output(
        ["gh", "api", endpoint],
        encoding="utf-8",
        timeout=60,
        creationflags=NO_WINDOW,
    )
    return json.loads(out)


def fetch_upstream_snapshot(name: str) -> dict:
    cfg = UPSTREAMS[name]
    repo, branch, prefix = cfg["repository"], cfg["branch"], cfg["prefix"]
    commit_obj = gh_json(f"repos/{repo}/commits/{branch}")
    commit_sha = commit_obj["sha"]
    root_tree_sha = commit_obj["commit"]["tree"]["sha"]

    if prefix:
        root_tree = gh_json(f"repos/{repo}/git/trees/{root_tree_sha}")
        target_name = prefix.rstrip("/")
        sub_entry = next((t for t in root_tree["tree"] if t["path"] == target_name and t["type"] == "tree"), None)
        if sub_entry is None:
            raise ValueError(f"{repo}@{commit_sha} has no subtree {target_name!r}")
        tree_sha = sub_entry["sha"]
        tree_resp = gh_json(f"repos/{repo}/git/trees/{tree_sha}?recursive=1")
        files = [
            {"path": t["path"], "sha": t["sha"], "size": t.get("size", 0)}
            for t in sorted(tree_resp["tree"], key=lambda x: x["path"])
            if t["type"] == "blob"
        ]
    else:
        tree_sha = commit_sha
        tree_resp = gh_json(f"repos/{repo}/git/trees/{commit_sha}?recursive=1")
        files = [
            {"path": t["path"], "sha": t["sha"], "size": t.get("size", 0)}
            for t in sorted(tree_resp["tree"], key=lambda x: x["path"])
            if t["type"] == "blob"
        ]

    return {
        "repository": repo,
        "commit": commit_sha,
        "prefix": prefix,
        "observed_date": dt.date.today().isoformat(),
        "tree_sha": tree_sha,
        "truncated": bool(tree_resp.get("truncated")),
        "source_url": f"https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1",
        "files": files,
    }


def check_live() -> dict:
    report = {"checked_date": dt.date.today().isoformat(), "has_drift": False, "sources": {}}
    for name in UPSTREAMS:
        pinned = json.loads((SOURCES_DIR / f"{name}.json").read_text(encoding="utf-8"))
        live = fetch_upstream_snapshot(name)
        pinned_inv = {f["path"]: f["sha"] for f in pinned["files"] if f["path"] in inventory_paths(pinned["files"])}
        live_inv = {f["path"]: f["sha"] for f in live["files"] if f["path"] in inventory_paths(live["files"])}
        added = sorted(set(live_inv) - set(pinned_inv))
        removed = sorted(set(pinned_inv) - set(live_inv))
        modified = sorted(p for p in (set(live_inv) & set(pinned_inv)) if live_inv[p] != pinned_inv[p])
        tree_changed = live["tree_sha"] != pinned["tree_sha"]
        inv_drift = bool(added or removed or modified)
        if inv_drift:
            report["has_drift"] = True
        report["sources"][name] = {
            "repository": pinned["repository"],
            "pinned_commit": pinned["commit"],
            "live_commit": live["commit"],
            "pinned_tree": pinned["tree_sha"],
            "live_tree": live["tree_sha"],
            "tree_changed": tree_changed,
            "inventory_drift": inv_drift,
            "added_workflows": added,
            "removed_workflows": removed,
            "modified_workflows": modified,
        }
    return report


NEW_MAPPINGS = {
    "pstack:skills/reframe/SKILL.md": {
        "name": "reframe",
        "kind": "skill",
        "distribution": "shipped",
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/deepmodebot/references/techniques/reframe.md"],
        "scenarios": [],
        "state": "mapped",
        "evidence": [],
        "limits": "Adapted local technique for problem disambiguation, ranked expert terms, neighboring-field analogies, and spec rewriting.",
    },
    "pstack:skills/poteto-mode/worker.md": {
        "name": "worker",
        "kind": "worker",
        "distribution": "shipped",
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/deepmodebot/worker.md"],
        "scenarios": [],
        "state": "mapped",
        "evidence": [],
        "limits": "Adapted subagent kickoff contract with Hardcore Mode, containment, and subscription-only rules.",
    },
    "pstack:skills/create-formal-verification-skill/SKILL.md": {
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/create-formal-verification-skill/SKILL.md"],
        "state": "mapped",
        "limits": "Adapted cross-harness formal verification skill generator; requires target verifier/model-checker runtime.",
    },
    "pstack:skills/maintain-formal-verification-skill/SKILL.md": {
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/maintain-formal-verification-skill/SKILL.md"],
        "state": "mapped",
        "limits": "Adapted cross-harness formal model upkeep workflow separating model drift from real bugs.",
    },
    "pstack:skills/statechart/SKILL.md": {
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/statechart/SKILL.md"],
        "state": "mapped",
        "limits": "Vendored TLA+ statechart compiler and shortest-counterexample Mermaid renderer on POSIX and native Windows; TLC/Java optional.",
    },
    "pstack:skills/ketchup-video/SKILL.md": {
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/deepmodebot/references/techniques/catchup-video.md"],
        "state": "mapped",
        "limits": "Adapted subtitled landscape MP4 catch-up slide workflow into .scratch/catchup-video/.",
    },
    "pstack:skills/make-bot-ui/SKILL.md": {
        "disposition": "mapped",
        "routes": ["plugins/deepmodebot/skills/deepmodebot/references/techniques/webhook-ui.md"],
        "state": "mapped",
        "limits": "Portable local/Tailscale webhook relay UI with server-held sender key; replaces Cursor-only Grok Bot routine cards.",
    },
    "pstack:skills/setup-pstack/SKILL.md": {
        "disposition": "mapped",
        "routes": [
            "plugins/deepmodebot/skills/deepmodebot/references/techniques/model-setup.md",
            "plugins/deepmodebot/skills/deepmodebot/assets/setup/model_setup.py",
        ],
        "state": "mapped",
        "limits": "Cross-harness .deepmodebot/models.json configurator and budget ladder rather than ~/.cursor/rules/pstack-models.mdc.",
    },
}


def refresh() -> dict:
    snapshots = {}
    for name in UPSTREAMS:
        snap = fetch_upstream_snapshot(name)
        (SOURCES_DIR / f"{name}.json").write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8", newline="\n")
        snapshots[name] = snap

    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in matrix["entries"]}
    wanted_ids: dict[str, tuple[str, str]] = {}
    for name, snap in snapshots.items():
        for p in sorted(inventory_paths(snap["files"])):
            wanted_ids[f"{name}:{p}"] = (name, p)

    new_entries = []
    for item_id in sorted(wanted_ids):
        upstream, rel_path = wanted_ids[item_id]
        snap = snapshots[upstream]
        source_url = f"https://github.com/{snap['repository']}/blob/{snap['commit']}/{snap['prefix']}{rel_path}"
        row = dict(by_id.get(item_id) or {})
        if not row:
            stem = Path(rel_path).parent.name if rel_path.endswith("/SKILL.md") else Path(rel_path).stem
            row = {
                "id": item_id,
                "upstream": upstream,
                "path": rel_path,
                "name": stem,
                "kind": "skill" if rel_path.endswith("/SKILL.md") else "workflow",
                "distribution": "shipped",
                "commit": snap["commit"],
                "source_url": source_url,
                "disposition": "missing",
                "routes": [],
                "scenarios": [],
                "state": "blocked",
                "evidence": [],
                "limits": "New upstream item awaiting local route mapping.",
            }
        row["commit"] = snap["commit"]
        row["source_url"] = source_url
        if item_id in NEW_MAPPINGS:
            row.update(NEW_MAPPINGS[item_id])
        if item_id.startswith("pstack:automations/benny/"):
            row["disposition"] = "not-applicable"
        new_entries.append(row)

    matrix["entries"] = new_entries
    MATRIX_PATH.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"entries": len(new_entries), "commits": {k: v["commit"] for k, v in snapshots.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    p_chk = sub.add_parser("check-live")
    p_chk.add_argument("--json", action="store_true")
    p_chk.add_argument("--out", help="Write JSON report to file")
    p_chk.add_argument("--strict", action="store_true", help="Exit 1 when upstream inventory drifted")
    sub.add_parser("refresh")
    args = parser.parse_args(argv)

    if args.action == "refresh":
        res = refresh()
        print(json.dumps(res, indent=2))
        return 0

    rep = check_live()
    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        for name, info in rep["sources"].items():
            status = "DRIFT" if info["inventory_drift"] else "OK"
            print(f"{name}: {status} (pinned={info['pinned_commit'][:10]}, live={info['live_commit'][:10]}, "
                  f"+{len(info['added_workflows'])}/-{len(info['removed_workflows'])}/~{len(info['modified_workflows'])})")
    if rep["has_drift"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
