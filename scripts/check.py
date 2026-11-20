#!/usr/bin/env python3
"""Structural checks for the skills in this repo. Prints OK or a list of problems and exits non-zero."""
import ast
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINE_BYTES = 760  # omp read truncates lines at 768 characters
BANNED = re.compile(
    r"(?<![a-z0-9])[pr]stack(?![a-z0-9])|poteto|lauren\s+tan|cursor/plugins|pocock|ras\s*mic"
    r"|cloud\s*x\s*berry|greptile|code\s*rabbit|james\s+clements",
    re.I,
)
# Source attribution and immutable observations retain upstream identities, not product branding.
WHITE_LABEL_EXEMPT = {
    Path("scripts/check.py"), Path("trending"), Path("evals/workflows"),
    Path("docs/evidence"), Path("docs/research/community-skills-review.md"),
    Path("plugins/deepmodebot/skills/deepmodebot/assets/repo-references.json"),
    Path("docs/research/youtube-learning/history-recovery.md"),
}
LOCAL_ONLY = {".git", ".scratch", ".worktrees", "__pycache__"}  # self-ignored work folders and caches, never shipped
RULES_WINDOW_BYTES = 20_000  # about 5,000 tokens at 4 bytes each: what Claude Code keeps of a skill after compaction
SKILL_BODY_MAX_BYTES = 24_000  # Antigravity truncates skill bodies above 24 KB
CORE_LINE_BYTES = 600  # deepmodebot's SKILL.md, sibling SKILL.md, playbooks and techniques: one instruction per line
# Reference skills hold cited facts that go stale; each SKILL.md states the date they were true as of.
LIBRARY_SKILLS = ("agent-harnesses", "cloud-devsecops", "domain-rules", "frontend-ui", "secrets-and-auth",
                  "software-architecture")
STALE_AFTER_DAYS = 120
problems = []


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    return fields


def iter_files(suffix=None):
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in LOCAL_ONLY)
        base = Path(dirpath)
        for name in sorted(filenames):
            if name in LOCAL_ONLY:
                continue
            if suffix is None or name.endswith(suffix):
                yield base / name


marketplace_versions = {}
for manifest in [ROOT / ".omp-plugin/marketplace.json", ROOT / ".claude-plugin/marketplace.json"]:
    try:
        catalog = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        problems.append(f"{manifest.relative_to(ROOT)}: {err}")
        continue
    rel_m = manifest.relative_to(ROOT)
    meta_ver = (catalog.get("metadata") or {}).get("version")
    for plugin in catalog.get("plugins", []):
        pname = plugin.get("name")
        source = plugin.get("source")
        if isinstance(source, str) and not (ROOT / source).is_dir():
            problems.append(f"{rel_m}: plugin {pname} source {source} is missing")
        if isinstance(pname, str):
            if meta_ver:
                marketplace_versions.setdefault(pname, []).append((f"{rel_m}#metadata.version", meta_ver))
            marketplace_versions.setdefault(pname, []).append((f"{rel_m}#plugins[{pname}].version", plugin.get("version")))

