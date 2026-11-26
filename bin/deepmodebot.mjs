#!/usr/bin/env node
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import { fileURLToPath } from "node:url";
import { disableAutoUpdate, enableAutoUpdate } from "../lib/autoupdate.mjs";
import { CLIENTS, clientById } from "../lib/clients.mjs";
import { parseJson, run, which } from "../lib/run.mjs";
import { upgradeDecision } from "../lib/version.mjs";
import { clearState, log, readState, withLock, writeState } from "../lib/state.mjs";

const PKG = "deepmodebot";
const here = dirname(realpathSync(fileURLToPath(import.meta.url)));
const pkgRoot = resolve(here, "..");
const version = JSON.parse(readFileSync(join(pkgRoot, "package.json"), "utf8")).version;

const args = process.argv.slice(2);
const cmd = args.find((a) => !a.startsWith("-")) ?? "help";
const flag = (name) => args.includes(`--${name}`);
const option = (name) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : args.find((a) => a.startsWith(`--${name}=`))?.slice(name.length + 3);
};
const quiet = flag("quiet");
const say = (msg) => {
  if (!quiet) console.log(msg);
};

const HELP = `deepmodebot ${version}: install and auto-update the deepmodebot plugin in Claude Code, omp, Codex, and Google Antigravity.

Usage: deepmodebot <command>

  setup      Install the plugin into every detected tool, turn on auto-update, and bootstrap current git repo
             --clients claude,omp,codex,agy   only these tools
             --dry-run                        show the plan, change nothing
             --no-auto-update                 skip the hourly task
             --no-init                        skip bootstrapping current git repo (AGENTS.md/CLAUDE.md/CI/memory)
             --yes                            do not ask before changing anything
  init       Bootstrap a project with .deepmodebot/ci.yml, policy.xml, memory DB, and AGENTS.md/CLAUDE.md
             [dir]                            target repo directory (default: current directory)
             --check                          exit 1 if project setup is incomplete
    --install-hooks  install <1s .git/hooks/pre-commit running zero-token slop gate
    --dependabot     also generate .github/dependabot.yml with 7-day cooldown
  gate [sub]         Run parallel check gate (slop|ci|perf|ui|seo|docs|sec|cleanup|agents|skill-check|map|guard)
  net [sub]          Run native concurrent Go engine (trending|pr-overlap|fetch-papers|webhook)
  build-native       Compile zero-dep Rust (dmb-gate) and Go (dmb-net) release binaries
  update             Upgrade this npm package, then re-sync the tools setup configured (--quiet for the hourly task)
  doctor             Show each tool's installed version next to this package's version
  uninstall  Remove the plugin from the configured tools and stop auto-update
  version    Print the package version

Run once with: npx deepmodebot@latest setup`;

