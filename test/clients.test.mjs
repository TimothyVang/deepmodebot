import assert from "node:assert/strict";
import { test } from "node:test";
import { clientById, PLUGIN_ID } from "../lib/clients.mjs";

const PKG_ROOT = "C:\\Users\\me\\AppData\\Roaming\\npm\\node_modules\\deepmodebot";

/** A fake Claude Code CLI: a marketplace source plus an installed version, mutated by the commands it receives. */
function fakeClaude({ source, installed }) {
  const calls = [];
  const state = { source, installed };
  const run = (bin, args) => {
    const line = args.join(" ");
    calls.push(line);
    if (line === "plugin marketplace list --json")
      return { code: 0, out: JSON.stringify(state.source ? [{ name: "deepmodebot", ...state.source }] : []) };
    if (line === "plugin list --json")
      return { code: 0, out: JSON.stringify(state.installed ? [{ id: PLUGIN_ID, version: state.installed }] : []) };
    if (line === "plugin marketplace remove deepmodebot") state.source = undefined;
    else if (line.startsWith("plugin marketplace add ")) state.source = { source: "directory", path: args.at(-1) };
    else if (line === `plugin install ${PLUGIN_ID}` || line === `plugin update ${PLUGIN_ID}`) state.installed = "0.9.0";
    return { code: 0, out: "" };
  };
  return { run, calls, state };
}

test("claude: replaces a GitHub marketplace with the npm package folder and updates", () => {
  const fake = fakeClaude({ source: { source: "github", repo: "TimothyVang/deepmodebot" }, installed: "0.8.1" });
  const res = clientById("claude").ensure({ run: fake.run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, true, res.detail);
  assert.ok(fake.calls.includes("plugin marketplace remove deepmodebot"));
  assert.ok(fake.calls.includes(`plugin marketplace add ${PKG_ROOT}`));
  assert.ok(fake.calls.includes(`plugin update ${PLUGIN_ID}`));
  assert.equal(res.detail, "0.8.1 -> 0.9.0");
});

test("claude: already pointing here and current means no install or remove", () => {
  const fake = fakeClaude({ source: { source: "directory", path: PKG_ROOT }, installed: "0.9.0" });
  const res = clientById("claude").ensure({ run: fake.run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, true);
  assert.ok(!fake.calls.some((c) => c.includes("remove") || c.includes("install")));
  assert.equal(res.detail, "already 0.9.0");
});

test("claude: fresh machine installs instead of updating", () => {
  const fake = fakeClaude({});
  const res = clientById("claude").ensure({ run: fake.run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, true);
  assert.ok(fake.calls.includes(`plugin install ${PLUGIN_ID}`));
  assert.ok(!fake.calls.includes("plugin marketplace remove deepmodebot"));
});

test("a version that does not land is reported as a failure, not success", () => {
  const fake = fakeClaude({ source: { source: "directory", path: PKG_ROOT }, installed: "0.8.1" });
  const stuck = (bin, args) => (args.join(" ").startsWith("plugin update") ? { code: 0, out: "" } : fake.run(bin, args));
  const res = clientById("claude").ensure({ run: stuck, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, false);
  assert.match(res.detail, /installed version is 0\.8\.1, expected 0\.9\.0/);
});

test("a failing CLI step stops and reports which step", () => {
  const run = (bin, args) =>
    args.join(" ").startsWith("plugin marketplace add") ? { code: 1, out: "boom" } : { code: 0, out: "[]" };
  const res = clientById("claude").ensure({ run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, false);
  assert.match(res.detail, /^add marketplace failed \(1\): boom/);
});

test("omp: reads the text marketplace list and upgrades by plugin name", () => {
  const calls = [];
  let version = "0.8.3";
  const run = (bin, args) => {
    const line = args.join(" ");
    calls.push(line);
    if (line === "plugin marketplace list") return { code: 0, out: `Configured Marketplaces:\n\n  other  someone/skills\n  deepmodebot  ${PKG_ROOT}\n` };
    if (line === "plugin list --json")
      return { code: 0, out: JSON.stringify({ npm: [], marketplace: [{ id: PLUGIN_ID, entries: [{ version }] }] }) };
    if (line === "plugin upgrade deepmodebot") version = "0.9.0";
    return { code: 0, out: "" };
  };
  const res = clientById("omp").ensure({ run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, true, res.detail);
  assert.ok(calls.includes("plugin marketplace update deepmodebot"));
  assert.ok(calls.includes("plugin upgrade deepmodebot"));
  assert.ok(!calls.some((c) => c.startsWith("plugin marketplace add")));
});

test("codex: adds the local marketplace and the plugin", () => {
  const calls = [];
  let installed;
  let roots = [];
  const run = (bin, args) => {
    const line = args.join(" ");
    calls.push(line);
    if (line === "plugin marketplace list --json") return { code: 0, out: JSON.stringify({ marketplaces: roots }) };
    if (line === "plugin list --json")
      return { code: 0, out: JSON.stringify({ installed: installed ? [{ pluginId: PLUGIN_ID, version: installed }] : [] }) };
    if (line.startsWith("plugin marketplace add")) roots = [{ name: "deepmodebot", root: args.at(-1) }];
    if (line === `plugin add ${PLUGIN_ID}`) installed = "0.9.0";
    return { code: 0, out: "" };
  };
  const res = clientById("codex").ensure({ run, pkgRoot: PKG_ROOT, version: "0.9.0" });
  assert.equal(res.ok, true, res.detail);
  assert.deepEqual(calls.filter((c) => !c.endsWith("--json")), [`plugin marketplace add ${PKG_ROOT}`, `plugin add ${PLUGIN_ID}`]);
});
