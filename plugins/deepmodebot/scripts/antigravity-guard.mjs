#!/usr/bin/env node
// Antigravity lifecycle hook: enforce deepmodebot "Contain the work" write boundaries and
// auto-inject a compact workspace-map overview once per conversation on turn 1.
// PreInvocation marks a conversation active when lastUserInput invokes a deepmodebot slash command
// (pruning marks older than 30 days) and injects workspace-map output inside git repos via
// injectSteps (deduplicated across tool-loop invocations and subsequent turns). PreToolUse blocks
// file writes outside the project root once active (or unconditionally when invoked with CLI
// argument "enforce"). Rule approval (skills/deepmodebot/assets/rules/rule_ledger.py) applies in
// every conversation: in a repo whose owner turned it on, file writes to agent rule files or the
// ledger and shell commands that write them are denied, and the owner-only
// `rules init|approve|reject|rotate` commands are denied everywhere. Other shell commands,
// workflows (run_workflow), and MCP tools are not covered here. Always exits 0 because
// Antigravity treats non-zero hook exits as execution errors and fails open.

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const MARK_MAX_AGE_MS = 30 * 24 * 3600 * 1000;
const WORKSPACE_MAP_TIMEOUT_MS = 7_000;
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WORKSPACE_MAP_SCRIPT = path.resolve(
  SCRIPT_DIR,
  "../skills/deepmodebot/assets/workspace-map/workspace_map.py",
);
const caseless = process.platform === "win32" || process.platform === "darwin";
const RULES_DIR = path.resolve(SCRIPT_DIR, "../skills/deepmodebot/assets/rules");
const RULE_LEDGER = path.join(RULES_DIR, "rule_ledger.py");
const LEDGER_REL = path.join(".deepmodebot", "rules", "ledger.json");
const PYTHONS =
  process.platform === "win32"
    ? [["py", ["-3", "-B"]], ["python3", ["-B"]], ["python", ["-B"]]]
    : [["python3", ["-B"]], ["python", ["-B"]]];
const RULES = loadRuleSpec();

