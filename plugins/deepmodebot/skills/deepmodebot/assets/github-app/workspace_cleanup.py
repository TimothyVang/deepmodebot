"""Conservative disposal of explicitly recorded, durably completed bot workspaces.

Callers hold the bot process lock and finish all agent turns before marking a job
ready. Inspection fails closed; only newly owned clones can lose Git metadata.
These private directories must have no external users. The bot lock, durable
session receipts and alias rejection serialize supported writers; inspection and
deletion are not atomic against arbitrary manual filesystem/Git writers.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


COMPLETED = {"pr": frozenset({"reviewed", "merged", "closed", "merged-reverting"}),
             "issue": frozenset({"discussed", "implemented"})}


def completed(kind, item):
    return (item.get("status") in COMPLETED.get(kind, ())
            and not item.get("afterMerge") and not item.get("pendingComments")
            and not item.get("workspaceIncomplete") and not item.get("workspaceActive"))


def _baseline_only(item):
    return (set(item) == {"heads"} and bool(item["heads"])
            and all(status == "before-install" for status in item["heads"].values()))


def repository_alias(repo, repositories):
    storage = repo.replace("/", "-").casefold()
    return next((other for other in repositories
                 if other != repo and other.replace("/", "-").casefold() == storage), None)


def _git(cwd, *args):
    routing = {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
               "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE",
               "GIT_REPLACE_REF_BASE", "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
               "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_IMPLICIT_WORK_TREE"}
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in routing and not key.upper().startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    proc = subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="strict", timeout=120, env=env,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode:
        raise RuntimeError(f"git {args[0]} inspection/removal failed: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def _plain(path):
    """Reject links and Windows reparse points, including every existing ancestor."""
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError(f"linked/reparse path: {part}")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _records(clone):
    records = []
    for block in _git(clone, "worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = block.split("\0")
        if fields[0].startswith("worktree "):
            records.append((Path(fields[0][9:]), fields[1:]))
    if not records:
        raise RuntimeError("Git returned no worktree membership records")
    return records


def record_worktree(path, item):
    """Record a newly created checkout before agents can generate disposable caches."""
    info = path.stat()
    git_info = (path / ".git").stat()
    item.setdefault("workspaceOwnership", {})[path.name] = {
        "identity": [info.st_dev, info.st_ino, git_info.st_dev, git_info.st_ino],
        "initialIgnored": _git(path, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").split("\0")[:-1]}


def _cache_file(name):
    parts = name.split("/")
    if parts[-1] == ".env" or parts[-1].startswith(".env."):
        return False
    return (any(part in {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
                for part in parts[:-1])
            or any(parts[i:i + 2] == [".scratch", "tmp"] for i in range(len(parts) - 2)))


def _clean_worktree(path, ownership):
    if _git(path, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("modified or untracked files remain")
    ignored = _git(path, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").split("\0")[:-1]
    if not ignored and not ownership:
        return
    info, git_info = path.stat(), (path / ".git").stat()
    identity = [info.st_dev, info.st_ino, git_info.st_dev, git_info.st_ino]
    if not ownership or ownership.get("identity") != identity:
        raise RuntimeError("ignored files remain without a matching creation-ownership receipt")
    if not ignored:
        return
    initial = ownership.get("initialIgnored")
    if not isinstance(initial, list) or any(name in initial or not _cache_file(name) for name in ignored):
        raise RuntimeError("ignored non-cache or original files remain")


def _job_refs(kind, number, item):
    refs = item.get("workspaceRefs", {})
    if not isinstance(refs, dict):
        raise RuntimeError("invalid recorded PR ref manifest")
    for local, remote in refs.items():
        if (kind != "pr" or not isinstance(local, str)
                or not re.fullmatch(rf"refs/(?!heads/|remotes/|tags/)[A-Za-z0-9_./-]+/pr/{int(number)}", local)
                or remote != f"refs/pull/{int(number)}/head"):
            raise RuntimeError("recorded ref does not belong to this PR")
    return refs


def _safe_tree(clone, root, path, ownership, pr_refs):
    _plain(clone)
    _plain(clone / ".git")
    _plain(path)
    if path.parent != root or not path.is_dir():
        raise RuntimeError("not an immediate job directory inside this repository's worktree root")
    if not (clone / ".git").is_dir():
        raise RuntimeError("shared clone is itself a linked worktree")
    members = [fields for p, fields in _records(clone) if _norm(p) == _norm(path)]
    if len(members) != 1 or any(f.startswith(("locked", "prunable")) for f in members[0]):
        raise RuntimeError("not a unique unlocked, non-prunable member of the shared clone")
    if _norm(_git(path, "rev-parse", "--show-toplevel").strip()) != _norm(path):
        raise RuntimeError("Git inspection resolves to a different working directory")
    common = Path(_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    gitdir = Path(_git(path, "rev-parse", "--absolute-git-dir").strip())
    if _norm(common) != _norm(clone / ".git") or _norm(gitdir.parent) != _norm(common / "worktrees"):
        raise RuntimeError("worktree Git metadata belongs to another repository")
    _plain(gitdir)
    _plain(path / ".git")
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            _plain(Path(directory) / name)
    for directory, dirs, files in os.walk(common, followlinks=False):
        for name in dirs + files:
            entry = Path(directory) / name
            _plain(entry)
            if name.endswith(".lock") or name in {"MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD",
                                                  "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer"}:
                raise RuntimeError(f"Git operation/lock present: {entry}")
    _clean_worktree(path, ownership)
    remote_commits, _ = _remote_commits(clone, pr_refs.values())
    if _git(path, "rev-list", "--max-count=1", "--reflog", "HEAD", "--not", *remote_commits).strip():
        raise RuntimeError("HEAD or reflog contains commits not recoverable from current origin refs")


def _remote_commits(clone, pull_refs=()):
    # Remote-tracking refs alone can be stale after a remote branch was deleted.
    advertised = _git(clone, "ls-remote", "origin", "refs/heads/*", "refs/tags/*", *sorted(set(pull_refs)))
    remote_refs = {line.split()[1]: line.split()[0] for line in advertised.splitlines() if line.strip()}
    remote_commits = []
    for oid in sorted({line.split()[0] for line in advertised.splitlines() if line.strip()}):
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
            raise RuntimeError("invalid remote object id")
        try:
            commit = _git(clone, "rev-parse", "--verify", f"{oid}^{{commit}}").strip()
        except RuntimeError:
            continue  # An advertised object not fetched locally cannot prove ancestry.
        remote_commits.append(commit)
    if not remote_commits:
        raise RuntimeError("no locally inspectable commits advertised by origin")
    return remote_commits, remote_refs


def cleanup_item(work, repo, kind, number, item, apply=False):
    """Return per-path outcomes; never let a cleanup failure change a job's result."""
    report = []
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or kind not in COMPLETED:
        return [{"action": "retain", "reason": "invalid repository or item identity"}]
    clone = Path(work).absolute() / "repos" / repo.replace("/", "-")
    root = Path(work).absolute() / "worktrees" / repo.replace("/", "-")
    if not completed(kind, item):
        return [{"action": "retain", "reason": "job is unfinished, failed, blocked or waiting"}]
    if not item.get("workspaceCleanupReady"):
        return [{"action": "retain", "reason": "no durable completed-agent/session receipt; legacy work preserved"}]
    if item.get("workspaceSessions"):
        return [{"action": "retain", "reason": "outstanding agent sessions must close before disposal"}]
    names = item.get("workspacePaths", [])
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        return [{"action": "retain", "reason": "invalid workspace ownership manifest"}]
    pattern = (rf"pr{int(number)}-(?:review|author|v[1-9][0-9]*|check|revert)" if kind == "pr"
               else rf"issue{int(number)}(?:-impl)?")
    for name in dict.fromkeys(names):
        path = root / name
        row = {"path": str(path), "action": "retain"}
        try:
            if not re.fullmatch(pattern, name):
                raise RuntimeError("manifest path does not belong to this job")
            if not os.path.lexists(path):
                row.update(action="absent", reason="already removed")
            else:
                ownership = item.get("workspaceOwnership", {}).get(name)
                _safe_tree(clone, root, path, ownership, _job_refs(kind, number, item))
                if apply:
                    # No --force: Git performs its own last clean/locked check as well.
                    _git(clone, "worktree", "remove", str(path))
                row.update(action="removed" if apply else "would-remove", reason="completed and recoverable")
        except Exception as err:
            row["reason"] = str(err)
        report.append(row)
    return report


