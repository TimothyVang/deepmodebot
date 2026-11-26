#!/usr/bin/env python3
"""Fail-closed E2E Rehearsal Gate Tracker (SQLite WAL + REHEARSAL.md) for any app, tool, or UI workflow.

    python -B rehearsal_gate.py init --root <repo> --slug <slug> --app <name> --intent <text> --beats b1,b2,... [--kind web|cli|desktop|demo] [--max-rounds 25] [--json]
    python -B rehearsal_gate.py approve --root <repo> --slug <slug> --note <user-approval-receipt> [--json]
    python -B rehearsal_gate.py record-run --root <repo> --slug <slug> --video <rel-video-path> --duration-sec <sec> --beats-covered b1,b2,... [--desktop-width 1440] [--mobile-width 390] [--auto-gate-ok] [--watched-full-video] --video-notes <text> --critic-verdict approve|revise --open-p0-p1 <n> [--critic-notes <text>] [--json]
    python -B rehearsal_gate.py verdict --root <repo> --slug <slug> [--strict] [--json]

Hard gates enforced before an E2E workflow may be reported complete:
1. intent-grilled-and-approved: user was grilled on intended journey/beats/standard and approved the spec.
2. full-e2e-video-recorded: real non-empty continuous video file inside repo root, SHA-256 hashed, covering 100% of beats.
3. automated-checks-passed: mechanical checks (runtime assertions / ui_audit.py / responsive widths) passed.
4. full-video-collective-playback-reviewed: entire continuous video watched together (pacing, transitions, pops, seams), never isolated frames alone.
5. fresh-eye-critic-approved: clean-context reviewer approved the full video with zero open P0/P1 findings.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

VALID_KINDS = frozenset({"web", "cli", "desktop", "mobile", "api", "demo", "tool"})
VALID_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov", ".mkv", ".gif"})
MIN_VIDEO_NOTES_CHARS = 24


def _safe_slug(slug: str) -> str:
    clean = "".join(c for c in slug.lower().strip() if c.isalnum() or c in ("-", "_"))
    if not clean:
        raise ValueError(f"invalid slug: {slug!r}")
    return clean


def _slug_dir(root: Path, slug: str) -> Path:
    resolved_root = root.resolve()
    scratch = resolved_root / ".scratch"
    if scratch.is_symlink():
        raise ValueError(f"refusing symlinked .scratch dir: {scratch}")
    scratch.mkdir(parents=True, exist_ok=True)
    gi = scratch / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    d = scratch / "e2e" / _safe_slug(slug)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _db_path(root: Path, slug: str) -> Path:
    p = _slug_dir(root, slug) / "rehearsal.db"
    if p.is_symlink():
        raise ValueError(f"refusing symlinked rehearsal DB: {p}")
    return p


@contextlib.contextmanager
def _connect(db_file: Path):
    conn = sqlite3.connect(str(db_file), timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                slug TEXT PRIMARY KEY,
                app_name TEXT NOT NULL,
                target_kind TEXT NOT NULL,
                intent TEXT NOT NULL,
                beats_json TEXT NOT NULL,
                standard_json TEXT NOT NULL,
                approved_by_user INTEGER NOT NULL DEFAULT 0,
                approved_at REAL,
                approval_note TEXT NOT NULL DEFAULT '',
                max_rounds INTEGER NOT NULL DEFAULT 25,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rehearsals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                version INTEGER NOT NULL,
                video_path TEXT NOT NULL,
                video_sha256 TEXT NOT NULL,
                video_bytes INTEGER NOT NULL,
                video_duration_sec REAL NOT NULL,
                desktop_width INTEGER NOT NULL DEFAULT 1440,
                mobile_width INTEGER NOT NULL DEFAULT 390,
                beats_covered_json TEXT NOT NULL,
                automated_gate_ok INTEGER NOT NULL DEFAULT 0,
                watched_full_video INTEGER NOT NULL DEFAULT 0,
                video_notes TEXT NOT NULL DEFAULT '',
                critic_verdict TEXT NOT NULL DEFAULT 'revise',
                open_p0_p1 INTEGER NOT NULL DEFAULT 0,
                critic_notes TEXT NOT NULL DEFAULT '',
                passed INTEGER NOT NULL DEFAULT 0,
                provenance_receipt TEXT NOT NULL DEFAULT '',
                compared_refs_json TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                UNIQUE(slug, version),
                FOREIGN KEY(slug) REFERENCES workflows(slug) ON DELETE CASCADE
            );
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(rehearsals)").fetchall()}
        if "provenance_receipt" not in cols:
            conn.execute("ALTER TABLE rehearsals ADD COLUMN provenance_receipt TEXT NOT NULL DEFAULT ''")
        if "compared_refs_json" not in cols:
            conn.execute("ALTER TABLE rehearsals ADD COLUMN compared_refs_json TEXT NOT NULL DEFAULT '[]'")
        conn.commit()
        yield conn
    finally:
        conn.close()


def _hash_repo_file(root: Path, rel_path: str, *, require_video: bool = False) -> tuple[str, str, int]:
    resolved_root = root.resolve()
    raw = Path(rel_path)
    if raw.is_absolute():
        raise ValueError(f"path must be repo-relative: {rel_path!r}")
    candidate = resolved_root / raw
    if candidate.is_symlink():
        raise ValueError(f"refusing symlinked file: {candidate}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path escapes project root: {rel_path!r}")
    if not resolved.is_file():
        raise ValueError(f"file not found: {resolved}")
    if require_video and resolved.suffix.lower() not in VALID_VIDEO_EXTS:
        raise ValueError(f"video must be one of {sorted(VALID_VIDEO_EXTS)}, got {resolved.suffix!r}")
    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError(f"file is empty (0 bytes): {resolved}")
    h = hashlib.sha256()
    with resolved.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return resolved.relative_to(resolved_root).as_posix(), h.hexdigest(), size


def _hash_video(root: Path, rel_video: str) -> tuple[str, str, int]:
    return _hash_repo_file(root, rel_video, require_video=True)


def _valid_provenance_receipt(receipt: str, required_producer: str) -> bool:
    clean = receipt.strip()
    if ":" not in clean:
        return False
    prod, job_id = clean.split(":", 1)
    p = prod.strip().lower()
    j = job_id.strip().lower()
    if not p or p in {"local", "mock", "fake", "primitive", "primitives", "blender-primitives", "none"}:
        return False
    if len(j) < 4 or j in {"none", "null", "local", "mock", "fake", "todo", "0"}:
        return False
    if required_producer and p != required_producer.strip().lower():
        return False
    return True

def init_workflow(
    root: Path,
    *,
    slug: str,
    app_name: str,
    target_kind: str,
    intent: str,
    beats: list[str],
    standard: dict | None = None,
    references: list[str] | None = None,
    required_producer: str = "",
    max_rounds: int = 25,
) -> dict:
    if target_kind not in VALID_KINDS:
        raise ValueError(f"invalid kind {target_kind!r}; expected one of {sorted(VALID_KINDS)}")
    clean_beats = [b.strip() for b in beats if b.strip()]
    if not clean_beats:
        raise ValueError("beats must contain at least one workflow step")
    if not intent.strip():
        raise ValueError("intent must be non-empty")
    clean_slug = _safe_slug(slug)
    dbf = _db_path(root, clean_slug)
    now = time.time()
    locked_refs = {rel: sha for raw in (references or []) if raw.strip() for rel, sha, _ in [_hash_repo_file(root, raw)]}
    std = dict(standard or {
        "require_user_approval": True,
        "require_full_video": True,
        "require_collective_video_review": True,
        "require_fresh_eye_critic": True,
        "viewports": ["1440x900", "390x844"],
    })
    if locked_refs:
        std["locked_references"] = locked_refs
    if required_producer.strip():
        std["required_producer"] = required_producer.strip()
    with _connect(dbf) as conn:
        conn.execute(
            """INSERT INTO workflows(slug, app_name, target_kind, intent, beats_json, standard_json, approved_by_user, max_rounds, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                   app_name=excluded.app_name,
                   target_kind=excluded.target_kind,
                   intent=excluded.intent,
                   beats_json=excluded.beats_json,
                   standard_json=excluded.standard_json,
                   approved_by_user=0,
                   approved_at=NULL,
                   approval_note='',
                   max_rounds=excluded.max_rounds""",
            (clean_slug, app_name.strip(), target_kind, intent.strip(), json.dumps(clean_beats), json.dumps(std), max(1, int(max_rounds)), now),
        )
        conn.commit()
    md_path = render_rehearsal_md(root, clean_slug)
    return {"slug": clean_slug, "db": str(dbf), "rehearsal_md": str(md_path), "approved_by_user": False, "beats": clean_beats}


def approve_workflow(root: Path, *, slug: str, note: str) -> dict:
    if len(note.strip()) < 4:
        raise ValueError("approval note must describe the user confirmation")
    clean_slug = _safe_slug(slug)
    dbf = _db_path(root, clean_slug)
    now = time.time()
    with _connect(dbf) as conn:
        cur = conn.execute(
            "UPDATE workflows SET approved_by_user = 1, approved_at = ?, approval_note = ? WHERE slug = ?",
            (now, note.strip(), clean_slug),
        )
        if cur.rowcount == 0:
            raise ValueError(f"workflow {clean_slug!r} not found; run init first")
        conn.commit()
    md_path = render_rehearsal_md(root, clean_slug)
    return {"slug": clean_slug, "approved_by_user": True, "approval_note": note.strip(), "rehearsal_md": str(md_path)}


def record_rehearsal_run(
    root: Path,
    *,
    slug: str,
    video_rel: str,
    duration_sec: float,
    beats_covered: list[str],
    desktop_width: int = 1440,
    mobile_width: int = 390,
    auto_gate_ok: bool = False,
    watched_full_video: bool = False,
    video_notes: str = "",
    critic_verdict: str = "revise",
    open_p0_p1: int = 0,
    critic_notes: str = "",
    provenance_receipt: str = "",
    compared_references: list[str] | None = None,
) -> dict:
    if critic_verdict not in ("approve", "revise"):
        raise ValueError("critic_verdict must be 'approve' or 'revise'")
    if duration_sec <= 0:
        raise ValueError("duration_sec must be > 0")
    clean_slug = _safe_slug(slug)
    dbf = _db_path(root, clean_slug)
    norm_video, digest, size = _hash_video(root, video_rel)
    covered = [b.strip() for b in beats_covered if b.strip()]
    now = time.time()

    with _connect(dbf) as conn:
        wf = conn.execute("SELECT * FROM workflows WHERE slug = ?", (clean_slug,)).fetchone()
        if wf is None:
            raise ValueError(f"workflow {clean_slug!r} not found; run init first")
        last_v = conn.execute("SELECT COALESCE(MAX(version), 0) FROM rehearsals WHERE slug = ?", (clean_slug,)).fetchone()[0]
        next_v = int(last_v) + 1
        max_rounds = int(wf["max_rounds"])
        if next_v > max_rounds:
            raise ValueError(f"rehearsal round cap reached ({max_rounds}); review blockers with user before extending")

        required_beats = set(json.loads(wf["beats_json"]))
        std = json.loads(wf["standard_json"] or "{}")
        locked_refs: dict[str, str] = std.get("locked_references") or {}
        req_prod: str = std.get("required_producer") or ""
        comp_norm = sorted({_hash_repo_file(root, r)[0] for r in (compared_references or []) if r.strip()})
        refs_ok = all(
            r in comp_norm and _hash_repo_file(root, r)[1] == sha
            for r, sha in locked_refs.items()
        )
        prov_ok = (not req_prod) or _valid_provenance_receipt(provenance_receipt, req_prod)
        all_beats = required_beats.issubset(set(covered))
        passed = int(
            bool(wf["approved_by_user"])
            and all_beats
            and bool(auto_gate_ok)
            and bool(watched_full_video)
            and len(video_notes.strip()) >= MIN_VIDEO_NOTES_CHARS
            and critic_verdict == "approve"
            and int(open_p0_p1) == 0
            and refs_ok
            and prov_ok
        )
        conn.execute(
            """INSERT INTO rehearsals(
                   slug, version, video_path, video_sha256, video_bytes, video_duration_sec,
                   desktop_width, mobile_width, beats_covered_json, automated_gate_ok,
                   watched_full_video, video_notes, critic_verdict, open_p0_p1, critic_notes,
                   passed, provenance_receipt, compared_refs_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                clean_slug, next_v, norm_video, digest, size, float(duration_sec),
                int(desktop_width), int(mobile_width), json.dumps(covered), int(bool(auto_gate_ok)),
                int(bool(watched_full_video)), video_notes.strip(), critic_verdict, int(open_p0_p1),
                critic_notes.strip(), passed, provenance_receipt.strip(), json.dumps(comp_norm), now,
            ),
        )
        conn.commit()
    render_rehearsal_md(root, clean_slug)
    return evaluate_verdict(root, slug=clean_slug)