// Use the npm that ships beside the node running us. A scheduled task can see a different
// `npm` on PATH (another Node install), which warns on stderr or targets another global root.
const bundledNpm = join(dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js");
const npm = (npmArgs) => (existsSync(bundledNpm) ? run(process.execPath, [bundledNpm, ...npmArgs]) : run("npm", npmArgs));

/** The global npm root; the plugin must live there so tool configs never point into a temporary npx cache. */
function globalRoot() {
  const r = npm(["root", "-g"]);
  const root = r.code === 0 ? r.stdout.split(/\r?\n/).pop()?.trim() : undefined;
  return root && existsSync(root) ? root : undefined;
}

const isGlobalInstall = () => {
  const root = globalRoot();
  return root !== undefined && resolve(root, PKG).toLowerCase() === pkgRoot.toLowerCase();
};

const ctx = { run, pkgRoot, version };

function detectClients(only) {
  const wanted = only ? only.split(",").map((s) => s.trim()) : CLIENTS.map((c) => c.id);
  const unknown = wanted.filter((id) => !clientById(id));
  if (unknown.length) throw new Error(`unknown client(s): ${unknown.join(", ")} (use claude, omp, codex, agy)`);
  return wanted.map(clientById).filter((c) => which(c.bin));
}

function syncClients(ids) {
  const results = [];
  for (const id of ids) {
    const client = clientById(id);
    if (!client || !which(client.bin)) {
      results.push({ id, ok: false, detail: "not on PATH, skipped" });
      continue;
    }
    let res;
    try {
      res = client.ensure(ctx);
    } catch (e) {
      res = { ok: false, detail: String(e.message ?? e) };
    }
    results.push({ id, ...res });
  }
  return results;
}

function report(results) {
  for (const r of results) say(`  ${r.ok ? "ok  " : "FAIL"} ${clientById(r.id)?.label ?? r.id}: ${r.detail}`);
  return results.every((r) => r.ok);
}

async function confirm(question) {
  if (flag("yes") || !process.stdin.isTTY) return true;
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = (await rl.question(`${question} [Y/n] `)).trim().toLowerCase();
  rl.close();
  return answer === "" || answer === "y" || answer === "yes";
}

async function setup() {
  if (!isGlobalInstall() && !flag("dry-run")) {
    // Running from npx: install globally first so every tool points at a folder that stays put.
    say(`Installing ${PKG}@${version} globally so the tools have a stable copy...`);
    const r = npm(["install", "-g", `${PKG}@${version}`]);
    if (r.code !== 0) throw new Error(`npm install -g failed: ${r.out.slice(-400)}`);
    const root = globalRoot();
    const r2 = run(process.execPath, [join(root, PKG, "bin", "deepmodebot.mjs"), ...args]);
    console.log(r2.out);
    return r2.code;
  }
  const clients = detectClients(option("clients"));
  if (!clients.length) {
    console.log("No supported tool found on PATH (claude, omp, codex, agy).");
    return 1;
  }
  const gitRoot = findGitRoot(process.cwd());
  const doInit = Boolean(gitRoot) && !flag("no-init");
  say(`deepmodebot ${version} from ${pkgRoot}`);
  say("Plan:");
  for (const c of clients) say(`  - ${c.label}: install or update the deepmodebot plugin from this package`);
  const auto = !flag("no-auto-update");
  if (auto) say("  - turn on hourly auto-update (deepmodebot update --quiet)");
  if (doInit) say(`  - bootstrap ${gitRoot} (.deepmodebot/ci.yml, policy.xml, memory DB, AGENTS.md, CLAUDE.md)`);
  if (flag("dry-run")) return 0;
  if (!(await confirm("Apply?"))) return 1;

  const results = syncClients(clients.map((c) => c.id));
  const ok = report(results);
  const state = { clients: clients.map((c) => c.id), autoUpdate: auto, version, lastResult: results };
  if (auto) {
    const r = enableAutoUpdate({ run, node: process.execPath, bin: join(pkgRoot, "bin", "deepmodebot.mjs") });
    say(`  ${r.ok ? "ok  " : "FAIL"} auto-update: ${r.detail}`);
    state.autoUpdate = r.ok;
  }
  writeState(state);
  if (doInit) {
    const ir = runProjectInit(gitRoot, false);
    say(`  ${ir.code === 0 ? "ok  " : "FAIL"} project-init: ${ir.out.trim() || "done"}`);
  }
  say(ok ? "Done. Restart open tools to load the new version." : "Some tools failed; the hourly update retries them.");
  return ok ? 0 : 1;
}

function findGitRoot(startDir) {
  let cur = resolve(startDir);
  while (true) {
    if (existsSync(join(cur, ".git"))) return cur;
    const parent = dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

function findPython() {
  if (process.platform === "win32" && which("py")) return ["py", ["-3", "-B"]];
  if (which("python3")) return ["python3", ["-B"]];
  if (which("python")) return ["python", ["-B"]];
  return null;
}

function runProjectInit(targetDir, checkOnly, extraFlags = []) {
  const py = findPython();
  if (!py) return { code: 1, out: "python 3 not found on PATH" };
  const script = join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "setup", "project_setup.py");
  if (!existsSync(script)) return { code: 1, out: `project_setup.py missing at ${script}` };
  const [exe, prefix] = py;
  const cliArgs = [...prefix, script, "--root", resolve(targetDir), ...(checkOnly ? ["--check"] : []), ...extraFlags];
  return run(exe, cliArgs);
}

function init() {
  const pos = args.filter((a) => !a.startsWith("-"));
  const targetDir = pos[1] || process.cwd();
  const extra = [];
  if (flag("install-hooks")) extra.push("--install-hooks");
  if (flag("dependabot")) extra.push("--dependabot");
  const res = runProjectInit(targetDir, flag("check"), extra);
  if (res.out.trim()) console.log(res.out.trim());
  return res.code;
}

function findNativeGate() {
  const ext = process.platform === "win32" ? ".exe" : "";
  const localBin = join(pkgRoot, "native", "dmb-gate", "target", "release", `dmb-gate${ext}`);
  if (existsSync(localBin)) return localBin;
  if (which(`dmb-gate${ext}`)) return `dmb-gate${ext}`;
  return null;
}

function gate() {
  const passArgs = args.slice(1);
  const sub = passArgs[0] && !passArgs[0].startsWith("-") ? passArgs[0] : "slop";
  const pyOnly = new Set(["seo", "docs", "sec"]);
  const nativeBin = pyOnly.has(sub) ? null : findNativeGate();
  if (nativeBin) {
    const res = run(nativeBin, passArgs);
    if (res.out.trim()) console.log(res.out.trim());
    return res.code;
  }
  const py = findPython();
  if (!py) {
    console.error("Neither native dmb-gate nor python 3 found.");
    return 1;
  }
  const rest = passArgs[0] === sub ? passArgs.slice(1) : passArgs;
  const map = {
    slop: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "local-ci", "slop_gate.py"),
    ci: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "local-ci", "local_ci.py"),
    perf: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "perf-audit", "perf_audit.py"),
    ui: join(pkgRoot, "plugins", "deepmodebot", "skills", "frontend-ui", "scripts", "ui_audit.py"),
    seo: join(pkgRoot, "plugins", "deepmodebot", "skills", "seo-and-geo", "scripts", "seo_audit.py"),
    docs: join(pkgRoot, "plugins", "deepmodebot", "skills", "office-documents", "scripts", "doc_audit.py"),
    sec: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "security-audit", "static_sec_audit.py"),
    cleanup: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "cleanup", "self_cleanup.py"),
    agents: join(pkgRoot, "plugins", "deepmodebot", "skills", "deepmodebot", "assets", "agents-md", "agents_md.py"),
  };
  const script = map[sub] || map.slop;
  const [exe, prefix] = py;
  const res = run(exe, [...prefix, script, ...rest]);
  if (res.out.trim()) console.log(res.out.trim());
  return res.code;
}