def _receipt(work, repo):
    return Path(work).absolute() / "repos" / f".{repo.replace('/', '-')}.cleanup.json"


def _metadata(clone):
    """Fingerprint metadata that normal fetch/checkout/commit must not change."""
    result = {}
    mutable = {"objects", "refs", "logs", "worktrees", "HEAD", "index", "packed-refs",
               "FETCH_HEAD", "ORIG_HEAD", "COMMIT_EDITMSG", "shallow"}
    for directory, dirs, files in os.walk(clone / ".git", followlinks=False):
        relative = Path(directory).relative_to(clone / ".git")
        if relative == Path("."):
            dirs[:] = [name for name in dirs if name not in mutable]
        for name in dirs + files:
            path = Path(directory) / name
            _plain(path)
            if relative == Path(".") and name in mutable:
                continue
            result[path.relative_to(clone / ".git").as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "directory")
    return result


def claim_clone(work, repo):
    """Only called immediately after this process successfully creates a fresh clone."""
    clone = Path(work).absolute() / "repos" / repo.replace("/", "-")
    _plain(clone / ".git")
    identity = (clone / ".git").stat()
    receipt = {"repo": repo, "clone": str(clone), "identity": [identity.st_dev, identity.st_ino],
               "metadata": _metadata(clone)}
    with _receipt(work, repo).open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True)


