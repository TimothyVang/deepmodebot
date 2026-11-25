import { existsSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { parseJson } from "./run.mjs";
import { mirror, treeDiffs } from "./tree.mjs";

export function pruneStaleOmpShadows(skillsDir = join(homedir(), ".omp", "agent", "skills")) {
  const removed = [];
  for (const name of [PLUGIN, "deep-mode"]) {
    const p = join(skillsDir, name);
    if (existsSync(p)) {
      rmSync(p, { recursive: true, force: true });
      removed.push(name);
    }
  }
  return removed;
}
export const MARKETPLACE = "deepmodebot";
export const PLUGIN = "deepmodebot";
export const PLUGIN_ID = `${PLUGIN}@${MARKETPLACE}`;

const norm = (p) => resolve(String(p)).replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
const mentions = (value, path) => value !== undefined && JSON.stringify(value).replace(/\\\\/g, "/").toLowerCase().includes(norm(path));
const fail = (step, r) => ({ ok: false, detail: `${step} failed (${r.code}): ${r.out.split("\n").slice(-3).join(" ").slice(0, 300)}` });

/**
 * Point a marketplace-based CLI at the npm package folder, then install or update the plugin.
 * `api` describes one CLI: how to read its marketplace source and installed version, and its subcommands.
 */
function ensureViaMarketplace(api, ctx) {
  const { run, pkgRoot } = ctx;
  const source = api.marketplaceSource(run);
  const pointsHere = mentions(source, pkgRoot);
  if (source !== undefined && !pointsHere) {
    const r = run(api.bin, api.removeMarketplace);
    if (r.code !== 0) return fail("remove old marketplace", r);
  }
  if (!pointsHere) {
    const r = run(api.bin, [...api.addMarketplace, pkgRoot]);
    if (r.code !== 0) return fail("add marketplace", r);
  } else if (api.refreshMarketplace) {
    const r = run(api.bin, api.refreshMarketplace);
    if (r.code !== 0) return fail("refresh marketplace", r);
  }
  const before = api.installedVersion(run);
  if (before === undefined || before !== ctx.version) {
    const args = before === undefined ? api.install : api.update;
    const r = run(api.bin, args);
    if (r.code !== 0) return fail(before === undefined ? "install" : "update", r);
  }
  const after = api.installedVersion(run);
  if (after !== ctx.version) return { ok: false, detail: `installed version is ${after ?? "none"}, expected ${ctx.version}` };
  return { ok: true, detail: before === ctx.version ? `already ${after}` : `${before ?? "none"} -> ${after}` };
}

function uninstallViaMarketplace(api, { run }) {
  const r1 = run(api.bin, api.uninstallArgs);
  const r2 = run(api.bin, api.removeMarketplace);
  return { ok: r1.code === 0 || r2.code === 0, detail: "removed plugin and marketplace" };
}

const claude = {
  id: "claude",
  label: "Claude Code",
  bin: "claude",
  marketplaceSource: (run) => parseJson(run("claude", ["plugin", "marketplace", "list", "--json"]).out)?.find?.((m) => m.name === MARKETPLACE),
  installedVersion: (run) => parseJson(run("claude", ["plugin", "list", "--json"]).out)?.find?.((p) => p.id === PLUGIN_ID)?.version,
  addMarketplace: ["plugin", "marketplace", "add"],
  removeMarketplace: ["plugin", "marketplace", "remove", MARKETPLACE],
  refreshMarketplace: ["plugin", "marketplace", "update", MARKETPLACE],
  install: ["plugin", "install", PLUGIN_ID],
  update: ["plugin", "update", PLUGIN_ID],
  uninstallArgs: ["plugin", "uninstall", PLUGIN_ID],
};

const omp = {
  id: "omp",
  label: "omp",
  bin: "omp",
  // `omp plugin marketplace list` has no JSON output: "  <name>  <source>" per line.
  marketplaceSource: (run) => run("omp", ["plugin", "marketplace", "list"]).out.match(/^\s*deepmodebot\s+(.+?)\s*$/m)?.[1],
  installedVersion: (run) =>
    parseJson(run("omp", ["plugin", "list", "--json"]).out)?.marketplace?.find?.((p) => p.id === PLUGIN_ID)?.entries?.[0]?.version,
  addMarketplace: ["plugin", "marketplace", "add"],
  removeMarketplace: ["plugin", "marketplace", "remove", MARKETPLACE],
  refreshMarketplace: ["plugin", "marketplace", "update", MARKETPLACE],
  install: ["plugin", "install", PLUGIN_ID],
  update: ["plugin", "upgrade", PLUGIN],
  uninstallArgs: ["plugin", "uninstall", PLUGIN_ID],
};

const codex = {
  id: "codex",
  label: "Codex",
  bin: "codex",
  marketplaceSource: (run) => parseJson(run("codex", ["plugin", "marketplace", "list", "--json"]).out)?.marketplaces?.find?.((m) => m.name === MARKETPLACE),
  installedVersion: (run) => parseJson(run("codex", ["plugin", "list", "--json"]).out)?.installed?.find?.((p) => p.pluginId === PLUGIN_ID)?.version,
  addMarketplace: ["plugin", "marketplace", "add"],
  removeMarketplace: ["plugin", "marketplace", "remove", MARKETPLACE],
  // A local marketplace is read in place, so re-adding the plugin picks up the new files.
  refreshMarketplace: undefined,
  install: ["plugin", "add", PLUGIN_ID],
  update: ["plugin", "add", PLUGIN_ID],
  uninstallArgs: ["plugin", "remove", PLUGIN_ID],
};

const agyInfo = (run) => parseJson(run("agy", ["plugin", "list", "--json"]).out)?.find?.((p) => p.name === PLUGIN);
const agyDefaultPath = () => join(homedir(), ".gemini", "config", "plugins", PLUGIN);
const LOCKED = /being used by another process|access is denied|EBUSY|EPERM/i;

const agy = {
  id: "agy",
  label: "Google Antigravity",
  bin: "agy",
  installedVersion: (run) => agyInfo(run)?.version,
  ensure(ctx) {
    const { run, pkgRoot } = ctx;
    const src = join(pkgRoot, "plugins", PLUGIN);
    const dst = agyInfo(run)?.path ?? agyDefaultPath();
    if (treeDiffs(src, dst).length === 0) return { ok: true, detail: `already ${ctx.version} (files verified)` };
    const r = run("agy", ["plugin", "install", src]);
    let method = "agy plugin install";
    if (r.code !== 0) {
      // A running agy holds the plugin folder open, so its installer cannot swap it.
      // Overwriting the files in place still works; the check below decides success.
      if (!LOCKED.test(r.out) || !existsSync(dst)) return fail("agy plugin install", r);
      try {
        mirror(src, dst);
        method = "in-place copy (agy was running)";
      } catch (e) {
        return { ok: false, detail: `agy is running and holds plugin files (${e.code ?? e.message}); close agy and it retries next hour` };
      }
    }
    const left = treeDiffs(src, dst);
    if (left.length) return { ok: false, detail: `files still differ after ${method} (${left.join(", ")}); retries next hour` };
    return { ok: true, detail: `installed ${ctx.version} via ${method} (files verified)` };
  },
  uninstall: ({ run }) => {
    const r = run("agy", ["plugin", "uninstall", PLUGIN]);
    return { ok: r.code === 0, detail: r.code === 0 ? "removed plugin" : r.out.slice(0, 200) };
  },
};

for (const api of [claude, omp, codex]) {
  api.ensure = (ctx) => {
    const res = ensureViaMarketplace(api, ctx);
    if (res.ok && api.id === "omp") {
      const pruned = pruneStaleOmpShadows(ctx.ompSkillsDir);
      if (pruned.length) return { ...res, detail: `${res.detail} (removed stale shadow: ${pruned.join(", ")})` };
    }
    return res;
  };
  api.uninstall = (ctx) => uninstallViaMarketplace(api, ctx);
}

export const CLIENTS = [claude, omp, codex, agy];
export const clientById = (id) => CLIENTS.find((c) => c.id === id);
