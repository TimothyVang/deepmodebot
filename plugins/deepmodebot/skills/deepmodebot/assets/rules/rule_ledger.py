#!/usr/bin/env python3
"""Owner-approved agent rules: track every rule an AI agent loads and block the ones the owner never approved.

Rules are the instruction and permission files coding agents load (AGENTS.md, CLAUDE.md, .cursor/rules/, skills,
agent settings; the full list is rule-paths.json) plus `convention` records in the deepmodebot project memory.
.deepmodebot/rules/ledger.json pins the approved SHA-256 of each rule, .deepmodebot/rules/approved/<sha256> keeps the
approved bytes, and the history logs every decision. The ledger is signed with an Ed25519 key derived from a passphrase
only the owner knows: agents can read, review and propose, but approving, rejecting and re-keying need the passphrase.
Trust is anchored on the committed ledger at HEAD and at the merge-base with the remote default branch.

    python -B rule_ledger.py status  [--root R] [--json]
    python -B rule_ledger.py review  [--root R] [--json]
    python -B rule_ledger.py log     [--root R] [--json]
    python -B rule_ledger.py propose --item AGENTS.md --file .scratch/AGENTS.draft.md --reason "why" [--by NAME] [--root R]
    python -B rule_ledger.py check   [--root R] [--staged] [--base REF] [--json]
    python -B rule_ledger.py guard   (hook helper: JSON {"cwd", "paths", "command"} on stdin, JSON verdict out)
  Owner only; each asks for the owner passphrase on the terminal:
    python -B rule_ledger.py init    [--root R] [--yes] [--reset]
    python -B rule_ledger.py approve (ID ... | --all) [--root R] [--yes]
    python -B rule_ledger.py reject  (ID ... | --all) [--root R] [--yes]
    python -B rule_ledger.py rotate  [--root R]
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import fnmatch
import getpass
import glob
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import secrets
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "rule_ledger.py"
STORE_REL = ".deepmodebot/rules"
LEDGER_REL = STORE_REL + "/ledger.json"
APPROVED_REL = STORE_REL + "/approved"
PROPOSALS_REL = STORE_REL + "/proposals"
MEMORY_PREFIX = "memory:"
LEDGER_VERSION = 1
KDF_ITERATIONS = 600_000
MAX_KDF_ITERATIONS = 20_000_000
MIN_PASSPHRASE = 8
ROTATE_TAG = b"deepmodebot-rules-rotate:"
SUBCOMMANDS = frozenset({"status", "review", "log", "propose", "check", "guard", "init", "approve", "reject", "rotate"})
OWNER_COMMANDS = frozenset({"init", "approve", "reject", "rotate"})
SKIP_SEGMENTS = frozenset({".git", "node_modules", ".scratch", ".worktrees"})
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DIFF_LINES_SHOWN = 40
COPY_WALK_LIMIT = 2000

PUNCT = frozenset("();<>|&\n")
WRAPPERS = frozenset({"sudo", "doas", "env", "command", "builtin", "exec", "nohup", "time", "timeout", "nice", "ionice",
                      "stdbuf", "chronic"})
WRAPPER_ARG_OPTS = {
    "sudo": frozenset({"-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D", "-R"}),
    "doas": frozenset({"-u", "-C"}),
    "env": frozenset({"-u", "-C", "-S"}),
    "timeout": frozenset({"-s", "-k", "--signal", "--kill-after"}),
    "nice": frozenset({"-n"}),
    "ionice": frozenset({"-c", "-n", "-p"}),
}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
SHELL_C_RE = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
INTERPRETERS = frozenset({"python", "python3", "py", "node", "bun", "deno", "ruby", "perl", "php", "pwsh", "powershell"})
CODE_FLAGS = frozenset({"--eval", "--print", "-p", "-command", "-r"})
CODE_FLAG_RE = re.compile(r"-[A-Za-z]*[ce]")
DELETERS = frozenset({"rm", "unlink", "shred", "truncate", "rmdir", "del", "erase", "remove-item"})
MOVERS = frozenset({"mv", "move", "ren", "rename", "move-item"})
COPIERS = frozenset({"cp", "ln", "install", "rsync", "scp", "copy", "copy-item"})
IN_PLACE = frozenset({"sed", "perl", "ruby"})
IN_PLACE_FLAG_RE = re.compile(r"--in-place(?:=.*)?|-[A-Za-z]*i\S*")
FIND_ACTIONS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
HEREDOC_RE = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
WRITE_CODE_RE = re.compile(
    r"(?<!stdout\.)(?<!stderr\.)\bwrite|append|unlink|remove|rename|os\.replace|rmtree|rmSync|rmdir|truncate|copy"
    r"|cpSync|createWriteStream|symlink|\bmove\b|Set-Content|Out-File|Add-Content"
    r"|open\s*\([^)]*,\s*['\"][rbt]*[wax+]|mode\s*=\s*['\"][rbt]*[wax+]|['\"]\s*\+?>{1,2}",
    re.IGNORECASE,
)
CODE_WORD_RE = re.compile(r"[\w./\\~-]+")
FALLBACK_WORD_RE = re.compile(r"[^\s'\"`<>|;&()]+")
FALLBACK_WRITE_RE = re.compile(r">|\b(?:rm|mv|cp|tee|sed|perl|truncate|ln|install|rsync|dd|unlink|shred)\b")
CONTROL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


class RuleError(Exception):
    """A refused ledger action; the message is shown to the user as is."""


def _load_spec() -> tuple[frozenset, tuple, frozenset, tuple]:
    data = json.loads((HERE / "rule-paths.json").read_text(encoding="utf-8"))
    names = frozenset(n.lower() for n in data["names"])
    dirs = tuple("/" + d.lower().strip("/") + "/" for d in data["dirs"])
    files = frozenset(f.lower() for f in data["files"])
    pathspecs = tuple([f":(glob,icase)**/{n}" for n in data["names"]]
                      + [f":(glob,icase)**/{d.strip('/')}/**" for d in data["dirs"]]
                      + [f":(icase){f}" for f in data["files"]])
    return names, dirs, files, pathspecs


RULE_NAMES, RULE_DIRS, RULE_FILES, RULE_PATHSPECS = _load_spec()


def norm_rel(raw: str) -> str:
    s = str(raw).replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.rstrip("/")


def is_store_path(rel: str) -> bool:
    low = norm_rel(rel).lower()
    return low == STORE_REL or low.startswith(STORE_REL + "/")


def is_rule_path(rel: str) -> bool:
    low = norm_rel(rel).lower()
    if not low or low.startswith("/") or is_store_path(low):
        return False
    parts = low.split("/")
    if ".." in parts or any(p in SKIP_SEGMENTS for p in parts[:-1]):
        return False
    if parts[-1] in RULE_NAMES or low in RULE_FILES:
        return True
    padded = "/" + low
    return any(d in padded for d in RULE_DIRS)


def _rule_ish(rel: str) -> bool:
    """A rule path itself, or a folder that holds rule paths (a symlinked `.claude/skills`)."""
    return is_rule_path(rel) or is_rule_path(norm_rel(rel) + "/x")


def _clean(text) -> str:
    """Escape control and bidi characters so agent text cannot hide or rewrite lines on the owner's terminal."""
    return CONTROL_RE.sub(lambda m: f"\\u{ord(m.group()):04x}", str(text))


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], input=input_bytes, capture_output=True,
                              timeout=60, creationflags=NO_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_text(root: Path, *args: str) -> str | None:
    out = _git(root, *args)
    if out is None or out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace").strip()


