#!/usr/bin/env node
// Antigravity lifecycle hook: enforce deepmodebot "Contain the work" write boundaries.
// PreInvocation marks a conversation active when lastUserInput invokes a deepmodebot slash command
// (pruning marks older than 30 days). PreToolUse blocks file writes outside the project root once
// active (or unconditionally when invoked with CLI argument "enforce"). Always exits 0 because
// Antigravity treats non-zero hook exits as execution errors and fails open.

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const MARK_MAX_AGE_MS = 30 * 24 * 3600 * 1000;
const caseless = process.platform === "win32" || process.platform === "darwin";

const WRITE_TOOLS = new Set([
  "write_file",
  "edit_file",
  "write_to_file",
  "replace_file_content",
  "multi_replace_file_content",
]);

// Kept as explicit slash tokens so scripts/whitelabel.py rebrands both /deepmodebot: and /deep.
const SLASH_PREFIX = "/deepmodebot:";
const SLASH_COMMANDS = [
  "/deep",
  "/deepmodebot",
  "/tournament",
  "/review-pr",
  "/land-pr",
  "/pr-thread",
  "/contribute",
  "/project-brief",
];

function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildActivationRegex() {
  const names = SLASH_COMMANDS.map(cmd => escapeRegex(cmd.slice(1)));
  const prefix = escapeRegex(SLASH_PREFIX.slice(1));
  return new RegExp(`^\\s*/(?:${prefix})?(?:${names.join("|")})\\b`);
}

const ACTIVATION_RE = buildActivationRegex();

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

function projectRoots(cwd) {
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
    if (lines.length < 2) return [cwd];
    const [toplevel, common] = lines;
    return path.basename(common) === ".git" ? [toplevel, path.dirname(common)] : [toplevel];
  } catch {
    return [cwd];
  }
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

function markSessionActive(markPath) {
  const folder = path.dirname(markPath);
  fs.mkdirSync(folder, { recursive: true });
  const now = Date.now();
  try {
    for (const entry of fs.readdirSync(folder)) {
      const candidate = path.join(folder, entry);
      try {
        const stat = fs.statSync(candidate);
        if (now - stat.mtimeMs > MARK_MAX_AGE_MS) {
          fs.unlinkSync(candidate);
        }
      } catch {
        // Ignore concurrent removals.
      }
    }
  } catch {
    // Ignore directory scan errors.
  }
  fs.writeFileSync(markPath, "", "utf8");
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
    if (markPath && ACTIVATION_RE.test(promptText)) {
      try {
        markSessionActive(markPath);
      } catch {
        // Unable to persist session mark; continue without failing the turn.
      }
    }
    writeJsonAndExit({});
    return;
  }

  if (mode !== "enforce" && !(markPath && fs.existsSync(markPath))) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }

  const toolCall = event.toolCall && typeof event.toolCall === "object" ? event.toolCall : {};
  const toolName = String(toolCall.name ?? "");
  if (!WRITE_TOOLS.has(toolName)) {
    writeJsonAndExit({ decision: "allow" });
    return;
  }

  const args = toolCall.args && typeof toolCall.args === "object" ? toolCall.args : {};
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
