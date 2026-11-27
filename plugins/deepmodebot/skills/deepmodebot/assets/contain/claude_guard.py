#!/usr/bin/env python3
"""Claude Code hook: deny Write, Edit and NotebookEdit outside the project root (deepmodebot "Contain the work").

Hooks start it through claude-guard.sh, which picks a Python 3.8+ and denies the write when there is none.
Modes (first argument):
  (none)               PreToolUse: always enforce. Used by the deepmodebot skill's frontmatter hook.
  if-active <data-dir> PreToolUse: enforce only in sessions marked active. Used by the plugin's hooks.json.
  activate <data-dir>  UserPromptSubmit: mark the session active when the prompt runs a /deepmodebot: command.
                       The mark outlives the process, so a resumed session (same session id) stays guarded;
                       marks older than 30 days are pruned here.

The allowed roots are the worktree holding the session's cwd and its main checkout (they differ in a linked
worktree, e.g. one under <root>/.worktrees/ or an Orca workspace), or the cwd itself outside git. Also allowed:
Claude Code's own plan and project-memory dirs, and any `extraWriteRoots` listed in a root's .deepmodebot.json
(only paths the user named).
Bash, MCP tools and hook programs are not covered here.
"""
import json
import os
import math
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True

MARK_MAX_AGE_SECONDS = 30 * 24 * 3600
METRIC_FLOORS = {
    "iou": 0.50, "ssim": 0.50, "dice": 0.50, "f1": 0.50, "auc": 0.50,
    "accuracy": 0.50, "acc": 0.50, "precision": 0.50, "recall": 0.50,
    "fidelity": 0.50, "similarity": 0.50, "coverage": 0.50, "pass-rate": 0.50, "win-rate": 0.50,
    "clip": 0.15, "clip-score": 0.15, "ap": 0.15, "map": 0.15, "bleu": 0.15, "rouge": 0.15,
    "psnr": 10.0, "protrusion": 0.02, "score": 0.05, "confidence": 0.05, "symmetry": 0.05,
}
MIN_FLAG_VAL_RE = re.compile(
    r"(?:^|[\s;&|(])(--(?:gate-)?mi(?:n(?:-([a-z0-9_-]*))?)?(?:\s+|=)['\"]?\s*([-+]?(?:inf(?:inity)?|nan|(?:\d[\d_]*\.?[\d_]*|\.[\d_]+)(?:[eE][-+]?[\d_]+)?))\s*['\"]?)(?=$|[\s;&|)])",
    re.I,
)
REWARD_HACK_CMD_RE = re.compile(
    r"(?:^|[\s;&|(])--(?:skip-reference|skip-fidelity|skip-gates?|skip-verify|skip-validation|bypass-gate|pass-if-no-tests|passWithNoTests)(?=$|[\s;&|)])"
    r"|(?:^|[\s;&|(])(?:--require-spark-receipt(?:\s+|=)['\"]?false|--gate-mode(?:\s+|=)['\"]?off|--measured-gates(?:\s+|=)['\"]?off|--check-360(?:\s+|=)['\"]?(?:false|0))['\"]?(?=$|[\s;&|)])"
    r"|\bgit\b[^\n;&|]*\bcommit\b[^\n;&|]*\s(?:-n|--no-verify)(?=$|[\s;&|)])"
    r"|\b(?:reward-guard\.db|contract-lock\.json|judge_verdicts)\b"
    r"|\breward_guard\.py\b[^\n;&|]*\brecord-judge\b",
    re.I,
)


def _min_flag_floor(tok):
    norm = (tok or "").lower().replace("_", "-")
    if not norm:
        return 0.50
    if norm in METRIC_FLOORS:
        return METRIC_FLOORS[norm]
    matches = [v for k, v in METRIC_FLOORS.items() if k.startswith(norm)]
    return max(matches) if matches else None