def project_root(start) -> Path:
    start = Path(start).expanduser().resolve()
    top = _git_text(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else start


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cat_blobs(root: Path, specs: list[str]) -> dict[str, bytes | None]:
    specs = [s for s in specs if "\n" not in s]
    res: dict[str, bytes | None] = {s: None for s in specs}
    if not specs:
        return res
    proc = _git(root, "cat-file", "--batch", input_bytes="".join(s + "\n" for s in specs).encode("utf-8"))
    if proc is None or proc.returncode != 0:
        return res
    out, pos = proc.stdout, 0
    for spec in specs:
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(header) != 3 or not header[2].isdigit():
            continue
        size = int(header[2])
        if header[1] == "blob":
            res[spec] = out[pos:pos + size]
        pos += size + 1
    return res


class Source:
    """Rule bytes from the working tree ("work"), the git index ("index", pre-commit), or a commit ("ref").

    Symlinks read as their link text in every mode, the way git stores them.
    """

    def __init__(self, root: Path, mode: str = "work", ref: str = ""):
        self.root, self.mode, self.ref = Path(root), mode, ref

    def read_many(self, rels: list[str]) -> dict[str, bytes | None]:
        if self.mode != "work":
            prefix = ":" if self.mode == "index" else self.ref + ":"
            blobs = _cat_blobs(self.root, [prefix + r for r in rels])
            return {r: blobs.get(prefix + r) for r in rels}
        out: dict[str, bytes | None] = {}
        for rel in rels:
            path = self.root / rel
            try:
                if path.is_symlink():
                    out[rel] = os.readlink(path).encode("utf-8", "surrogateescape")
                else:
                    out[rel] = path.read_bytes() if path.is_file() else None
            except OSError:
                out[rel] = None
        return out

    def read(self, rel: str) -> bytes | None:
        return self.read_many([rel])[rel]

    def paths(self) -> list[str]:
        if self.mode == "index":
            return self._git_list("ls-files", "-z", "--cached") or []
        if self.mode == "ref":
            return self._git_list("ls-tree", "-r", "-z", "--name-only", self.ref) or []
        listed = self._git_list("ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if listed is None:
            listed = []
            for folder, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_SEGMENTS]
                base = Path(folder).relative_to(self.root)
                listed += [(base / n).as_posix() for n in filenames]
        else:
            listed += self._git_list("ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--",
                                     *RULE_PATHSPECS) or []
        listed += [n for n in os.listdir(self.root) if n.lower() in RULE_NAMES]
        return sorted({p for p in listed if os.path.lexists(self.root / p)})

    def links(self) -> dict[str, str]:
        """Symlinked rule paths and rule folders: {repo path: link target}."""
        if self.mode == "work":
            out = {}
            for rel in self.paths():
                path = self.root / rel
                if _rule_ish(rel) and path.is_symlink():
                    out[rel] = os.readlink(path)
            return out
        args = ("ls-files", "-s", "-z") if self.mode == "index" else ("ls-tree", "-r", "-z", self.ref)
        shas: dict[str, str] = {}
        for entry in self._git_list(*args) or []:
            meta, _, rel = entry.partition("\t")
            parts = meta.split()
            if len(parts) >= 3 and parts[0] == "120000" and _rule_ish(rel):
                shas[rel] = parts[1] if self.mode == "index" else parts[2]
        blobs = _cat_blobs(self.root, sorted(set(shas.values())))
        return {rel: (blobs.get(sha) or b"").decode("utf-8", "surrogateescape") for rel, sha in shas.items()}

    def _git_list(self, *args: str) -> list[str] | None:
        out = _git(self.root, *args)
        if out is None or out.returncode != 0:
            return None
        return [p for p in out.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def rule_files(src: Source) -> list[str]:
    return sorted(p for p in src.paths() if is_rule_path(p))


def untracked_links(src: Source) -> list[tuple[str, str]]:
    """Symlinked rules whose target is not itself a rule path: the target's content could change unseen."""
    bad = []
    for rel, target in sorted(src.links().items()):
        t = target.replace("\\", "/")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), t))
        outside = posixpath.isabs(t) or re.match(r"^[A-Za-z]:", t) or resolved == ".." or resolved.startswith("../")
        if outside or not _rule_ish(resolved):
            bad.append((rel, target))
    return bad


