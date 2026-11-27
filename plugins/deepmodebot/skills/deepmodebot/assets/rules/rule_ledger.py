#!/usr/bin/env python3
"""Owner-approved agent rules: track every rule an AI agent loads and block the ones the owner never approved.

Rules are the instruction and permission files coding agents load (AGENTS.md, CLAUDE.md, .cursor/rules/, skills,
agent settings; the full list is rule-paths.json) plus `convention` records in the deepmodebot project memory.
.deepmodebot/rules/ledger.json pins the approved SHA-256 of each rule, .deepmodebot/rules/approved/<sha256> keeps the
approved bytes, and the history logs every decision. The ledger is signed with an Ed25519 key derived from a passphrase
only the owner knows: agents can read, review and propose, but approving, rejecting and re-keying need the passphrase.

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
import getpass
import glob
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import sqlite3
import stat
import subprocess
import sys
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
MEMORY_DB_REL = ".scratch/deepmode-memory.db"
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

PUNCT = frozenset("();<>|&")
WRAPPERS = frozenset({"sudo", "doas", "env", "command", "builtin", "exec", "nohup", "time", "nice", "stdbuf", "xargs"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
INTERPRETERS = frozenset({"python", "python3", "py", "node", "bun", "deno", "ruby", "perl", "php", "pwsh", "powershell"})
DELETERS = frozenset({"rm", "unlink", "shred", "truncate", "rmdir", "del", "erase", "remove-item"})
MOVERS = frozenset({"mv", "move", "ren", "rename", "move-item"})
COPIERS = frozenset({"cp", "ln", "install", "rsync", "scp", "copy", "copy-item"})
IN_PLACE = frozenset({"sed", "perl", "ruby"})
IN_PLACE_FLAG_RE = re.compile(r"--in-place(?:=.*)?|-[A-Za-z]*i\S*")
FIND_ACTIONS = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir"})
CODE_FLAGS = frozenset({"-c", "-e", "--eval", "-p", "--print", "-command"})
HEREDOC_RE = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
WRITE_CODE_RE = re.compile(
    r"write|unlink|remove|rename|rmtree|rmSync|rmdir|truncate|copy|\bmove\b|Set-Content|Out-File|Add-Content"
    r"|open\s*\([^)]*,\s*['\"][rbt]*[wax+]|mode\s*=\s*['\"][rbt]*[wax+]"
)
CODE_WORD_RE = re.compile(r"[\w./\\~-]+")
FALLBACK_WORD_RE = re.compile(r"[^\s'\"`<>|;&()]+")
FALLBACK_WRITE_RE = re.compile(r">|\b(?:rm|mv|cp|tee|sed|perl|truncate|ln|install|rsync|dd|unlink|shred)\b")


class RuleError(Exception):
    """A refused ledger action; the message is shown to the user as is."""


def _load_spec() -> tuple[frozenset, tuple, frozenset]:
    data = json.loads((HERE / "rule-paths.json").read_text(encoding="utf-8"))
    names = frozenset(n.lower() for n in data["names"])
    dirs = tuple("/" + d.lower().strip("/") + "/" for d in data["dirs"])
    files = frozenset(f.lower() for f in data["files"])
    return names, dirs, files


RULE_NAMES, RULE_DIRS, RULE_FILES = _load_spec()


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


def _main_checkout(root: Path) -> Path:
    common = _git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and Path(common).name == ".git":
        return Path(common).parent
    return root


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
            return self._git_list("ls-files", "-z", "--cached")
        if self.mode == "ref":
            return self._git_list("ls-tree", "-r", "-z", "--name-only", self.ref)
        listed = self._git_list("ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if listed is None:
            listed = []
            for folder, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_SEGMENTS]
                base = Path(folder).relative_to(self.root)
                listed += [(base / n).as_posix() for n in filenames]
        listed += [n for n in os.listdir(self.root) if n.lower() in RULE_NAMES]
        return sorted({p for p in listed if os.path.lexists(self.root / p)})

    def _git_list(self, *args: str) -> list[str] | None:
        out = _git(self.root, *args)
        if out is None or out.returncode != 0:
            return [] if self.mode != "work" else None
        return [p for p in out.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def rule_files(src: Source) -> list[str]:
    return sorted(p for p in src.paths() if is_rule_path(p))


def memory_rules(root: Path) -> dict[str, bytes]:
    """Unexpired `convention` records in the project memory, keyed `memory:<key>`."""
    db = _main_checkout(root) / MEMORY_DB_REL
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
            or not isinstance(owner.get("iterations"), int) or not 0 < owner["iterations"] <= MAX_KDF_ITERATIONS):
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


def _require_ledger(root: Path) -> dict:
    raw = Source(root).read(LEDGER_REL)
    if raw is None:
        raise RuleError("rule approval is off in this repo; the owner turns it on with `deepmodebot rules init`")
    ledger = parse_ledger(raw)
    if not signature_ok(ledger):
        raise RuleError(f"{LEDGER_REL} does not carry a valid owner signature. "
                        f"Restore it from git (`git checkout HEAD -- {STORE_REL}`) before changing rules.")
    return ledger


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


def trusted_approvals(root) -> dict | None:
    """Approved item hashes from a signed ledger that extends the committed one; None when approval is off.

    A forged, rolled-back or re-keyed ledger yields {} so nothing it lists counts as approved.
    """
    root = project_root(root)
    raw = Source(root).read(LEDGER_REL)
    committed = Source(root, "ref", "HEAD").read(LEDGER_REL)
    if raw is None:
        return {} if committed is not None else None
    try:
        ledger = parse_ledger(raw)
    except RuleError:
        return {}
    if not signature_ok(ledger) or _trust_problem(ledger, committed, "HEAD"):
        return {}
    return dict(ledger["approved"])


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
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    if path.is_file():
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
    os.replace(tmp, path)


def _safe_unlink(root: Path, rel: str) -> None:
    path = _target(root, rel, final_link_ok=True)
    if os.path.lexists(path):
        path.unlink()


def _memory_write(root: Path, item: str, data: bytes | None) -> None:
    pm = _asset_module("dmb_project_memory", "memory/project_memory.py")
    key = item[len(MEMORY_PREFIX):]
    db = _main_checkout(root) / MEMORY_DB_REL
    if data is None:
        if db.is_file():
            with pm.connect_db(db) as conn:
                conn.execute("DELETE FROM memories WHERE key = ? AND kind = 'convention'", (key,))
                conn.commit()
        return
    text = data.decode("utf-8")
    if db.is_file():
        with pm.connect_db(db) as conn:
            if conn.execute("SELECT 1 FROM memories WHERE key = ?", (key,)).fetchone():
                conn.execute(
                    "UPDATE memories SET kind = 'convention', content = ?, content_hash = ?, updated_at = ? WHERE key = ?",
                    (text, pm.content_digest("convention", text), time.time(), key),
                )
                conn.commit()
                return
    pm.put_memory(root, key=key, kind="convention", content=text, priority=0)


def _write_item(root: Path, item: str, data: bytes | None) -> None:
    if item.startswith(MEMORY_PREFIX):
        _memory_write(root, item, data)
    elif data is None:
        _safe_unlink(root, item)
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


def _change(item: str, kind: str, old: list[str], new: list[str], seen: dict, **extra) -> dict:
    key = (item, "".join(old), "".join(new))
    nth = seen.get(key, 0)
    seen[key] = nth + 1
    cid = _sha("\0".join((*key, str(nth))).encode("utf-8", "surrogateescape"))[:8]
    added = [line.rstrip("\r\n") for line in new]
    removed = [line.rstrip("\r\n") for line in old]
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
    return [_change(item, "changed", a[i1:i2], b[j1:j2], seen, block=idx)
            for idx, (tag, i1, i2, j1, j2) in enumerate(ops) if tag != "equal"]


def load_proposals(root: Path) -> list[dict]:
    folder = root / PROPOSALS_REL
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
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
                         reason=str(prop.get("reason") or ""), by=str(prop.get("by") or "agent"), file=prop["file"],
                         base_sha256=prop.get("base_sha256"), content=prop["content"])
        change["id"] = str(prop.get("id") or change["id"])
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


def _approve_bytes(root: Path, ledger: dict, item: str, data: bytes) -> None:
    sha = _sha(data)
    blob = f"{APPROVED_REL}/{sha}"
    existing = root / blob
    if not (existing.is_file() and _sha(existing.read_bytes()) == sha):
        _safe_write(root, blob, data)
    ledger["approved"][item] = sha


def _save(root: Path, ledger: dict, seed: bytes) -> None:
    ledger["version"] = LEDGER_VERSION
    ledger["signature"] = sign(seed, _canonical(ledger))
    _safe_write(root, LEDGER_REL, (json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    keep = set(ledger["approved"].values())
    folder = root / APPROVED_REL
    for blob in folder.iterdir() if folder.is_dir() else []:
        if blob.is_file() and blob.name not in keep:
            blob.unlink()


def _history(at: str, action: str, change: dict) -> dict:
    entry = {"at": at, "action": action, "item": change["item"], "change": change["id"], "kind": change["kind"],
             "added": change["added"], "removed": change["removed"], "summary": change["summary"]}
    if change["kind"] == "proposal":
        entry.update(reason=change["reason"], by=change["by"])
    return entry


def _decide_item(root: Path, ledger: dict, item: str, group: list[dict], current: dict, kept: dict, approve: bool) -> None:
    drift = [c for c in group if c["kind"] != "proposal"]
    if drift:
        new, old = current.get(item), kept.get(item)
        blocks = {c["block"] for c in drift if "block" in c}
        if blocks:
            a, b, ops = _opcodes(_text(old), _text(new))
            changed = {i for i, op in enumerate(ops) if op[0] != "equal"}
            if approve:
                _approve_bytes(root, ledger, item, _merge(a, b, ops, blocks))
            else:
                _write_item(root, item, _merge(a, b, ops, changed - blocks))
        elif approve:
            if new is None:
                ledger["approved"].pop(item, None)
            else:
                _approve_bytes(root, ledger, item, new)
        else:
            if item in ledger["approved"] and old is None:
                raise RuleError(f"the approved copy of {item} is missing, so it cannot be restored")
            _write_item(root, item, old)
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
    owner, seed = _new_owner(passphrase)
    ledger = {"version": LEDGER_VERSION, "owner": owner, "approved": {}, "history": history}
    current, _ = _state(root, src, {}, memory=True)
    for item, data in sorted(current.items()):
        if data is not None:
            _approve_bytes(root, ledger, item, data)
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
            "reason": reason.strip(), "by": by.strip() or "agent", "proposed_at": _now()}
    _safe_write(root, f"{PROPOSALS_REL}/{pid}.json", (json.dumps(prop, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return prop


def _finding(severity: str, rule: str, file: str, message: str, fix: str) -> dict:
    return {"severity": severity, "rule": rule, "file": file, "line": 1, "message": message, "fix": fix}


def check(root: Path, *, staged: bool = False, base: str = "HEAD") -> dict:
    """Gate: fail on unapproved rules, a forged or rolled-back ledger, or a swapped owner key."""
    root = Path(root)
    src = Source(root, "index" if staged else "work")
    findings: list[dict] = []
    base_ok = bool(base) and _git_text(root, "rev-parse", "--verify", "--quiet", base + "^{commit}") is not None
    base_raw = Source(root, "ref", base).read(LEDGER_REL) if base_ok else None
    raw = src.read(LEDGER_REL)

    def result(enabled: bool) -> dict:
        blocking = [f for f in findings if f["severity"] in ("P0", "P1")]
        return {"enabled": enabled, "ok": not blocking, "root": str(root), "findings": findings}

    if raw is None:
        if base_raw is not None:
            findings.append(_finding("P0", "rules-ledger-removed", LEDGER_REL,
                                     f"The owner-signed rule ledger exists at {base} but is gone now.",
                                     f"Restore it: `git checkout {base} -- {STORE_REL}`."))
        return result(base_raw is not None)
    restore = f"Restore it: `git checkout {base or 'HEAD'} -- {STORE_REL}`."
    try:
        ledger = parse_ledger(raw)
    except RuleError as exc:
        findings.append(_finding("P0", "rules-ledger-forged", LEDGER_REL, str(exc), restore))
        return result(True)
    if not signature_ok(ledger):
        findings.append(_finding("P0", "rules-ledger-forged", LEDGER_REL,
                                 "The rule ledger was edited without the owner's passphrase (bad signature).", restore))
        return result(True)
    problem = _trust_problem(ledger, base_raw, base)
    if problem:
        findings.append(_finding("P0", problem[0], LEDGER_REL, problem[1],
                                 f"{restore} Owners change the passphrase with `deepmodebot rules rotate`."))
    approved = {i: s for i, s in ledger["approved"].items() if not (staged and i.startswith(MEMORY_PREFIX))}
    _, kept = _state(root, src, approved, memory=False)
    for item in sorted(i for i in approved if not i.startswith(MEMORY_PREFIX) and kept.get(i) is None):
        findings.append(_finding("P0", "rules-snapshot-missing", f"{APPROVED_REL}/{approved[item]}",
                                 f"The approved copy of `{item}` is missing or altered.", restore))
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
    if os.path.lexists(Path(root) / LEDGER_REL):
        return True
    out = _git(Path(root), "cat-file", "-e", "HEAD:" + LEDGER_REL)
    return out is not None and out.returncode == 0


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


def _locate(cwd: Path, raw: str) -> tuple[Path, str] | None:
    """(repo root, repo-relative path) for a path the agent named; the last component stays unresolved."""
    p = os.path.expanduser(str(raw).strip())
    if not p:
        return None
    joined = (p if os.path.isabs(p) else os.path.join(str(cwd), p)).rstrip("/\\") or os.sep
    full = os.path.join(os.path.realpath(os.path.dirname(joined)), os.path.basename(joined))
    root = _owning_root(full)
    if root is None:
        return None
    rel = os.path.relpath(full, str(root))
    return root, ("" if rel == "." else rel.replace(os.sep, "/"))


def _rule_reason(rel: str) -> str:
    return (f"deepmodebot rule approval: `{rel}` is an agent rule file, and only the project owner approves rule changes. "
            f"Write your draft under .scratch/, run `\"{sys.executable or 'python3'}\" -B \"{SCRIPT}\" propose --item {rel} --file <draft> "
            f"--reason \"<why>\"`, and tell the owner to review it with `deepmodebot rules review`.")


STORE_REASON = (f"deepmodebot rule approval: {STORE_REL}/ holds the owner-signed rule ledger; agents may not write, "
                "move or delete anything in it.")


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


def _token_reason(cwd: Path, token: str, *, removes: bool = False) -> str | None:
    """Deny reason when writing (or, with removes, deleting/moving) `token` would change a rule in a ledger repo."""
    if any(ch in token for ch in "*?["):
        for match in glob.glob(os.path.join(str(cwd), os.path.expanduser(token)))[:500]:
            reason = _token_reason(cwd, match, removes=removes)
            if reason:
                return reason
        return None
    loc = _locate(cwd, token)
    if loc is None:
        return None
    root, rel = loc
    reason = _path_reason(rel) if rel else None
    if reason is None and removes and (root / rel).is_dir() and ledger_enabled(root) and _dir_has_rules(root, rel):
        return STORE_REASON if (STORE_REL + "/").startswith(rel.lower().strip("/") + "/") else _rule_reason(rel or ".")
    return reason if reason and ledger_enabled(root) else None


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


def _tokenize(line: str) -> list[str] | None:
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
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


def _simple_reason(cwd: Path, toks: list[str]) -> str | None:
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
    while words and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or _base(words[0]) in WRAPPERS):
        words.pop(0)
        while words and words[0].startswith("-"):
            words.pop(0)
    owner = _owner_command(words)
    if owner:
        return _owner_reason(owner)
    for target in targets:
        reason = _token_reason(cwd, target)
        if reason:
            return reason
    if not words:
        return None
    cmd, args = _base(words[0]), words[1:]
    plain = [a for a in args if not a.startswith("-")]

    def first(tokens, removes=False):
        return next(filter(None, (_token_reason(cwd, t, removes=removes) for t in tokens)), None)

    if cmd == "git" and plain[:1] in (["rm"], ["mv"]):
        return first(plain[1:], removes=True)
    if cmd in DELETERS or cmd in MOVERS:
        return first(plain, removes=True)
    if cmd in ("tee", "sd") or (cmd in IN_PLACE and any(IN_PLACE_FLAG_RE.fullmatch(a) for a in args)):
        return first(plain)
    if cmd in COPIERS and plain:
        dest = args[args.index("-t") + 1] if "-t" in args[:-1] else plain[-1]
        sources = [a for a in plain if a != dest]
        return first([dest] + [os.path.join(dest, os.path.basename(s.rstrip("/\\"))) for s in sources])
    if cmd == "dd":
        return first(a[3:] for a in args if a.startswith("of="))
    if cmd == "find" and FIND_ACTIONS & set(args):
        return first((a for a in args if not a.startswith("-")), removes=True)
    if cmd in SHELLS or cmd == "eval":
        code = args[args.index("-c") + 1] if "-c" in args[:-1] else (" ".join(args) if cmd == "eval" else "")
        return _shell_reason(cwd, code) if code else None
    if cmd in INTERPRETERS:
        flags = [j for j, a in enumerate(args[:-1]) if a.lower() in CODE_FLAGS]
        return next(filter(None, (_code_reason(cwd, args[j + 1]) for j in flags)), None)
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


def _shell_reason(cwd: Path, command: str) -> str | None:
    lines, bodies = _split_heredocs(command)
    for line in lines:
        tokens = _tokenize(line)
        if tokens is None:
            if FALLBACK_WRITE_RE.search(line):
                reason = next(filter(None, (_token_reason(cwd, w) for w in FALLBACK_WORD_RE.findall(line))), None)
                if reason:
                    return reason
            continue
        for simple in _split_simple(tokens):
            reason = _simple_reason(cwd, simple)
            if reason:
                return reason
    for owner_line, body in bodies:
        names = {_base(t) for t in _tokenize(owner_line) or []}
        if names & SHELLS:
            reason = _shell_reason(cwd, body)
        elif names & INTERPRETERS:
            reason = _code_reason(cwd, body)
        else:
            reason = None
        if reason:
            return reason
    return None


def guard(cwd, *, paths=(), command: str = "") -> str | None:
    """Hook verdict: why to deny a tool call that writes a rule file or the ledger in a repo with rule approval on,
    or that runs an owner-only rule command anywhere. None allows it."""
    cwd = Path(cwd).expanduser().resolve()
    for raw in paths:
        reason = _token_reason(cwd, raw) if isinstance(raw, str) else None
        if reason:
            return reason
    return _shell_reason(cwd, command) if command else None


def status(root: Path) -> dict:
    root = Path(root)
    src = Source(root)
    raw = src.read(LEDGER_REL)
    committed = Source(root, "ref", "HEAD").read(LEDGER_REL)
    if raw is None:
        if committed is None:
            return {"enabled": False, "root": str(root), "rule_files": rule_files(src)}
        return {"enabled": True, "root": str(root), "problem": "the committed rule ledger was deleted from the working tree",
                "items": [], "pending": 0, "proposals": []}
    ledger = parse_ledger(raw)
    if not signature_ok(ledger):
        return {"enabled": True, "root": str(root), "items": [], "pending": 0, "proposals": [],
                "problem": "the ledger was edited without the owner passphrase (bad signature)"}
    trust = _trust_problem(ledger, committed, "HEAD")
    problem = trust[1] if trust else ""
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
        print(f"[{c['id']}] {where}  {c['kind']}  +{c['added']} -{c['removed']}{extra}")
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


def _cmd_status(root: Path, as_json: bool) -> int:
    res = status(root)
    if as_json:
        print(json.dumps(res, indent=2))
        return 0
    if not res["enabled"]:
        print(f"Rule approval is off in {root}. Rule files agents load here ({len(res['rule_files'])}):")
        for item in res["rule_files"]:
            print(f"  {item}")
        print("The owner turns approval on with `deepmodebot rules init`.")
        return 0
    if res["problem"]:
        print(f"WARNING: {LEDGER_REL} cannot be trusted: {res['problem'].rstrip('.')}. "
              f"Restore it with `git checkout HEAD -- {STORE_REL}`.")
        if not res["items"]:
            return 1
    approved = sum(1 for r in res["items"] if r["state"] == "approved")
    print(f"Rule ledger for {root}: {approved} approved, {res['pending']} pending (owner key {res['owner_key'][:16]})")
    for row in res["items"]:
        note = f"  {row['pending']} unapproved change(s)" if row["state"] == "changed" else ""
        when = f"  approved {row['approved_at']}" if row["state"] == "approved" and row["approved_at"] else ""
        print(f"  {row['state'].upper():9} {row['item']}{note}{when}")
    for prop in res["proposals"]:
        print(f"  PROPOSAL  {prop['item']}  [{prop['id']}] by {prop['by']}: {prop['reason']}")
    if res["pending"]:
        print("Review with `deepmodebot rules review`; decide with `deepmodebot rules approve <id>` or `reject <id>`.")
    return 0


def _cmd_review(root: Path, as_json: bool) -> int:
    changes = pending_changes(root, Source(root), _require_ledger(root))
    if as_json:
        print(json.dumps(changes, indent=2))
    elif not changes:
        print("No pending rule changes: every rule agents load here is owner-approved.")
    else:
        _print_changes(changes)
        print(f"{len(changes)} pending. Owner: `deepmodebot rules approve <id> ...` or `deepmodebot rules reject <id> ...` "
              "(`--all` for everything).")
    return 0


def _cmd_log(root: Path, as_json: bool) -> int:
    history = _require_ledger(root)["history"]
    if as_json:
        print(json.dumps(history, indent=2))
        return 0
    for e in history:
        if e.get("action") in ("init", "reset"):
            print(f"{e.get('at')}  {e['action']:7} baseline of {len(e.get('items', []))} rule(s)")
        elif e.get("action") == "rotate":
            print(f"{e.get('at')}  rotate  owner key {str(e.get('from'))[:16]} -> {str(e.get('to'))[:16]}")
        else:
            by = f" (proposed by {e.get('by', 'agent')})" if e.get("kind") == "proposal" else ""
            print(f"{e.get('at')}  {e.get('action', '?'):7} {e.get('item')} [{e.get('change')}] {e.get('kind')} "
                  f"+{e.get('added')} -{e.get('removed')} {e.get('summary', '')}{by}")
    return 0


def _cmd_decide(root: Path, ids: list[str], select_all: bool, approve: bool, yes: bool) -> int:
    ledger = _require_ledger(root)
    chosen = _select(pending_changes(root, Source(root), ledger), ids, select_all)
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
        print(f"  {item}")
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


def _cmd_check(root: Path, staged: bool, base: str, as_json: bool) -> int:
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
    sp.add_argument("--base", default="HEAD", help="Commit whose ledger this one must extend (default HEAD).")
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