def check_bash_reward_hack(cmd_text):
    cleaned = re.sub(r"(-m|--message)(=|\s+)(\"[^\"]*\"|'[^']*')", r'\1 ""', str(cmd_text or ""))
    for raw_ln in cleaned.replace("\\\r\n", " ").replace("\\\n", " ").splitlines():
        ln = raw_ln.strip()
        if not ln or re.match(r"^(?:grep|rg)\s+[^;&|`$]*$", ln):
            continue
        for fm in MIN_FLAG_VAL_RE.finditer(ln):
            floor = _min_flag_floor(fm.group(2))
            if floor is not None:
                try:
                    val = float(fm.group(3))
                    if not math.isfinite(val) or val < floor:
                        return fm.group(1).strip()
                except ValueError:
                    pass
        m = REWARD_HACK_CMD_RE.search(ln)
        if m:
            return m.group(0).strip()
    return None


def real(path):
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def project_roots(cwd):
    """The worktree holding cwd, then the main checkout (they differ in a linked worktree); cwd outside git."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return [cwd]
    lines = out.stdout.splitlines()
    if out.returncode or len(lines) < 2:
        return [cwd]
    toplevel, common = lines[0], lines[1].rstrip("/\\")
    return [toplevel, os.path.dirname(common)] if os.path.basename(common) == ".git" else [toplevel]


def allowed_roots(roots):
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join("~", ".claude")
    allowed = [*roots, os.path.join(claude_dir, "plans"), os.path.join(claude_dir, "projects")]
    for root in roots:
        try:
            with open(os.path.join(root, ".deepmodebot.json"), encoding="utf-8") as handle:
                cfg = json.load(handle)
            extra = cfg.get("extraWriteRoots") if isinstance(cfg, dict) else None
            if isinstance(extra, list):
                allowed += [
                    p if os.path.isabs(os.path.expanduser(p)) else os.path.join(root, p)
                    for p in extra
                    if isinstance(p, str) and p.strip()
                ]
        except (OSError, ValueError, AttributeError):
            pass
    return [real(r) for r in allowed]


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


def session_mark(data_dir, event):
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(event.get("session_id") or ""))
    return os.path.join(data_dir, "active-sessions", session) if data_dir and session else None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "enforce"
    try:
        event = json.load(sys.stdin)
    except ValueError:
        print("deepmodebot contain guard: unreadable hook input; not blocking", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    mark = session_mark(sys.argv[2] if len(sys.argv) > 2 else "", event)
    if mode == "activate":
        if mark and re.match(r"\s*/(?:deepmodebot:|(?:deep|deepmodebot|suggest|research|tournament|review-pr|land-pr|pr-thread|contribute|project-brief)\b)", str(event.get("prompt") or "")):
            folder = os.path.dirname(mark)
            os.makedirs(folder, exist_ok=True)
            try:
                entries = os.listdir(folder)
            except OSError:
                entries = []
            for name in entries:
                stale = os.path.join(folder, name)
                try:
                    if os.path.isfile(stale) and time.time() - os.path.getmtime(stale) > MARK_MAX_AGE_SECONDS:
                        os.remove(stale)
                except OSError:
                    pass
            open(mark, "w").close()
        return 0
    if mode == "if-active" and not (mark and os.path.exists(mark)):
        return 0
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    if tool_name == "Bash":
        bad = check_bash_reward_hack(tool_input.get("command") or "")
        if bad:
            deny(f"deepmodebot anti-reward-hacking guard blocked `{bad}`: builders may not zero thresholds, skip reference/verification gates, or tamper with provenance ledgers.")
        return 0
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        return 0
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(target, str) or not target:
        return 0
    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path = real(target if os.path.isabs(os.path.expanduser(target)) else os.path.join(cwd, target))
    roots = project_roots(cwd)
    root = os.path.normpath(roots[0])
    if any(inside(path, r) for r in allowed_roots(roots)):
        return 0
    deny(f"deepmodebot keeps all writes inside the project root {root}. {target} is outside it. "
         f"Put scratch and temp files in {os.path.join(root, '.scratch')} and worktrees in "
         f"{os.path.join(root, '.worktrees')}. If the user explicitly named this path, add it to "
         f"extraWriteRoots in {os.path.join(root, '.deepmodebot.json')}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
