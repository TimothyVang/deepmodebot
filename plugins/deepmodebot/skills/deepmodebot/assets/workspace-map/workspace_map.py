#!/usr/bin/env python3
"""Zero-bloat memory-mapped workspace, repo, Orca, PR, and project-state index.

    python workspace_map.py sync [path] [--offline] [--no-orca] [--force-prs] [--fast]
    python workspace_map.py overview [path] [--max-bytes 1400] [--offline] [--no-orca] [--fast]
    python workspace_map.py query <term> [path] [--limit 15] [--all-repos] [--no-sync]
    python workspace_map.py workspaces [path] [--all-repos] [--no-orca] [--fast]
    python workspace_map.py prs [path] [--all-repos] [--offline] [--force-prs]
    python workspace_map.py prune [--days 30]

All subcommands accept `--json`, `--db <path>`, and `--global`.
One shared SQLite DB per repo lives at `<main-checkout>/.scratch/workspace-map.db`
so linked git/Orca worktrees share the same symbol index without duplication.
No file bodies, no embeddings, no background daemon, 100% Python 3 stdlib.
"""
import argparse
import ast
import concurrent.futures
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

SCHEMA_VERSION = 2
MAX_FILE_BYTES = 256 * 1024
MAX_SIGNATURE_CHARS = 120
PR_TTL_SECONDS = 180.0
DEFAULT_OVERVIEW_BYTES = 1400
DEFAULT_PRUNE_DAYS = 30
MMAP_SIZE_BYTES = 0
MAX_DIRTY_CHECK_WORKTREES = 16
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PR_JSON_FIELDS = (
    "number,title,headRefName,baseRefName,state,isDraft,"
    "mergeStateStatus,reviewDecision,url,updatedAt,statusCheckRollup"
)

SKIP_DIR_PARTS = {
    ".git", ".scratch", ".worktrees", "node_modules", "__pycache__",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

LOCKFILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock",
    "poetry.lock", "uv.lock", "composer.lock", "gemfile.lock",
    "bun.lock", "bun.lockb", "flake.lock", "pipfile.lock", "podfile.lock",
    "go.sum", "shrinkwrap.yaml", "npm-shrinkwrap.json",
}

SKIP_SUFFIXES = (
    ".min.js", ".min.css", ".min.mjs", ".min.cjs", ".bundle.js", ".js.map", ".css.map",
)

BINARY_MEDIA_EXTS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff",
    ".psd", ".avif", ".heic", ".tga", ".exr", ".hdr", ".icns", ".svg",
    # Audio / Video
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".mp4", ".mov", ".avi",
    ".mkv", ".webm",
    # 3D / Game assets
    ".blend", ".blend1", ".fbx", ".glb", ".gltf", ".obj", ".stl", ".dae",
    ".usdz", ".usd", ".usda", ".usdc", ".abc", ".ply", ".3ds", ".uasset",
    ".umap", ".pak", ".unitypackage", ".dds", ".ktx", ".ktx2",
    # Archives / Binaries / Fonts / Databases
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".exe", ".dll",
    ".so", ".dylib", ".pdb", ".lib", ".a", ".o", ".pyc", ".pyo", ".class",
    ".jar", ".war", ".wasm", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".sqlite", ".sqlite3", ".db", ".bin", ".dat", ".hex", ".dmg", ".iso",
}

LANG_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".cs": "csharp",
    ".java": "java",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".c": "c", ".h": "c",
    ".md": "markdown", ".mdx": "markdown",
    ".json": "json", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
    ".html": "html", ".css": "css", ".sql": "sql",
}

ENTRYPOINT_NAMES = {
    "main.py", "app.py", "cli.py", "server.py", "manage.py", "run.py", "__main__.py",
    "index.ts", "index.tsx", "index.js", "index.mjs", "main.ts", "main.js", "server.ts", "server.js",
    "main.rs", "lib.rs", "main.go", "program.cs", "makefile", "justfile",
    "package.json", "pyproject.toml", "cargo.toml", "go.mod",
}

TOP_DOC_NAMES = {"readme.md", "agents.md", "claude.md", "contributing.md", "project_brief.md"}

# Lightweight regex extractors (line-oriented to avoid catastrophic backtracking).
JS_FUNC_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)\s*(?:<[^>{]*>)?\s*\([^)]*\)"
)
JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
)
JS_IFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")
JS_TYPE_RE = re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*=")
JS_ENUM_RE = re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+([A-Za-z_$][\w$]*)")
JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]{1,60})?=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)

RS_FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?(?:extern\s+\"[^\"]*\"\s+)?fn\s+([A-Za-z_]\w*)"
)
RS_STRUCT_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_]\w*)")
RS_ENUM_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_]\w*)")
RS_TRAIT_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?trait\s+([A-Za-z_]\w*)")
RS_IMPL_RE = re.compile(r"^\s*(?:unsafe\s+)?impl(?:<[^>]*>)?\s+([A-Za-z_][\w:<>,\s]*?)(?:\s+where\b|\s*\{|$)")
RS_TYPE_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?type\s+([A-Za-z_]\w*)\b")

GO_FUNC_RE = re.compile(r"^func\s+(?:\(([^)]*)\)\s+)?([A-Za-z_]\w*)\s*\(")
GO_TYPE_RE = re.compile(r"^type\s+([A-Za-z_]\w*)\s+(struct|interface|\S+)")

CLAN_TYPE_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|final|abstract|sealed|partial|readonly|export)\s+)*"
    r"(class|struct|interface|enum|record)\s+([A-Za-z_]\w*)"
)
CLAN_FUNC_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|async|inline|extern|"
    r"constexpr|const|final|synchronized|abstract|native|unsafe)\s+)*"
    r"(?:[\w:<>\[\],*&~]+\s+)+([A-Za-z_~]\w*)\s*\([^;{}]*\)\s*"
    r"(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?(?:throws\s+[\w.,\s]+)?(?:\{|=>|$)"
)
CLAN_CONTROL_KW = {
    "if", "for", "while", "switch", "catch", "return", "else", "sizeof",
    "typeof", "delete", "new", "throw", "case", "do", "using", "lock", "fixed",
}

MD_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
MD_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")

REMOTE_SLUG_RE = re.compile(r"(?:github\.com[:/]|[:/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", re.I)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repos (
    repo_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    main_checkout TEXT NOT NULL,
    common_dir TEXT NOT NULL,
    remote_url TEXT NOT NULL DEFAULT '',
    remote_slug TEXT NOT NULL DEFAULT '',
    default_branch TEXT NOT NULL DEFAULT '',
    last_sync_ts REAL NOT NULL DEFAULT 0,
    last_pr_sync_ts REAL NOT NULL DEFAULT 0,
    file_count INTEGER NOT NULL DEFAULT 0,
    symbol_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    worktree_key TEXT NOT NULL DEFAULT '',
    rel_path TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    lang TEXT NOT NULL,
    role TEXT NOT NULL,
    blob_sha TEXT NOT NULL DEFAULT '',
    UNIQUE(repo_key, worktree_key, rel_path)
);
CREATE INDEX IF NOT EXISTS idx_files_repo_role ON files(repo_key, worktree_key, role);

CREATE TABLE IF NOT EXISTS worktree_deleted (
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    worktree_key TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    PRIMARY KEY (repo_key, worktree_key, rel_path)
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    worktree_key TEXT NOT NULL DEFAULT '',
    rel_path TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    signature TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_repo_wt ON symbols(repo_key, worktree_key);

CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name,
    signature,
    rel_path,
    content='symbols',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS symbols_ai AFTER INSERT ON symbols BEGIN
    INSERT INTO symbols_fts(rowid, name, signature, rel_path)
    VALUES (new.id, new.name, new.signature, new.rel_path);
END;

CREATE TRIGGER IF NOT EXISTS symbols_ad AFTER DELETE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, signature, rel_path)
    VALUES ('delete', old.id, old.name, old.signature, old.rel_path);
END;

CREATE TRIGGER IF NOT EXISTS symbols_au AFTER UPDATE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, signature, rel_path)
    VALUES ('delete', old.id, old.name, old.signature, old.rel_path);
    INSERT INTO symbols_fts(rowid, name, signature, rel_path)
    VALUES (new.id, new.name, new.signature, new.rel_path);
END;

CREATE TABLE IF NOT EXISTS workspaces (
    worktree_key TEXT PRIMARY KEY,
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    path TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    head_sha TEXT NOT NULL DEFAULT '',
    is_main INTEGER NOT NULL DEFAULT 0,
    is_detached INTEGER NOT NULL DEFAULT 0,
    is_dirty INTEGER NOT NULL DEFAULT 0,
    dirty_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'git',
    orca_id TEXT NOT NULL DEFAULT '',
    orca_name TEXT NOT NULL DEFAULT '',
    orca_host TEXT NOT NULL DEFAULT '',
    orca_status TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_workspaces_repo ON workspaces(repo_key);
CREATE INDEX IF NOT EXISTS idx_workspaces_branch ON workspaces(repo_key, branch);

CREATE TABLE IF NOT EXISTS prs (
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    head_branch TEXT NOT NULL DEFAULT '',
    base_branch TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'OPEN',
    is_draft INTEGER NOT NULL DEFAULT 0,
    merge_state TEXT NOT NULL DEFAULT '',
    review_decision TEXT NOT NULL DEFAULT '',
    checks_summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    synced_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_key, number)
);
CREATE INDEX IF NOT EXISTS idx_prs_branch ON prs(repo_key, head_branch);

CREATE TABLE IF NOT EXISTS project_state (
    repo_key TEXT NOT NULL REFERENCES repos(repo_key) ON DELETE CASCADE,
    worktree_key TEXT NOT NULL DEFAULT '',
    state_key TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    product TEXT NOT NULL DEFAULT '',
    active_sprint INTEGER,
    passed_slices INTEGER NOT NULL DEFAULT 0,
    active_slices INTEGER NOT NULL DEFAULT 0,
    total_slices INTEGER NOT NULL DEFAULT 0,
    deferred_count INTEGER NOT NULL DEFAULT 0,
    pending_inventory INTEGER NOT NULL DEFAULT 0,
    sme_gate_blocked INTEGER NOT NULL DEFAULT 0,
    last_exit_code INTEGER,
    last_exit_reason TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_key, worktree_key, state_key)
);
CREATE INDEX IF NOT EXISTS idx_project_state_repo ON project_state(repo_key);
"""


def run_cmd(args, cwd=None, timeout=15):
    """Run an external command safely on Windows and POSIX without console popups."""
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return subprocess.CompletedProcess(args, 127, "", str(err))


def run_cmd_bytes(args, cwd=None, timeout=15):
    """Run an external command returning raw bytes (e.g. git ls-files -z)."""
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return subprocess.CompletedProcess(args, 127, b"", str(err).encode("utf-8", errors="replace"))


def normalize_path_key(path):
    """Canonical lowercase POSIX key so Windows/POSIX paths match identically across tools."""
    resolved = os.path.realpath(os.path.abspath(path))
    return os.path.normcase(resolved).replace("\\", "/").rstrip("/") or "/"


def display_path(path):
    """Clean normalized path with forward slashes for concise cross-platform output."""
    return os.path.realpath(os.path.abspath(path)).replace("\\", "/")


def cap_sig(text, limit=MAX_SIGNATURE_CHARS):
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def truncate_utf8(text, max_bytes):
    """Truncate text so its UTF-8 encoding fits strictly within max_bytes."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    if max_bytes <= 0:
        return ""
    suffix = b"\n..." if max_bytes >= 8 else b"..."
    if max_bytes <= len(suffix):
        return raw[:max_bytes].decode("utf-8", errors="ignore")
    cut = raw[: max_bytes - len(suffix)]
    decoded = cut.decode("utf-8", errors="ignore").rstrip()
    result = decoded + suffix.decode("ascii")
    while len(result.encode("utf-8")) > max_bytes and decoded:
        decoded = decoded[:-1]
        result = decoded + suffix.decode("ascii")
    return result


