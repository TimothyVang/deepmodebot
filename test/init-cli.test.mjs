import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(fileURLToPath(import.meta.url), "../..");
const cliBin = join(repoRoot, "bin", "deepmodebot.mjs");
const scratchRoot = join(repoRoot, ".scratch", "tmp");
mkdirSync(scratchRoot, { recursive: true });
const tmp = mkdtempSync(join(scratchRoot, "init-cli-test-"));
after(() => rmSync(tmp, { recursive: true, force: true }));

test("deepmodebot init bootstraps .deepmodebot/ci.yml, policy.xml, memory DB, AGENTS.md, CLAUDE.md and passes --check", () => {
  const demo = join(tmp, "demo");
  mkdirSync(demo, { recursive: true });
  execFileSync("git", ["init", "-q", "-b", "main"], { cwd: demo });
  writeFileSync(join(demo, "package.json"), JSON.stringify({ name: "demo", scripts: { test: "node -e \"console.log('ok')\"" } }));

  const before = spawnSync(process.execPath, [cliBin, "init", "--check", demo], { encoding: "utf8" });
  assert.equal(before.status, 1);

  const runInit = spawnSync(process.execPath, [cliBin, "init", demo], { encoding: "utf8" });
  assert.equal(runInit.status, 0, runInit.stdout + runInit.stderr);
  assert.equal(existsSync(join(demo, ".deepmodebot", "ci.yml")), true);
  assert.equal(existsSync(join(demo, ".deepmodebot", "policy.xml")), true);
  assert.equal(existsSync(join(demo, ".scratch", "deepmode-memory.db")), true);

  const agents = readFileSync(join(demo, "AGENTS.md"), "utf8");
  const claude = readFileSync(join(demo, "CLAUDE.md"), "utf8");
  assert.match(agents, /\.deepmodebot\/ci\.yml/);
  assert.match(agents, /\.deepmodebot\/policy\.xml/);
  assert.match(agents, /deepmode-memory\.db/);
  assert.match(claude, /@AGENTS\.md/);

  const afterCheck = spawnSync(process.execPath, [cliBin, "init", "--check", demo], { encoding: "utf8" });
  assert.equal(afterCheck.status, 0, afterCheck.stdout + afterCheck.stderr);
});

test("deepmodebot gate reward blocks threshold zeroing and enforces provenance + independent judge contract", () => {
  const demo = join(tmp, "reward-demo");
  mkdirSync(join(demo, "gates"), { recursive: true });
  mkdirSync(join(demo, "refs"), { recursive: true });
  execFileSync("git", ["init", "-q", "-b", "main"], { cwd: demo });
  execFileSync("git", ["config", "user.email", "test@example.com"], { cwd: demo });
  execFileSync("git", ["config", "user.name", "Test"], { cwd: demo });
  writeFileSync(join(demo, "gates", "gate.py"), "MIN_IOU = 0.75\n");
  writeFileSync(join(demo, "refs", "concept.png"), "PNG-CONCEPT-BYTES");
  execFileSync("git", ["add", "."], { cwd: demo });
  execFileSync("git", ["commit", "-q", "-m", "init"], { cwd: demo });

  writeFileSync(join(demo, "hack.py"), "cmd = ['gate.py', '--min-iou', '0.0']\n");
  const scanBad = spawnSync(process.execPath, [cliBin, "gate", "reward", "--root", demo, "--json"], { encoding: "utf8" });
  assert.equal(scanBad.status, 1, scanBad.stdout + scanBad.stderr);
  const parsedBad = JSON.parse(scanBad.stdout);
  assert.equal(parsedBad.ok, false);
  assert.equal(parsedBad.findings.some((f) => f.rule === "reward-hack-threshold-zero"), true);
  rmSync(join(demo, "hack.py"));

  const lockRun = spawnSync(
    process.execPath,
    [cliBin, "gate", "reward", "lock-contract", "--root", demo, "--slug", "corsair", "--gates", "gates/gate.py", "--references", "refs/concept.png", "--thresholds", "min_iou=0.75", "--required-producers", "dgx-spark", "--artifacts", "mesh.glb"],
    { encoding: "utf8" }
  );
  assert.equal(lockRun.status, 0, lockRun.stdout + lockRun.stderr);

  const blockedVerdict = spawnSync(process.execPath, [cliBin, "gate", "reward", "verdict", "--root", demo, "--slug", "corsair", "--strict"], { encoding: "utf8" });
  assert.equal(blockedVerdict.status, 1);
});
