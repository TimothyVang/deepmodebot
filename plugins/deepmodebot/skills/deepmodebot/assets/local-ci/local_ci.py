#!/usr/bin/env python3
"""GitHub-Actions-style local CI runner for .deepmodebot/ci.yml (DAG + parallel + Merkle cache).

    python -B local_ci.py validate [--root <repo>] [--file .deepmodebot/ci.yml] [--json]
    python -B local_ci.py plan [--root <repo>] [--job <id>] [--json]
    python -B local_ci.py run [--root <repo>] [--job <id>] [--cached] [--max-workers 4] [--json]

Algorithms & guarantees:
- Pure Python 3 stdlib YAML parser (mappings, lists, inline arrays, block scalars, comments).
- Kahn's topological sort over job `needs` with explicit cycle/missing-dep rejection and parallel execution waves.
- Merkle content-hash step caching (`inputs` globs + commands -> SHA-256) under `.scratch/local-ci-cache.json`.
- Enforces containment env (`PYTHONDONTWRITEBYTECODE=1`, repo-local `TMPDIR`/`TEMP`/`TMP`) and records compact `ci_result` into `.scratch/deepmode-memory.db`.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_CI_REL = ".deepmodebot/ci.yml"
CACHE_REL = ".scratch/local-ci-cache.json"
ASSETS_DIR = Path(__file__).resolve().parent.parent


def _parse_scalar(raw: str):
    s = raw.strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        if s.startswith('"'):
            try:
                return json.loads(s)
            except ValueError:
                return s[1:-1]
        return s[1:-1].replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_inline_list(inner)]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _split_inline_list(inner: str) -> list[str]:
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return parts


def _strip_comment(line: str) -> str:
    quote = None
    for idx, ch in enumerate(line):
        if quote:
            if ch == quote and (idx == 0 or line[idx - 1] != "\\"):
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == "#" and (idx == 0 or line[idx - 1] in (" ", "\t")):
            return line[:idx].rstrip()
    return line.rstrip()


def parse_yaml_lite(text: str) -> dict:
    """Parse the GitHub-Actions YAML subset used by .deepmodebot/ci.yml (stdlib only)."""
    raw_lines = text.replace("\r\n", "\n").splitlines()
    tokens: list[tuple[int, str]] = []
    i = 0
    while i < len(raw_lines):
        raw = raw_lines[i]
        stripped = _strip_comment(raw)
        if not stripped.strip():
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        tokens.append((indent, stripped.strip()))
        i += 1

    def parse_block(idx: int, min_indent: int):
        if idx >= len(tokens):
            return None, idx
        ind, content = tokens[idx]
        if ind < min_indent:
            return None, idx
        if content.startswith("- ") or content == "-":
            arr = []
            while idx < len(tokens) and tokens[idx][0] == ind and (tokens[idx][1].startswith("- ") or tokens[idx][1] == "-"):
                item_text = tokens[idx][1][1:].strip()
                idx += 1
                if not item_text:
                    val, idx = parse_block(idx, ind + 1)
                    arr.append(val)
                elif ":" in item_text and not item_text.startswith(('"', "'", "[")):
                    k, _, v = item_text.partition(":")
                    obj = {}
                    v = v.strip()
                    if v in ("|", ">"):
                        val, idx = _consume_block_scalar(idx, ind + 2, fold=(v == ">"))
                        obj[k.strip()] = val
                    elif v == "":
                        val, idx = parse_block(idx, ind + 2)
                        obj[k.strip()] = val
                    else:
                        obj[k.strip()] = _parse_scalar(v)
                    if idx < len(tokens) and tokens[idx][0] > ind:
                        extra, idx = parse_block(idx, tokens[idx][0])
                        if isinstance(extra, dict):
                            obj.update(extra)
                    arr.append(obj)
                else:
                    arr.append(_parse_scalar(item_text))
            return arr, idx

        mapping = {}
        while idx < len(tokens) and tokens[idx][0] == ind and not tokens[idx][1].startswith("- "):
            line = tokens[idx][1]
            if ":" not in line:
                raise ValueError(f"invalid YAML line: {line!r}")
            k, _, v = line.partition(":")
            key = k.strip().strip('"').strip("'")
            v = v.strip()
            idx += 1
            if v in ("|", ">"):
                val, idx = _consume_block_scalar(idx, ind + 1, fold=(v == ">"))
                mapping[key] = val
            elif v == "":
                if idx < len(tokens) and tokens[idx][0] > ind:
                    val, idx = parse_block(idx, tokens[idx][0])
                else:
                    val = {}
                mapping[key] = val
            else:
                mapping[key] = _parse_scalar(v)
        return mapping, idx

    def _consume_block_scalar(idx: int, min_ind: int, fold: bool):
        lines = []
        base = None
        while idx < len(tokens) and tokens[idx][0] >= min_ind:
            if base is None:
                base = tokens[idx][0]
            pad = " " * max(0, tokens[idx][0] - base)
            lines.append(pad + tokens[idx][1])
            idx += 1
        return (" ".join(lines) if fold else "\n".join(lines)), idx

    parsed, _ = parse_block(0, 0)
    if not isinstance(parsed, dict):
        raise ValueError("ci.yml root must be a YAML mapping")
    return parsed


def normalize_needs(raw_needs) -> list[str]:
    if not raw_needs:
        return []
    if isinstance(raw_needs, str):
        return [raw_needs]
    if isinstance(raw_needs, list):
        return [str(x) for x in raw_needs if str(x).strip()]
    raise ValueError(f"invalid needs value: {raw_needs!r}")


def validate_workflow(doc: dict) -> list[str]:
    errors: list[str] = []
    if not doc.get("name"):
        errors.append("missing top-level `name`")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append("missing non-empty `jobs` mapping")
        return errors
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"job `{jid}` must be a mapping")
            continue
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"job `{jid}` has no `steps`")
        else:
            for si, st in enumerate(steps):
                if not isinstance(st, dict) or not st.get("run"):
                    errors.append(f"job `{jid}` step[{si}] missing `run` command")
        if "timeout-minutes" in job:
            try:
                if float(job["timeout-minutes"]) <= 0:
                    errors.append(f"job `{jid}` timeout-minutes must be > 0")
            except (TypeError, ValueError):
                errors.append(f"job `{jid}` invalid timeout-minutes: {job['timeout-minutes']!r}")
        for dep in normalize_needs(job.get("needs")):
            if dep not in jobs:
                errors.append(f"job `{jid}` needs unknown job `{dep}`")
    if not errors:
        try:
            plan_dag(doc)
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def plan_dag(doc: dict, target_job: str | None = None) -> list[list[str]]:
    """Kahn's topological sort producing parallel execution waves; raises on cycles."""
    jobs: dict = doc.get("jobs") or {}
    if target_job:
        if target_job not in jobs:
            raise ValueError(f"unknown job `{target_job}`")
        needed: set[str] = set()
        stack = [target_job]
        while stack:
            cur = stack.pop()
            if cur in needed:
                continue
            needed.add(cur)
            for dep in normalize_needs(jobs[cur].get("needs")):
                if dep not in jobs:
                    raise ValueError(f"job `{cur}` needs unknown job `{dep}`")
                stack.append(dep)
        subset = {k: jobs[k] for k in jobs if k in needed}
    else:
        subset = dict(jobs)

    indeg = {k: 0 for k in subset}
    adj: dict[str, list[str]] = {k: [] for k in subset}
    for jid, job in subset.items():
        for dep in normalize_needs(job.get("needs")):
            if dep in subset:
                adj[dep].append(jid)
                indeg[jid] += 1

    waves: list[list[str]] = []
    ready = sorted(k for k, d in indeg.items() if d == 0)
    visited = 0
    while ready:
        waves.append(ready)
        nxt = []
        for u in ready:
            visited += 1
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    nxt.append(v)
        ready = sorted(nxt)

    if visited != len(subset):
        stuck = sorted(k for k, d in indeg.items() if d > 0)
        raise ValueError(f"dependency cycle detected in jobs: {', '.join(stuck)}")
    return waves


