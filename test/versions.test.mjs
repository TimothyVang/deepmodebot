import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(import.meta.url), "../..");
const read = (rel) => JSON.parse(readFileSync(resolve(root, rel), "utf8"));

// npm publishes package.json's version; every plugin manifest must match it so all four tools see one version.
test("package.json and every plugin manifest carry the same version", () => {
  const want = read("package.json").version;
  const found = {
    ".claude-plugin/marketplace.json metadata": read(".claude-plugin/marketplace.json").metadata.version,
    ".claude-plugin/marketplace.json plugin": read(".claude-plugin/marketplace.json").plugins[0].version,
    ".omp-plugin/marketplace.json metadata": read(".omp-plugin/marketplace.json").metadata.version,
    ".omp-plugin/marketplace.json plugin": read(".omp-plugin/marketplace.json").plugins[0].version,
    "plugins/deepmodebot/.claude-plugin/plugin.json": read("plugins/deepmodebot/.claude-plugin/plugin.json").version,
    "plugins/deepmodebot/.antigravity-plugin/plugin.json": read("plugins/deepmodebot/.antigravity-plugin/plugin.json").version,
  };
  for (const [where, v] of Object.entries(found)) assert.equal(v, want, `${where} is ${v}, package.json is ${want}`);
});