def evaluate_verdict(root: Path, *, slug: str) -> dict:
    clean_slug = _safe_slug(slug)
    dbf = _db_path(root, clean_slug)
    if not dbf.is_file():
        return {"verdict": "REHEARSAL_BLOCKED", "slug": clean_slug, "failed_gates": ["workflow-not-initialized"], "version": 0}
    with _connect(dbf) as conn:
        wf = conn.execute("SELECT * FROM workflows WHERE slug = ?", (clean_slug,)).fetchone()
        if wf is None:
            return {"verdict": "REHEARSAL_BLOCKED", "slug": clean_slug, "failed_gates": ["workflow-not-initialized"], "version": 0}
        latest = conn.execute(
            "SELECT * FROM rehearsals WHERE slug = ? ORDER BY version DESC LIMIT 1",
            (clean_slug,),
        ).fetchone()
        total_runs = conn.execute("SELECT COUNT(*) FROM rehearsals WHERE slug = ?", (clean_slug,)).fetchone()[0]

    failed: list[str] = []
    required_beats = json.loads(wf["beats_json"])
    std = json.loads(wf["standard_json"] or "{}")
    locked_refs: dict[str, str] = std.get("locked_references") or {}
    req_prod: str = std.get("required_producer") or ""
    if not wf["approved_by_user"]:
        failed.append("intent-grilled-and-approved")

    missing_beats: list[str] = list(required_beats)
    video_verified = False
    if latest is None:
        failed.extend([
            "full-e2e-video-recorded",
            "automated-checks-passed",
            "full-video-collective-playback-reviewed",
            "fresh-eye-critic-approved",
        ])
        if locked_refs:
            failed.append("reference-comparison-verified")
        if req_prod:
            failed.append("provenance-verified")
    else:
        covered = set(json.loads(latest["beats_covered_json"]))
        missing_beats = [b for b in required_beats if b not in covered]
        try:
            _, live_sha, _ = _hash_video(root, latest["video_path"])
            video_verified = live_sha == latest["video_sha256"] and float(latest["video_duration_sec"]) > 0
        except ValueError:
            video_verified = False
        if not video_verified or missing_beats:
            failed.append("full-e2e-video-recorded")
        if not latest["automated_gate_ok"]:
            failed.append("automated-checks-passed")
        if not latest["watched_full_video"] or len((latest["video_notes"] or "").strip()) < MIN_VIDEO_NOTES_CHARS:
            failed.append("full-video-collective-playback-reviewed")
        if latest["critic_verdict"] != "approve" or int(latest["open_p0_p1"]) > 0:
            failed.append("fresh-eye-critic-approved")
        if locked_refs:
            comp_set = set(json.loads(latest["compared_refs_json"] or "[]"))
            refs_intact = True
            for r, expected_sha in locked_refs.items():
                try:
                    _, live_r_sha, _ = _hash_repo_file(root, r)
                    if r not in comp_set or live_r_sha != expected_sha:
                        refs_intact = False
                except ValueError:
                    refs_intact = False
            if not refs_intact:
                failed.append("reference-comparison-verified")
        if req_prod and not _valid_provenance_receipt(latest["provenance_receipt"] or "", req_prod):
            failed.append("provenance-verified")

    return {
        "verdict": "REHEARSAL_PASSED" if not failed else "REHEARSAL_BLOCKED",
        "slug": clean_slug,
        "app_name": wf["app_name"],
        "target_kind": wf["target_kind"],
        "approved_by_user": bool(wf["approved_by_user"]),
        "version": int(latest["version"]) if latest else 0,
        "total_runs": int(total_runs),
        "max_rounds": int(wf["max_rounds"]),
        "missing_beats": missing_beats,
        "video_verified": video_verified,
        "failed_gates": failed,
        "rehearsal_md": str(_slug_dir(root, clean_slug) / "REHEARSAL.md"),
    }


