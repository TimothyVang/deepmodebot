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
Rule approval (../rules/rule_ledger.py) runs in every PreToolUse mode, active session or not: in a repo whose owner
turned it on, Write/Edit/NotebookEdit on agent rule files or the ledger are denied, and so are Bash commands that
write them; the owner-only `rules init|approve|reject|rotate` commands are denied everywhere.
Other Bash, MCP tools and hook programs are not covered here.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True

MARK_MAX_AGE_SECONDS = 30 * 24 * 3600
RULE_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rules", "rule_ledger.py")
REWARD_HACK_CMD_RE = re.compile(
    r"(?:^|[ ;&|(])--(?:gate-)?min-(?:iou|ssim|psnr|clip|clip-score|dice|f1|score|fidelity|similarity|coverage|accuracy|protrusion)(?:\s+|=)['\"]?(?:-\d+(?:\.\d+)?|0+(?:\.0+)?|\d+(?:\.\d+)?[eE]-[6-9]\d*)['\"]?(?=$|[ ;&|)])"
    r"|(?:^|[ ;&|(])--(?:skip-reference|skip-fidelity|skip-gates?|bypass-gate)(?=$|[ ;&|)])"
    r"|(?:^|[ ;&|(])(?:--require-spark-receipt(?:\s+|=)['\"]?false|--gate-mode(?:\s+|=)['\"]?off)['\"]?(?=$|[ ;&|)])"
    r"|\bgit\b[^\n;&|]*\bcommit\b[^\n;&|]*\s(?:-n|--no-verify)(?=$|[ ;&|)])"
    r"|\bsqlite3\b[^\n;&|]*reward-guard\.db\b"
    r"|\b(?:rm|del|unlink|Remove-Item)\b[^\n;&|]*(?:contract-lock\.json|reward-guard\.db)\b"
    r"|\breward_guard\.py\b[^\n;&|]*\brecord-judge\b",
    re.I,
)


def check_bash_reward_hack(cmd_text):
    cleaned = re.sub(r"(-m|--message)(=|\s+)(\"[^\"]*\"|'[^']*')", r'\1 ""', str(cmd_text or ""))
    for raw_ln in cleaned.replace("\\\r\n", " ").replace("\\\n", " ").splitlines():
        ln = raw_ln.strip()
        if not ln or re.match(r"^(?:grep|rg)\s+[^;&|`$]*$", ln):
            continue
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


def rule_hints():
    """Lowercase fragments that any rule path or owner rule command contains (from rules/rule-paths.json)."""
    try:
        with open(os.path.join(os.path.dirname(RULE_LEDGER), "rule-paths.json"), encoding="utf-8") as handle:
            spec = json.load(handle)
    except (OSError, ValueError):
        return []
    dirs = [str(d).lower().strip("/") for d in spec.get("dirs", [])]
    named = [str(n).lower() for n in spec.get("names", []) + spec.get("files", [])]
    return named + dirs + [d.split("/")[0] for d in dirs] + ["deepmodebot", "rule_ledger"]


def ledger_near(folder):
    """Whether the repo holding `folder` has an owner rule ledger in its working tree."""
    cur = os.path.abspath(folder)
    while True:
        if os.path.lexists(os.path.join(cur, ".deepmodebot", "rules", "ledger.json")):
            return True
        parent = os.path.dirname(cur)
        if os.path.lexists(os.path.join(cur, ".git")) or parent == cur:
            return False
        cur = parent


def rule_guard_reason(event, tool_name, tool_input):
    """Why rule approval denies this tool call, or None (see rules/rule_ledger.py guard).

    rules/rule_ledger.py loads only for shell commands in a ledger repo, text naming a rule path or an owner command,
    or a write whose target (or its resolved target) looks like a rule path.
    """
    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if tool_name == "Bash":
        paths, command = [], str(tool_input.get("command") or "")
        text = command
    elif tool_name in ("Write", "Edit", "NotebookEdit"):
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        paths, command = ([target] if isinstance(target, str) and target else []), ""
        full = [os.path.join(cwd, os.path.expanduser(p)) for p in paths]
        text = " ".join(full + [os.path.realpath(p) for p in full])
    else:
        return None
    text = text.lower().replace("\\", "/")
    needed = any(h in text for h in rule_hints()) or (tool_name == "Bash" and ledger_near(cwd))
    if not os.path.isfile(RULE_LEDGER) or not needed:
        return None
    mod = sys.modules.get("dmb_rule_ledger")
    if mod is None:
        spec = importlib.util.spec_from_file_location("dmb_rule_ledger", RULE_LEDGER)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return mod.guard(cwd, paths=paths, command=command)


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
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    rule_reason = rule_guard_reason(event, tool_name, tool_input)
    if rule_reason:
        deny(rule_reason)
        return 0
    if mode == "if-active" and not (mark and os.path.exists(mark)):
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
