#!/usr/bin/env python3
"""Optimized SQLite WAL + mmap + FTS5/BM25 + decay + token-knapsack project memory engine.

    python -B project_memory.py init [--root <repo>] [--json]
    python -B project_memory.py put --key <k> --kind <kind> --content <text> [--priority 0..3] [--tags a,b] [--source ref] [--ttl-hours N] [--root <repo>]
    python -B project_memory.py recall [--query <q>] [--kind <k>] [--budget-tokens 800] [--format xml|json|yaml] [--root <repo>]
    python -B project_memory.py compact [--max-records 500] [--root <repo>] [--json]
    python -B project_memory.py stats [--root <repo>] [--json]

Design:
- Single shared SQLite DB at <main-checkout>/.scratch/deepmode-memory.db (shared across linked git worktrees).
- WAL + 64 MB mmap + MEMORY temp_store + bounded 8 MB page cache + incremental auto_vacuum.
- SHA-256 content-addressed dedup + FTS5 BM25 + exponential time-decay + LFU hits + token-budgeted greedy knapsack packing.
- Compact XML (<deepmode-memory>), JSON, and YAML exporters. Stdlib only; zero bytecode writes.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.dont_write_bytecode = True

SCHEMA_VERSION = 1
MMAP_BYTES = 0
MAX_CONTENT_CHARS = 2048
VALID_KINDS = frozenset({"fact", "decision", "gotcha", "convention", "ci_result", "hotspot", "handoff"})
PRIORITY_WEIGHT = {0: 4.0, 1: 2.4, 2: 1.4, 3: 0.7}
DECAY_LAMBDA_PER_DAY = {0: 0.004, 1: 0.02, 2: 0.05, 3: 0.18}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def resolve_main_root(start: Path) -> Path:
    resolved = start.expanduser().resolve()
    try:
        common = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, creationflags=NO_WINDOW,
        )
        if common.returncode == 0 and common.stdout.strip():
            cpath = Path(common.stdout.strip())
            if cpath.name == ".git":
                parent_repo = cpath.parent
                try:
                    rel_parts = resolved.relative_to(parent_repo).parts
                except ValueError:
                    rel_parts = ()
                if ".scratch" in rel_parts:
                    return resolved
                return parent_repo
    except OSError:
        pass
    return resolved


def db_path_for(root: Path) -> Path:
    main_root = resolve_main_root(root)
    scratch = main_root / ".scratch"
    if scratch.is_symlink():
        raise ValueError(f"refusing symlinked scratch dir: {scratch}")
    scratch.mkdir(parents=True, exist_ok=True)
    gi = scratch / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    dbf = scratch / "deepmode-memory.db"
    if dbf.is_symlink():
        raise ValueError(f"refusing symlinked memory DB: {dbf}")
    return dbf


@contextlib.contextmanager
def connect_db(db_file: Path, readonly: bool = False):
    if readonly:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=5.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute(f"PRAGMA mmap_size={MMAP_BYTES}")
            conn.execute("PRAGMA cache_size=-8000")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
        finally:
            conn.close()
        return
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA mmap_size={MMAP_BYTES}")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        ensure_schema(conn)
        yield conn
    finally:
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kv_meta (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 2,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            tokens_est INTEGER NOT NULL,
            hits INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_accessed REAL NOT NULL,
            expires_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_mem_rank ON memories(priority, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind, priority);
        CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(content_hash);
        CREATE INDEX IF NOT EXISTS idx_mem_exp ON memories(expires_at) WHERE expires_at IS NOT NULL;

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key, kind, tags, content,
            content='memories', content_rowid='id',
            tokenize='porter unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, kind, tags, content)
            VALUES (new.id, new.key, new.kind, new.tags, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, kind, tags, content)
            VALUES ('delete', old.id, old.key, old.kind, old.tags, old.content);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, kind, tags, content)
            VALUES ('delete', old.id, old.key, old.kind, old.tags, old.content);
            INSERT INTO memories_fts(rowid, key, kind, tags, content)
            VALUES (new.id, new.key, new.kind, new.tags, new.content);
        END;
        """
    )
    conn.execute("INSERT OR IGNORE INTO kv_meta(k, v) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    conn.commit()


def estimate_tokens(key: str, content: str, source: str = "") -> int:
    return max(8, (len(key) + len(content) + len(source) + 32) // 4)


def content_digest(kind: str, content: str) -> str:
    norm = " ".join(content.strip().split()).lower()
    return hashlib.sha256(f"{kind}:{norm}".encode("utf-8")).hexdigest()[:16]


def put_memory(
    root: Path,
    *,
    key: str,
    kind: str,
    content: str,
    priority: int = 2,
    tags: str = "",
    source: str = "",
    ttl_hours: float | None = None,
) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid kind {kind!r}; expected one of {sorted(VALID_KINDS)}")
    prio = max(0, min(3, int(priority)))
    clean_content = content.strip()[:MAX_CONTENT_CHARS]
    if not clean_content:
        raise ValueError("content must be non-empty")
    clean_tags = ",".join(sorted({t.strip().lower() for t in tags.split(",") if t.strip()}))
    now = time.time()
    exp = now + ttl_hours * 3600.0 if ttl_hours and ttl_hours > 0 else None
    digest = content_digest(kind, clean_content)
    tok = estimate_tokens(key, clean_content, source)

    db_file = db_path_for(root)
    with connect_db(db_file) as conn:
        dup = conn.execute(
            "SELECT id, key, tags FROM memories WHERE content_hash = ? AND kind = ? AND key != ?",
            (digest, kind, key),
        ).fetchone()
        if dup:
            merged_tags = ",".join(sorted({t for t in f"{dup['tags']},{clean_tags}".split(",") if t}))
            conn.execute(
                "UPDATE memories SET priority = MIN(priority, ?), tags = ?, updated_at = ?, expires_at = ? WHERE id = ?",
                (prio, merged_tags, now, exp, dup["id"]),
            )
            conn.commit()
            return {"status": "deduped", "key": dup["key"], "content_hash": digest, "tokens_est": tok}

        existing = conn.execute("SELECT id FROM memories WHERE key = ?", (key,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE memories
                   SET kind=?, priority=?, content=?, tags=?, source=?, content_hash=?, tokens_est=?, updated_at=?, expires_at=?
                   WHERE id=?""",
                (kind, prio, clean_content, clean_tags, source, digest, tok, now, exp, existing["id"]),
            )
            status = "updated"
        else:
            conn.execute(
                """INSERT INTO memories(key, kind, priority, content, tags, source, content_hash, tokens_est, hits, created_at, updated_at, last_accessed, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                (key, kind, prio, clean_content, clean_tags, source, digest, tok, now, now, now, exp),
            )
            status = "inserted"
        conn.commit()
    return {"status": status, "key": key, "content_hash": digest, "tokens_est": tok, "db": str(db_file)}


def _fts_query(raw: str) -> str:
    tokens = FTS_TOKEN_RE.findall(raw.lower())
    if not tokens:
        return ""
    return " OR ".join(f"{t}*" for t in tokens[:12])


def _score_row(row: sqlite3.Row, bm25_boost: float, now: float) -> float:
    prio = int(row["priority"])
    age_days = max(0.0, (now - float(row["updated_at"])) / 86400.0)
    decay = math.exp(-DECAY_LAMBDA_PER_DAY.get(prio, 0.05) * age_days)
    lfu = 0.15 * math.log1p(int(row["hits"]))
    return (PRIORITY_WEIGHT.get(prio, 1.0) + bm25_boost + lfu) * decay


def recall_memories(
    root: Path,
    *,
    query: str = "",
    kind: str = "",
    budget_tokens: int = 800,
    limit: int = 40,
    touch_hits: bool = True,
) -> dict:
    db_file = db_path_for(root)
    if not db_file.exists():
        return {"db": str(db_file), "repo": resolve_main_root(root).name, "budget_tokens": budget_tokens, "used_tokens": 0, "items": []}

    now = time.time()
    with connect_db(db_file, readonly=not touch_hits) as conn:
        fts_scores: dict[int, float] = {}
        fq = _fts_query(query)
        if fq:
            try:
                fts_rows = conn.execute(
                    "SELECT rowid, bm25(memories_fts, 3.0, 1.5, 2.0, 1.0) AS rank FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT 120",
                    (fq,),
                ).fetchall()
                for r in fts_rows:
                    fts_scores[int(r["rowid"])] = 1.5 + min(4.0, abs(float(r["rank"])))
            except sqlite3.OperationalError:
                pass

        sql = "SELECT * FROM memories WHERE (expires_at IS NULL OR expires_at > ?)"
        params: list = [now]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if fq:
            if fts_scores:
                ids = ",".join(str(i) for i in fts_scores)
                sql += f" AND (id IN ({ids}) OR priority = 0)"
            else:
                sql += " AND priority = 0"
        rows = conn.execute(sql, params).fetchall()

        scored = []
        for r in rows:
            boost = fts_scores.get(int(r["id"]), 0.0)
            sc = _score_row(r, boost, now)
            tok = max(1, int(r["tokens_est"]))
            scored.append((r, sc, tok))

        p0 = sorted([x for x in scored if int(x[0]["priority"]) == 0], key=lambda x: -x[1])
        rest = sorted([x for x in scored if int(x[0]["priority"]) > 0], key=lambda x: -(x[1] / x[2]))

        packed = []
        used = 0
        chosen_ids: list[int] = []
        for r, sc, tok in p0 + rest:
            if len(packed) >= limit:
                break
            if used + tok > budget_tokens and packed:
                continue
            used += tok
            chosen_ids.append(int(r["id"]))
            packed.append({
                "key": r["key"],
                "kind": r["kind"],
                "priority": int(r["priority"]),
                "content": r["content"],
                "tags": [t for t in r["tags"].split(",") if t],
                "source": r["source"],
                "tokens_est": tok,
                "score": round(sc, 3),
            })

        if touch_hits and chosen_ids:
            conn.executemany(
                "UPDATE memories SET hits = hits + 1, last_accessed = ? WHERE id = ?",
                [(now, cid) for cid in chosen_ids],
            )
            conn.commit()

    return {
        "db": str(db_file),
        "repo": resolve_main_root(root).name,
        "budget_tokens": budget_tokens,
        "used_tokens": used,
        "items": packed,
    }


def format_xml(payload: dict) -> str:
    attrs = (
        f'repo="{xml_escape(payload["repo"])}" '
        f'count="{len(payload["items"])}" '
        f'tokens="{payload["used_tokens"]}/{payload["budget_tokens"]}"'
    )
    lines = [f"<deepmode-memory {attrs}>"]
    for item in payload["items"]:
        src = f' src="{xml_escape(item["source"])}"' if item["source"] else ""
        tags = f' tags="{xml_escape(",".join(item["tags"]))}"' if item["tags"] else ""
        lines.append(
            f'  <m k="{xml_escape(item["key"])}" kind="{xml_escape(item["kind"])}" p="{item["priority"]}"{src}{tags}>'
            f'{xml_escape(item["content"])}</m>'
        )
    lines.append("</deepmode-memory>")
    return "\n".join(lines)


def format_yaml(payload: dict) -> str:
    lines = [
        f"repo: {json.dumps(payload['repo'])}",
        f"budget_tokens: {payload['budget_tokens']}",
        f"used_tokens: {payload['used_tokens']}",
        "items:",
    ]
    for item in payload["items"]:
        lines.append(f"  - key: {json.dumps(item['key'])}")
        lines.append(f"    kind: {item['kind']}")
        lines.append(f"    priority: {item['priority']}")
        if item["source"]:
            lines.append(f"    source: {json.dumps(item['source'])}")
        if item["tags"]:
            lines.append(f"    tags: [{', '.join(json.dumps(t) for t in item['tags'])}]")
        lines.append(f"    content: {json.dumps(item['content'])}")
    return "\n".join(lines)


def compact_memory(root: Path, max_records: int = 500) -> dict:
    db_file = db_path_for(root)
    if not db_file.exists():
        return {"db": str(db_file), "expired_removed": 0, "trimmed": 0, "remaining": 0, "bytes": 0}
    now = time.time()
    with connect_db(db_file) as conn:
        cur = conn.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
        expired = cur.rowcount
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        trimmed = 0
        if total > max_records:
            excess = total - max_records
            cur2 = conn.execute(
                """DELETE FROM memories WHERE id IN (
                       SELECT id FROM memories WHERE priority > 0
                       ORDER BY priority DESC, last_accessed ASC LIMIT ?
                   )""",
                (excess,),
            )
            trimmed = cur2.rowcount
        conn.commit()
        conn.execute("PRAGMA incremental_vacuum")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA optimize")
        remaining = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return {
        "db": str(db_file),
        "expired_removed": expired,
        "trimmed": trimmed,
        "remaining": remaining,
        "bytes": db_file.stat().st_size if db_file.exists() else 0,
    }


def memory_stats(root: Path) -> dict:
    db_file = db_path_for(root)
    if not db_file.exists():
        return {"exists": False, "db": str(db_file), "records": 0, "bytes": 0}
    with connect_db(db_file, readonly=True) as conn:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        by_kind = {r["kind"]: r["c"] for r in conn.execute("SELECT kind, COUNT(*) AS c FROM memories GROUP BY kind")}
        tok_sum = conn.execute("SELECT COALESCE(SUM(tokens_est), 0) FROM memories").fetchone()[0]
    return {
        "exists": True,
        "db": str(db_file),
        "records": total,
        "total_tokens_est": tok_sum,
        "by_kind": by_kind,
        "bytes": db_file.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Optimized SQLite WAL+FTS5 project memory engine for deepmodebot.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize the project memory database.")
    p_init.add_argument("--root", default=".")
    p_init.add_argument("--json", action="store_true")

    p_put = sub.add_parser("put", help="Upsert a deduplicated memory record.")
    p_put.add_argument("--root", default=".")
    p_put.add_argument("--key", required=True)
    p_put.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    p_put.add_argument("--content", required=True)
    p_put.add_argument("--priority", type=int, default=2)
    p_put.add_argument("--tags", default="")
    p_put.add_argument("--source", default="")
    p_put.add_argument("--ttl-hours", type=float, default=None)

    p_rec = sub.add_parser("recall", help="Retrieve highest value-per-token memories within a token budget.")
    p_rec.add_argument("--root", default=".")
    p_rec.add_argument("--query", default="")
    p_rec.add_argument("--kind", default="")
    p_rec.add_argument("--budget-tokens", type=int, default=800)
    p_rec.add_argument("--limit", type=int, default=40)
    p_rec.add_argument("--format", choices=("xml", "json", "yaml"), default="xml")
    p_rec.add_argument("--no-touch", action="store_true")

    p_cmp = sub.add_parser("compact", help="Evict expired/excess records and vacuum SQLite WAL.")
    p_cmp.add_argument("--root", default=".")
    p_cmp.add_argument("--max-records", type=int, default=500)
    p_cmp.add_argument("--json", action="store_true")

    p_st = sub.add_parser("stats", help="Show DB size and record counts.")
    p_st.add_argument("--root", default=".")
    p_st.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "init":
        dbf = db_path_for(root)
        with connect_db(dbf):
            pass
        out = {"initialized": True, "db": str(dbf), "bytes": dbf.stat().st_size}
        print(json.dumps(out, indent=2) if args.json else f"initialized {dbf}")
        return 0
    if args.cmd == "put":
        res = put_memory(
            root, key=args.key, kind=args.kind, content=args.content,
            priority=args.priority, tags=args.tags, source=args.source, ttl_hours=args.ttl_hours,
        )
        print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "recall":
        res = recall_memories(
            root, query=args.query, kind=args.kind,
            budget_tokens=args.budget_tokens, limit=args.limit, touch_hits=not args.no_touch,
        )
        if args.format == "xml":
            print(format_xml(res))
        elif args.format == "yaml":
            print(format_yaml(res))
        else:
            print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "compact":
        res = compact_memory(root, max_records=args.max_records)
        print(json.dumps(res, indent=2) if args.json else f"compacted {res['db']}: {res['remaining']} records ({res['bytes']} B)")
        return 0
    if args.cmd == "stats":
        res = memory_stats(root)
        print(json.dumps(res, indent=2) if args.json else f"{res['records']} records, {res['bytes']} B ({res['db']})")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