def db_disk_bytes(db_path):
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = db_path + suffix
        if os.path.exists(candidate):
            try:
                total += os.path.getsize(candidate)
            except OSError:
                pass
    return total


def global_db_path():
    return os.path.join(os.path.expanduser("~"), ".cache", "deepmodebot", "workspace-map.db")


def ensure_scratch_gitignore(main_checkout):
    scratch_dir = os.path.join(main_checkout, ".scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    ignore_path = os.path.join(scratch_dir, ".gitignore")
    if not os.path.exists(ignore_path):
        with open(ignore_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("*\n")


def parse_remote_slug(remote_url):
    if not remote_url:
        return ""
    match = REMOTE_SLUG_RE.search(remote_url.strip())
    return match.group(1) if match else ""


def _read_git_head_branch(git_dir):
    try:
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8", errors="replace") as handle:
            line = handle.readline().strip()
    except OSError:
        return None
    if line.startswith("ref: refs/heads/"):
        return line[len("ref: refs/heads/"):].strip()
    return ""


def _read_origin_remote_url(common_dir):
    config_path = os.path.join(common_dir, "config")
    try:
        with open(config_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    in_origin = False
    has_include = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line[1:-1].strip()
            in_origin = header.lower() == 'remote "origin"'
            if header.lower().startswith("include"):
                has_include = True
            continue
        if in_origin and "=" in line:
            key, val = line.split("=", 1)
            if key.strip().lower() == "url":
                return val.strip()
    return None if has_include else ""


def _read_origin_default_branch(common_dir):
    ref_path = os.path.join(common_dir, "refs", "remotes", "origin", "HEAD")
    try:
        with open(ref_path, encoding="utf-8", errors="replace") as handle:
            line = handle.readline().strip()
    except OSError:
        return ""
    prefix = "ref: refs/remotes/origin/"
    if line.startswith(prefix):
        return line[len(prefix):].strip()
    return ""


def resolve_repo(path="."):
    """Resolve git checkout + common dir so linked worktrees share one repo_key and DB."""
    abs_path = os.path.abspath(path or ".")
    probe = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if not os.path.isdir(probe):
        return None

    rev = run_cmd([
        "git", "-C", probe, "rev-parse", "--path-format=absolute",
        "--show-toplevel", "--git-common-dir", "--git-dir",
    ])
    lines = [ln.strip() for ln in rev.stdout.splitlines() if ln.strip()]
    if rev.returncode == 0 and len(lines) >= 3:
        checkout_root = os.path.realpath(lines[0])
        common_dir = os.path.realpath(lines[1])
        git_dir = os.path.realpath(lines[2])
    else:
        top = run_cmd(["git", "-C", probe, "rev-parse", "--show-toplevel"])
        if top.returncode != 0 or not top.stdout.strip():
            return None
        checkout_root = os.path.realpath(top.stdout.strip())
        common = run_cmd(["git", "-C", checkout_root, "rev-parse", "--git-common-dir"])
        if common.returncode != 0 or not common.stdout.strip():
            return None
        raw_common = common.stdout.strip()
        common_dir = os.path.realpath(
            raw_common if os.path.isabs(raw_common) else os.path.join(checkout_root, raw_common)
        )
        gdir = run_cmd(["git", "-C", checkout_root, "rev-parse", "--git-dir"])
        raw_gdir = gdir.stdout.strip() if gdir.returncode == 0 and gdir.stdout.strip() else ".git"
        git_dir = os.path.realpath(
            raw_gdir if os.path.isabs(raw_gdir) else os.path.join(checkout_root, raw_gdir)
        )

    if os.path.basename(common_dir).lower() == ".git":
        main_checkout = os.path.realpath(os.path.dirname(common_dir))
    else:
        main_checkout = common_dir

    repo_key = normalize_path_key(main_checkout)
    remote_url = _read_origin_remote_url(common_dir)
    if remote_url is None:
        remote = run_cmd(["git", "-C", checkout_root, "config", "--get", "remote.origin.url"])
        remote_url = remote.stdout.strip() if remote.returncode == 0 else ""
    remote_slug = parse_remote_slug(remote_url)

    current_branch = _read_git_head_branch(git_dir)
    if current_branch is None:
        branch_res = run_cmd(["git", "-C", checkout_root, "symbolic-ref", "--short", "HEAD"])
        current_branch = branch_res.stdout.strip() if branch_res.returncode == 0 else ""

    def_branch = _read_origin_default_branch(common_dir) or current_branch

    name = remote_slug or os.path.basename(main_checkout) or "repo"
    return {
        "repo_key": repo_key,
        "name": name,
        "checkout_root": checkout_root,
        "worktree_key": normalize_path_key(checkout_root),
        "main_checkout": main_checkout,
        "common_dir": common_dir,
        "remote_url": remote_url,
        "remote_slug": remote_slug,
        "current_branch": current_branch,
        "default_branch": def_branch,
    }


def resolve_db_path(opts, repo_info=None):
    explicit_db = getattr(opts, "db", None)
    use_global = getattr(opts, "use_global", False)
    if explicit_db:
        return os.path.abspath(explicit_db)
    if use_global:
        return global_db_path()
    env_db = os.environ.get("DEEPMODEBOT_MAP_DB", "").strip()
    if env_db:
        return os.path.abspath(env_db)
    if repo_info is not None:
        ensure_scratch_gitignore(repo_info["main_checkout"])
        return os.path.join(repo_info["main_checkout"], ".scratch", "workspace-map.db")
    return global_db_path()


def connect_db(db_path, readonly=False):
    if readonly:
        uri = f"file:{Path(os.path.abspath(db_path)).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute(f"PRAGMA mmap_size={MMAP_SIZE_BYTES}")
            conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            conn.close()
            raise
        return conn
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA mmap_size={MMAP_SIZE_BYTES}")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        if cols and "worktree_key" not in cols:
            conn.executescript(
                "DROP TRIGGER IF EXISTS symbols_ai;"
                "DROP TRIGGER IF EXISTS symbols_ad;"
                "DROP TRIGGER IF EXISTS symbols_au;"
                "DROP TABLE IF EXISTS symbols_fts;"
                "DROP TABLE IF EXISTS symbols;"
                "DROP TABLE IF EXISTS files;"
            )
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def should_skip_relpath(rel_path):
    norm = rel_path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    norm = norm.lstrip("/")
    if not norm:
        return True
    parts = [p.lower() for p in norm.split("/")]
    if any(part in SKIP_DIR_PARTS for part in parts[:-1]):
        return True
    base = parts[-1]
    if base in LOCKFILE_NAMES:
        return True
    if any(base.endswith(suf) for suf in SKIP_SUFFIXES):
        return True
    _, ext = os.path.splitext(base)
    if ext in BINARY_MEDIA_EXTS:
        return True
    return False


def detect_lang(rel_path):
    base = os.path.basename(rel_path).lower()
    if base in ("makefile", "justfile", "dockerfile"):
        return base
    _, ext = os.path.splitext(base)
    return LANG_BY_EXT.get(ext, "text")


def classify_role(rel_path):
    norm = rel_path.replace("\\", "/").lower()
    parts = norm.split("/")
    base = parts[-1]
    if base == "skill.md":
        if len(parts) >= 2 and parts[-2].startswith("verify-"):
            return "verify-skill"
        return "skill"
    if base.endswith("-manifest.json") and (norm.startswith("docs/specs/") or norm.startswith(".scratch/goals/")):
        return "manifest"
    if (
        any(p in ("tests", "test", "__tests__") for p in parts[:-1])
        or base.startswith("test_")
        or base.endswith(("_test.py", "_test.go", "_test.rs", ".test.ts", ".test.js", ".test.tsx", ".spec.ts", ".spec.js"))
    ):
        return "test"
    if base in TOP_DOC_NAMES or (len(parts) == 1 and base.endswith(".md")) or (parts[0] == "docs" and base.endswith(".md")):
        return "doc"
    if base in ENTRYPOINT_NAMES or (parts[0] in ("bin", "cmd", "scripts") and not base.endswith(".md")):
        return "entrypoint"
    if base.endswith((".json", ".toml", ".yaml", ".yml", ".ini", ".cfg")) or norm.startswith(".github/workflows/"):
        return "config"
    return "source"


def _py_format_args(args_node):
    if hasattr(ast, "unparse"):
        try:
            return ast.unparse(args_node)
        except Exception:
            pass
    names = [a.arg for a in args_node.posonlyargs + args_node.args]
    if args_node.vararg:
        names.append("*" + args_node.vararg.arg)
    names.extend(a.arg for a in args_node.kwonlyargs)
    if args_node.kwarg:
        names.append("**" + args_node.kwarg.arg)
    return ", ".join(names)


def _extract_python_symbols(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out = []

    def visit_body(body, class_prefix=""):
        for node in body:
            if isinstance(node, ast.ClassDef):
                bases = []
                if hasattr(ast, "unparse"):
                    for base in node.bases:
                        try:
                            bases.append(ast.unparse(base))
                        except Exception:
                            pass
                base_str = f"({', '.join(bases)})" if bases else ""
                full_name = f"{class_prefix}.{node.name}" if class_prefix else node.name
                out.append((full_name, "class", node.lineno, cap_sig(f"class {full_name}{base_str}")))
                visit_body(node.body, full_name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                arg_str = _py_format_args(node.args)
                ret = ""
                if node.returns is not None and hasattr(ast, "unparse"):
                    try:
                        ret = f" -> {ast.unparse(node.returns)}"
                    except Exception:
                        ret = ""
                kind = "method" if class_prefix else "function"
                full_name = f"{class_prefix}.{node.name}" if class_prefix else node.name
                sig = cap_sig(f"{prefix} {full_name}({arg_str}){ret}")
                out.append((full_name, kind, node.lineno, sig))

    visit_body(tree.body)
    return out


def _extract_js_ts_symbols(text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        for regex, kind in (
            (JS_FUNC_RE, "function"),
            (JS_CLASS_RE, "class"),
            (JS_IFACE_RE, "interface"),
            (JS_TYPE_RE, "type"),
            (JS_ENUM_RE, "enum"),
            (JS_ARROW_RE, "function"),
        ):
            match = regex.match(line)
            if match:
                name = match.group(1)
                sig = cap_sig(stripped.split("{", 1)[0].rstrip())
                out.append((name, kind, lineno, sig))
                break
    return out


def _extract_rust_symbols(text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("//", "/*", "*", "#[")):
            continue
        for regex, kind in (
            (RS_FN_RE, "function"),
            (RS_STRUCT_RE, "struct"),
            (RS_ENUM_RE, "enum"),
            (RS_TRAIT_RE, "trait"),
            (RS_IMPL_RE, "impl"),
            (RS_TYPE_RE, "type"),
        ):
            match = regex.match(line)
            if match:
                name = re.sub(r"\s+", " ", match.group(1)).strip()
                sig = cap_sig(stripped.split("{", 1)[0].rstrip("; "))
                out.append((name, kind, lineno, sig))
                break
    return out


def _extract_go_symbols(text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        match = GO_FUNC_RE.match(line)
        if match:
            recv, name = match.group(1), match.group(2)
            kind = "method" if recv else "function"
            sig = cap_sig(stripped.split("{", 1)[0].rstrip())
            out.append((name, kind, lineno, sig))
            continue
        match = GO_TYPE_RE.match(line)
        if match:
            name, target = match.group(1), match.group(2)
            kind = target if target in ("struct", "interface") else "type"
            sig = cap_sig(stripped.split("{", 1)[0].rstrip())
            out.append((name, kind, lineno, sig))
    return out


def _extract_clan_symbols(text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("//", "/*", "*", "#")):
            continue
        match = CLAN_TYPE_RE.match(line)
        if match:
            kind, name = match.group(1), match.group(2)
            sig = cap_sig(stripped.split("{", 1)[0].rstrip())
            out.append((name, kind, lineno, sig))
            continue
        match = CLAN_FUNC_RE.match(line)
        if match:
            name = match.group(1)
            if name.lower() in CLAN_CONTROL_KW:
                continue
            sig = cap_sig(stripped.split("{", 1)[0].split("=>", 1)[0].rstrip())
            out.append((name, "function", lineno, sig))
    return out


def _extract_markdown_symbols(text):
    out = []
    fence_char = ""
    fence_len = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        fmatch = MD_FENCE_RE.match(line)
        if fmatch:
            marker = fmatch.group(1)
            if not fence_char:
                fence_char, fence_len = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char, fence_len = "", 0
            continue
        if fence_char:
            continue
        hmatch = MD_HEADING_RE.match(line)
        if hmatch:
            hashes, title = hmatch.group(1), hmatch.group(2).strip()
            out.append((cap_sig(title, 80), "heading", lineno, cap_sig(f"{hashes} {title}")))
    return out


def extract_symbols(rel_path, lang, text):
    if lang == "python":
        return _extract_python_symbols(text)
    if lang in ("typescript", "javascript"):
        return _extract_js_ts_symbols(text)
    if lang == "rust":
        return _extract_rust_symbols(text)
    if lang == "go":
        return _extract_go_symbols(text)
    if lang in ("csharp", "java", "cpp", "c"):
        return _extract_clan_symbols(text)
    if lang == "markdown":
        return _extract_markdown_symbols(text)
    return []


def list_tracked_files(checkout_root):
    res = run_cmd_bytes(["git", "-C", checkout_root, "ls-files", "-z"])
    if res.returncode != 0:
        return []
    raw_items = res.stdout.split(b"\x00")
    return [item.decode("utf-8", errors="replace") for item in raw_items if item]


def list_tracked_blobs(checkout_root):
    """Return ordered list of (rel_path, clean_blob_sha) for tracked files; dirty files get '' as blob_sha."""
    res = run_cmd_bytes(["git", "-C", checkout_root, "ls-files", "-s", "-z"])
    if res.returncode != 0:
        return [(p.replace("\\", "/"), "") for p in list_tracked_files(checkout_root)]
    dirty_res = run_cmd_bytes(["git", "-C", checkout_root, "diff", "--name-only", "-z"])
    dirty = set()
    if dirty_res.returncode == 0:
        for item in dirty_res.stdout.split(b"\x00"):
            if item:
                dirty.add(item.decode("utf-8", errors="replace").replace("\\", "/"))
    by_path = {}
    for entry in res.stdout.split(b"\x00"):
        if not entry or b"\t" not in entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        parts = meta.decode("ascii", errors="replace").split()
        blob_sha = parts[1] if len(parts) >= 2 else ""
        rel_path = raw_path.decode("utf-8", errors="replace").replace("\\", "/")
        by_path[rel_path] = "" if rel_path in dirty else blob_sha
    return list(by_path.items())


def _active_view_counts(conn, repo_key, wt_key):
    """Count files and symbols visible from `wt_key` (baseline '' plus per-worktree overlay minus tombstones)."""
    is_main = not wt_key or wt_key == repo_key
    if is_main:
        total_files = conn.execute(
            "SELECT COUNT(*) FROM files WHERE repo_key = ? AND worktree_key = ''",
            (repo_key,),
        ).fetchone()[0]
        total_symbols = conn.execute(
            "SELECT COUNT(*) FROM symbols WHERE repo_key = ? AND worktree_key = ''",
            (repo_key,),
        ).fetchone()[0]
        return total_files, total_symbols
    total_files = conn.execute(
        """SELECT COUNT(*) FROM files f
           WHERE f.repo_key = ?
             AND (f.worktree_key = ? OR (
                 f.worktree_key = ''
                 AND NOT EXISTS (
                     SELECT 1 FROM files ov
                     WHERE ov.repo_key = f.repo_key AND ov.worktree_key = ? AND ov.rel_path = f.rel_path
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM worktree_deleted wd
                     WHERE wd.repo_key = f.repo_key AND wd.worktree_key = ? AND wd.rel_path = f.rel_path
                 )
             ))""",
        (repo_key, wt_key, wt_key, wt_key),
    ).fetchone()[0]
    total_symbols = conn.execute(
        """SELECT COUNT(*) FROM symbols s
           WHERE s.repo_key = ?
             AND (s.worktree_key = ? OR (
                 s.worktree_key = ''
                 AND NOT EXISTS (
                     SELECT 1 FROM files ov
                     WHERE ov.repo_key = s.repo_key AND ov.worktree_key = ? AND ov.rel_path = s.rel_path
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM worktree_deleted wd
                     WHERE wd.repo_key = s.repo_key AND wd.worktree_key = ? AND wd.rel_path = s.rel_path
                 )
             ))""",
        (repo_key, wt_key, wt_key, wt_key),
    ).fetchone()[0]
    return total_files, total_symbols


def sync_files_and_symbols(conn, repo_info):
    """Sync tracked files and symbols for a checkout.

    Main checkout owns the shared baseline (`worktree_key = ''`). Linked worktrees inherit unchanged baseline
    files (same clean git blob SHA) with zero duplication and store only added/modified files in their own
    `worktree_key` overlay plus tombstones in `worktree_deleted`, so branches never clobber each other.
    """
    repo_key = repo_info["repo_key"]
    wt_key = repo_info["worktree_key"]
    checkout_root = repo_info["checkout_root"]
    is_main = wt_key == repo_key
    target_wt = "" if is_main else wt_key
    tracked = list_tracked_blobs(checkout_root)

    baseline = {
        row["rel_path"]: (row["id"], row["mtime_ns"], row["size"], row["blob_sha"])
        for row in conn.execute(
            "SELECT id, rel_path, mtime_ns, size, blob_sha FROM files WHERE repo_key = ? AND worktree_key = ''",
            (repo_key,),
        )
    }
    existing = (
        baseline
        if is_main
        else {
            row["rel_path"]: (row["id"], row["mtime_ns"], row["size"], row["blob_sha"])
            for row in conn.execute(
                "SELECT id, rel_path, mtime_ns, size, blob_sha FROM files WHERE repo_key = ? AND worktree_key = ?",
                (repo_key, target_wt),
            )
        }
    )

    seen_target = set()
    seen_all_tracked = set()
    files_indexed = 0
    files_skipped = 0
    files_filtered = 0
    file_updates = []
    delete_sym_ids = []
    pending_existing_syms = []
    file_inserts = []
    pending_new_syms = []

    for rel_path, blob_sha in tracked:
        if should_skip_relpath(rel_path):
            files_filtered += 1
            continue
        abs_path = os.path.join(checkout_root, rel_path)
        try:
            st = os.stat(abs_path)
        except OSError:
            continue
        if not os.path.isfile(abs_path):
            continue
        if st.st_size > MAX_FILE_BYTES:
            files_filtered += 1
            continue

        seen_all_tracked.add(rel_path)

        if not is_main:
            base_row = baseline.get(rel_path)
            if base_row is not None and blob_sha and base_row[3] and base_row[3] == blob_sha:
                # Identical clean file in shared baseline: inherit without duplicating rows.
                files_skipped += 1
                continue

        prev = existing.get(rel_path)
        if prev is not None and prev[1] == st.st_mtime_ns and prev[2] == st.st_size and prev[3] == blob_sha:
            seen_target.add(rel_path)
            files_skipped += 1
            continue

        try:
            with open(abs_path, "rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            continue
        if len(raw) > MAX_FILE_BYTES or b"\x00" in raw[:8192]:
            files_filtered += 1
            continue

        text = raw.decode("utf-8", errors="replace")
        lang = detect_lang(rel_path)
        role = classify_role(rel_path)
        symbols = extract_symbols(rel_path, lang, text)

        if prev is not None:
            file_id = prev[0]
            file_updates.append((st.st_mtime_ns, st.st_size, lang, role, blob_sha, file_id))
            delete_sym_ids.append((file_id,))
            if symbols:
                for name, kind, line, sig in symbols:
                    pending_existing_syms.append((file_id, repo_key, target_wt, rel_path, name, kind, line, sig))
        else:
            file_inserts.append((repo_key, target_wt, rel_path, st.st_mtime_ns, st.st_size, lang, role, blob_sha))
            if symbols:
                pending_new_syms.append((rel_path, symbols))
        seen_target.add(rel_path)
        files_indexed += 1

    if file_updates:
        conn.executemany(
            "UPDATE files SET mtime_ns = ?, size = ?, lang = ?, role = ?, blob_sha = ? WHERE id = ?",
            file_updates,
        )
    if delete_sym_ids:
        conn.executemany("DELETE FROM symbols WHERE file_id = ?", delete_sym_ids)
    if file_inserts:
        conn.executemany(
            "INSERT INTO files(repo_key, worktree_key, rel_path, mtime_ns, size, lang, role, blob_sha) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            file_inserts,
        )
        if pending_new_syms:
            new_id_map = {
                r["rel_path"]: r["id"]
                for r in conn.execute(
                    "SELECT id, rel_path FROM files WHERE repo_key = ? AND worktree_key = ?",
                    (repo_key, target_wt),
                ).fetchall()
            }
            for rel_path, symbols in pending_new_syms:
                fid = new_id_map.get(rel_path)
                if fid is not None:
                    for name, kind, line, sig in symbols:
                        pending_existing_syms.append((fid, repo_key, target_wt, rel_path, name, kind, line, sig))
    if pending_existing_syms:
        conn.executemany(
            "INSERT INTO symbols(file_id, repo_key, worktree_key, rel_path, name, kind, line, signature) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            pending_existing_syms,
        )
    removed_ids = [file_id for rel_path, (file_id, _, _, _) in existing.items() if rel_path not in seen_target]
    if removed_ids:
        conn.executemany("DELETE FROM files WHERE id = ?", [(fid,) for fid in removed_ids])

    if is_main:
        # Prune redundant linked-worktree overlay rows that now match the clean main baseline.
        conn.execute(
            """DELETE FROM files
               WHERE repo_key = ? AND worktree_key != '' AND blob_sha != ''
                 AND EXISTS (
                     SELECT 1 FROM files b
                     WHERE b.repo_key = files.repo_key AND b.worktree_key = ''
                       AND b.rel_path = files.rel_path AND b.blob_sha = files.blob_sha
                 )""",
            (repo_key,),
        )
    else:
        conn.execute(
            "DELETE FROM worktree_deleted WHERE repo_key = ? AND worktree_key = ?",
            (repo_key, target_wt),
        )
        deleted_from_base = [rp for rp in baseline if rp not in seen_all_tracked]
        if deleted_from_base:
            conn.executemany(
                "INSERT OR IGNORE INTO worktree_deleted(repo_key, worktree_key, rel_path) VALUES(?, ?, ?)",
                [(repo_key, target_wt, rp) for rp in deleted_from_base],
            )

    total_files, total_symbols = _active_view_counts(conn, repo_key, wt_key)
    return {
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "files_filtered": files_filtered,
        "files_removed": len(removed_ids),
        "total_files": total_files,
        "total_symbols": total_symbols,
    }


def parse_git_worktrees(checkout_root, main_checkout):
    res = run_cmd(["git", "-C", checkout_root, "worktree", "list", "--porcelain"])
    if res.returncode != 0:
        return []
    main_key = normalize_path_key(main_checkout)
    items = []
    cur = {}

    def flush():
        if not cur.get("path"):
            return
        if cur.get("prunable") or not os.path.isdir(cur["path"]):
            return
        wkey = normalize_path_key(cur["path"])
        items.append({
            "worktree_key": wkey,
            "path": display_path(cur["path"]),
            "raw_path": cur["path"],
            "branch": cur.get("branch", ""),
            "head_sha": cur.get("head", "")[:12],
            "is_main": 1 if wkey == main_key else 0,
            "is_detached": 1 if cur.get("detached") else 0,
            "is_dirty": 0,
            "dirty_count": 0,
            "source": "git",
            "orca_id": "",
            "orca_name": "",
            "orca_host": "",
            "orca_status": "",
        })

    for line in res.stdout.splitlines():
        if not line.strip():
            flush()
            cur = {}
            continue
        if line.startswith("worktree "):
            cur["path"] = line[9:].strip()
        elif line.startswith("HEAD "):
            cur["head"] = line[5:].strip()
        elif line.startswith("branch "):
            ref = line[7:].strip()
            cur["branch"] = ref[11:] if ref.startswith("refs/heads/") else ref
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("prunable"):
            cur["prunable"] = True
    flush()
    return items


def _check_dirty(raw_path):
    res = run_cmd(["git", "-C", raw_path, "status", "--porcelain"], timeout=4)
    if res.returncode != 0:
        return 0, 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    return (1 if lines else 0), len(lines)


def populate_dirty_status(worktrees, current_wkey, fast=False):
    """Check dirty status in parallel for current, main, and (unless fast) branch-attached worktrees."""
    prioritized = []
    seen = set()
    if fast:
        predicates = (
            lambda w: w["worktree_key"] == current_wkey,
            lambda w: w["is_main"] == 1,
        )
        max_checks = 2
    else:
        predicates = (
            lambda w: w["worktree_key"] == current_wkey,
            lambda w: w["is_main"] == 1,
            lambda w: not w["is_detached"],
        )
        max_checks = MAX_DIRTY_CHECK_WORKTREES
    for predicate in predicates:
        for wt in worktrees:
            if wt["worktree_key"] not in seen and predicate(wt):
                prioritized.append(wt)
                seen.add(wt["worktree_key"])
            if len(prioritized) >= max_checks:
                break
        if len(prioritized) >= max_checks:
            break
    if not prioritized:
        return
    workers = min(6, len(prioritized))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_check_dirty, wt["raw_path"]): wt for wt in prioritized}
        for future, wt in future_map.items():
            try:
                is_dirty, dirty_count = future.result()
                wt["is_dirty"] = is_dirty
                wt["dirty_count"] = dirty_count
            except Exception:
                pass


def fetch_orca_worktrees():
    """Query `orca worktree list --json` when Orca CLI is available; skip gracefully otherwise."""
    if not shutil.which("orca"):
        return None
    res = run_cmd(["orca", "worktree", "list", "--json"], timeout=4)
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        payload = json.loads(res.stdout)
    except ValueError:
        return None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = (
            payload.get("worktrees")
            or payload.get("items")
            or payload.get("data")
            or payload.get("rows")
            or []
        )
    else:
        return None
    if not isinstance(rows, list):
        return None
    parsed = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_path = (
            item.get("path")
            or item.get("worktreePath")
            or item.get("worktree_path")
            or item.get("directory")
            or item.get("dir")
            or ""
        )
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        branch = str(item.get("branch") or item.get("headRef") or item.get("gitBranch") or "")
        if branch.startswith("refs/heads/"):
            branch = branch[11:]
        repo_path = str(item.get("repoPath") or item.get("repo_path") or item.get("repoRoot") or "")
        parsed.append({
            "raw_path": raw_path,
            "worktree_key": normalize_path_key(raw_path),
            "path": display_path(raw_path),
            "branch": branch,
            "repo_path": repo_path,
            "orca_id": str(item.get("id") or ""),
            "orca_name": str(item.get("name") or item.get("displayName") or ""),
            "orca_host": str(item.get("host") or item.get("environment") or ""),
            "orca_status": str(item.get("status") or item.get("state") or ""),
            "is_dirty": 1 if item.get("dirty") or item.get("isDirty") else 0,
        })
    return parsed


def sync_workspaces(conn, repo_info, no_orca=False, include_foreign_orca=False, fast=False):
    repo_key = repo_info["repo_key"]
    now = time.time()
    if fast:
        dirty_targets = [repo_info["checkout_root"]]
        if normalize_path_key(repo_info["main_checkout"]) != repo_info["worktree_key"]:
            dirty_targets.append(repo_info["main_checkout"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(dirty_targets) + 1) as pool:
            wt_future = pool.submit(parse_git_worktrees, repo_info["checkout_root"], repo_info["main_checkout"])
            dirty_futures = {normalize_path_key(p): pool.submit(_check_dirty, p) for p in dirty_targets}
            git_wts = wt_future.result()
            dirty_results = {}
            for wkey, fut in dirty_futures.items():
                try:
                    dirty_results[wkey] = fut.result()
                except Exception:
                    dirty_results[wkey] = (0, 0)
        for wt in git_wts:
            if wt["worktree_key"] in dirty_results:
                wt["is_dirty"], wt["dirty_count"] = dirty_results[wt["worktree_key"]]
    else:
        git_wts = parse_git_worktrees(repo_info["checkout_root"], repo_info["main_checkout"])
        populate_dirty_status(git_wts, repo_info["worktree_key"], fast=False)
    by_key = {wt["worktree_key"]: wt for wt in git_wts}

    orca_used = False
    if not no_orca:
        orca_rows = fetch_orca_worktrees()
        if orca_rows is not None:
            orca_used = True
            main_prefix = repo_key + "/"
            foreign_orca_rows = []
            for row in orca_rows:
                wkey = row["worktree_key"]
                if wkey in by_key:
                    target = by_key[wkey]
                    target["source"] = "git+orca"
                    target["orca_id"] = row["orca_id"]
                    target["orca_name"] = row["orca_name"]
                    target["orca_host"] = row["orca_host"]
                    target["orca_status"] = row["orca_status"]
                    if not target["branch"] and row["branch"]:
                        target["branch"] = row["branch"]
                    continue
                same_repo = (
                    (row["repo_path"] and normalize_path_key(row["repo_path"]) == repo_key)
                    or wkey == repo_key
                    or wkey.startswith(main_prefix)
                )
                if same_repo and os.path.isdir(row["raw_path"]):
                    by_key[wkey] = {
                        "worktree_key": wkey,
                        "path": row["path"],
                        "raw_path": row["raw_path"],
                        "branch": row["branch"],
                        "head_sha": "",
                        "is_main": 1 if wkey == repo_key else 0,
                        "is_detached": 0 if row["branch"] else 1,
                        "is_dirty": row["is_dirty"],
                        "dirty_count": 1 if row["is_dirty"] else 0,
                        "source": "orca",
                        "orca_id": row["orca_id"],
                        "orca_name": row["orca_name"],
                        "orca_host": row["orca_host"],
                        "orca_status": row["orca_status"],
                    }
                elif include_foreign_orca and os.path.isdir(row["raw_path"]):
                    foreign = resolve_repo(row["raw_path"])
                    if foreign and foreign["repo_key"] != repo_key:
                        upsert_repo_row(conn, foreign, touch_sync=False)
                        foreign_orca_rows.append((
                            wkey, foreign["repo_key"], row["path"], row["branch"],
                            1 if wkey == foreign["repo_key"] else 0,
                            0 if row["branch"] else 1,
                            row["is_dirty"], 1 if row["is_dirty"] else 0,
                            row["orca_id"], row["orca_name"], row["orca_host"], row["orca_status"], now,
                        ))
            if foreign_orca_rows:
                conn.executemany(
                    """INSERT INTO workspaces(
                        worktree_key, repo_key, path, branch, head_sha, is_main, is_detached,
                        is_dirty, dirty_count, source, orca_id, orca_name, orca_host, orca_status, updated_at
                    ) VALUES(?, ?, ?, ?, '', ?, ?, ?, ?, 'orca', ?, ?, ?, ?, ?)
                    ON CONFLICT(worktree_key) DO UPDATE SET
                        repo_key=excluded.repo_key, path=excluded.path, branch=excluded.branch,
                        source=CASE WHEN workspaces.source='git' THEN 'git+orca' ELSE excluded.source END,
                        orca_id=excluded.orca_id, orca_name=excluded.orca_name,
                        orca_host=excluded.orca_host, orca_status=excluded.orca_status,
                        updated_at=excluded.updated_at""",
                    foreign_orca_rows,
                )
    existing_keys = {
        r["worktree_key"]
        for r in conn.execute("SELECT worktree_key FROM workspaces WHERE repo_key = ?", (repo_key,))
    }
    stale_keys = existing_keys - set(by_key.keys())
    if stale_keys:
        conn.executemany("DELETE FROM workspaces WHERE worktree_key = ?", [(k,) for k in stale_keys])
        conn.executemany("DELETE FROM files WHERE repo_key = ? AND worktree_key = ?", [(repo_key, k) for k in stale_keys])
        conn.executemany(
            "DELETE FROM worktree_deleted WHERE repo_key = ? AND worktree_key = ?",
            [(repo_key, k) for k in stale_keys],
        )

    wt_params = [
        (
            wt["worktree_key"], repo_key, wt["path"], wt["branch"], wt["head_sha"],
            wt["is_main"], wt["is_detached"], wt["is_dirty"], wt["dirty_count"],
            wt["source"], wt["orca_id"], wt["orca_name"], wt["orca_host"], wt["orca_status"], now,
        )
        for wt in by_key.values()
    ]
    if wt_params:
        conn.executemany(
            """INSERT INTO workspaces(
                worktree_key, repo_key, path, branch, head_sha, is_main, is_detached,
                is_dirty, dirty_count, source, orca_id, orca_name, orca_host, orca_status, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(worktree_key) DO UPDATE SET
                repo_key=excluded.repo_key, path=excluded.path, branch=excluded.branch,
                head_sha=excluded.head_sha, is_main=excluded.is_main, is_detached=excluded.is_detached,
                is_dirty=excluded.is_dirty, dirty_count=excluded.dirty_count, source=excluded.source,
                orca_id=excluded.orca_id, orca_name=excluded.orca_name, orca_host=excluded.orca_host,
                orca_status=excluded.orca_status, updated_at=excluded.updated_at""",
            wt_params,
        )
    return len(by_key), orca_used


def summarize_checks(rollup):
    if not isinstance(rollup, list) or not rollup:
        return ""
    passed = failed = pending = 0
    for item in rollup:
        if not isinstance(item, dict):
            continue
        conclusion = str(item.get("conclusion") or item.get("state") or "").upper()
        status = str(item.get("status") or "").upper()
        if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            passed += 1
        elif conclusion in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            failed += 1
        elif status in ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED") or conclusion in ("PENDING", "EXPECTED", ""):
            pending += 1
        else:
            pending += 1
    parts = []
    if failed:
        parts.append(f"fail:{failed}")
    if pending:
        parts.append(f"pending:{pending}")
    if passed:
        parts.append(f"pass:{passed}")
    return ",".join(parts)


def sync_prs(conn, repo_info, offline=False, force_prs=False):
    repo_key = repo_info["repo_key"]
    if offline or not repo_info["remote_url"] or not shutil.which("gh"):
        count = conn.execute("SELECT COUNT(*) FROM prs WHERE repo_key = ?", (repo_key,)).fetchone()[0]
        return count, True

    row = conn.execute("SELECT last_pr_sync_ts FROM repos WHERE repo_key = ?", (repo_key,)).fetchone()
    last_pr_ts = float(row["last_pr_sync_ts"]) if row and row["last_pr_sync_ts"] else 0.0
    now = time.time()
    if not force_prs and last_pr_ts > 0 and (now - last_pr_ts) < PR_TTL_SECONDS:
        count = conn.execute("SELECT COUNT(*) FROM prs WHERE repo_key = ?", (repo_key,)).fetchone()[0]
        return count, True

    res = run_cmd(
        [
            "gh", "pr", "list", "--author", "@me", "--state", "open",
            "--limit", "50", "--json", PR_JSON_FIELDS,
        ],
        cwd=repo_info["checkout_root"],
        timeout=10,
    )
    if res.returncode != 0 or not res.stdout.strip():
        count = conn.execute("SELECT COUNT(*) FROM prs WHERE repo_key = ?", (repo_key,)).fetchone()[0]
        return count, True

    try:
        items = json.loads(res.stdout)
    except ValueError:
        count = conn.execute("SELECT COUNT(*) FROM prs WHERE repo_key = ?", (repo_key,)).fetchone()[0]
        return count, True

    if not isinstance(items, list):
        count = conn.execute("SELECT COUNT(*) FROM prs WHERE repo_key = ?", (repo_key,)).fetchone()[0]
        return count, True

    seen_nums = set()
    pr_params = []
    for pr in items:
        if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
            continue
        num = pr["number"]
        seen_nums.add(num)
        pr_params.append((
            repo_key,
            num,
            cap_sig(str(pr.get("title") or ""), 120),
            str(pr.get("headRefName") or ""),
            str(pr.get("baseRefName") or ""),
            str(pr.get("state") or "OPEN"),
            1 if pr.get("isDraft") else 0,
            str(pr.get("mergeStateStatus") or ""),
            str(pr.get("reviewDecision") or ""),
            summarize_checks(pr.get("statusCheckRollup")),
            str(pr.get("url") or ""),
            str(pr.get("updatedAt") or ""),
            now,
        ))
    if pr_params:
        conn.executemany(
            """INSERT INTO prs(
                repo_key, number, title, head_branch, base_branch, state, is_draft,
                merge_state, review_decision, checks_summary, url, updated_at, synced_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_key, number) DO UPDATE SET
                title=excluded.title, head_branch=excluded.head_branch, base_branch=excluded.base_branch,
                state=excluded.state, is_draft=excluded.is_draft, merge_state=excluded.merge_state,
                review_decision=excluded.review_decision, checks_summary=excluded.checks_summary,
                url=excluded.url, updated_at=excluded.updated_at, synced_at=excluded.synced_at""",
            pr_params,
        )
    existing_nums = {
        r["number"] for r in conn.execute("SELECT number FROM prs WHERE repo_key = ?", (repo_key,))
    }
    closed_nums = existing_nums - seen_nums
    if closed_nums:
        conn.executemany(
            "DELETE FROM prs WHERE repo_key = ? AND number = ?",
            [(repo_key, n) for n in closed_nums],
        )
    conn.execute("UPDATE repos SET last_pr_sync_ts = ? WHERE repo_key = ?", (now, repo_key))
    return len(seen_nums), False


def _parse_goal_frontmatter(goal_path):
    """Extract lightweight YAML frontmatter key/value pairs from a goal markdown file."""
    try:
        with open(goal_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(32768)
    except OSError:
        return {}
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields


def _normalize_rel_manifest(raw_rel):
    rel = str(raw_rel or "").strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _safe_int(value, default=0):
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_relpath(target, root):
    try:
        return os.path.relpath(target, root)
    except ValueError:
        return None


def _scan_project_state_for_checkout(checkout_root):
    """Scan goal frontmatter, scope manifests, and goal latest-summary.json files inside a checkout."""
    records = {}
    root_key = normalize_path_key(checkout_root)

    # Read active_sprint and manifest links from .scratch/goals/*.md frontmatter (newest wins per manifest).
    goal_by_manifest = {}
    linked_manifest_paths = set()
    goal_files = glob.glob(os.path.join(checkout_root, ".scratch", "goals", "*.md"))
    goal_files.sort(key=lambda p: (os.path.getmtime(p) if os.path.exists(p) else 0.0, p))
    for gpath in goal_files:
        fields = _parse_goal_frontmatter(gpath)
        manifest_rel = _normalize_rel_manifest(fields.get("manifest"))
        if not manifest_rel:
            continue
        raw_sprint = str(fields.get("active_sprint") or "").strip()
        active_sprint = int(raw_sprint) if raw_sprint.isdigit() and int(raw_sprint) >= 1 else None
        goal_by_manifest[manifest_rel] = {
            "goal": str(fields.get("goal") or "").strip(),
            "active_sprint": active_sprint,
        }
        candidate = os.path.join(checkout_root, manifest_rel)
        if os.path.isfile(candidate):
            cand_key = normalize_path_key(candidate)
            if cand_key == root_key or cand_key.startswith(root_key + "/"):
                linked_manifest_paths.add(os.path.realpath(candidate))

    manifest_paths = sorted({
        *(os.path.realpath(p) for p in glob.glob(os.path.join(checkout_root, "docs", "specs", "*-manifest.json"))),
        *(os.path.realpath(p) for p in glob.glob(os.path.join(checkout_root, ".scratch", "goals", "*-manifest.json"))),
        *linked_manifest_paths,
    })
    for mpath in manifest_paths:
        try:
            with open(mpath, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("slices"), list):
            continue
        raw_rel = _safe_relpath(mpath, checkout_root)
        if raw_rel is None:
            continue
        rel = _normalize_rel_manifest(raw_rel)
        slices = [s for s in data["slices"] if isinstance(s, dict)]
        goal_meta = goal_by_manifest.get(rel) or {}
        active_sprint = goal_meta.get("active_sprint")
        if active_sprint is not None:
            active_slices = [s for s in slices if _safe_int(s.get("sprint"), 1) <= active_sprint]
            deferred_count = len(slices) - len(active_slices)
        else:
            active_slices = slices
            deferred_count = 0
        pending_inv = sum(
            1 for item in data.get("inventory", ())
            if isinstance(item, dict) and str(item.get("status") or "").lower() == "pending"
        )
        sme_blocked = (
            str(data.get("sme_gate") or "none").lower() == "required"
            or any(str(s.get("sme_gate") or "none").lower() == "required" for s in active_slices)
        )
        records[rel] = {
            "state_key": rel,
            "source_kind": "manifest",
            "source_path": rel,
            "product": cap_sig(str(data.get("product") or goal_meta.get("goal") or Path(mpath).stem), 80),
            "active_sprint": active_sprint,
            "passed_slices": 0,
            "active_slices": len(active_slices),
            "total_slices": len(slices),
            "deferred_count": deferred_count,
            "pending_inventory": pending_inv,
            "sme_gate_blocked": 1 if sme_blocked else 0,
            "last_exit_code": None,
            "last_exit_reason": "",
        }

    summary_paths = glob.glob(os.path.join(checkout_root, ".scratch", "goals", "*", "latest-summary.json"))
    summary_paths.sort(key=lambda p: (os.path.getmtime(p) if os.path.exists(p) else 0.0, p))
    for spath in summary_paths:
        try:
            with open(spath, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        raw_rel = _safe_relpath(spath, checkout_root)
        if raw_rel is None:
            continue
        rel = _normalize_rel_manifest(raw_rel)
        exit_code = data.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            exit_code = None
        exit_reason = str(data.get("exit_reason") or "")
        scope = data.get("scope") if isinstance(data.get("scope"), dict) else None

        if scope:
            manifest_rel = _normalize_rel_manifest(scope.get("manifest"))
            s_sprint = scope.get("active_sprint")
            if isinstance(s_sprint, bool) or not isinstance(s_sprint, int):
                s_sprint = None
            deferred_val = scope.get("deferred_slices", 0)
            deferred_count = len(deferred_val) if isinstance(deferred_val, list) else _safe_int(deferred_val, 0)
            pending_val = scope.get("pending_inventory", 0)
            pending_count = len(pending_val) if isinstance(pending_val, list) else _safe_int(pending_val, 0)
            passed = _safe_int(scope.get("passed_slices"), 0)
            active_cnt = _safe_int(scope.get("active_slices"), 0)
            total_cnt = _safe_int(scope.get("total_slices"), 0)
            sme_blocked = 1 if scope.get("sme_gate_blocked") else 0

            if manifest_rel and manifest_rel in records:
                rec = records[manifest_rel]
                if s_sprint is not None:
                    rec["active_sprint"] = s_sprint
                rec["passed_slices"] = passed
                if active_cnt:
                    rec["active_slices"] = active_cnt
                if total_cnt:
                    rec["total_slices"] = total_cnt
                rec["deferred_count"] = deferred_count
                rec["pending_inventory"] = pending_count
                rec["sme_gate_blocked"] = 1 if (rec["sme_gate_blocked"] or sme_blocked) else 0
                rec["last_exit_code"] = exit_code
                rec["last_exit_reason"] = exit_reason
            else:
                records[rel] = {
                    "state_key": rel,
                    "source_kind": "goal_summary",
                    "source_path": rel,
                    "product": cap_sig(str(data.get("goal") or Path(spath).parent.name), 80),
                    "active_sprint": s_sprint,
                    "passed_slices": passed,
                    "active_slices": active_cnt,
                    "total_slices": total_cnt,
                    "deferred_count": deferred_count,
                    "pending_inventory": pending_count,
                    "sme_gate_blocked": sme_blocked,
                    "last_exit_code": exit_code,
                    "last_exit_reason": exit_reason,
                }
        else:
            records[rel] = {
                "state_key": rel,
                "source_kind": "goal_summary",
                "source_path": rel,
                "product": cap_sig(str(data.get("goal") or Path(spath).parent.name), 80),
                "active_sprint": None,
                "passed_slices": 0,
                "active_slices": 0,
                "total_slices": 0,
                "deferred_count": 0,
                "pending_inventory": 0,
                "sme_gate_blocked": 0,
                "last_exit_code": exit_code,
                "last_exit_reason": exit_reason,
            }
    return records


def sync_project_state(conn, repo_info):
    repo_key = repo_info["repo_key"]
    wkey = repo_info["worktree_key"]
    now = time.time()
    records = _scan_project_state_for_checkout(repo_info["checkout_root"])

    existing_keys = {
        r["state_key"]
        for r in conn.execute(
            "SELECT state_key FROM project_state WHERE repo_key = ? AND worktree_key = ?",
            (repo_key, wkey),
        )
    }
    stale = existing_keys - set(records.keys())
    if stale:
        conn.executemany(
            "DELETE FROM project_state WHERE repo_key = ? AND worktree_key = ? AND state_key = ?",
            [(repo_key, wkey, sk) for sk in stale],
        )

    state_params = [
        (
            repo_key, wkey, rec["state_key"], rec["source_kind"], rec["source_path"], rec["product"],
            rec["active_sprint"], rec["passed_slices"], rec["active_slices"], rec["total_slices"],
            rec["deferred_count"], rec["pending_inventory"], rec["sme_gate_blocked"],
            rec["last_exit_code"], rec["last_exit_reason"], now,
        )
        for rec in records.values()
    ]
    if state_params:
        conn.executemany(
            """INSERT INTO project_state(
                repo_key, worktree_key, state_key, source_kind, source_path, product,
                active_sprint, passed_slices, active_slices, total_slices, deferred_count,
                pending_inventory, sme_gate_blocked, last_exit_code, last_exit_reason, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_key, worktree_key, state_key) DO UPDATE SET
                source_kind=excluded.source_kind, source_path=excluded.source_path, product=excluded.product,
                active_sprint=excluded.active_sprint, passed_slices=excluded.passed_slices,
                active_slices=excluded.active_slices, total_slices=excluded.total_slices,
                deferred_count=excluded.deferred_count, pending_inventory=excluded.pending_inventory,
                sme_gate_blocked=excluded.sme_gate_blocked, last_exit_code=excluded.last_exit_code,
                last_exit_reason=excluded.last_exit_reason, updated_at=excluded.updated_at""",
            state_params,
        )
    return len(records)


def upsert_repo_row(conn, repo_info, touch_sync=True):
    now = time.time() if touch_sync else 0.0
    conn.execute(
        """INSERT INTO repos(
            repo_key, name, main_checkout, common_dir, remote_url, remote_slug, default_branch, last_sync_ts
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_key) DO UPDATE SET
            name=excluded.name, main_checkout=excluded.main_checkout, common_dir=excluded.common_dir,
            remote_url=excluded.remote_url, remote_slug=excluded.remote_slug,
            default_branch=excluded.default_branch,
            last_sync_ts=CASE WHEN excluded.last_sync_ts > 0 THEN excluded.last_sync_ts ELSE repos.last_sync_ts END""",
        (
            repo_info["repo_key"],
            repo_info["name"],
            display_path(repo_info["main_checkout"]),
            display_path(repo_info["common_dir"]),
            repo_info["remote_url"],
            repo_info["remote_slug"],
            repo_info["default_branch"],
            now,
        ),
    )


def perform_sync(
    conn,
    repo_info,
    offline=False,
    no_orca=False,
    force_prs=False,
    include_foreign_orca=False,
    fast=False,
):
    started = time.perf_counter()
    upsert_repo_row(conn, repo_info, touch_sync=True)
    file_stats = sync_files_and_symbols(conn, repo_info)
    wt_count, orca_used = sync_workspaces(
        conn, repo_info, no_orca=no_orca, include_foreign_orca=include_foreign_orca, fast=fast
    )
    pr_count, prs_cached = sync_prs(conn, repo_info, offline=offline, force_prs=force_prs)
    ps_count = sync_project_state(conn, repo_info)
    conn.execute(
        "UPDATE repos SET file_count = ?, symbol_count = ?, last_sync_ts = ? WHERE repo_key = ?",
        (file_stats["total_files"], file_stats["total_symbols"], time.time(), repo_info["repo_key"]),
    )
    conn.commit()
    conn.execute("PRAGMA incremental_vacuum")
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    return {
        "repo": repo_info["name"],
        "repo_key": repo_info["repo_key"],
        "checkout": display_path(repo_info["checkout_root"]),
        "main_checkout": display_path(repo_info["main_checkout"]),
        "branch": repo_info["current_branch"] or "detached",
        **file_stats,
        "workspaces_count": wt_count,
        "orca_used": orca_used,
        "prs_count": pr_count,
        "prs_cached": prs_cached,
        "project_states": ps_count,
        "elapsed_ms": elapsed_ms,
    }


def build_fts_query(raw_term):
    tokens = [tok for tok in raw_term.strip().split() if tok]
    if not tokens:
        return ""
    parts = []
    for tok in tokens:
        prefix = tok.endswith("*") and len(tok) > 1
        core = tok[:-1] if prefix else tok
        core = core.strip('"')
        if not core:
            continue
        escaped = core.replace('"', '""')
        parts.append(f'"{escaped}"*' if prefix else f'"{escaped}"')
    return " ".join(parts)


def format_project_state_compact(ps):
    parts = [ps["product"] or ps["source_path"]]
    if ps["active_sprint"] is not None:
        parts.append(f"S{ps['active_sprint']}")
    if ps["total_slices"]:
        parts.append(f"{ps['passed_slices']}/{ps['total_slices']}")
    if ps["deferred_count"]:
        parts.append(f"def={ps['deferred_count']}")
    if ps["pending_inventory"]:
        parts.append(f"pend_inv={ps['pending_inventory']}")
    if ps["sme_gate_blocked"]:
        parts.append("SME_BLOCKED")
    if ps["last_exit_code"] is not None:
        reason = f"({ps['last_exit_reason']})" if ps["last_exit_reason"] else ""
        parts.append(f"exit={ps['last_exit_code']}{reason}")
    return " ".join(parts)


def collect_workspaces(conn, repo_key=None):
    where = "WHERE w.repo_key = ?" if repo_key else ""
    params = (repo_key,) if repo_key else ()
    rows = conn.execute(
        f"""SELECT w.*, r.name AS repo_name
            FROM workspaces w
            JOIN repos r ON r.repo_key = w.repo_key
            {where}
            ORDER BY r.name, w.is_main DESC, w.is_detached ASC, w.path ASC""",
        params,
    ).fetchall()

    prs_by_key = {}
    pr_rows = conn.execute(
        f"SELECT * FROM prs {'WHERE repo_key = ?' if repo_key else ''} ORDER BY number DESC",
        params,
    ).fetchall()
    for pr in pr_rows:
        if pr["head_branch"]:
            prs_by_key.setdefault((pr["repo_key"], pr["head_branch"]), dict(pr))

    ps_by_wt = {}
    ps_rows = conn.execute(
        f"SELECT * FROM project_state {'WHERE repo_key = ?' if repo_key else ''} ORDER BY source_path",
        params,
    ).fetchall()
    for ps in ps_rows:
        ps_by_wt.setdefault((ps["repo_key"], ps["worktree_key"]), []).append(dict(ps))

    out = []
    for row in rows:
        item = dict(row)
        matched_pr = prs_by_key.get((item["repo_key"], item["branch"])) if item["branch"] else None
        item["pr"] = (
            {
                "number": matched_pr["number"],
                "title": matched_pr["title"],
                "merge_state": matched_pr["merge_state"],
                "checks_summary": matched_pr["checks_summary"],
                "is_draft": bool(matched_pr["is_draft"]),
                "url": matched_pr["url"],
            }
            if matched_pr else None
        )
        item["project_state"] = ps_by_wt.get((item["repo_key"], item["worktree_key"]), [])
        out.append(item)
    return out


def collect_prs(conn, repo_key=None):
    where = "WHERE p.repo_key = ?" if repo_key else ""
    params = (repo_key,) if repo_key else ()
    rows = conn.execute(
        f"""SELECT p.*, r.name AS repo_name
            FROM prs p
            JOIN repos r ON r.repo_key = p.repo_key
            {where}
            ORDER BY r.name, p.number DESC""",
        params,
    ).fetchall()

    wt_by_branch = {}
    wt_rows = conn.execute(
        f"SELECT * FROM workspaces {'WHERE repo_key = ?' if repo_key else ''} ORDER BY is_main DESC, path ASC",
        params,
    ).fetchall()
    for wt in wt_rows:
        if wt["branch"]:
            wt_by_branch.setdefault((wt["repo_key"], wt["branch"]), dict(wt))

    out = []
    for row in rows:
        item = dict(row)
        wt = wt_by_branch.get((item["repo_key"], item["head_branch"])) if item["head_branch"] else None
        item["worktree_path"] = wt["path"] if wt else None
        item["worktree_dirty"] = bool(wt["is_dirty"]) if wt else None
        out.append(item)
    return out


def render_overview_text(repo_info, sync_stats, db_size_kb, key_files, workspaces, prs, states, max_bytes):
    lines = []
    branch = repo_info["current_branch"] or "detached"
    cur_wkey = repo_info["worktree_key"]
    lines.append(
        f"repo: {repo_info['name']} [{branch}] | "
        f"files:{sync_stats['total_files']} syms:{sync_stats['total_symbols']} | db:{db_size_kb:.1f}KB"
    )
    if normalize_path_key(repo_info["checkout_root"]) != repo_info["repo_key"]:
        lines.append(f"cwd: {display_path(repo_info['checkout_root'])} (main: {display_path(repo_info['main_checkout'])})")
    else:
        lines.append(f"root: {display_path(repo_info['main_checkout'])}")

    key_bits = []
    if key_files["docs"]:
        key_bits.append("docs: " + ", ".join(key_files["docs"][:5]))
    if key_files["entrypoints"]:
        key_bits.append("entry: " + ", ".join(key_files["entrypoints"][:5]))
    if key_files["verify_skills"]:
        key_bits.append("verify: " + ", ".join(key_files["verify_skills"][:4]))
    if key_bits:
        lines.append(" | ".join(key_bits))

    if states:
        state_bits = [format_project_state_compact(s) for s in states[:3]]
        extra_s = f" (+{len(states) - 3})" if len(states) > 3 else ""
        lines.append("state: " + "; ".join(state_bits) + extra_s)

    if prs:
        pr_bits = []
        for pr in prs[:4]:
            meta = []
            if pr["is_draft"]:
                meta.append("draft")
            if pr["merge_state"]:
                meta.append(pr["merge_state"])
            if pr["checks_summary"]:
                meta.append(pr["checks_summary"])
            mstr = f" ({', '.join(meta)})" if meta else ""
            pr_bits.append(f"#{pr['number']}[{pr['head_branch']}] {cap_sig(pr['title'], 42)}{mstr}")
        extra_p = f" (+{len(prs) - 4})" if len(prs) > 4 else ""
        lines.append("prs: " + "; ".join(pr_bits) + extra_p)

    if workspaces:
        interesting = []
        detached_extra = 0
        for wt in workspaces:
            is_cur = wt["worktree_key"] == cur_wkey
            if is_cur or wt["is_main"] or not wt["is_detached"] or wt["source"] != "git" or wt["pr"]:
                interesting.append(wt)
            else:
                detached_extra += 1
        interesting.sort(
            key=lambda w: (
                0 if w["worktree_key"] == cur_wkey else 1,
                0 if w["pr"] else 1,
                0 if w["source"] != "git" else 1,
                0 if w["is_main"] else 1,
                w["branch"] or w["path"],
            )
        )
        wt_lines = []
        shown = 0
        for wt in interesting[:6]:
            shown += 1
            tag = "*" if wt["worktree_key"] == cur_wkey else " "
            dirty = f" dirty({wt['dirty_count']})" if wt["is_dirty"] else ""
            label = wt["branch"] or f"detached@{wt['head_sha']}"
            src = f" [{wt['source']}]" if wt["source"] != "git" else ""
            pr_tag = f" PR#{wt['pr']['number']}" if wt["pr"] else ""
            short_p = os.path.basename(wt["path"].rstrip("/")) or wt["path"]
            wt_lines.append(f"  {tag} {short_p} ({label}){dirty}{src}{pr_tag}")
        omitted = (len(interesting) - shown) + detached_extra
        header = f"worktrees ({len(workspaces)}):"
        if omitted:
            header += f" (+{omitted} more)"
        lines.append(header)
        lines.extend(wt_lines)

    text = "\n".join(lines)
    return truncate_utf8(text, max_bytes)


def cmd_sync(opts):
    repo_info = resolve_repo(opts.path)
    if repo_info is None:
        raise SystemExit(f"not inside a git repository: {os.path.abspath(opts.path)}")
    db_path = resolve_db_path(opts, repo_info)
    conn = connect_db(db_path)
    try:
        stats = perform_sync(
            conn,
            repo_info,
            offline=opts.offline,
            no_orca=opts.no_orca,
            force_prs=opts.force_prs,
            include_foreign_orca=getattr(opts, "use_global", False),
            fast=opts.fast,
        )
    finally:
        conn.close()
    db_kb = round(db_disk_bytes(db_path) / 1024.0, 2)
    stats["db_path"] = display_path(db_path)
    stats["db_size_kb"] = db_kb
    if opts.json:
        print(json.dumps(stats, indent=2))
    else:
        print(
            f"synced {stats['repo']} [{stats['branch']}]: "
            f"{stats['files_indexed']} indexed, {stats['files_skipped']} skipped, {stats['files_removed']} removed "
            f"({stats['total_files']} files, {stats['total_symbols']} symbols, {stats['workspaces_count']} worktrees, "
            f"{stats['prs_count']} prs, {stats['project_states']} states) | db {db_kb:.1f} KB in {stats['elapsed_ms']}ms"
        )
    return 0


def cmd_overview(opts):
    repo_info = resolve_repo(opts.path)
    if repo_info is None:
        raise SystemExit(f"not inside a git repository: {os.path.abspath(opts.path)}")
    db_path = resolve_db_path(opts, repo_info)
    conn = connect_db(db_path)
    try:
        stats = perform_sync(
            conn,
            repo_info,
            offline=opts.offline,
            no_orca=opts.no_orca,
            force_prs=False,
            include_foreign_orca=getattr(opts, "use_global", False),
            fast=opts.fast,
        )
        rkey = repo_info["repo_key"]
        wkey = repo_info["worktree_key"]
        is_main = wkey == rkey

        def role_files(role_name, order_by, limit=8):
            if is_main:
                sql = f"SELECT rel_path FROM files WHERE repo_key = ? AND worktree_key = '' AND role = ? ORDER BY {order_by} LIMIT ?"
                params = (rkey, role_name, limit)
            else:
                sql = (
                    "SELECT rel_path FROM files f "
                    "WHERE f.repo_key = ? AND f.role = ? "
                    "AND (f.worktree_key = ? OR ("
                    "  f.worktree_key = '' "
                    "  AND NOT EXISTS (SELECT 1 FROM files ov WHERE ov.repo_key = f.repo_key AND ov.worktree_key = ? AND ov.rel_path = f.rel_path) "
                    "  AND NOT EXISTS (SELECT 1 FROM worktree_deleted wd WHERE wd.repo_key = f.repo_key AND wd.worktree_key = ? AND wd.rel_path = f.rel_path)"
                    f")) ORDER BY {order_by} LIMIT ?"
                )
                params = (rkey, role_name, wkey, wkey, wkey, limit)
            return [r["rel_path"] for r in conn.execute(sql, params)]

        docs = role_files("doc", "length(rel_path), rel_path")
        entrypoints = role_files("entrypoint", "length(rel_path), rel_path")
        verify_skills = role_files("verify-skill", "rel_path")
        workspaces = collect_workspaces(conn, rkey)
        prs = collect_prs(conn, rkey)
        states = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM project_state WHERE repo_key = ? ORDER BY updated_at DESC, source_path",
                (rkey,),
            )
        ]
    finally:
        conn.close()

    db_kb = round(db_disk_bytes(db_path) / 1024.0, 2)
    key_files = {"docs": docs, "entrypoints": entrypoints, "verify_skills": verify_skills}
    overview_text = render_overview_text(
        repo_info, stats, db_kb, key_files, workspaces, prs, states, opts.max_bytes
    )
    if opts.json:
        payload = {
            "repo": repo_info["name"],
            "repo_key": repo_info["repo_key"],
            "branch": repo_info["current_branch"] or "detached",
            "checkout": display_path(repo_info["checkout_root"]),
            "main_checkout": display_path(repo_info["main_checkout"]),
            "db_path": display_path(db_path),
            "db_size_kb": db_kb,
            "sync": stats,
            **key_files,
            "workspaces": workspaces,
            "prs": prs,
            "project_state": states,
            "overview_text": overview_text,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(overview_text)
    return 0


def cmd_query(opts):
    repo_info = resolve_repo(opts.path)
    db_path = resolve_db_path(opts, repo_info)
    just_synced = False
    if not os.path.exists(db_path):
        if repo_info is None:
            raise SystemExit(f"index DB does not exist: {db_path}")
        conn = connect_db(db_path)
        try:
            perform_sync(conn, repo_info, offline=True, no_orca=True, fast=True)
            just_synced = True
        finally:
            conn.close()

    fts_q = build_fts_query(opts.term)
    conn = connect_db(db_path, readonly=bool(opts.no_sync))
    try:
        repo_key = None if opts.all_repos else (repo_info["repo_key"] if repo_info else None)
        wt_key = repo_info["worktree_key"] if (repo_info and repo_key is not None) else None
        if repo_info is not None:
            exists = conn.execute("SELECT 1 FROM repos WHERE repo_key = ?", (repo_info["repo_key"],)).fetchone()
            if exists is None and getattr(opts, "db", None):
                if repo_key == repo_info["repo_key"]:
                    repo_key = None
                    wt_key = None
            elif exists is None and not opts.no_sync and not just_synced:
                perform_sync(conn, repo_info, offline=True, no_orca=True, fast=True)
            elif exists is not None and not opts.no_sync and not just_synced:
                file_stats = sync_files_and_symbols(conn, repo_info)
                conn.execute(
                    "UPDATE repos SET file_count = ?, symbol_count = ?, last_sync_ts = ? WHERE repo_key = ?",
                    (file_stats["total_files"], file_stats["total_symbols"], time.time(), repo_info["repo_key"]),
                )
                conn.commit()

        results = []
        if fts_q:
            sql = (
                "SELECT s.rel_path, s.line, s.kind, s.name, s.signature, r.name AS repo_name "
                "FROM symbols_fts f "
                "JOIN symbols s ON s.id = f.rowid "
                "JOIN repos r ON r.repo_key = s.repo_key "
                "WHERE symbols_fts MATCH ?"
            )
            params = [fts_q]
            if repo_key is not None:
                sql += " AND s.repo_key = ?"
                params.append(repo_key)
                if wt_key and wt_key != repo_key:
                    sql += (
                        " AND (s.worktree_key = ? OR ("
                        "  s.worktree_key = '' "
                        "  AND NOT EXISTS (SELECT 1 FROM files ov WHERE ov.repo_key = s.repo_key AND ov.worktree_key = ? AND ov.rel_path = s.rel_path) "
                        "  AND NOT EXISTS (SELECT 1 FROM worktree_deleted wd WHERE wd.repo_key = s.repo_key AND wd.worktree_key = ? AND wd.rel_path = s.rel_path)"
                        "))"
                    )
                    params.extend([wt_key, wt_key, wt_key])
                else:
                    sql += " AND s.worktree_key = ''"
            else:
                sql += (
                    " AND (s.worktree_key = '' OR NOT EXISTS ("
                    "  SELECT 1 FROM files fb WHERE fb.repo_key = s.repo_key AND fb.worktree_key = ''"
                    "))"
                )
            sql += " ORDER BY bm25(symbols_fts, 10.0, 3.0, 1.0), s.rel_path, s.line LIMIT ?"
            params.append(max(1, opts.limit))
            try:
                rows = conn.execute(sql, params).fetchall()
                results = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                results = []
    finally:
        conn.close()

    if opts.json:
        print(json.dumps({"query": opts.term, "count": len(results), "results": results}, indent=2))
    else:
        multi_repo = opts.all_repos and len({r["repo_name"] for r in results}) > 1
        for r in results:
            prefix = f"[{r['repo_name']}] " if multi_repo else ""
            print(f"{prefix}{r['rel_path']}:{r['line']} {r['kind']} {r['signature']}")
        if not results:
            print(f"no matches for {opts.term!r}")
    return 0


def cmd_workspaces(opts):
    repo_info = resolve_repo(opts.path)
    db_path = resolve_db_path(opts, repo_info)
    just_synced = False
    if not os.path.exists(db_path):
        if repo_info is None:
            raise SystemExit(f"index DB does not exist: {db_path}")
        conn = connect_db(db_path)
        try:
            perform_sync(
                conn,
                repo_info,
                offline=True,
                no_orca=opts.no_orca,
                include_foreign_orca=getattr(opts, "use_global", False),
                fast=opts.fast,
            )
            just_synced = True
        finally:
            conn.close()

    conn = connect_db(db_path)
    try:
        repo_key = None if opts.all_repos else (repo_info["repo_key"] if repo_info else None)
        if repo_info is not None:
            exists = conn.execute("SELECT 1 FROM repos WHERE repo_key = ?", (repo_info["repo_key"],)).fetchone()
            if exists is None and getattr(opts, "db", None):
                if repo_key == repo_info["repo_key"]:
                    repo_key = None
            elif exists is None and not just_synced:
                perform_sync(
                    conn,
                    repo_info,
                    offline=True,
                    no_orca=opts.no_orca,
                    include_foreign_orca=getattr(opts, "use_global", False),
                    fast=opts.fast,
                )
            elif exists is not None and not just_synced:
                sync_workspaces(
                    conn,
                    repo_info,
                    no_orca=opts.no_orca,
                    include_foreign_orca=getattr(opts, "use_global", False),
                    fast=opts.fast,
                )
                sync_project_state(conn, repo_info)
                conn.commit()
        items = collect_workspaces(conn, repo_key)
    finally:
        conn.close()

    if opts.json:
        print(json.dumps({"count": len(items), "workspaces": items}, indent=2))
    else:
        for wt in items:
            branch = wt["branch"] or f"detached@{wt['head_sha']}"
            dirty = f"dirty({wt['dirty_count']})" if wt["is_dirty"] else "clean"
            bits = [f"{wt['path']} [{branch}]", dirty, wt["source"]]
            if wt["orca_host"]:
                bits.append(f"host={wt['orca_host']}")
            if wt["pr"]:
                pr = wt["pr"]
                pr_meta = "/".join(x for x in (pr["merge_state"], pr["checks_summary"]) if x)
                bits.append(f"PR#{pr['number']}" + (f"({pr_meta})" if pr_meta else ""))
            if wt["project_state"]:
                bits.append("state:" + ";".join(format_project_state_compact(s) for s in wt["project_state"][:2]))
            print(" | ".join(bits))
        if not items:
            print("no workspaces indexed")
    return 0


def cmd_prs(opts):
    repo_info = resolve_repo(opts.path)
    db_path = resolve_db_path(opts, repo_info)
    just_synced = False
    if not os.path.exists(db_path):
        if repo_info is None:
            raise SystemExit(f"index DB does not exist: {db_path}")
        conn = connect_db(db_path)
        try:
            perform_sync(
                conn,
                repo_info,
                offline=opts.offline,
                no_orca=True,
                force_prs=opts.force_prs,
                fast=True,
            )
            just_synced = True
        finally:
            conn.close()

    conn = connect_db(db_path)
    try:
        repo_key = None if opts.all_repos else (repo_info["repo_key"] if repo_info else None)
        if repo_info is not None:
            exists = conn.execute("SELECT 1 FROM repos WHERE repo_key = ?", (repo_info["repo_key"],)).fetchone()
            if exists is None and getattr(opts, "db", None):
                if repo_key == repo_info["repo_key"]:
                    repo_key = None
            elif exists is None and not just_synced:
                perform_sync(
                    conn,
                    repo_info,
                    offline=opts.offline,
                    no_orca=True,
                    force_prs=opts.force_prs,
                    fast=True,
                )
            elif exists is not None and not opts.offline and not just_synced:
                sync_prs(conn, repo_info, offline=False, force_prs=opts.force_prs)
                conn.commit()
        items = collect_prs(conn, repo_key)
    finally:
        conn.close()

    if opts.json:
        print(json.dumps({"count": len(items), "prs": items}, indent=2))
    else:
        for pr in items:
            draft = "draft " if pr["is_draft"] else ""
            status_bits = [x for x in (pr["merge_state"], pr["review_decision"], pr["checks_summary"]) if x]
            status_str = ", ".join(status_bits) if status_bits else pr["state"]
            wt_str = pr["worktree_path"] or "none"
            print(
                f"#{pr['number']} [{draft}{pr['head_branch']}->{pr['base_branch']}] "
                f"{pr['title']} | {status_str} | wt={wt_str}"
            )
        if not items:
            print("no open PRs indexed")
    return 0


def cmd_prune(opts):
    repo_info = resolve_repo(".")
    db_path = resolve_db_path(opts, repo_info)
    if not os.path.exists(db_path):
        payload = {
            "db_path": display_path(db_path),
            "dropped_repos": 0,
            "dropped_workspaces": 0,
            "dropped_prs": 0,
            "dropped_states": 0,
            "before_bytes": 0,
            "after_bytes": 0,
            "reclaimed_bytes": 0,
        }
        if opts.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"prune: nothing to prune ({db_path} does not exist)")
        return 0

    before_bytes = db_disk_bytes(db_path)
    cutoff = time.time() - (max(0.0, float(opts.days)) * 86400.0)
    conn = connect_db(db_path)
    try:
        drop_repos = []
        wt_max_by_repo = {
            r[0]: float(r[1] or 0.0)
            for r in conn.execute("SELECT repo_key, MAX(updated_at) FROM workspaces GROUP BY repo_key").fetchall()
        }
        repo_rows = conn.execute("SELECT repo_key, main_checkout, last_sync_ts FROM repos").fetchall()
        for row in repo_rows:
            last_ts = float(row["last_sync_ts"] or 0.0)
            if last_ts <= 0.0:
                last_ts = wt_max_by_repo.get(row["repo_key"], 0.0)
            stale = (last_ts <= 0.0 and float(opts.days) >= 0.0) or (last_ts > 0.0 and last_ts < cutoff)
            if not os.path.isdir(row["main_checkout"]) or stale:
                drop_repos.append(row["repo_key"])
        if drop_repos:
            conn.executemany("DELETE FROM repos WHERE repo_key = ?", [(k,) for k in drop_repos])

        drop_wts = []
        wt_rows = conn.execute("SELECT repo_key, worktree_key, path, updated_at FROM workspaces").fetchall()
        for row in wt_rows:
            stale = row["updated_at"] and row["updated_at"] < cutoff
            if not os.path.isdir(row["path"]) or stale:
                drop_wts.append((row["repo_key"], row["worktree_key"]))
        if drop_wts:
            conn.executemany("DELETE FROM workspaces WHERE worktree_key = ?", [(wk,) for _, wk in drop_wts])
            conn.executemany(
                "DELETE FROM files WHERE repo_key = ? AND worktree_key = ?",
                [(rk, wk) for rk, wk in drop_wts if wk != rk],
            )
            conn.executemany(
                "DELETE FROM worktree_deleted WHERE repo_key = ? AND worktree_key = ?",
                [(rk, wk) for rk, wk in drop_wts if wk != rk],
            )

        pr_cur = conn.execute("DELETE FROM prs WHERE synced_at > 0 AND synced_at < ?", (cutoff,))
        dropped_prs = pr_cur.rowcount

        ps_cur = conn.execute("DELETE FROM project_state WHERE updated_at > 0 AND updated_at < ?", (cutoff,))
        dropped_states = ps_cur.rowcount

        conn.commit()
        conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('optimize')")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()

    after_bytes = db_disk_bytes(db_path)
    reclaimed = max(0, before_bytes - after_bytes)
    payload = {
        "db_path": display_path(db_path),
        "dropped_repos": len(drop_repos),
        "dropped_workspaces": len(drop_wts),
        "dropped_prs": dropped_prs,
        "dropped_states": dropped_states,
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "reclaimed_bytes": reclaimed,
    }
    if opts.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"pruned: repos={len(drop_repos)} workspaces={len(drop_wts)} prs={dropped_prs} "
            f"states={dropped_states} | reclaimed {reclaimed} bytes ({before_bytes} -> {after_bytes})"
        )
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="emit machine-readable JSON")
    common.add_argument("--db", default=argparse.SUPPRESS, help="explicit SQLite DB path")
    common.add_argument(
        "--global", dest="use_global", action="store_true", default=argparse.SUPPRESS,
        help="use cross-repo global index at ~/.cache/deepmodebot/workspace-map.db",
    )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", default=False, help="emit machine-readable JSON")
    parser.add_argument("--db", default=None, help="explicit SQLite DB path")
    parser.add_argument(
        "--global", dest="use_global", action="store_true", default=False,
        help="use cross-repo global index at ~/.cache/deepmodebot/workspace-map.db",
    )

    sub = parser.add_subparsers(dest="action", required=True)

    p_sync = sub.add_parser("sync", parents=[common], help="incrementally index files, symbols, worktrees, PRs, state")
    p_sync.add_argument("path", nargs="?", default=".")
    p_sync.add_argument("--offline", action="store_true", help="skip gh PR lookup")
    p_sync.add_argument("--no-orca", action="store_true", help="skip orca worktree lookup")
    p_sync.add_argument("--force-prs", action="store_true", help="bypass 180s PR TTL cache")
    p_sync.add_argument("--fast", action="store_true", help="check dirty status on current and main worktrees only")

    p_ov = sub.add_parser("overview", parents=[common], help="auto-sync and print a byte-capped turn-1 orientation")
    p_ov.add_argument("path", nargs="?", default=".")
    p_ov.add_argument("--max-bytes", type=int, default=DEFAULT_OVERVIEW_BYTES, help="hard UTF-8 byte cap")
    p_ov.add_argument("--offline", action="store_true", help="skip gh PR lookup")
    p_ov.add_argument("--no-orca", action="store_true", help="skip orca worktree lookup")
    p_ov.add_argument("--fast", action="store_true", help="check dirty status on current and main worktrees only")

    p_q = sub.add_parser("query", parents=[common], help="FTS5 symbol lookup returning rel_path:line kind signature")
    p_q.add_argument("term", help="search term or prefix (e.g. evaluate_manifest or eval*)")
    p_q.add_argument("path", nargs="?", default=".")
    p_q.add_argument("--limit", type=int, default=15, help="max results")
    p_q.add_argument("--all-repos", action="store_true", help="search across every repo in the DB")
    p_q.add_argument("--no-sync", action="store_true", help="skip incremental file/symbol refresh before querying")

    p_ws = sub.add_parser("workspaces", parents=[common], help="list worktrees joined with dirty state, PRs, and manifests")
    p_ws.add_argument("path", nargs="?", default=".")
    p_ws.add_argument("--all-repos", action="store_true", help="include all repos in the DB")
    p_ws.add_argument("--no-orca", action="store_true", help="skip orca worktree lookup")
    p_ws.add_argument("--fast", action="store_true", help="check dirty status on current and main worktrees only")

    p_prs = sub.add_parser("prs", parents=[common], help="list own open PRs joined with local worktrees")
    p_prs.add_argument("path", nargs="?", default=".")
    p_prs.add_argument("--all-repos", action="store_true", help="include all repos in the DB")
    p_prs.add_argument("--offline", action="store_true", help="skip gh PR refresh and read cached rows only")
    p_prs.add_argument("--force-prs", action="store_true", help="bypass 180s PR TTL cache")

    p_prune = sub.add_parser("prune", parents=[common], help="drop missing repos/worktrees and stale rows, then VACUUM")
    p_prune.add_argument("--days", type=float, default=DEFAULT_PRUNE_DAYS, help="drop rows older than N days")

    return parser


def main(argv=None):
    parser = build_parser()
    opts = parser.parse_args(argv)
    handlers = {
        "sync": cmd_sync,
        "overview": cmd_overview,
        "query": cmd_query,
        "workspaces": cmd_workspaces,
        "prs": cmd_prs,
        "prune": cmd_prune,
    }
    return handlers[opts.action](opts)


if __name__ == "__main__":
    sys.exit(main())
