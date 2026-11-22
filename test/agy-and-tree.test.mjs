import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { clientById } from "../lib/clients.mjs";
import { cronWithLine } from "../lib/autoupdate.mjs";
import { mirror, treeDiffs } from "../lib/tree.mjs";

// Repo-local scratch (never system temp), removed afterwards.
const scratchRoot = resolve(fileURLToPath(import.meta.url), "../../.scratch/tmp");
mkdirSync(scratchRoot, { recursive: true });
const tmp = mkdtempSync(join(scratchRoot, "npm-test-"));
after(() => rmSync(tmp, { recursive: true, force: true }));

function writeTree(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    mkdirSync(join(root, rel, ".."), { recursive: true });
    writeFileSync(join(root, rel), body);
  }
}

test("treeDiffs finds changed, missing, and extra files, and ignores caches", () => {
  const a = join(tmp, "a");
  const b = join(tmp, "b");
  writeTree(a, { "x.md": "1", "sub/y.md": "2", "__pycache__/z.pyc": "c" });
  writeTree(b, { "x.md": "1", "sub/y.md": "CHANGED", "extra.md": "e" });
  assert.deepEqual(treeDiffs(a, b), ["extra.md", "sub/y.md"]);
  assert.deepEqual(treeDiffs(a, join(tmp, "missing")), ["<not installed>"]);
});

test("mirror makes the destination identical, deleting extra files", () => {
  const src = join(tmp, "m-src");
  const dst = join(tmp, "m-dst");
  writeTree(src, { "a.md": "new", "d/b.md": "b" });
  writeTree(dst, { "a.md": "old", "stale.md": "s" });
  mirror(src, dst);
  assert.deepEqual(treeDiffs(src, dst), []);
});

test("mirror works when the source lives under node_modules (the real npm install path)", () => {
  const src = join(tmp, "nm", "node_modules", "deepmodebot", "plugins", "deepmodebot");
  const dst = join(tmp, "nm-dst");
  writeTree(src, { "a.md": "new", "__pycache__/x.pyc": "skip" });
  writeTree(dst, { "a.md": "old" });
  mirror(src, dst);
  assert.deepEqual(treeDiffs(src, dst), []);
});

function agyFixture(name, installerResult) {
  const pkgRoot = join(tmp, name, "pkg");
  const installed = join(tmp, name, "installed");
  writeTree(join(pkgRoot, "plugins/deepmodebot"), { ".antigravity-plugin/plugin.json": '{"version":"0.9.0"}', "skills/a.md": "new" });
  writeTree(installed, { ".antigravity-plugin/plugin.json": '{"version":"0.8.1"}', "skills/a.md": "old" });
  const calls = [];
  const run = (bin, args) => {
    calls.push(args.join(" "));
    if (args[1] === "list") return { code: 0, out: JSON.stringify([{ name: "deepmodebot", version: "0.8.1", path: installed }]) };
    return installerResult;
  };
  return { pkgRoot, installed, run, calls };
}

test("agy: when the installer is blocked by a running agy, files are copied in place and verified", () => {
  const f = agyFixture("locked", { code: 1, out: "rename ...: The process cannot access the file because it is being used by another process." });
  const res = clientById("agy").ensure({ run: f.run, pkgRoot: f.pkgRoot, version: "0.9.0" });
  assert.equal(res.ok, true, res.detail);
  assert.match(res.detail, /in-place copy/);
  assert.deepEqual(treeDiffs(join(f.pkgRoot, "plugins/deepmodebot"), f.installed), []);
});

test("agy: an installer that exits 0 but leaves old files is a failure (the bug that kept agy on 0.8.1)", () => {
  const f = agyFixture("silent", { code: 0, out: "ok" });
  const res = clientById("agy").ensure({ run: f.run, pkgRoot: f.pkgRoot, version: "0.9.0" });
  assert.equal(res.ok, false);
  assert.match(res.detail, /files still differ/);
});

test("agy: matching files skip the installer entirely", () => {
  const f = agyFixture("current", { code: 1, out: "should not run" });
  mirror(join(f.pkgRoot, "plugins/deepmodebot"), f.installed);
  const res = clientById("agy").ensure({ run: f.run, pkgRoot: f.pkgRoot, version: "0.9.0" });
  assert.equal(res.ok, true);
  assert.ok(!f.calls.some((c) => c.startsWith("plugin install")));
});

test("cron line is replaced, not duplicated, and can be removed", () => {
  const base = "0 1 * * * backup\n";
  const once = cronWithLine(base, "17 * * * * node dmb update --quiet");
  const twice = cronWithLine(once, "17 * * * * node dmb update --quiet");
  assert.equal(once, twice);
  assert.equal(twice.match(/deepmodebot-auto-update/g).length, 1);
  assert.equal(cronWithLine(twice, undefined), base);
});