def compute_job_merkle(root: Path, jid: str, job: dict, global_env: dict) -> str:
    """Content-hash job steps, env, and matched `inputs` globs for O(1) skip caching."""
    h = hashlib.sha256()
    h.update(jid.encode("utf-8"))
    h.update(json.dumps(global_env, sort_keys=True).encode("utf-8"))
    h.update(json.dumps(job.get("env") or {}, sort_keys=True).encode("utf-8"))
    for st in job.get("steps") or []:
        h.update(str(st.get("run", "")).encode("utf-8"))
    patterns = job.get("inputs") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    resolved_root = root.resolve()
    matched: set[Path] = set()
    for pat in patterns:
        pat_str = str(pat).strip()
        if not pat_str or Path(pat_str).is_absolute() or ".." in Path(pat_str).parts:
            raise ValueError(f"job `{jid}` input pattern escapes project root: {pat_str!r}")
        for hit in glob.glob(str(resolved_root / pat_str), recursive=True):
            p = Path(hit)
            if p.is_symlink() or not p.is_file() or "__pycache__" in p.parts:
                continue
            rp = p.resolve()
            if not rp.is_relative_to(resolved_root):
                continue
            matched.add(rp)
    for p in sorted(matched):
        rel = p.relative_to(resolved_root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()[:24]

def _load_cache(root: Path) -> dict:
    p = root / CACHE_REL
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(root: Path, cache: dict) -> None:
    p = root / CACHE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    gi = p.parent / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    p.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_memory(root: Path, summary: dict) -> None:
    mem_script = ASSETS_DIR / "memory" / "project_memory.py"
    if not mem_script.is_file():
        return
    try:
        spec = importlib.util.spec_from_file_location("deepmode_project_memory", mem_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        status = "PASS" if summary["ok"] else "FAIL"
        jobs_txt = ", ".join(f"{j['id']}={j['status']}({j['seconds']}s)" for j in summary["jobs"])
        mod.put_memory(
            root,
            key="ci:last-run",
            kind="ci_result",
            priority=1,
            tags="ci,gate",
            source=summary["file"],
            content=f"Local CI {status} ({summary['seconds']}s): {jobs_txt}",
        )
    except (OSError, ImportError, ValueError) as exc:
        print(f"warning: memory record skipped: {exc}", file=sys.stderr)


STRIPPED_API_KEYS = frozenset({
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
})


def _build_step_env(root: Path, global_env: dict, job_env: dict) -> dict:
    tmp_dir = root / ".scratch" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() not in STRIPPED_API_KEYS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)
    env["TMPDIR"] = str(tmp_dir)
    for src in (global_env, job_env):
        for k, v in (src or {}).items():
            env[str(k)] = str(v)
    return env

def _run_job(root: Path, jid: str, job: dict, global_env: dict, use_cache: bool, cache: dict) -> dict:
    started = time.monotonic()
    merkle = compute_job_merkle(root, jid, job, global_env) if job.get("inputs") else None
    if use_cache and merkle and cache.get(jid) == merkle:
        return {"id": jid, "status": "cached", "ok": True, "seconds": 0.0, "merkle": merkle, "steps": []}

    timeout_sec = float(job.get("timeout-minutes") or 5) * 60.0
    env = _build_step_env(root, global_env, job.get("env") or {})
    step_results = []
    job_ok = True
    for idx, step in enumerate(job.get("steps") or []):
        sname = str(step.get("name") or f"step-{idx + 1}")
        cmd = str(step["run"])
        st_start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=str(root), env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout_sec, creationflags=NO_WINDOW,
            )
            rc = proc.returncode
            tail = (proc.stdout + "\n" + proc.stderr).strip()[-600:]
        except subprocess.TimeoutExpired:
            rc = 124
            tail = f"timed out after {timeout_sec:.0f}s"
        dur = round(time.monotonic() - st_start, 2)
        cont = bool(step.get("continue-on-error"))
        passed = rc == 0 or cont
        step_results.append({"name": sname, "exit_code": rc, "ok": passed, "seconds": dur, "tail": "" if passed else tail})
        if not passed:
            job_ok = False
            break
    return {
        "id": jid,
        "status": "passed" if job_ok else "failed",
        "ok": job_ok,
        "seconds": round(time.monotonic() - started, 2),
        "merkle": merkle,
        "steps": step_results,
    }