for json_path in [*ROOT.glob("plugins/*/.claude-plugin/plugin.json"),
                  *ROOT.glob("plugins/*/.antigravity-plugin/plugin.json"),
                  *ROOT.glob("plugins/*/hooks/hooks.json"),
                  *ROOT.glob("plugins/*/hooks.json"),
                  *ROOT.glob("plugins/*/mcp_config.json")]:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except ValueError as err:
        problems.append(f"{json_path.relative_to(ROOT)}: {err}")
        continue
    rel_j = json_path.relative_to(ROOT)
    if not isinstance(data, dict):
        problems.append(f"{rel_j}: root must be a JSON object")
        continue
    if json_path.name == "hooks.json" and json_path.parent.parent.name == "plugins":
        if not all(isinstance(v, dict) for v in data.values()):
            problems.append(f"{rel_j}: each top-level hook entry must be an object")
    elif json_path.name == "mcp_config.json":
        if not isinstance(data.get("mcpServers"), dict):
            problems.append(f"{rel_j}: mcpServers must be an object")
    elif json_path.parent.name == ".antigravity-plugin":
        plugin_dir = json_path.parent.parent
        pname = data.get("name")
        if not isinstance(pname, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", pname):
            problems.append(f"{rel_j}: invalid or missing kebab-case name {pname!r}")
        elif pname != plugin_dir.name:
            problems.append(f"{rel_j}: name {pname!r} does not match folder {plugin_dir.name!r}")
        for key in ("description", "version"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                problems.append(f"{rel_j}: missing {key}")
        logo = data.get("logo")
        if logo is not None and (not isinstance(logo, str) or not (plugin_dir / logo).is_file()):
            problems.append(f"{rel_j}: logo {logo!r} does not exist under {plugin_dir.relative_to(ROOT)}")
        extra_skills = data.get("skills")
        if extra_skills is not None:
            dirs = [extra_skills] if isinstance(extra_skills, str) else extra_skills
            if not isinstance(dirs, list) or not all(isinstance(s, str) and s.strip() for s in dirs):
                problems.append(f"{rel_j}: skills must be a string or array of strings")
            else:
                for s in dirs:
                    if not (plugin_dir / s).is_dir():
                        problems.append(f"{rel_j}: skills directory {s!r} is missing")

for plugin_dir in sorted(p for p in (ROOT / "plugins").iterdir() if p.is_dir()):
    versions = list(marketplace_versions.get(plugin_dir.name, []))
    for sub in (".claude-plugin/plugin.json", ".antigravity-plugin/plugin.json"):
        mpath = plugin_dir / sub
        if mpath.is_file():
            try:
                versions.append((str(mpath.relative_to(ROOT)), json.loads(mpath.read_text(encoding="utf-8")).get("version")))
            except ValueError:
                pass
    distinct = {v for _, v in versions}
    if versions and (None in distinct or "" in distinct or len(distinct) > 1):
        detail = ", ".join(f"{src}={ver!r}" for src, ver in versions)
        problems.append(f"plugins/{plugin_dir.name}: version mismatch across manifests ({detail})")

for skill_md in [*ROOT.glob("plugins/*/skills/*/SKILL.md"),
                 *ROOT.glob("plugins/*/.antigravity-plugin/skills/*/SKILL.md"),
                 *ROOT.glob(".omp/skills/*/SKILL.md"),
                 *ROOT.glob(".agents/skills/*/SKILL.md")]:
    fields = frontmatter(skill_md.read_text(encoding="utf-8"))
    rel = skill_md.relative_to(ROOT)
    if fields is None:
        problems.append(f"{rel}: missing frontmatter")
    elif not fields.get("name") or not fields.get("description"):
        problems.append(f"{rel}: frontmatter needs name and description")
    elif fields["name"] != skill_md.parent.name:
        problems.append(f"{rel}: name {fields['name']!r} does not match folder {skill_md.parent.name!r}")

for agent_md in [*ROOT.glob("plugins/*/agents/*.md"),
                 *ROOT.glob("plugins/*/agents/*/agent.md"),
                 *ROOT.glob("plugins/*/.antigravity-plugin/agents/*.md"),
                 *ROOT.glob("plugins/*/.antigravity-plugin/agents/*/agent.md")]:
    fields = frontmatter(agent_md.read_text(encoding="utf-8"))
    rel = agent_md.relative_to(ROOT)
    expected_name = agent_md.parent.name if agent_md.name == "agent.md" else agent_md.stem
    if fields is None:
        problems.append(f"{rel}: missing frontmatter")
    elif not fields.get("name") or not fields.get("description"):
        problems.append(f"{rel}: frontmatter needs name and description")
    elif fields["name"] != expected_name:
        problems.append(f"{rel}: name {fields['name']!r} does not match {expected_name!r}")

for md in iter_files(".md"):
    rel = md.relative_to(ROOT)
    text = md.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            problems.append(f"{rel}:{number}: line is {len(line.encode('utf-8'))} bytes (max {MAX_LINE_BYTES})")
    skill_dir = next((p for p in md.parents if (p / "SKILL.md").is_file()), None)
    if skill_dir is None:
        continue
    sibling_skills = [p.parent for p in skill_dir.parent.glob("*/SKILL.md")]
    if skill_dir.parent.name == "skills" and skill_dir.parent.parent.name == ".antigravity-plugin":
        sibling_skills += [p.parent for p in (skill_dir.parents[2] / "skills").glob("*/SKILL.md")]
    for link in re.findall(r"references/[\w\-/]+\.md", text):
        if not any((d / link).is_file() for d in [md.parent, skill_dir, *sibling_skills]):
            problems.append(f"{rel}: broken link {link}")
    for anchor in re.findall(r"[\w\-]+\.md#[\w\-]+", text):
        problems.append(f"{rel}: anchor link {anchor} (omp can't read anchors; link the file)")

for path in iter_files():
    rel = path.relative_to(ROOT)
    if not path.is_file() or rel.name.upper().startswith(("LICENSE", "NOTICE")):
        continue
    if any(rel == exempt or exempt in rel.parents for exempt in WHITE_LABEL_EXEMPT):
        continue
    text = path.read_bytes().decode("utf-8", errors="ignore")
    for number, line in enumerate(text.splitlines(), 1):
        for match in BANNED.finditer(line):
            problems.append(f"{rel}:{number}: banned name {match.group(0)!r}")
    if BANNED.search(str(rel)):
        problems.append(f"{rel}: banned name in path")

skill_root = ROOT / "plugins/deepmodebot/skills/deepmodebot"

# README counts must match the folders.
counts = re.search(r"(\d+) playbooks, (\d+) principles and (\d+) techniques", (ROOT / "README.md").read_text(encoding="utf-8"))
actual = tuple(len(list((skill_root / "references" / kind).glob("*.md"))) for kind in ("playbooks", "principles", "techniques"))
if not counts or tuple(map(int, counts.groups())) != actual:
    problems.append(f"README.md: says {counts.groups() if counts else 'no'} playbooks, principles, techniques; the folders hold {actual}")

# Process files: every playbook and technique says when it is done, and core lines stay one instruction long.
for kind in ("playbooks", "techniques"):
    for md in sorted((skill_root / "references" / kind).glob("*.md")):
        if "Done when" not in md.read_text(encoding="utf-8"):
            problems.append(f"{md.relative_to(ROOT)}: no 'Done when' completion criterion")
core_mds = sorted({
    *ROOT.glob("plugins/*/skills/*/SKILL.md"),
    *(skill_root / "references").glob("playbooks/*.md"),
    *(skill_root / "references").glob("techniques/*.md"),
    *ROOT.glob("plugins/*/.antigravity-plugin/skills/*/SKILL.md"),
})
for md in core_mds:
    text = md.read_text(encoding="utf-8")
    body_start = text.find("\n---\n", 4) + 5 if text.startswith("---\n") else 0  # the frontmatter hook is one line
    for number, line in enumerate(text[body_start:].splitlines(), text[:body_start].count("\n") + 1):
        if len(line.encode("utf-8")) > CORE_LINE_BYTES:
            problems.append(f"{md.relative_to(ROOT)}:{number}: line is {len(line.encode('utf-8'))} bytes "
                            f"(max {CORE_LINE_BYTES} in core files; split it)")

# references/catalog.md must list every playbook, principle, and technique file.
catalog_path = skill_root / "references/catalog.md"
if not catalog_path.is_file():
    problems.append(f"{catalog_path.relative_to(ROOT)}: missing catalog.md")
else:
    catalog_text = catalog_path.read_text(encoding="utf-8")
    for kind in ("playbooks", "principles", "techniques"):
        for md in sorted((skill_root / "references" / kind).glob("*.md")):
            if md.name not in catalog_text and f"`{md.stem}`" not in catalog_text:
                problems.append(f"{catalog_path.relative_to(ROOT)}: missing entry for {kind}/{md.name}")

# Every shipped command file must be registered in antigravity-guard.mjs SLASH_COMMANDS.
plugin_root = skill_root.parents[1]
guard_mjs = plugin_root / "scripts/antigravity-guard.mjs"
if guard_mjs.is_file():
    guard_text = guard_mjs.read_text(encoding="utf-8")
    m_cmds = re.search(r"const\s+SLASH_COMMANDS\s*=\s*\[(.*?)\];", guard_text, re.S)
    guard_cmds = set(re.findall(r'"(/[^"]+)"', m_cmds.group(1))) if m_cmds else set()
    for cmd_md in sorted((plugin_root / "commands").glob("*.md")):
        token = f"/{cmd_md.stem}"
        if token not in guard_cmds:
            problems.append(
                f"{guard_mjs.relative_to(ROOT)}: SLASH_COMMANDS is missing {token!r} for {cmd_md.relative_to(ROOT)}"
            )

# Library skills carry the date their facts were checked; an old one is reported, not failed.
for name in LIBRARY_SKILLS:
    head = (ROOT / "plugins/deepmodebot/skills" / name / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
    stamp = re.search(r'^\s+as-of:\s*"?(\d{4}-\d{2}-\d{2})"?\s*$', head, re.M)
    if not stamp:
        problems.append(f"plugins/deepmodebot/skills/{name}/SKILL.md: frontmatter needs metadata.as-of: YYYY-MM-DD")
    elif (dt.date.today() - dt.date.fromisoformat(stamp.group(1))).days > STALE_AFTER_DAYS:
        print(f"note: {name} facts are as of {stamp.group(1)}, over {STALE_AFTER_DAYS} days old; recheck and restamp")

# docs/llms-full.txt embeds whole files; each embedded copy must match its source. --fix rewrites it.
llms = ROOT / "docs/llms-full.txt"
blob_base = "https://github.com/TimothyVang/deepmodebot/blob/main/"
pieces = re.split(r"\n\n---\n\nSource: (\S+)\n\n", llms.read_text(encoding="utf-8"))
fresh = pieces[0] + "".join(
    f"\n\n---\n\nSource: {url}\n\n" + (ROOT / url.removeprefix(blob_base)).read_text(encoding="utf-8") for url in pieces[1::2])
if fresh != llms.read_text(encoding="utf-8"):
    if "--fix" in sys.argv:
        llms.write_text(fresh, encoding="utf-8", newline="\n")
        print("fixed: docs/llms-full.txt")
    else:
        problems.append("docs/llms-full.txt: embedded files are stale; run `python scripts/check.py --fix`")

# SKILL.md puts the rules that must survive compaction first; the lookup tables start at "## Routes".
skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
skill_bytes = skill_text.encode("utf-8")
fm_end = skill_text.find("\n---\n", 4)
skill_body_bytes = len(skill_text[fm_end + 5:].encode("utf-8")) if skill_text.startswith("---\n") and fm_end >= 0 else len(skill_bytes)
if skill_body_bytes > SKILL_BODY_MAX_BYTES:
    problems.append(
        f"plugins/deepmodebot/skills/deepmodebot/SKILL.md: body is {skill_body_bytes} bytes "
        f"(max {SKILL_BODY_MAX_BYTES} under Antigravity's 24 KB limit)"
    )
window = skill_bytes.find(b"\n## Routes\n")
if window < 0 or window > RULES_WINDOW_BYTES:
    problems.append(f"plugins/deepmodebot/skills/deepmodebot/SKILL.md: '## Routes' starts at byte {window}; the rules before it must fit in {RULES_WINDOW_BYTES} bytes")

# Every shipped Node ESM script parses cleanly when node is available.
node_exe = shutil.which("node")
if node_exe:
    for mjs in sorted(ROOT.glob("plugins/*/scripts/*.mjs")):
        node_check = subprocess.run([node_exe, "--check", str(mjs)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if node_check.returncode:
            problems.append(f"{mjs.relative_to(ROOT)}: node --check failed\n{(node_check.stdout + node_check.stderr).strip()}")

# Validate Antigravity plugin manifests when agy is on PATH (0 errors, 0 truncation warnings).
agy_exe = shutil.which("agy")
if agy_exe:
    for agy_manifest in sorted(ROOT.glob("plugins/*/.antigravity-plugin/plugin.json")):
        pdir = agy_manifest.parent.parent
        agy_run = subprocess.run([agy_exe, "plugin", "validate", str(pdir), "--json"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if agy_run.returncode:
            problems.append(f"{pdir.relative_to(ROOT)}: agy plugin validate exited {agy_run.returncode}\n"
                            f"{(agy_run.stdout + agy_run.stderr).strip()[-2000:]}")
        else:
            try:
                report = json.loads(agy_run.stdout)
            except ValueError as err:
                problems.append(f"{pdir.relative_to(ROOT)}: agy plugin validate returned invalid JSON ({err})")
            else:
                for item in report.get("findings") or []:
                    sev = str(item.get("severity") or "").lower()
                    msg = str(item.get("message") or "")
                    if sev == "error" or "truncat" in msg.lower():
                        problems.append(f"{pdir.relative_to(ROOT)}: agy plugin validate {sev}: {item.get('file')}: {msg}")

# Every skill's own references and skill:// links resolve (check_skill.py, the per-skill checker).
skill_dirs = sorted(str(p.parent) for p in [
    *ROOT.glob("plugins/*/skills/*/SKILL.md"),
    *ROOT.glob("plugins/*/.antigravity-plugin/skills/*/SKILL.md"),
])
run = subprocess.run([sys.executable, str(skill_root / "scripts/check_skill.py"), *skill_dirs],
                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
if run.returncode:
    problems.append(f"check_skill.py found problems:\n{(run.stdout + run.stderr).strip()[-3000:]}")

# Every shipped Python file parses, and every test folder passes.
test_dirs = set()
for py in iter_files(".py"):
    try:
        ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    except SyntaxError as err:
        problems.append(f"{py.relative_to(ROOT)}:{err.lineno}: {err.msg}")
    if py.name.startswith("test_"):
        test_dirs.add(py.parent)
test_tmp = ROOT / ".scratch/tmp" / f"check-{os.getpid()}"
test_tmp.mkdir(parents=True, exist_ok=True)
sorted_dirs = sorted(test_dirs)


def _run_test_dir(item):
    idx, test_dir = item
    sub_tmp = test_tmp / f"d{idx}"
    sub_tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "TMP": str(sub_tmp), "TEMP": str(sub_tmp), "TMPDIR": str(sub_tmp)}
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(test_dir), "-p", "test_*.py"],
                         env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    return test_dir, run


try:
    workers = min(4, len(sorted_dirs)) or 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_test_dir, enumerate(sorted_dirs)))
    for test_dir, run in results:
        if run.returncode:
            problems.append(f"{test_dir.relative_to(ROOT)}: tests failed\n{run.stderr[-3000:]}")
        elif run.stderr.splitlines() and "skipped" in run.stderr.splitlines()[-1]:
            print(f"note: {test_dir.relative_to(ROOT)}: {run.stderr.splitlines()[-1]} ({'bun' if shutil.which('bun') else 'no bun'} on PATH)")
finally:
    shutil.rmtree(test_tmp, ignore_errors=True)

# AGENTS.md and CLAUDE.md carry the current generated block (agents_md.py, writing-for-agents technique).
agents_md = skill_root / "assets/agents-md/agents_md.py"
run = subprocess.run([sys.executable, str(agents_md), "check", str(ROOT)],
                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
if run.returncode:
    problems.append(f"{run.stdout.strip()}\n  fix: python {agents_md.relative_to(ROOT).as_posix()} build .")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print("OK")