const WRITE_TOOLS = new Set([
  "write_file",
  "edit_file",
  "write_to_file",
  "replace_file_content",
  "multi_replace_file_content",
]);
const SHELL_TOOLS = new Set(["run_command", "execute_command", "bash"]);
const METRIC_FLOORS = {
  iou: 0.5, ssim: 0.5, dice: 0.5, f1: 0.5, auc: 0.5,
  accuracy: 0.5, acc: 0.5, precision: 0.5, recall: 0.5,
  fidelity: 0.5, similarity: 0.5, coverage: 0.5, "pass-rate": 0.5, "win-rate": 0.5,
  clip: 0.15, "clip-score": 0.15, ap: 0.15, map: 0.15, bleu: 0.15, rouge: 0.15,
  psnr: 10.0, protrusion: 0.02, score: 0.05, confidence: 0.05, symmetry: 0.05,
  "cov-fail-under": 50.0,
};
const MIN_FLAG_VAL_RE =
  /(?:^|[\s;&|(])(['"]?--(?:(?:gate-)?mi(?:n(?:-([a-z0-9_-]*))?)?|(cov-fail-under))['"]?(?:\s+|=)['"]?\s*([-+]?(?:inf(?:inity)?|nan|(?:\d[\d_]*\.?[\d_]*|\.[\d_]+)(?:e[-+]?[\d_]+)?))\s*['"]?)(?=$|[\s;&|)])/gi;
const REWARD_HACK_CMD_RE = new RegExp(
  [
    String.raw`(?:^|[\s;&|(])--(?:skip-reference|skip-fidelity|skip-gates?|skip-verify|skip-validation|bypass-gate|pass-if-no-tests|passWithNoTests|no-cov)(?=$|[\s;&|)])`,
    String.raw`(?:^|[\s;&|(])(?:--require-spark-receipt(?:\s+|=)['"]?false|--gate-mode(?:\s+|=)['"]?off|--measured-gates(?:\s+|=)['"]?off|--check-360(?:\s+|=)['"]?(?:false|0))['"]?(?=$|[\s;&|)])`,
    String.raw`\bgit\b[^\n;&|]*\bcommit\b[^\n;&|]*\s(?:-n|--no-verify)(?=$|[\s;&|)])`,
    String.raw`\b(?:reward-guard\.db|contract-lock\.json|judge_verdicts)\b`,
    String.raw`\breward_guard\.py\b[^\n;&|]*\brecord-judge\b`,
  ].join("|"),
  "i",
);

function minFlagFloor(rawTok) {
  const tok = (rawTok ?? "").toLowerCase().replace(/_/g, "-");
  if (!tok) return 0.5;
  if (Object.hasOwn(METRIC_FLOORS, tok)) return METRIC_FLOORS[tok];
  const matches = Object.entries(METRIC_FLOORS)
    .filter(([k]) => k.startsWith(tok))
    .map(([, v]) => v);
  return matches.length ? Math.max(...matches) : null;
}
function parseGuardFloat(raw) {
  const c = String(raw).trim().replace(/_/g, "");
  if (/^[-+]?inf(?:inity)?$/i.test(c)) return c.startsWith("-") ? -Infinity : Infinity;
  if (/^[-+]?nan$/i.test(c)) return NaN;
  return Number(c);
}

// rule-paths.json, lowercased, for the cheap pre-check that decides whether rule_ledger.py needs to run at all.
function loadRuleSpec() {
  try {
    const spec = JSON.parse(fs.readFileSync(path.join(RULES_DIR, "rule-paths.json"), "utf8"));
    const low = xs => (Array.isArray(xs) ? xs.map(x => String(x).toLowerCase().replace(/^\/+|\/+$/g, "")) : []);
    const names = low(spec.names);
    const dirs = low(spec.dirs);
    const files = low(spec.files);
    return {
      names: new Set(names),
      dirs: dirs.map(d => `/${d}/`),
      files: files.map(f => `/${f}`),
      hints: [...names, ...files, ...dirs, ...dirs.map(d => d.split("/")[0]), "deepmodebot", "rule_ledger"],
    };
  } catch {
    return undefined;
  }
}

function mayBeRulePath(abs) {
  if (!RULES) return false;
  const p = abs.toLowerCase().replace(/\\/g, "/");
  return (
    RULES.names.has(p.slice(p.lastIndexOf("/") + 1)) ||
    p.includes("/.deepmodebot/rules") ||
    RULES.dirs.some(d => p.includes(d)) ||
    RULES.files.some(f => p.endsWith(f))
  );
}

// Whether the repo holding `abs` has an owner rule ledger in its working tree.
function ledgerNear(abs) {
  let dir = path.dirname(abs);
  while (true) {
    if (fs.existsSync(path.join(dir, LEDGER_REL))) return true;
    if (fs.existsSync(path.join(dir, ".git"))) return false;
    const parent = path.dirname(dir);
    if (parent === dir) return false;
    dir = parent;
  }
}

// rule_ledger.py guard verdict: a deny reason, "" to allow, or null when no Python could run it.
function pythonGuard(request) {
  for (const [exe, prefix] of PYTHONS) {
    try {
      const out = execFileSync(exe, [...prefix, RULE_LEDGER, "guard"], {
        input: JSON.stringify(request),
        encoding: "utf8",
        timeout: 8_000,
        stdio: ["pipe", "pipe", "ignore"],
        windowsHide: true,
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
      });
      const verdict = JSON.parse(out);
      return verdict && verdict.block ? String(verdict.reason) : "";
    } catch (err) {
      if (err && err.code === "ENOENT") continue;
      return "";
    }
  }
  return null;
}

// Python runs only for shell commands in a ledger repo or naming a rule path or owner command, and for writes whose
// target (or resolved target) looks like a rule path.
function ruleDenyReason(cwd, paths, command) {
  const candidates = paths.filter(p => mayBeRulePath(absolute(p, cwd)) || mayBeRulePath(real(absolute(p, cwd))));
  const lowered = command.toLowerCase().replace(/\\/g, "/");
  const hinted = Boolean(RULES && RULES.hints.some(h => lowered.includes(h)));
  const shell = command !== "" && (hinted || ledgerNear(path.join(cwd, "_")));
  if (candidates.length === 0 && !shell) return "";
  const verdict = pythonGuard({ cwd, paths: candidates, command: shell ? command : "" });
  if (verdict !== null) return verdict;
  return candidates.some(p => ledgerNear(absolute(p, cwd)))
    ? "deepmodebot rule approval needs Python 3 on PATH to check rule files; install it, then retry."
    : "";
}

function findShellRewardHack(rawCmd) {
  const cleaned = String(rawCmd ?? "").replace(/(-m|--message)(=|\s+)("[^"]*"|'[^']*')/g, '$1 ""');
  for (const rawLine of cleaned.replace(/\\\r?\n/g, " ").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || /^(?:grep|rg)\s+[^;&|`$]*$/.test(line)) continue;
    MIN_FLAG_VAL_RE.lastIndex = 0;
    let fm;
    while ((fm = MIN_FLAG_VAL_RE.exec(line)) !== null) {
      const floor = minFlagFloor(fm[3] || fm[2]);
      const val = parseGuardFloat(fm[4]);
      if (floor !== null && (!Number.isFinite(val) || val < floor)) return fm[1].trim();
    }
    const m = REWARD_HACK_CMD_RE.exec(line);
    if (m) return m[0].trim();
  }
  return null;
}

// Kept as explicit slash tokens so scripts/whitelabel.py rebrands both /deepmodebot: and /deep.
const SLASH_PREFIX = "/deepmodebot:";
const SLASH_COMMANDS = [
  "/deep",
  "/deepmodebot",
  "/suggest",
  "/research",
  "/tournament",
  "/review-pr",
  "/land-pr",
  "/pr-thread",
  "/contribute",
  "/project-brief",
];
// Read-only commands skip creating .scratch/workspace-map.db unless it already exists.
const READ_ONLY_MAP_COMMANDS = ["/review-pr", "/pr-thread"];

function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildCommandRegex(commands) {
  const names = commands.map(cmd => escapeRegex(cmd.slice(1)));
  const prefix = escapeRegex(SLASH_PREFIX.slice(1));
  return new RegExp(`^\\s*/(?:${prefix})?(?:${names.join("|")})\\b`);
}

const ACTIVATION_RE = buildCommandRegex(SLASH_COMMANDS);
const READ_ONLY_MAP_RE = buildCommandRegex(READ_ONLY_MAP_COMMANDS);

function homeDirectory() {
  return process.env.HOME || process.env.USERPROFILE || os.homedir();
}

function expandHome(p) {
  const home = homeDirectory();
  if (p === "~") return home;
  if (p.startsWith("~/") || p.startsWith("~\\")) return path.join(home, p.slice(2));
  return p;
}

function absolute(p, cwd) {
  return path.resolve(cwd, expandHome(p));
}

function stripWinNamespace(p) {
  return process.platform === "win32" ? p.replace(/^\\\\\?\\/, "") : p;
}

function real(p) {
  let resolved = path.resolve(expandHome(p));
  try {
    const fn = fs.realpathSync.native ?? fs.realpathSync;
    resolved = stripWinNamespace(fn(resolved));
  } catch {
    const parent = path.dirname(resolved);
    if (parent !== resolved) {
      resolved = path.join(real(parent), path.basename(resolved));
    }
  }
  return caseless ? resolved.toLowerCase() : resolved;
}

function inside(targetPath, rootPath) {
  const rel = path.relative(rootPath, targetPath);
  if (rel === "") return true;
  if (rel === ".." || rel.startsWith(".." + path.sep)) return false;
  return !path.isAbsolute(rel);
}

function gitProjectRoots(cwd) {
  try {
    const out = execFileSync(
      "git",
      ["-C", cwd, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
      { encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "ignore"], windowsHide: true },
    );
    const lines = out
      .split(/\r?\n/)
      .map(line => line.replace(/[\\/]+$/, ""))
      .filter(Boolean);
    if (lines.length < 2) return null;
    const [toplevel, common] = lines;
    return path.basename(common) === ".git" ? [toplevel, path.dirname(common)] : [toplevel];
  } catch {
    return null;
  }
}

function projectRoots(cwd) {
  return gitProjectRoots(cwd) ?? [cwd];
}

function workspaceMapDbPath(roots) {
  const envDb = typeof process.env.DEEPMODEBOT_MAP_DB === "string" ? process.env.DEEPMODEBOT_MAP_DB.trim() : "";
  if (envDb) return path.resolve(envDb);
  const mainCheckout = roots[roots.length - 1];
  return path.join(mainCheckout, ".scratch", "workspace-map.db");
}

function buildWorkspaceMapOverview(cwd, { onlyIfDbExists = false } = {}) {
  if (!fs.existsSync(WORKSPACE_MAP_SCRIPT)) return null;
  const roots = gitProjectRoots(cwd);
  if (!roots) return null;
  if (onlyIfDbExists && !fs.existsSync(workspaceMapDbPath(roots))) return null;

  const candidates =
    process.platform === "win32"
      ? [
          ["py", ["-3", "-B"]],
          ["python3", ["-B"]],
          ["python", ["-B"]],
        ]
      : [
          ["python3", ["-B"]],
          ["python", ["-B"]],
        ];
  const deadline = Date.now() + WORKSPACE_MAP_TIMEOUT_MS;
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };

  for (const [cmd, prefixArgs] of candidates) {
    const remaining = deadline - Date.now();
    if (remaining <= 100) break;
    try {
      const out = execFileSync(
        cmd,
        [
          ...prefixArgs,
          WORKSPACE_MAP_SCRIPT,
          "overview",
          cwd,
          "--fast",
          "--offline",
          "--no-orca",
          "--max-bytes",
          "1200",
        ],
        {
          encoding: "utf8",
          timeout: remaining,
          stdio: ["ignore", "pipe", "ignore"],
          windowsHide: true,
          env,
        },
      );
      const trimmed = typeof out === "string" ? out.trim() : "";
      return trimmed || null;
    } catch (err) {
      if (err && (err.code === "ETIMEDOUT" || err.killed)) {
        return null;
      }
      // Try next Python launcher if missing or unusable.
    }
  }
  return null;
}

function allowedRoots(roots, event) {
  const home = homeDirectory();
  const allowed = [
    ...roots,
    path.join(home, ".gemini", "antigravity", "brain"),
    path.join(home, ".gemini", "antigravity-cli", "brain"),
    path.join(home, ".gemini", "antigravity-ide", "brain"),
  ];
  if (typeof event.artifactDirectoryPath === "string" && event.artifactDirectoryPath.trim()) {
    allowed.push(expandHome(event.artifactDirectoryPath.trim()));
  }
  for (const root of roots) {
    try {
      const cfgPath = path.join(root, ".deepmodebot.json");
      const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
      const extra = cfg && typeof cfg === "object" ? cfg.extraWriteRoots : undefined;
      if (Array.isArray(extra)) {
        for (const item of extra) {
          if (typeof item === "string" && item.trim()) {
            allowed.push(absolute(item.trim(), root));
          }
        }
      }
    } catch {
      // Missing or unreadable .deepmodebot.json grants no extra roots.
    }
  }
  return allowed.map(real);
}

function sessionMarkPath(event) {
  const dataDir =
    process.env.PLUGIN_DATA ||
    path.join(homeDirectory(), ".gemini", "antigravity", "deepmodebot-guard");
  const rawId = String(event.conversationId ?? event.session_id ?? "");
  const cleanId = rawId.replace(/[^A-Za-z0-9_-]/g, "");
  return cleanId ? path.join(dataDir, "active-sessions", cleanId) : null;
}

function readMarkState(markPath) {
  try {
    const raw = fs.readFileSync(markPath, "utf8").trim();
    if (!raw) return { active: true, mapInjected: false };
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return { active: true, mapInjected: Boolean(parsed.mapInjected) };
    }
    return { active: true, mapInjected: false };
  } catch {
    return null;
  }
}

function writeMarkState(markPath, state) {
  fs.mkdirSync(path.dirname(markPath), { recursive: true });
  fs.writeFileSync(
    markPath,
    JSON.stringify({ active: true, mapInjected: Boolean(state && state.mapInjected) }),
    "utf8",
  );
}

function markSessionActive(markPath, prevState = null) {
  const folder = path.dirname(markPath);
  fs.mkdirSync(folder, { recursive: true });
  const now = Date.now();
  try {
    for (const entry of fs.readdirSync(folder)) {
      const candidate = path.join(folder, entry);
      try {
        const stat = fs.statSync(candidate);
        if (stat.isFile() && now - stat.mtimeMs > MARK_MAX_AGE_MS) {
          fs.unlinkSync(candidate);
        }
      } catch {
        // Ignore concurrent removals.
      }
    }
  } catch {
    // Ignore directory scan errors.
  }
  const existing = prevState ?? readMarkState(markPath);
  writeMarkState(markPath, { active: true, mapInjected: Boolean(existing && existing.mapInjected) });
}

function resolveSessionCwd(event) {
  if (typeof event.cwd === "string" && event.cwd.trim()) {
    return expandHome(event.cwd.trim());
  }
  if (Array.isArray(event.workspacePaths)) {
    const first = event.workspacePaths.find(p => typeof p === "string" && p.trim());
    if (first) return expandHome(first.trim());
  }
  return process.cwd();
}

function readStdinText() {
  try {
    return fs.readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function writeJsonAndExit(payload) {
  process.stdout.write(JSON.stringify(payload) + "\n");
  process.exit(0);
}

function main() {
  const mode = process.argv[2] === "enforce" ? "enforce" : "session";
  const raw = readStdinText();
  let event;
  try {
    event = JSON.parse(raw);
  } catch {
    process.stderr.write("deepmodebot contain guard: unreadable hook input; not blocking\n");
    writeJsonAndExit({});
    return;
  }
  if (!event || typeof event !== "object") {
    writeJsonAndExit({});
    return;
  }

  const markPath = sessionMarkPath(event);
  const promptText = String(event.lastUserInput ?? event.prompt ?? "");
  const isPreToolUse =
    event.hookEventName === "PreToolUse" ||
    (event.hookEventName == null && event.toolCall != null);

  if (!isPreToolUse) {
    if (ACTIVATION_RE.test(promptText)) {
      const prevState = markPath ? readMarkState(markPath) : null;
      if (markPath) {
        try {
          markSessionActive(markPath, prevState);
        } catch {
          // Unable to persist session mark; continue without failing the turn.
        }
      }
      const invocationNum = typeof event.invocationNum === "number" ? event.invocationNum : null;
      const alreadyInjected = Boolean(prevState && prevState.mapInjected);
      if (!alreadyInjected && (invocationNum === null || invocationNum <= 1)) {
        try {
          const onlyIfDbExists = READ_ONLY_MAP_RE.test(promptText);
          const overview = buildWorkspaceMapOverview(resolveSessionCwd(event), { onlyIfDbExists });
          if (overview) {
            if (markPath) {
              try {
                writeMarkState(markPath, { active: true, mapInjected: true });
              } catch {
                // Non-fatal: still return the overview for this invocation.
              }
            }
            writeJsonAndExit({
              injectSteps: [
                {
                  systemMessage: {
                    systemMessage: `deepmodebot workspace-map (auto-injected):\n${overview}`,
                    metadata: { source: "deepmodebot", kind: "workspace-map" },
                  },
                },
              ],
            });
            return;
          }
        } catch {
          // Fail open cleanly if workspace-map overview cannot be generated.
        }
      }
    }
    writeJsonAndExit({});
    return;
  }

  const toolCall = event.toolCall && typeof event.toolCall === "object" ? event.toolCall : {};
  const toolName = String(toolCall.name ?? "");
  const args = toolCall.args && typeof toolCall.args === "object" ? toolCall.args : {};
  const sessionCwd = resolveSessionCwd(event);
  const ruleTarget = args.Path ?? args.TargetFile ?? args.path ?? args.targetFile;
  const ruleCwd = SHELL_TOOLS.has(toolName) && typeof (args.Cwd ?? args.cwd) === "string"
    ? absolute(String(args.Cwd ?? args.cwd), sessionCwd)
    : sessionCwd;
  const ruleReason = SHELL_TOOLS.has(toolName)
    ? ruleDenyReason(ruleCwd, [], String(args.CommandLine ?? args.command ?? args.cmd ?? ""))
    : WRITE_TOOLS.has(toolName) && typeof ruleTarget === "string" && ruleTarget.trim()
      ? ruleDenyReason(sessionCwd, [ruleTarget.trim()], "")
      : "";
  if (ruleReason) {
    writeJsonAndExit({ decision: "deny", reason: ruleReason });
    return;
  }

  if (mode !== "enforce" && !(markPath && fs.existsSync(markPath))) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }

  if (SHELL_TOOLS.has(toolName)) {
    const cmdStr = args.CommandLine ?? args.command ?? args.cmd ?? "";
    const hit = findShellRewardHack(cmdStr);
    if (hit) {
      writeJsonAndExit({
        decision: "deny",
        reason: `deepmodebot anti-reward-hacking guard blocked "${hit}": builders may not zero thresholds, skip reference/verification gates, or tamper with provenance ledgers.`,
      });
      return;
    }
    writeJsonAndExit({ decision: "allow" });
    return;
  }
  if (!WRITE_TOOLS.has(toolName)) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }
  const target = args.Path ?? args.TargetFile ?? args.path ?? args.targetFile;
  if (typeof target !== "string" || !target.trim()) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }

  const cwd = resolveSessionCwd(event);
  const roots = projectRoots(cwd);
  if (!event.cwd && Array.isArray(event.workspacePaths)) {
    for (const ws of event.workspacePaths.slice(1)) {
      if (typeof ws === "string" && ws.trim()) {
        for (const extraRoot of projectRoots(expandHome(ws.trim()))) {
          if (!roots.includes(extraRoot)) roots.push(extraRoot);
        }
      }
    }
  }

  const resolvedTarget = real(absolute(target.trim(), cwd));
  const allowed = allowedRoots(roots, event);
  if (allowed.some(r => inside(resolvedTarget, r))) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }

  const root = path.normalize(roots[0]);
  const reason =
    `deepmodebot keeps all writes inside the project root ${root}. ${target} is outside it. ` +
    `Put scratch and temp files in ${path.join(root, ".scratch")} and worktrees in ` +
    `${path.join(root, ".worktrees")}. If the user explicitly named this path, add it to ` +
    `extraWriteRoots in ${path.join(root, ".deepmodebot.json")}.`;
  writeJsonAndExit({ decision: "deny", reason });
}

main();
