import assert from "node:assert/strict";
import { test } from "node:test";
import { parseRelease, upgradeDecision } from "../lib/version.mjs";

const manifest = (version, bin = { deepmodebot: "bin/deepmodebot.mjs" }) => ({ name: "deepmodebot", version, bin });

test("parseRelease takes plain releases only", () => {
  assert.deepEqual(parseRelease("0.9.0"), [0, 9, 0]);
  assert.equal(parseRelease("0.0.0-stage"), undefined);
  assert.equal(parseRelease(undefined), undefined);
});

test("a newer release with the command is installed", () => {
  assert.deepEqual(upgradeDecision("0.9.0", manifest("0.9.1")), { install: true, reason: "0.9.0 -> 0.9.1" });
  assert.equal(upgradeDecision("0.9.0", manifest("0.10.0")).install, true);
});

test("npm's first-publish placeholder is refused (it replaced a working install once)", () => {
  const d = upgradeDecision("0.9.0", { name: "deepmodebot", version: "0.0.0-stage" });
  assert.equal(d.install, false);
  assert.match(d.reason, /not a release/);
});

test("the same or an older version is never installed", () => {
  assert.equal(upgradeDecision("0.9.0", manifest("0.9.0")).install, false);
  assert.equal(upgradeDecision("0.9.1", manifest("0.9.0")).install, false);
});

test("a release without the deepmodebot command is refused", () => {
  const d = upgradeDecision("0.9.0", manifest("0.9.1", {}));
  assert.equal(d.install, false);
  assert.match(d.reason, /no deepmodebot command/);
});