def render_rehearsal_md(root: Path, slug: str) -> Path:
    clean_slug = _safe_slug(slug)
    dbf = _db_path(root, clean_slug)
    out = _slug_dir(root, clean_slug) / "REHEARSAL.md"
    with _connect(dbf) as conn:
        wf = conn.execute("SELECT * FROM workflows WHERE slug = ?", (clean_slug,)).fetchone()
        runs = conn.execute("SELECT * FROM rehearsals WHERE slug = ? ORDER BY version ASC", (clean_slug,)).fetchall()
    verdict = evaluate_verdict(root, slug=clean_slug)
    beats = json.loads(wf["beats_json"]) if wf else []
    lines = [
        f"# E2E Rehearsal: {wf['app_name']} (`{clean_slug}`)",
        "",
        f"- **Status:** `{verdict['verdict']}` (round `v{verdict['version']}/{wf['max_rounds']}`)",
        f"- **Target kind:** `{wf['target_kind']}`",
        f"- **User intent approved:** `{'yes' if wf['approved_by_user'] else 'NO'}`"
        + (f" — {wf['approval_note']}" if wf["approval_note"] else ""),
        f"- **Intent:** {wf['intent']}",
        f"- **Required beats ({len(beats)}):** {', '.join(beats)}",
    ]
    if verdict["failed_gates"]:
        lines.append(f"- **Blocking gates:** {', '.join(verdict['failed_gates'])}")
    lines += [
        "",
        "## Rehearsal history",
        "",
        "| Version | Video | Duration | Auto Gate | Full Video Watched | Critic | Open P0/P1 | Result |",
        "| --- | --- | ---: | --- | --- | --- | ---: | --- |",
    ]
    for r in runs:
        lines.append(
            f"| v{r['version']} | `{r['video_path']}` (`{r['video_sha256'][:10]}`) | {r['video_duration_sec']:.1f}s | "
            f"{'pass' if r['automated_gate_ok'] else 'fail'} | {'yes' if r['watched_full_video'] else 'NO'} | "
            f"{r['critic_verdict']} | {r['open_p0_p1']} | {'PASS' if r['passed'] else 'REHEARSE'} |"
        )
    if runs:
        last = runs[-1]
        lines += [
            "",
            f"## Latest collective video review (v{last['version']})",
            "",
            f"- **Whole-video continuity notes:** {last['video_notes'] or '(missing)'}",
            f"- **Fresh-eye critic notes:** {last['critic_notes'] or '(none)'}",
        ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fail-closed E2E Rehearsal Gate Tracker (SQLite WAL + REHEARSAL.md).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_init = sub.add_parser("init")
    sp_init.add_argument("--root", default=".")
    sp_init.add_argument("--slug", required=True)
    sp_init.add_argument("--app", required=True)
    sp_init.add_argument("--kind", default="web", choices=sorted(VALID_KINDS))
    sp_init.add_argument("--intent", required=True)
    sp_init.add_argument("--beats", required=True, help="Comma-separated ordered workflow beats.")
    sp_init.add_argument("--max-rounds", type=int, default=25)
    sp_init.add_argument("--references", default="", help="Optional comma-separated reference files to hash-lock.")
    sp_init.add_argument("--required-producer", default="", help="Optional upstream producer required in provenance receipt.")
    sp_init.add_argument("--json", action="store_true")

    sp_app = sub.add_parser("approve")
    sp_app.add_argument("--root", default=".")
    sp_app.add_argument("--slug", required=True)
    sp_app.add_argument("--note", required=True)
    sp_app.add_argument("--json", action="store_true")

    sp_rec = sub.add_parser("record-run")
    sp_rec.add_argument("--root", default=".")
    sp_rec.add_argument("--slug", required=True)
    sp_rec.add_argument("--video", required=True)
    sp_rec.add_argument("--duration-sec", type=float, required=True)
    sp_rec.add_argument("--beats-covered", required=True)
    sp_rec.add_argument("--desktop-width", type=int, default=1440)
    sp_rec.add_argument("--mobile-width", type=int, default=390)
    sp_rec.add_argument("--auto-gate-ok", action="store_true")
    sp_rec.add_argument("--watched-full-video", action="store_true")
    sp_rec.add_argument("--video-notes", default="")
    sp_rec.add_argument("--critic-verdict", default="revise", choices=("approve", "revise"))
    sp_rec.add_argument("--open-p0-p1", type=int, default=0)
    sp_rec.add_argument("--critic-notes", default="")
    sp_rec.add_argument("--provenance-receipt", default="", help="Optional producer:job_id receipt for generated assets.")
    sp_rec.add_argument("--compared-references", default="", help="Comma-separated locked references compared by critic.")
    sp_rec.add_argument("--json", action="store_true")

    sp_ver = sub.add_parser("verdict")
    sp_ver.add_argument("--root", default=".")
    sp_ver.add_argument("--slug", required=True)
    sp_ver.add_argument("--strict", action="store_true")
    sp_ver.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "init":
        res = init_workflow(
            root, slug=args.slug, app_name=args.app, target_kind=args.kind,
            intent=args.intent, beats=args.beats.split(","),
            references=[x for x in args.references.split(",") if x.strip()],
            required_producer=args.required_producer,
            max_rounds=args.max_rounds,
        )
        print(json.dumps(res, indent=2) if args.json else f"initialized rehearsal {res['slug']} (awaiting user approval)")
        return 0
    if args.cmd == "approve":
        res = approve_workflow(root, slug=args.slug, note=args.note)
        print(json.dumps(res, indent=2) if args.json else f"approved rehearsal {res['slug']}")
        return 0
    if args.cmd == "record-run":
        res = record_rehearsal_run(
            root, slug=args.slug, video_rel=args.video, duration_sec=args.duration_sec,
            beats_covered=args.beats_covered.split(","), desktop_width=args.desktop_width,
            mobile_width=args.mobile_width, auto_gate_ok=args.auto_gate_ok,
            watched_full_video=args.watched_full_video, video_notes=args.video_notes,
            critic_verdict=args.critic_verdict, open_p0_p1=args.open_p0_p1, critic_notes=args.critic_notes,
            provenance_receipt=args.provenance_receipt,
            compared_references=[x for x in args.compared_references.split(",") if x.strip()],
        )
        print(json.dumps(res, indent=2) if args.json else f"v{res['version']}: {res['verdict']} (failed: {res['failed_gates']})")
        return 0 if res["verdict"] == "REHEARSAL_PASSED" else 1
    if args.cmd == "verdict":
        res = evaluate_verdict(root, slug=args.slug)
        print(json.dumps(res, indent=2) if args.json else f"{res['verdict']} (v{res['version']}/{res.get('max_rounds', 25)}; failed: {res['failed_gates']})")
        if args.strict and res["verdict"] != "REHEARSAL_PASSED":
            return 1
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