def run_workflow(root: Path, ci_file: Path, target_job: str | None = None, use_cache: bool = False, max_workers: int = 4) -> dict:
    doc = parse_yaml_lite(ci_file.read_text(encoding="utf-8"))
    errors = validate_workflow(doc)
    if errors:
        return {"ok": False, "file": ci_file.relative_to(root).as_posix(), "errors": errors, "jobs": [], "seconds": 0.0}

    waves = plan_dag(doc, target_job=target_job)
    jobs = doc["jobs"]
    global_env = doc.get("env") or {}
    cache = _load_cache(root) if use_cache else {}
    new_cache = dict(cache)
    started = time.monotonic()
    results: list[dict] = []
    failed_ids: set[str] = set()

    for wave in waves:
        runnable = []
        for jid in wave:
            deps = normalize_needs(jobs[jid].get("needs"))
            if any(d in failed_ids for d in deps):
                failed_ids.add(jid)
                results.append({"id": jid, "status": "skipped", "ok": False, "seconds": 0.0, "merkle": None, "steps": []})
            else:
                runnable.append(jid)
        if not runnable:
            continue
        workers = min(max(1, max_workers), len(runnable))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_run_job, root, jid, jobs[jid], global_env, use_cache, cache) for jid in runnable]
            for fut in futs:
                r = fut.result()
                results.append(r)
                if r["ok"] and r.get("merkle"):
                    new_cache[r["id"]] = r["merkle"]
                if not r["ok"]:
                    failed_ids.add(r["id"])

    if use_cache or any(r.get("merkle") for r in results):
        _save_cache(root, new_cache)

    summary = {
        "ok": not failed_ids,
        "name": doc.get("name", "local-ci"),
        "file": ci_file.relative_to(root).as_posix(),
        "waves": waves,
        "seconds": round(time.monotonic() - started, 2),
        "jobs": results,
    }
    _record_memory(root, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Local GitHub-Actions-style CI runner for .deepmodebot/ci.yml.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "plan", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=".")
        sp.add_argument("--file", default=DEFAULT_CI_REL)
        sp.add_argument("--json", action="store_true")
        if name in ("plan", "run"):
            sp.add_argument("--job", default=None)
        if name == "run":
            sp.add_argument("--cached", action="store_true")
            sp.add_argument("--max-workers", type=int, default=4)

    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    raw_ci = Path(args.file)
    if raw_ci.is_absolute():
        print(f"error: CI file must be repo-relative: {args.file}", file=sys.stderr)
        return 2
    candidate = root / raw_ci
    if candidate.is_symlink():
        print(f"error: refusing symlinked CI file: {candidate}", file=sys.stderr)
        return 2
    ci_file = candidate.resolve()
    if not ci_file.is_relative_to(root):
        print(f"error: CI file escapes project root: {args.file}", file=sys.stderr)
        return 2
    if not ci_file.is_file():
        print(f"error: CI file not found: {ci_file}", file=sys.stderr)
        return 2
    if args.cmd == "validate":
        doc = parse_yaml_lite(ci_file.read_text(encoding="utf-8"))
        errs = validate_workflow(doc)
        out = {"ok": not errs, "file": ci_file.relative_to(root).as_posix(), "errors": errs, "jobs": list((doc.get("jobs") or {}).keys())}
        print(json.dumps(out, indent=2) if args.json else ("ok" if not errs else "\n".join(errs)))
        return 0 if not errs else 1

    if args.cmd == "plan":
        doc = parse_yaml_lite(ci_file.read_text(encoding="utf-8"))
        errs = validate_workflow(doc)
        if errs:
            print(json.dumps({"ok": False, "errors": errs}, indent=2) if args.json else "\n".join(errs))
            return 1
        waves = plan_dag(doc, target_job=args.job)
        out = {"ok": True, "name": doc.get("name"), "waves": waves}
        print(json.dumps(out, indent=2) if args.json else "\n".join(f"wave {i+1}: {', '.join(w)}" for i, w in enumerate(waves)))
        return 0

    if args.cmd == "run":
        res = run_workflow(root, ci_file, target_job=args.job, use_cache=args.cached, max_workers=args.max_workers)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"local-ci [{res.get('name', 'ci')}]: {'OK' if res['ok'] else 'FAILED'} ({res['seconds']}s)")
            for j in res["jobs"]:
                print(f"  - {j['id']}: {j['status']} ({j['seconds']}s)")
                for s in j["steps"]:
                    if not s["ok"]:
                        print(f"      FAIL {s['name']} (exit {s['exit_code']}): {s['tail']}")
        return 0 if res["ok"] else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