function findNativeNet() {
  const ext = process.platform === "win32" ? ".exe" : "";
  const localBin = join(pkgRoot, "native", "dmb-net", "bin", `dmb-net${ext}`);
  if (existsSync(localBin)) return localBin;
  if (which(`dmb-net${ext}`)) return `dmb-net${ext}`;
  return null;
}

function net() {
  const passArgs = args.slice(1);
  const bin = findNativeNet();
  if (!bin) {
    console.error("dmb-net binary not built yet. Run: deepmodebot build-native");
    return 1;
  }
  const res = run(bin, passArgs);
  if (res.out.trim()) console.log(res.out.trim());
  return res.code;
}

function buildNative() {
  const ext = process.platform === "win32" ? ".exe" : "";
  let code = 0;
  const cargoManifest = join(pkgRoot, "native", "dmb-gate", "Cargo.toml");
  if (existsSync(cargoManifest) && which("cargo")) {
    const r = run("cargo", ["build", "--release", "--manifest-path", cargoManifest]);
    if (r.out.trim()) console.log(r.out.trim());
    if (r.code !== 0) code = r.code;
  }
  const goDir = join(pkgRoot, "native", "dmb-net");
  if (existsSync(join(goDir, "go.mod")) && which("go")) {
    const outBin = join(goDir, "bin", `dmb-net${ext}`);
    const r = run("go", ["build", "-C", goDir, "-ldflags=-s -w", "-o", outBin, "."]);
    if (r.out.trim()) console.log(r.out.trim());
    if (r.code !== 0) code = r.code;
  }
  return code;
}