def cleanup_clone(work, repo, items, apply=False):
    """Dispose an owned clone only after every recorded job and linked worktree is finished."""
    row = {"action": "retain"}
    try:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise RuntimeError("invalid repository identity")
        alias = repository_alias(repo, (key.split("#", 1)[0] for key in items))
        if alias:
            raise RuntimeError(f"repository storage aliases {alias}; refusing shared-directory disposal")
        clone = Path(work).absolute() / "repos" / repo.replace("/", "-")
        row["path"] = str(clone)
        if not os.path.lexists(clone):
            return []
        receipt_path = _receipt(work, repo)
        if not receipt_path.exists():
            raise RuntimeError("preexisting clone has no creation-ownership receipt; preserving local Git metadata")
        _plain(clone / ".git")
        _plain(receipt_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        identity = (clone / ".git").stat()
        if (receipt.get("repo") != repo or receipt.get("clone") != str(clone)
                or receipt.get("identity") != [identity.st_dev, identity.st_ino]):
            raise RuntimeError("clone ownership receipt does not match this repository/directory")
        jobs = [(key.split("#", 1)[1].split(":", 1), item)
                for key, item in items.items() if key.startswith(repo + "#") and not _baseline_only(item)]
        if not jobs or any(not completed(identity[0], item) or not item.get("workspaceCleanupReady")
                           or item.get("workspaceSessions") for identity, item in jobs):
            raise RuntimeError("repository has unfinished jobs or lacks durable completed-agent receipts")
        pr_refs = {}
        for identity, item in jobs:
            if len(identity) != 2 or not identity[1].isdigit():
                raise RuntimeError("invalid job identity")
            pr_refs.update(_job_refs(identity[0], int(identity[1]), item))
        members = _records(clone)
        if (len(members) != 1 or _norm(members[0][0]) != _norm(clone)
                or any(f.startswith(("locked", "prunable")) for f in members[0][1])):
            raise RuntimeError("registered, locked or foreign worktrees still depend on this clone")
        if _norm(_git(clone, "rev-parse", "--absolute-git-dir").strip()) != _norm(clone / ".git"):
            raise RuntimeError("clone Git directory is external")
        if _norm(_git(clone, "rev-parse", "--show-toplevel").strip()) != _norm(clone):
            raise RuntimeError("clone Git inspection resolves to a different working directory")
        if receipt.get("metadata") != _metadata(clone):
            raise RuntimeError("Git configuration, hooks or other protected metadata changed since creation")
        for directory, dirs, files in os.walk(clone, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                _plain(path)
                if path.is_file() and path.stat().st_nlink > 1:
                    raise RuntimeError(f"hardlinked file is not exclusively owned: {path}")
                if name.endswith(".lock") or name in {"MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD",
                                                      "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer"}:
                    raise RuntimeError(f"Git operation/lock present: {path}")
        if (clone / ".git" / "objects" / "info" / "alternates").exists():
            raise RuntimeError("alternate object database is not exclusively owned")
        if _git(clone, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"):
            raise RuntimeError("clone has modified, untracked or ignored files")
        remote_commits, remote_refs = _remote_commits(clone, pr_refs.values())
        refs = _git(clone, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
        head = _git(clone, "rev-parse", "HEAD").strip()
        for line in refs:
            name, oid = line.split()
            if name in pr_refs:
                if remote_refs.get(pr_refs[name]) != oid:
                    raise RuntimeError(f"recorded PR ref is not recoverable from its live pull ref: {name}")
            elif not name.startswith(("refs/heads/", "refs/remotes/", "refs/tags/")):
                raise RuntimeError(f"non-disposable ref remains: {name}")
            if name.startswith("refs/tags/") and oid not in remote_refs.values():
                raise RuntimeError(f"tag is not recoverable from origin: {name}")
        if _git(clone, "rev-list", "--max-count=1", "--all", "--reflog", "HEAD", "--not",
                *remote_commits).strip():
            raise RuntimeError("local refs, HEAD or reflogs contain commits not recoverable from origin")
        unreachable = _git(clone, "fsck", "--full", "--unreachable", "--no-reflogs")
        for line in unreachable.splitlines():
            if line.startswith(("unreachable ", "dangling ")):
                _, kind, oid = line.split()
                # Do not discard even dangling blobs/trees: they may be staged/recovery evidence.
                raise RuntimeError(f"unreferenced {kind} {oid} remains in the object database")
        if apply:
            _plain(clone / ".git")
            current = (clone / ".git").stat()
            if ([current.st_dev, current.st_ino] != receipt["identity"]
                    or _records(clone) != members
                    or _metadata(clone) != receipt["metadata"]
                    or _git(clone, "rev-parse", "HEAD").strip() != head
                    or _git(clone, "for-each-ref", "--format=%(refname) %(objectname)").splitlines() != refs
                    or _git(clone, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching")
                    or any((clone / ".git").rglob("*.lock"))):
                raise RuntimeError("clone changed during disposal inspection")
            def writable_retry(func, name, exc):
                if not isinstance(exc[1], PermissionError):
                    raise exc[1]
                os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
                func(name)
            shutil.rmtree(clone, onerror=writable_retry)
            receipt_path.unlink()
        row.update(action="removed" if apply else "would-remove",
                   reason="owned clone; completed jobs, no linked worktrees, clean and remotely recoverable")
    except Exception as err:
        row["reason"] = str(err)
    return [row]