def memory_rules(root: Path) -> dict[str, bytes]:
    """Unexpired `convention` records in the project memory, keyed `memory:<key>`."""
    pm = _asset_module("dmb_project_memory", "memory/project_memory.py")
    db = pm.resolve_main_root(Path(root)) / ".scratch" / "deepmode-memory.db"
    if not db.is_file():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
        try:
            rows = conn.execute(
                "SELECT key, content FROM memories WHERE kind = 'convention' AND (expires_at IS NULL OR expires_at > ?)",
                (time.time(),),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return {MEMORY_PREFIX + key: content.encode("utf-8") for key, content in rows}


_MODULES: dict[str, object] = {}


def _asset_module(name: str, rel: str):
    if name not in _MODULES:
        existing = sys.modules.get(name)
        if existing is None:
            spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
            existing = importlib.util.module_from_spec(spec)
            sys.modules[name] = existing
            spec.loader.exec_module(existing)
        _MODULES[name] = existing
    return _MODULES[name]


def _ed():
    return _asset_module("dmb_reward_guard", "reward-guard/reward_guard.py")


def _expand_seed(seed: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(h[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, h[32:]


def _encode_point(point) -> bytes:
    p = _ed()._ED_P
    x, y, z, _ = point
    zi = pow(z, p - 2, p)
    x, y = x * zi % p, y * zi % p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def public_key(seed: bytes) -> str:
    ed = _ed()
    scalar, _ = _expand_seed(seed)
    return _encode_point(ed._ed_mul(ed._ED_B, scalar)).hex()


def sign(seed: bytes, msg: bytes) -> str:
    """RFC 8032 Ed25519 signature over msg with the 32-byte private seed."""
    ed = _ed()
    scalar, prefix = _expand_seed(seed)
    pub = _encode_point(ed._ed_mul(ed._ED_B, scalar))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % ed._ED_L
    big_r = _encode_point(ed._ed_mul(ed._ED_B, r))
    k = int.from_bytes(hashlib.sha512(big_r + pub + msg).digest(), "little") % ed._ED_L
    return (big_r + ((r + k * scalar) % ed._ED_L).to_bytes(32, "little")).hex()


def verify(pubkey_hex: str, msg: bytes, sig_hex: str) -> bool:
    return bool(_ed().ed25519_verify(str(pubkey_hex), msg, str(sig_hex)))


def derive_seed(passphrase: str, owner: dict) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), bytes.fromhex(owner["salt"]),
                               int(owner["iterations"]), dklen=32)


def _new_owner(passphrase: str) -> tuple[dict, bytes]:
    if len(passphrase) < MIN_PASSPHRASE:
        raise RuleError(f"pick a passphrase of at least {MIN_PASSPHRASE} characters")
    owner = {"kdf": "pbkdf2-sha256", "salt": secrets.token_hex(16), "iterations": KDF_ITERATIONS}
    seed = derive_seed(passphrase, owner)
    owner["pubkey"] = public_key(seed)
    return owner, seed


def _owner_seed(ledger: dict, passphrase: str) -> bytes:
    seed = derive_seed(passphrase, ledger["owner"])
    if public_key(seed) != ledger["owner"]["pubkey"]:
        raise RuleError("wrong passphrase: it does not match the owner key that signed this ledger")
    return seed


def _canonical(ledger: dict) -> bytes:
    body = {k: v for k, v in ledger.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_ledger(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuleError(f"{LEDGER_REL} is not valid JSON: {exc}") from None
    owner = data.get("owner") if isinstance(data, dict) else None
    if (not isinstance(owner, dict) or not isinstance(data.get("approved"), dict)
            or not isinstance(data.get("history"), list)
            or not all(isinstance(owner.get(k), str) for k in ("pubkey", "salt"))
            or not isinstance(owner.get("iterations"), int) or not 0 < owner["iterations"] <= MAX_KDF_ITERATIONS
            or not isinstance(data.get("links", []), list)):
        raise RuleError(f"{LEDGER_REL} is malformed")
    return data


def signature_ok(ledger: dict) -> bool:
    return verify(ledger["owner"]["pubkey"], _canonical(ledger), str(ledger.get("signature") or ""))


def _key_chain_ok(start: str, entries: list, final: str) -> bool:
    key = start
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("action") != "rotate" or entry.get("from") != key:
            continue
        nxt = str(entry.get("to") or "")
        if verify(key, ROTATE_TAG + nxt.encode("utf-8"), str(entry.get("sig") or "")):
            key = nxt
    return key == final


def _resolves(root: Path, ref: str) -> bool:
    return _git_text(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None


def trust_bases(root: Path) -> list[str]:
    """Commits whose ledger the working one must extend: HEAD and the merge-base with the remote default branch."""
    bases = ["HEAD"] if _resolves(root, "HEAD") else []
    head = _git_text(root, "rev-parse", "HEAD") if bases else None
    default = _git_text(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    for ref in ([default] if default else []) + ["refs/remotes/origin/main", "refs/remotes/origin/master"]:
        if head and _resolves(root, ref):
            mb = _git_text(root, "merge-base", "HEAD", ref)
            if mb and mb != head:
                bases.append(mb)
            break
    return bases


def _trust_problem(ledger: dict, committed_raw: bytes | None, base: str) -> tuple[str, str] | None:
    """(rule, message) when a validly signed ledger does not extend the committed one at `base`, else None."""
    try:
        committed = parse_ledger(committed_raw) if committed_raw is not None else None
    except RuleError:
        return None
    if committed is None:
        return None
    n = len(committed["history"])
    extends = ledger["history"][:n] == committed["history"]
    if extends and _key_chain_ok(committed["owner"]["pubkey"], ledger["history"][n:], ledger["owner"]["pubkey"]):
        return None
    if ledger["owner"]["pubkey"] != committed["owner"]["pubkey"]:
        return "rules-owner-key-changed", f"The owner key differs from {base} with no rotation signed by the old key."
    return "rules-ledger-rollback", f"The rule ledger drops decisions recorded at {base} (an older ledger was restored)."


def _committed(root: Path, bases: list[str]) -> list[tuple[str, bytes | None]]:
    return [(b, Source(root, "ref", b).read(LEDGER_REL)) for b in bases]


def _trust_warning(root: Path, ledger: dict) -> str:
    for base, raw in _committed(root, trust_bases(root)):
        problem = _trust_problem(ledger, raw, base[:12])
        if problem:
            return problem[1]
    return ""


def trusted_approvals(root) -> dict | None:
    """Approved item hashes from a signed ledger that extends the committed ones; None when approval is off.

    A forged, rolled-back, re-keyed or deleted ledger yields {} so nothing it lists counts as approved.
    """
    root = project_root(root)
    raw = Source(root).read(LEDGER_REL)
    committed = _committed(root, trust_bases(root))
    if raw is None:
        return {} if any(c is not None for _, c in committed) else None
    try:
        ledger = parse_ledger(raw)
    except RuleError:
        return {}
    if not signature_ok(ledger) or any(_trust_problem(ledger, c, b) for b, c in committed):
        return {}
    return dict(ledger["approved"])


def _require_ledger(root: Path) -> dict:
    raw = Source(root).read(LEDGER_REL)
    if raw is None:
        raise RuleError("rule approval is off in this repo; the owner turns it on with `deepmodebot rules init`")
    ledger = parse_ledger(raw)
    if not signature_ok(ledger):
        raise RuleError(f"{LEDGER_REL} does not carry a valid owner signature. "
                        f"Restore it from git (`git checkout HEAD -- {STORE_REL}`) before changing rules.")
    return ledger


def _target(root: Path, rel: str, *, final_link_ok: bool = False) -> Path:
    rel = norm_rel(rel)
    parts = rel.split("/")
    if not rel or rel.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", rel):
        raise RuleError(f"refusing path outside the repo: {rel!r}")
    probe = root
    for i, part in enumerate(parts):
        probe = probe / part
        if probe.is_symlink() and not (final_link_ok and i == len(parts) - 1):
            raise RuleError(f"refusing to write through the symlink {probe}")
    return probe


def _safe_write(root: Path, rel: str, data: bytes) -> None:
    path = _target(root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if path.is_file():
            mode = stat.S_IMODE(path.stat().st_mode)
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def _safe_unlink(root: Path, rel: str) -> None:
    path = _target(root, rel, final_link_ok=True)
    if os.path.lexists(path):
        path.unlink()


def _memory_write(root: Path, item: str, data: bytes | None) -> None:
    pm = _asset_module("dmb_project_memory", "memory/project_memory.py")
    key = item[len(MEMORY_PREFIX):]
    db = pm.db_path_for(Path(root))
    with pm.connect_db(db) as conn:
        if data is None:
            conn.execute("DELETE FROM memories WHERE key = ? AND kind = 'convention'", (key,))
        else:
            text, now = data.decode("utf-8"), time.time()
            digest = pm.content_digest("convention", text)
            if conn.execute("SELECT 1 FROM memories WHERE key = ?", (key,)).fetchone():
                conn.execute(
                    "UPDATE memories SET kind = 'convention', content = ?, content_hash = ?, updated_at = ?,"
                    " expires_at = NULL WHERE key = ?", (text, digest, now, key))
            else:
                conn.execute(
                    "INSERT INTO memories(key, kind, priority, content, tags, source, content_hash, tokens_est, hits,"
                    " created_at, updated_at, last_accessed, expires_at)"
                    " VALUES (?, 'convention', 0, ?, '', 'rule-ledger', ?, ?, 0, ?, ?, ?, NULL)",
                    (key, text, digest, pm.estimate_tokens(key, text), now, now, now))
        conn.commit()


def _write_item(root: Path, item: str, data: bytes | None, *, link: bool = False) -> None:
    if item.startswith(MEMORY_PREFIX):
        _memory_write(root, item, data)
    elif data is None:
        _safe_unlink(root, item)
    elif link:
        path = _target(root, item, final_link_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(path):
            path.unlink()
        os.symlink(data.decode("utf-8", "surrogateescape"), path)
    else:
        _safe_write(root, item, data)


def _state(root: Path, src: Source, approved: dict, *, memory: bool) -> tuple[dict, dict]:
    """(current bytes per rule item, approved bytes per approved item); a tampered approved copy reads as None."""
    approved = {i: s for i, s in approved.items() if memory or not i.startswith(MEMORY_PREFIX)}
    files = set(rule_files(src)) | {i for i in approved if not i.startswith(MEMORY_PREFIX)}
    current = src.read_many(sorted(files))
    if memory:
        mem = memory_rules(root)
        current.update(mem)
        current.update({i: None for i in approved if i.startswith(MEMORY_PREFIX) and i not in mem})
    blobs = src.read_many(sorted({f"{APPROVED_REL}/{sha}" for sha in approved.values()}))
    kept = {}
    for item, sha in approved.items():
        blob = blobs.get(f"{APPROVED_REL}/{sha}")
        kept[item] = blob if blob is not None and _sha(blob) == sha else None
    return current, kept


def _text(data: bytes | None) -> str | None:
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _seg(data: bytes | None) -> list[str]:
    if data is None:
        return []
    text = _text(data)
    return text.splitlines(keepends=True) if text is not None else [f"<binary, {len(data)} bytes, sha256 {_sha(data)[:12]}>\n"]


def _opcodes(old: str, new: str) -> tuple[list[str], list[str], list[tuple]]:
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    return a, b, difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def _merge(a: list[str], b: list[str], ops: list[tuple], take_new: set[int]) -> bytes:
    out: list[str] = []
    for idx, (tag, i1, i2, j1, j2) in enumerate(ops):
        out.extend(b[j1:j2] if tag != "equal" and idx in take_new else a[i1:i2])
    return "".join(out).encode("utf-8")


def _change(item: str, kind: str, old: list[str], new: list[str], seen: dict, *, context: tuple = (), **extra) -> dict:
    """One pending change. Its id hashes the change and its unchanged neighbours, so it survives other decisions."""
    key = (item, "".join(old), "".join(new), *context)
    nth = seen.get(key, 0)
    seen[key] = nth + 1
    cid = _sha("\0".join((*key, str(nth))).encode("utf-8", "surrogateescape"))[:8]
    added = [_clean(line.rstrip("\r\n")) for line in new]
    removed = [_clean(line.rstrip("\r\n")) for line in old]
    summary = next((line.strip() for line in added if line.strip()), "")
    if not summary:
        summary = next(("removed: " + line.strip() for line in removed if line.strip()), "")
    return {"id": cid, "item": item, "kind": kind, "added": len(new), "removed": len(old), "summary": summary[:120],
            "diff": ["- " + line for line in removed] + ["+ " + line for line in added], **extra}


def _item_changes(item: str, new: bytes | None, approved: bool, old: bytes | None, seen: dict) -> list[dict]:
    if not approved:
        return [] if new is None else [_change(item, "new", [], _seg(new), seen)]
    if new is None:
        return [_change(item, "removed", _seg(old) or ["<approved copy missing>\n"], [], seen)]
    old_text, new_text = _text(old), _text(new)
    if old_text is None or new_text is None:
        return [_change(item, "changed", _seg(old) or ["<approved copy missing>\n"], _seg(new), seen)]
    a, b, ops = _opcodes(old_text, new_text)
    return [_change(item, "changed", a[i1:i2], b[j1:j2], seen, block=idx,
                    context=(a[i1 - 1] if i1 else "", a[i2] if i2 < len(a) else ""))
            for idx, (tag, i1, i2, j1, j2) in enumerate(ops) if tag != "equal"]


def load_proposals(root: Path) -> list[dict]:
    folder = root / PROPOSALS_REL
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() and not folder.is_symlink() else []:
        try:
            prop = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(prop, dict) and isinstance(prop.get("content"), str) and is_rule_path(str(prop.get("item", ""))):
            out.append({**prop, "file": f"{PROPOSALS_REL}/{path.name}"})
    return out


def pending_changes(root: Path, src: Source, ledger: dict, *, memory: bool = True, proposals: bool = True) -> list[dict]:
    """Every rule change the owner has not decided yet: drift blocks, new/removed rules, memory conventions, proposals."""
    approved = ledger["approved"]
    current, kept = _state(root, src, approved, memory=memory)
    seen: dict = {}
    out: list[dict] = []
    for item in sorted(current):
        new = current[item]
        if item in approved and new is not None and _sha(new) == approved[item]:
            continue
        out += _item_changes(item, new, item in approved, kept.get(item), seen)
    for prop in load_proposals(root) if proposals else []:
        old = kept.get(prop["item"]) if prop["item"] in approved else b""
        new = prop["content"].encode("utf-8")
        old_text = _text(old)
        if old_text is None:
            removed, added = _seg(old) or ["<approved copy missing>\n"], _seg(new)
        else:
            a, b, ops = _opcodes(old_text, prop["content"])
            removed = [line for tag, i1, i2, _, _ in ops if tag != "equal" for line in a[i1:i2]]
            added = [line for tag, _, _, j1, j2 in ops if tag != "equal" for line in b[j1:j2]]
        change = _change(prop["item"], "proposal", removed, added, seen,
                         reason=_clean(prop.get("reason") or ""), by=_clean(prop.get("by") or "agent"), file=prop["file"],
                         base_sha256=prop.get("base_sha256"), content=prop["content"])
        change["id"] = _clean(prop.get("id") or change["id"])
        change["summary"] = change["reason"][:120] or change["summary"]
        out.append(change)
    return out


def _select(changes: list[dict], ids: list[str], select_all: bool) -> list[dict]:
    if select_all:
        return list(changes)
    chosen, missing = [], []
    for raw in ids:
        hits = [c for c in changes if c["id"] == raw] or [c for c in changes if len(raw) >= 4 and c["id"].startswith(raw)]
        if len(hits) != 1:
            missing.append(raw)
        elif hits[0] not in chosen:
            chosen.append(hits[0])
    if missing:
        raise RuleError(f"no single pending change matches {', '.join(missing)}; run `review` for the current ids")
    if not chosen:
        raise RuleError("name the change ids to decide, or pass --all")
    return chosen


def _approve_bytes(root: Path, ledger: dict, item: str, data: bytes, *, link: bool = False) -> None:
    sha = _sha(data)
    blob = f"{APPROVED_REL}/{sha}"
    existing = _target(root, blob)
    if not (existing.is_file() and _sha(existing.read_bytes()) == sha):
        _safe_write(root, blob, data)
    ledger["approved"][item] = sha
    links = set(ledger.get("links") or [])
    if link:
        links.add(item)
    else:
        links.discard(item)
    if links:
        ledger["links"] = sorted(links)
    else:
        ledger.pop("links", None)


def _forget(ledger: dict, item: str) -> None:
    ledger["approved"].pop(item, None)
    links = [i for i in ledger.get("links") or [] if i != item]
    if links:
        ledger["links"] = links
    else:
        ledger.pop("links", None)


def _save(root: Path, ledger: dict, seed: bytes) -> None:
    folder = _target(root, APPROVED_REL)
    ledger["version"] = LEDGER_VERSION
    ledger["signature"] = sign(seed, _canonical(ledger))
    _safe_write(root, LEDGER_REL, (json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    keep = set(ledger["approved"].values())
    for blob in folder.iterdir() if folder.is_dir() else []:
        if blob.name not in keep and blob.is_file() and not blob.is_symlink():
            blob.unlink()


def _history(at: str, action: str, change: dict) -> dict:
    entry = {"at": at, "action": action, "item": change["item"], "change": change["id"], "kind": change["kind"],
             "added": change["added"], "removed": change["removed"], "summary": change["summary"]}
    if change["kind"] == "proposal":
        entry.update(reason=change["reason"], by=change["by"])
    return entry


def _is_link(root: Path, item: str) -> bool:
    return not item.startswith(MEMORY_PREFIX) and (root / item).is_symlink()


def _decide_item(root: Path, ledger: dict, item: str, group: list[dict], current: dict, kept: dict, approve: bool) -> None:
    drift = [c for c in group if c["kind"] != "proposal"]
    if drift:
        new, old = current.get(item), kept.get(item)
        was_link = item in (ledger.get("links") or [])
        blocks = set() if was_link or _is_link(root, item) else {c["block"] for c in drift if "block" in c}
        if blocks:
            a, b, ops = _opcodes(_text(old), _text(new))
            changed = {i for i, op in enumerate(ops) if op[0] != "equal"}
            if approve:
                _approve_bytes(root, ledger, item, _merge(a, b, ops, blocks))
            else:
                _write_item(root, item, _merge(a, b, ops, changed - blocks))
        elif approve:
            if new is None:
                _forget(ledger, item)
            else:
                _approve_bytes(root, ledger, item, new, link=_is_link(root, item))
        else:
            if item in ledger["approved"] and old is None:
                raise RuleError(f"the approved copy of {item} is missing, so it cannot be restored")
            _write_item(root, item, old, link=was_link)
    for prop in (c for c in group if c["kind"] == "proposal"):
        if approve:
            content = prop["content"].encode("utf-8")
            _write_item(root, item, content)
            _approve_bytes(root, ledger, item, content)
        _safe_unlink(root, prop["file"])


def decide(root: Path, ids: list[str], *, approve: bool, passphrase: str, select_all: bool = False) -> list[dict]:
    """Owner approves (or rejects) pending changes; rejecting puts the approved text back."""
    root = Path(root)
    ledger = _require_ledger(root)
    seed = _owner_seed(ledger, passphrase)
    src = Source(root)
    changes = pending_changes(root, src, ledger)
    chosen = _select(changes, ids, select_all)
    current, kept = _state(root, src, ledger["approved"], memory=True)
    if approve:
        for prop in (c for c in chosen if c["kind"] == "proposal"):
            if any(c["item"] == prop["item"] and c["kind"] == "proposal" and c is not prop for c in chosen):
                raise RuleError(f"approve one proposal for {prop['item']} at a time")
            live = current.get(prop["item"])
            if (_sha(live) if live is not None else None) != prop["base_sha256"]:
                raise RuleError(f"{prop['item']} changed after proposal {prop['id']} was made; reject it and propose again")
    by_item: dict[str, list[dict]] = {}
    for change in chosen:
        by_item.setdefault(change["item"], []).append(change)
    at = _now()
    for item, group in by_item.items():
        _decide_item(root, ledger, item, group, current, kept, approve)
        ledger["history"] += [_history(at, "approve" if approve else "reject", c) for c in group]
    _save(root, ledger, seed)
    return chosen


def init_ledger(root: Path, passphrase: str, *, reset: bool = False) -> dict:
    """Owner turns rule approval on: every rule present now becomes the signed, approved baseline."""
    root = Path(root)
    src = Source(root)
    raw = src.read(LEDGER_REL)
    history: list = []
    if raw is not None:
        if not reset:
            raise RuleError("rule approval is already on here; `rotate` changes the passphrase")
        try:
            history = list(parse_ledger(raw)["history"])
        except RuleError:
            history = []
    links = untracked_links(src)
    if links:
        listed = ", ".join(f"{rel} -> {target}" for rel, target in links)
        raise RuleError(f"these rule symlinks point at files that are not rule paths, so their content could change "
                        f"unseen: {listed}. Replace each link with the real file (or link it to a rule path), then run init again.")
    owner, seed = _new_owner(passphrase)
    ledger = {"version": LEDGER_VERSION, "owner": owner, "approved": {}, "history": history}
    current, _ = _state(root, src, {}, memory=True)
    for item, data in sorted(current.items()):
        if data is not None:
            _approve_bytes(root, ledger, item, data, link=_is_link(root, item))
    ledger["history"].append({"at": _now(), "action": "reset" if raw is not None else "init",
                              "items": sorted(ledger["approved"])})
    _save(root, ledger, seed)
    return ledger


def rotate_key(root: Path, old_passphrase: str, new_passphrase: str) -> dict:
    root = Path(root)
    ledger = _require_ledger(root)
    old_seed = _owner_seed(ledger, old_passphrase)
    owner, seed = _new_owner(new_passphrase)
    ledger["history"].append({"at": _now(), "action": "rotate", "from": ledger["owner"]["pubkey"], "to": owner["pubkey"],
                              "sig": sign(old_seed, ROTATE_TAG + owner["pubkey"].encode("utf-8"))})
    ledger["owner"] = owner
    _save(root, ledger, seed)
    return ledger


def propose(root: Path, item: str, content: bytes, reason: str, by: str = "agent") -> dict:
    """Agent-facing: park a full new version of a rule file for the owner to approve. The rule file is untouched."""
    root = Path(root)
    rel = norm_rel(item)
    if not is_rule_path(rel):
        raise RuleError(f"{rel} is not an agent rule file (see rule-paths.json), so it needs no approval")
    if Source(root).read(LEDGER_REL) is None:
        raise RuleError("rule approval is off in this repo, so there is nothing to propose to")
    text = _text(content)
    if text is None:
        raise RuleError("a proposal must be UTF-8 text")
    if not reason.strip():
        raise RuleError("say why the rule is needed with --reason")
    live = Source(root).read(rel)
    pid = "p" + _sha(f"{rel}\0{text}".encode("utf-8", "surrogateescape"))[:7]
    prop = {"id": pid, "item": rel, "base_sha256": _sha(live) if live is not None else None, "content": text,
            "reason": _clean(reason.strip()), "by": _clean(by.strip() or "agent"), "proposed_at": _now()}
    _safe_write(root, f"{PROPOSALS_REL}/{pid}.json", (json.dumps(prop, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return prop


def _finding(severity: str, rule: str, file: str, message: str, fix: str) -> dict:
    return {"severity": severity, "rule": rule, "file": _clean(file), "line": 1, "message": _clean(message), "fix": fix}


def check(root: Path, *, staged: bool = False, base: str | None = None) -> dict:
    """Gate: fail on unapproved rules, a forged, rolled-back or deleted ledger, or a swapped owner key.

    Without `base` the ledger must extend the committed ones at HEAD and at the merge-base with the remote default
    branch; a CI run passes the protected branch it merges into.
    """
    root = project_root(root)
    src = Source(root, "index" if staged else "work")
    findings: list[dict] = []
    if base and not _resolves(root, base):
        findings.append(_finding("P0", "rules-base-missing", LEDGER_REL,
                                 f"The base `{base}` does not resolve, so the ledger cannot be checked against it.",
                                 "Fetch the base branch (`git fetch origin`) or pass a commit that exists."))
    committed = _committed(root, [base] if base else trust_bases(root))
    raw = src.read(LEDGER_REL)

    def result(enabled: bool) -> dict:
        blocking = [f for f in findings if f["severity"] in ("P0", "P1")]
        return {"enabled": enabled, "ok": not blocking, "root": str(root), "findings": findings}

    if raw is None:
        for label, committed_raw in committed:
            if committed_raw is not None:
                findings.append(_finding("P0", "rules-ledger-removed", LEDGER_REL,
                                         f"The owner-signed rule ledger exists at {label[:12]} but is gone now.",
                                         f"Restore it: `git checkout {label} -- {STORE_REL}`."))
                break
        return result(bool(findings))
    restore = f"Restore it: `git checkout HEAD -- {STORE_REL}`."
    try:
        _target(root, APPROVED_REL)
    except RuleError as exc:
        findings.append(_finding("P0", "rules-store-symlink", STORE_REL, str(exc), restore))
        return result(True)
    try:
        ledger = parse_ledger(raw)
    except RuleError as exc:
        findings.append(_finding("P0", "rules-ledger-forged", LEDGER_REL, str(exc), restore))
        return result(True)
    if not signature_ok(ledger):
        findings.append(_finding("P0", "rules-ledger-forged", LEDGER_REL,
                                 "The rule ledger was edited without the owner's passphrase (bad signature).", restore))
        return result(True)
    for label, committed_raw in committed:
        problem = _trust_problem(ledger, committed_raw, label[:12])
        if problem:
            findings.append(_finding("P0", problem[0], LEDGER_REL, problem[1],
                                     f"{restore} Owners change the passphrase with `deepmodebot rules rotate`."))
            break
    approved = {i: s for i, s in ledger["approved"].items() if not (staged and i.startswith(MEMORY_PREFIX))}
    _, kept = _state(root, src, approved, memory=False)
    for item in sorted(i for i in approved if not i.startswith(MEMORY_PREFIX) and kept.get(i) is None):
        findings.append(_finding("P0", "rules-snapshot-missing", f"{APPROVED_REL}/{approved[item]}",
                                 f"The approved copy of `{item}` is missing or altered.", restore))
    for rel, target in untracked_links(src):
        findings.append(_finding("P1", "rules-symlink-untracked", rel,
                                 f"`{rel}` links to `{target}`, which is not a rule path, so its content is never approved.",
                                 "Replace the link with the real file, or link it to a rule path."))
    review = "Owner: `deepmodebot rules review`, then `deepmodebot rules approve <id>` or `reject <id>`."
    for change in pending_changes(root, src, ledger, memory=not staged, proposals=not staged):
        label = f"[{change['id']}] ({change['kind']}, +{change['added']} -{change['removed']}) \"{change['summary']}\""
        if change["kind"] == "proposal":
            findings.append(_finding("P2", "rules-proposal-pending", change["item"],
                                     f"Rule proposal {label} waits for the owner.", review))
        elif change["item"].startswith(MEMORY_PREFIX):
            findings.append(_finding("P2", "rules-memory-pending", change["item"],
                                     f"Unapproved memory convention {label} is hidden from recall.", review))
        else:
            findings.append(_finding("P1", "rules-unapproved", change["item"], f"Unapproved rule change {label}",
                                     review + " Agents never edit rule files; they run `rule_ledger.py propose`."))
    return result(True)


def ledger_enabled(root: Path) -> bool:
    root = Path(root)
    if os.path.lexists(root / LEDGER_REL):
        return True
    return any(raw is not None for _, raw in _committed(root, trust_bases(root)))


def _owning_root(full: str) -> Path | None:
    """The repo (or ledger-holding folder) a path belongs to: nearest ancestor with .git or a rule ledger."""
    cur = full if os.path.isdir(full) else os.path.dirname(full)
    while True:
        if os.path.lexists(os.path.join(cur, ".git")) or os.path.lexists(os.path.join(cur, LEDGER_REL)):
            return Path(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _locations(cwd: Path, raw: str, removes: bool) -> list[tuple[Path, str]]:
    """(repo root, repo path) for a path as written, with its folders resolved, and (writes only) fully resolved."""
    p = os.path.expanduser(str(raw).strip())
    if not p:
        return []
    joined = (p if os.path.isabs(p) else os.path.join(str(cwd), p)).rstrip("/\\") or os.sep
    variants = [os.path.normpath(joined),
                os.path.join(os.path.realpath(os.path.dirname(joined)), os.path.basename(joined))]
    if not removes:
        variants.append(os.path.realpath(joined))
    out = []
    for full in dict.fromkeys(variants):
        root = _owning_root(full)
        if root is None:
            continue
        rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
        if rel == "..":
            continue
        out.append((root, "" if rel == "." else rel))
    return out


def _rule_reason(rel: str) -> str:
    return (f"deepmodebot rule approval: `{_clean(rel)}` is an agent rule file, and only the project owner approves rule "
            f"changes. Write your draft under .scratch/, run `\"{sys.executable or 'python3'}\" -B \"{SCRIPT}\" propose "
            f"--item {_clean(rel)} --file <draft> --reason \"<why>\"`, and tell the owner to review it with "
            "`deepmodebot rules review`.")


STORE_REASON = (f"deepmodebot rule approval: {STORE_REL}/ holds the owner-signed rule ledger; agents may not write, "
                "move or delete anything in it.")
HOOK_REASON = ("deepmodebot rule approval: skipping git hooks (`--no-verify`, `commit -n`, `core.hooksPath`) is blocked "
               "in a repo with owner rule approval, because those hooks run the rule gate.")
UNSEEN_REASON = ("deepmodebot rule approval: this command changes files chosen by `xargs` or `$(...)`, so the guard "
                 "cannot tell whether it rewrites agent rule files. Name the files explicitly.")


def _owner_reason(sub: str) -> str:
    return (f"deepmodebot rule approval: `rules {sub}` is owner-only. Ask the owner to run `deepmodebot rules {sub}` in "
            "their own terminal. Never ask for, store or type the owner's passphrase.")


def _path_reason(rel: str) -> str | None:
    if is_store_path(rel):
        return STORE_REASON
    return _rule_reason(rel) if is_rule_path(rel) else None


def _dir_has_rules(root: Path, rel: str) -> bool:
    prefix = rel.lower().strip("/") + "/" if rel.strip("/") else ""
    if not prefix or (STORE_REL + "/").startswith(prefix):
        return True
    return any(p.lower().startswith(prefix) for p in rule_files(Source(root)))


def _literal_reason(cwd: Path, raw: str, removes: bool) -> str | None:
    for root, rel in _locations(cwd, raw, removes):
        reason = _path_reason(rel) if rel else None
        if reason is None and removes and (root / rel).is_dir() and not (root / rel).is_symlink():
            if ledger_enabled(root) and _dir_has_rules(root, rel):
                return STORE_REASON if (STORE_REL + "/").startswith(rel.lower().strip("/") + "/") else _rule_reason(rel or ".")
        if reason and ledger_enabled(root):
            return reason
    return None


def _token_reason(cwd: Path, token: str, *, removes: bool = False, expand: bool = True) -> str | None:
    """Deny reason when writing (or, with removes, deleting/moving) `token` would change a rule in a ledger repo."""
    reason = _literal_reason(cwd, token, removes)
    if reason or not expand or not any(ch in token for ch in "*?["):
        return reason
    for match in sorted(glob.glob(os.path.join(str(cwd), os.path.expanduser(token))))[:500]:
        reason = _literal_reason(cwd, match, removes)
        if reason:
            return reason
    return None


def _first(cwd: Path, tokens, *, removes: bool = False) -> str | None:
    return next(filter(None, (_token_reason(cwd, t, removes=removes) for t in tokens)), None)


def _code_reason(cwd: Path, code: str) -> str | None:
    if not WRITE_CODE_RE.search(code):
        return None
    for word in CODE_WORD_RE.findall(code):
        reason = _token_reason(cwd, word)
        if reason:
            return reason
    return None


def _base(word: str) -> str:
    name = os.path.basename(word.replace("\\", "/")).lower()
    return name[:-4] if name.endswith(".exe") else name


def _owner_command(words: list[str]) -> str | None:
    for i, word in enumerate(words):
        name = _base(word)
        if name in ("rule_ledger.py", "rule_ledger"):
            sub = next((w for w in words[i + 1:] if w in SUBCOMMANDS), "")
            return sub if sub in OWNER_COMMANDS else None
        if name in ("deepmodebot", "deepmodebot.mjs") or name.startswith("deepmodebot@"):
            rest = [w for w in words[i + 1:] if not w.startswith("-")]
            if "rules" in rest[:2]:
                j = rest.index("rules")
                if j + 1 < len(rest) and rest[j + 1] in OWNER_COMMANDS:
                    return rest[j + 1]
    return None


def _hook_skip(cwd: Path, words: list[str]) -> str | None:
    """HOOK_REASON for git commands that skip or reroute hooks in a ledger repo."""
    if not words or _base(words[0]) != "git":
        return None
    args, i, sub, hooks_path = words[1:], 0, "", False
    while i < len(args):
        arg = args[i]
        if arg == "-c" and i + 1 < len(args):
            hooks_path = hooks_path or args[i + 1].lower().startswith("core.hookspath")
            i += 2
        elif arg.startswith("-c") and "core.hookspath" in arg.lower():
            hooks_path, i = True, i + 1
        elif arg in ("-C", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(args):
            i += 2
        elif arg.startswith("-"):
            i += 1
        else:
            sub = arg
            break
    rest = args[i + 1:]
    skips = hooks_path or "--no-verify" in rest
    skips = skips or (sub == "commit" and any(re.fullmatch(r"-[A-Za-z]*n[A-Za-z]*", r) for r in rest))
    reads = {"--get", "--get-all", "--get-regexp", "-l", "--list"} & set(rest)
    skips = skips or (sub == "config" and not reads and any(r.lower().startswith("core.hookspath") for r in rest))
    root = _owning_root(str(cwd))
    return HOOK_REASON if skips and root is not None and ledger_enabled(root) else None


def _copy_targets(cmd: str, cwd: Path, args: list[str], plain: list[str]) -> list[str]:
    """Paths a cp/mv/ln/rsync-style command writes: the destination, or each source's copy inside it."""
    if "-t" in args[:-1]:
        dest = args[args.index("-t") + 1]
        sources = [a for a in plain if a != dest]
    elif plain:
        dest, sources = plain[-1], plain[:-1]
    else:
        return []
    into_dir = ("-t" in args or dest.endswith(("/", "\\")) or len(sources) > 1
                or os.path.isdir(os.path.join(str(cwd), os.path.expanduser(dest))))
    if not into_dir:
        return [dest]
    out = []
    for src in sources:
        src_path = os.path.join(str(cwd), os.path.expanduser(src))
        name = "" if cmd == "rsync" and src.endswith(("/", "\\")) else os.path.basename(src.rstrip("/\\"))
        top = os.path.join(dest, name) if name else dest
        if name:
            out.append(top)
        if os.path.isdir(src_path) and not os.path.islink(src_path):
            for folder, dirnames, filenames in os.walk(src_path):
                dirnames[:] = [d for d in dirnames if d not in SKIP_SEGMENTS]
                out += [os.path.join(top, os.path.relpath(os.path.join(folder, f), src_path)) for f in filenames]
                if len(out) > COPY_WALK_LIMIT:
                    return out
    return out


def _download_targets(cmd: str, args: list[str]) -> list[str]:
    short, long_opts = ("o", ("--output",)) if cmd == "curl" else ("O", ("--output-document",))
    out = []
    for i, arg in enumerate(args):
        if (arg in long_opts or re.fullmatch(rf"-[A-Za-z]*{short}", arg)) and i + 1 < len(args):
            out.append(args[i + 1])
        elif any(arg.startswith(opt + "=") for opt in long_opts):
            out.append(arg.split("=", 1)[1])
    return [t for t in out if t != "-"]


def _find_reason(cwd: Path, args: list[str]) -> str | None:
    """find with -delete or a writing -exec: deny only when an existing rule file matches its tests."""
    writes = "-delete" in args
    for i, arg in enumerate(args[:-1]):
        if arg in FIND_ACTIONS:
            prog, rest = _base(args[i + 1]), args[i + 2:i + 8]
            writes = writes or prog in DELETERS | MOVERS | COPIERS | SHELLS or prog in ("tee", "sd")
            writes = writes or (prog in IN_PLACE and any(IN_PLACE_FLAG_RE.fullmatch(r) for r in rest))
    if not writes:
        return None
    starts = []
    for arg in args:
        if arg.startswith(("-", "(", "!", ")")):
            break
        starts.append(arg)
    names = [args[j + 1].lower() for j, a in enumerate(args[:-1]) if a in ("-name", "-iname")]
    paths = [args[j + 1].lower() for j, a in enumerate(args[:-1]) if a in ("-path", "-ipath", "-wholename", "-iwholename")]
    for start in starts or ["."]:
        for root, rel in _locations(cwd, start, True):
            if not ledger_enabled(root):
                continue
            prefix = rel.strip("/") + "/" if rel.strip("/") else ""
            for item in rule_files(Source(root)):
                if not item.lower().startswith(prefix.lower()):
                    continue
                shown = os.path.join(start, item[len(prefix):]).replace(os.sep, "/").lower()
                if names and not any(fnmatch.fnmatchcase(item.rsplit("/", 1)[-1].lower(), n) for n in names):
                    continue
                if paths and not any(fnmatch.fnmatchcase(shown, p) for p in paths):
                    continue
                return _rule_reason(item)
    return None


def _tokenize(text: str) -> list[str] | None:
    lex = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        return None


def _split_simple(tokens: list[str]) -> list[list[str]]:
    cmds, cur = [], []
    for tok in tokens:
        if tok and set(tok) <= PUNCT and ">" not in tok and "<" not in tok:
            cmds.append(cur)
            cur = []
        else:
            cur.append(tok)
    cmds.append(cur)
    return [c for c in cmds if c]


def _simple_reason(cwd: Path, toks: list[str], depth: int) -> str | None:
    words: list[str] = []
    targets: list[str] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if tok and set(tok) <= PUNCT:
            if ">" in tok and not (tok.endswith("&") and re.fullmatch(r"\d+|-", nxt)):
                targets.append(nxt)
            if words and words[-1].isdigit():
                words.pop()
            i += 2
            continue
        words.append(tok)
        i += 1
    via_xargs = False
    while words:
        name = _base(words[0])
        if ENV_ASSIGN_RE.match(words[0]):
            words.pop(0)
            continue
        if name == "xargs":
            via_xargs = True
        elif name not in WRAPPERS:
            break
        words.pop(0)
        while words and words[0].startswith("-"):
            if words.pop(0) in WRAPPER_ARG_OPTS.get(name, ()) and words:
                words.pop(0)
        if name == "timeout" and words:
            words.pop(0)
    owner = _owner_command(words)
    if owner:
        return _owner_reason(owner)
    hook = _hook_skip(cwd, words)
    if hook:
        return hook
    reason = _first(cwd, targets)
    if reason or not words:
        return reason
    cmd, args = _base(words[0]), words[1:]
    plain = [a for a in args if not a.startswith("-")]
    in_place = (cmd in IN_PLACE and any(IN_PLACE_FLAG_RE.fullmatch(a) for a in args)) or (
        cmd in ("awk", "gawk") and "inplace" in args)
    writer = in_place or cmd in DELETERS | MOVERS | COPIERS or cmd in ("tee", "sd", "dd")
    unseen = via_xargs or any(a == "$" or "$(" in a or "`" in a for a in args)
    if writer and unseen:
        root = _owning_root(str(cwd))
        if root is not None and ledger_enabled(root):
            return UNSEEN_REASON
    if cmd == "git" and plain[:1] in (["rm"], ["mv"]):
        return _first(cwd, plain[1:], removes=True)
    if cmd in DELETERS:
        return _first(cwd, plain, removes=True)
    if cmd in MOVERS:
        sources = [a for a in plain if a != args[args.index("-t") + 1]] if "-t" in args[:-1] else plain[:-1]
        return _first(cwd, sources, removes=True) or _first(cwd, _copy_targets(cmd, cwd, args, plain))
    if cmd in ("tee", "sd") or in_place:
        return _first(cwd, plain)
    if cmd in COPIERS:
        return _first(cwd, _copy_targets(cmd, cwd, args, plain))
    if cmd == "dd":
        return _first(cwd, (a[3:] for a in args if a.startswith("of=")))
    if cmd in ("curl", "wget"):
        return _first(cwd, _download_targets(cmd, args))
    if cmd == "find":
        return _find_reason(cwd, args)
    if cmd in SHELLS:
        flag = next((j for j, a in enumerate(args[:-1]) if SHELL_C_RE.fullmatch(a)), None)
        return _shell_reason(cwd, args[flag + 1], depth + 1) if flag is not None else None
    if cmd == "eval":
        return _shell_reason(cwd, " ".join(args), depth + 1)
    if cmd in INTERPRETERS:
        flags = [j for j, a in enumerate(args[:-1]) if a.lower() in CODE_FLAGS or CODE_FLAG_RE.fullmatch(a)]
        return next(filter(None, (_code_reason(cwd, args[j + 1]) for j in flags)), None)
    return None


def _chain_reason(cwd: Path, tokens: list[str], depth: int) -> str | None:
    cur = cwd
    for simple in _split_simple(tokens):
        if _base(simple[0]) in ("cd", "pushd") and len(simple) > 1 and simple[1] != "-":
            cur = Path(os.path.normpath(os.path.join(str(cur), os.path.expanduser(simple[1]))))
            continue
        reason = _simple_reason(cur, simple, depth)
        if reason:
            return reason
    return None


def _split_heredocs(command: str) -> tuple[list[str], list[tuple[str, str]]]:
    lines = command.replace("\\\r\n", " ").replace("\\\n", " ").splitlines()
    kept: list[str] = []
    bodies: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for match in HEREDOC_RE.finditer(line):
            body = []
            while i < len(lines) and lines[i].strip() != match.group(2):
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append((line, "\n".join(body)))
    return kept, bodies


def _shell_reason(cwd: Path, command: str, depth: int = 0) -> str | None:
    if depth > 4:
        return None
    lines, bodies = _split_heredocs(command)
    tokens = _tokenize("\n".join(lines))
    if tokens is not None:
        reason = _chain_reason(cwd, tokens, depth)
        if reason:
            return reason
    else:
        for line in lines:
            line_tokens = _tokenize(line)
            if line_tokens is not None:
                reason = _chain_reason(cwd, line_tokens, depth)
            elif FALLBACK_WRITE_RE.search(line):
                reason = next(filter(None, (_token_reason(cwd, w) for w in FALLBACK_WORD_RE.findall(line))), None)
            else:
                reason = None
            if reason:
                return reason
    for owner_line, body in bodies:
        names = {_base(t) for t in _tokenize(owner_line) or []}
        if names & SHELLS:
            reason = _shell_reason(cwd, body, depth + 1)
        elif names & INTERPRETERS:
            reason = _code_reason(cwd, body)
        else:
            reason = None
        if reason:
            return reason
    return None


def guard(cwd, *, paths=(), command: str = "") -> str | None:
    """Hook verdict: why to deny a tool call that writes a rule file or the ledger in a repo with rule approval on,
    skips its git hooks, or runs an owner-only rule command anywhere. None allows it."""
    cwd = Path(cwd).expanduser().resolve()
    for raw in paths:
        reason = _token_reason(cwd, raw, expand=False) if isinstance(raw, str) else None
        if reason:
            return reason
    return _shell_reason(cwd, command) if command else None


def status(root: Path) -> dict:
    root = project_root(root)
    src = Source(root)
    raw = src.read(LEDGER_REL)
    committed = _committed(root, trust_bases(root))
    if raw is None:
        if all(c is None for _, c in committed):
            return {"enabled": False, "root": str(root), "rule_files": rule_files(src)}
        return {"enabled": True, "root": str(root), "problem": "the committed rule ledger was deleted from the working tree",
                "items": [], "pending": 0, "proposals": []}
    ledger = parse_ledger(raw)
    if not signature_ok(ledger):
        return {"enabled": True, "root": str(root), "items": [], "pending": 0, "proposals": [],
                "problem": "the ledger was edited without the owner passphrase (bad signature)"}
    problem = next((p[1] for p in (_trust_problem(ledger, c, b[:12]) for b, c in committed) if p), "")
    links = untracked_links(src)
    if links and not problem:
        problem = "rule symlinks point outside the rule paths: " + ", ".join(f"{r} -> {t}" for r, t in links)
    changes = pending_changes(root, src, ledger)
    last: dict[str, str] = {}
    for entry in ledger["history"]:
        if entry.get("action") == "approve":
            last[entry.get("item", "")] = entry.get("at", "")
        elif entry.get("action") in ("init", "reset"):
            last.update({i: entry.get("at", "") for i in entry.get("items", [])})
    drift = [c for c in changes if c["kind"] != "proposal"]
    rows = []
    for item in sorted(set(ledger["approved"]) | {c["item"] for c in drift}):
        mine = [c for c in drift if c["item"] == item]
        state = mine[0]["kind"] if mine and mine[0]["kind"] in ("new", "removed") else ("changed" if mine else "approved")
        rows.append({"item": item, "state": state, "pending": len(mine), "approved_at": last.get(item, "")})
    return {"enabled": True, "root": str(root), "problem": problem, "owner_key": ledger["owner"]["pubkey"],
            "items": rows, "pending": len(changes), "proposals": [c for c in changes if c["kind"] == "proposal"]}


def _print_changes(changes: list[dict]) -> None:
    for c in changes:
        where = "memory convention " + c["item"][len(MEMORY_PREFIX):] if c["item"].startswith(MEMORY_PREFIX) else c["item"]
        extra = f"  by {c['by']}: {c['reason']}" if c["kind"] == "proposal" else ""
        print(f"[{c['id']}] {_clean(where)}  {c['kind']}  +{c['added']} -{c['removed']}{extra}")
        for line in c["diff"][:DIFF_LINES_SHOWN]:
            print("    " + line)
        if len(c["diff"]) > DIFF_LINES_SHOWN:
            print(f"    ... {len(c['diff']) - DIFF_LINES_SHOWN} more lines")


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _ask_new_passphrase() -> str:
    first = getpass.getpass("New owner passphrase (8+ characters; never give it to an AI agent): ")
    if getpass.getpass("Repeat the passphrase: ") != first:
        raise RuleError("the two passphrases differ")
    return first


def _warn_untrusted(root: Path, ledger: dict) -> None:
    warning = _trust_warning(root, ledger)
    if warning:
        print(f"WARNING: {LEDGER_REL} cannot be trusted: {warning.rstrip('.')}. "
              f"Restore it with `git checkout HEAD -- {STORE_REL}`.")


def _cmd_status(root: Path, as_json: bool) -> int:
    res = status(root)
    if as_json:
        print(json.dumps(res, indent=2))
        return 0
    if not res["enabled"]:
        print(f"Rule approval is off in {root}. Rule files agents load here ({len(res['rule_files'])}):")
        for item in res["rule_files"]:
            print(f"  {_clean(item)}")
        print("The owner turns approval on with `deepmodebot rules init`.")
        return 0
    if res["problem"]:
        print(f"WARNING: {LEDGER_REL} cannot be trusted: {_clean(res['problem']).rstrip('.')}. "
              f"Restore it with `git checkout HEAD -- {STORE_REL}`.")
        if not res["items"]:
            return 1
    approved = sum(1 for r in res["items"] if r["state"] == "approved")
    print(f"Rule ledger for {root}: {approved} approved, {res['pending']} pending (owner key {res['owner_key'][:16]})")
    for row in res["items"]:
        note = f"  {row['pending']} unapproved change(s)" if row["state"] == "changed" else ""
        when = f"  approved {row['approved_at']}" if row["state"] == "approved" and row["approved_at"] else ""
        print(f"  {row['state'].upper():9} {_clean(row['item'])}{note}{when}")
    for prop in res["proposals"]:
        print(f"  PROPOSAL  {_clean(prop['item'])}  [{prop['id']}] by {prop['by']}: {prop['reason']}")
    if res["pending"]:
        print("Review with `deepmodebot rules review`; decide with `deepmodebot rules approve <id>` or `reject <id>`.")
    return 0


def _cmd_review(root: Path, as_json: bool) -> int:
    ledger = _require_ledger(root)
    changes = pending_changes(root, Source(root), ledger)
    if as_json:
        print(json.dumps(changes, indent=2))
        return 0
    _warn_untrusted(root, ledger)
    if not changes:
        print("No pending rule changes.")
    else:
        _print_changes(changes)
        print(f"{len(changes)} pending. Owner: `deepmodebot rules approve <id> ...` or `deepmodebot rules reject <id> ...` "
              "(`--all` for everything).")
    return 0


def _cmd_log(root: Path, as_json: bool) -> int:
    ledger = _require_ledger(root)
    history = ledger["history"]
    if as_json:
        print(json.dumps(history, indent=2))
        return 0
    _warn_untrusted(root, ledger)
    for e in history:
        if e.get("action") in ("init", "reset"):
            print(f"{e.get('at')}  {e['action']:7} baseline of {len(e.get('items', []))} rule(s)")
        elif e.get("action") == "rotate":
            print(f"{e.get('at')}  rotate  owner key {str(e.get('from'))[:16]} -> {str(e.get('to'))[:16]}")
        else:
            by = f" (proposed by {e.get('by', 'agent')})" if e.get("kind") == "proposal" else ""
            print(_clean(f"{e.get('at')}  {e.get('action', '?'):7} {e.get('item')} [{e.get('change')}] {e.get('kind')} "
                         f"+{e.get('added')} -{e.get('removed')} {e.get('summary', '')}{by}"))
    return 0


def _cmd_decide(root: Path, ids: list[str], select_all: bool, approve: bool, yes: bool) -> int:
    ledger = _require_ledger(root)
    changes = pending_changes(root, Source(root), ledger)
    if select_all and not changes:
        print("No pending rule changes.")
        return 0
    chosen = _select(changes, ids, select_all)
    _warn_untrusted(root, ledger)
    _print_changes(chosen)
    verb = "Approve" if approve else "Reject"
    if not _confirm(f"{verb} these {len(chosen)} change(s)?", yes):
        print("Nothing changed.")
        return 1
    done = decide(root, [c["id"] for c in chosen], approve=approve, passphrase=getpass.getpass("Owner passphrase: "))
    if approve:
        print(f"Approved {len(done)} change(s). Commit {STORE_REL}/ with the rule files to record it.")
    else:
        print(f"Rejected {len(done)} change(s); the rules are back to their approved text. Commit {STORE_REL}/ to record it.")
    return 0


def _cmd_init(root: Path, yes: bool, reset: bool) -> int:
    src = Source(root)
    items = [i for i, d in _state(root, src, {}, memory=True)[0].items() if d is not None]
    print(f"Turning on rule approval in {root}. These {len(items)} rules become the approved baseline:")
    for item in sorted(items):
        print(f"  {_clean(item)}")
    if not _confirm("Approve all of them exactly as they are now?", yes):
        print("Nothing changed. Fix or remove unwanted rules first, then run init again.")
        return 1
    init_ledger(root, _ask_new_passphrase(), reset=reset)
    print(f"Rule approval is on. Commit {STORE_REL}/ so every clone and CI run enforces it.")
    return 0


def _cmd_rotate(root: Path) -> int:
    old = getpass.getpass("Current owner passphrase: ")
    _owner_seed(_require_ledger(root), old)
    rotate_key(root, old, _ask_new_passphrase())
    print(f"Owner key rotated. Commit {STORE_REL}/ to record it.")
    return 0


def _cmd_check(root: Path, staged: bool, base: str | None, as_json: bool) -> int:
    res = check(root, staged=staged, base=base)
    if as_json:
        print(json.dumps(res, indent=2))
    elif res["enabled"]:
        print(f"rule-gate [{'OK' if res['ok'] else 'BLOCKED'}]: {len(res['findings'])} finding(s)")
        for f in res["findings"]:
            print(f"  {f['file']} [{f['severity']}:{f['rule']}] {f['message']} -> {f['fix']}")
    else:
        print("rule-gate [OFF]: no owner rule ledger in this repo")
    return 0 if res["ok"] else 1


def _cmd_guard() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        req = {}
    req = req if isinstance(req, dict) else {}
    cwd = req.get("cwd") or os.getcwd()
    paths = [p for p in req.get("paths") or [] if isinstance(p, str)]
    reason = guard(cwd, paths=paths, command=str(req.get("command") or ""))
    print(json.dumps({"block": bool(reason), "reason": reason or ""}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Owner-approved agent rules: track, review and sign off every rule AI agents load.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, text in (("status", "List tracked rules and what waits for approval."),
                       ("review", "Show every pending rule change with its id and diff."),
                       ("log", "Show the signed decision history.")):
        sp = sub.add_parser(name, help=text)
        sp.add_argument("--root", default=".")
        sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("propose", help="Agents: park a new version of a rule file for the owner.")
    sp.add_argument("--root", default=".")
    sp.add_argument("--item", required=True, help="Repo-relative rule file, e.g. AGENTS.md.")
    sp.add_argument("--file", required=True, help="Draft holding the full new file text.")
    sp.add_argument("--reason", required=True)
    sp.add_argument("--by", default="agent", help="Who proposes (harness or agent name).")
    sp = sub.add_parser("check", help="Gate: exit 1 on unapproved rules or a tampered ledger.")
    sp.add_argument("--root", default=".")
    sp.add_argument("--staged", action="store_true", help="Check the git index (pre-commit).")
    sp.add_argument("--base", default=None,
                    help="Commit whose ledger this one must extend (default: HEAD and the merge-base with origin's default branch).")
    sp.add_argument("--json", action="store_true")
    sub.add_parser("guard", help="Hook helper: JSON request on stdin, JSON verdict on stdout.")
    sp = sub.add_parser("init", help="Owner: turn approval on; current rules become the signed baseline.")
    sp.add_argument("--root", default=".")
    sp.add_argument("--yes", action="store_true")
    sp.add_argument("--reset", action="store_true", help="Replace a ledger whose passphrase is lost (history kept).")
    for name in ("approve", "reject"):
        sp = sub.add_parser(name, help=f"Owner: {name} pending changes by id.")
        sp.add_argument("ids", nargs="*")
        sp.add_argument("--all", action="store_true")
        sp.add_argument("--root", default=".")
        sp.add_argument("--yes", action="store_true")
    sp = sub.add_parser("rotate", help="Owner: change the passphrase (signed by the old key).")
    sp.add_argument("--root", default=".")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "guard":
        return _cmd_guard()
    root = project_root(args.root)
    try:
        if args.cmd in ("status", "review", "log"):
            return {"status": _cmd_status, "review": _cmd_review, "log": _cmd_log}[args.cmd](root, args.json)
        if args.cmd == "propose":
            prop = propose(root, args.item, Path(args.file).read_bytes(), args.reason, args.by)
            print(f"Proposed [{prop['id']}] for {prop['item']}. The rule file is unchanged until the owner runs "
                  f"`deepmodebot rules review` and `deepmodebot rules approve {prop['id']}`.")
            return 0
        if args.cmd == "check":
            return _cmd_check(root, args.staged, args.base, args.json)
        if args.cmd == "init":
            return _cmd_init(root, args.yes, args.reset)
        if args.cmd in ("approve", "reject"):
            return _cmd_decide(root, args.ids, args.all, args.cmd == "approve", args.yes)
        return _cmd_rotate(root)
    except (RuleError, OSError) as exc:
        print(f"rules: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