function update() {
  const state = readState();
  if (!state.clients?.length) {
    console.log("Nothing configured yet. Run: npx deepmodebot@latest setup");
    return 1;
  }
  // The hand-off child runs while its parent holds the lock; it must not wait on that lock.
  const lockHeld = flag("no-self-update") && process.env.DEEPMODEBOT_LOCK_HELD === "1";
  const outcome = (lockHeld ? (fn) => fn() : withLock)(() => {
    if (!flag("no-self-update")) {
      // Read the registry's latest manifest first and install only a stable, newer release that ships
      // the command: npm's first-publish placeholder (0.0.0-stage, no bin) once replaced a working install.
      const view = npm(["view", `${PKG}@latest`, "name", "version", "bin", "--json"]);
      const latest = view.code === 0 ? parseJson(view.stdout) : undefined;
      const decision = latest ? upgradeDecision(version, latest) : { install: false, reason: "registry unreachable" };
      if (decision.install) {
        const r = npm(["install", "-g", `${PKG}@${latest.version}`]);
        const root = globalRoot();
        const installedBin = root && join(root, PKG, "bin", "deepmodebot.mjs");
        if (r.code !== 0 || !installedBin || !existsSync(installedBin) || readInstalledVersion(root) !== latest.version) {
          log(`upgrade to ${latest.version} failed or left no command; restoring ${version}: ${r.out.slice(-200)}`);
          npm(["install", "-g", `${PKG}@${version}`]);
          say(`npm upgrade failed; kept ${version}`);
        } else {
          log(`upgraded ${decision.reason}`);
        }
      } else {
        say(`no upgrade: ${decision.reason}`);
      }
      // Hand off to the freshly installed copy so new client logic runs this sync.
      const root = globalRoot();
      const candidate = root && join(root, PKG, "bin", "deepmodebot.mjs");
      const fresh = candidate && existsSync(candidate) ? candidate : undefined;
      const isOtherCopy = fresh && resolve(fresh).toLowerCase() !== resolve(here, "deepmodebot.mjs").toLowerCase();
      const wasUpgraded = fresh && readInstalledVersion(root) !== version;
      if (isOtherCopy || wasUpgraded) {
        process.env.DEEPMODEBOT_LOCK_HELD = "1";
        const r2 = run(process.execPath, [fresh, "update", "--no-self-update", ...(quiet ? ["--quiet"] : [])]);
        if (!quiet) console.log(r2.out);
        return { code: r2.code };
      }
    }
    const results = syncClients(state.clients);
    const ok = report(results);
    writeState({ ...state, version, lastResult: results, lastUpdate: new Date().toISOString() });
    log(`${version}: ${results.map((r) => `${r.id}=${r.ok ? "ok" : "FAIL"} (${r.detail})`).join("; ")}`);
    return { code: ok ? 0 : 1 };
  });
  if (outcome.skipped) {
    say("Another update is running; skipped.");
    return 0;
  }
  return outcome.code;
}

function readInstalledVersion(root) {
  try {
    return JSON.parse(readFileSync(join(root, PKG, "package.json"), "utf8")).version;
  } catch {
    return undefined;
  }
}

function doctor() {
  const state = readState();
  console.log(`deepmodebot package ${version} at ${pkgRoot}${isGlobalInstall() ? "" : " (not the global install)"}`);
  console.log(`auto-update: ${state.autoUpdate ? "on" : "off"}${state.lastUpdate ? `, last run ${state.lastUpdate}` : ""}`);
  let ok = true;
  for (const c of CLIENTS) {
    if (!which(c.bin)) {
      console.log(`  -    ${c.label}: not on PATH`);
      continue;
    }
    const v = c.installedVersion(run);
    const managed = state.clients?.includes(c.id);
    const good = v === version;
    if (managed && !good) ok = false;
    console.log(`  ${good ? "ok  " : managed ? "FAIL" : "-   "} ${c.label}: ${v ?? "not installed"}${managed ? "" : " (not managed by setup)"}`);
  }
  return ok ? 0 : 1;
}

function uninstall() {
  const state = readState();
  for (const id of state.clients ?? []) {
    const c = clientById(id);
    if (c && which(c.bin)) say(`  ${c.label}: ${c.uninstall(ctx).detail}`);
  }
  disableAutoUpdate({ run });
  clearState();
  say(`Removed. To remove the package itself: npm uninstall -g ${PKG}`);
  return 0;
}

const commands = { setup, init, gate, net, "build-native": buildNative, update, doctor, uninstall, version: () => (console.log(version), 0), help: () => (console.log(HELP), 0) };
const handler = flag("version") ? commands.version : flag("help") || flag("h") ? commands.help : commands[cmd];
if (!handler) {
  console.error(`Unknown command: ${cmd}\n\n${HELP}`);
  process.exit(2);
}
try {
  process.exitCode = await handler();
} catch (e) {
  console.error(`deepmodebot: ${e.message ?? e}`);
  log(`error in ${cmd}: ${e.message ?? e}`);
  process.exitCode = 1;
}

