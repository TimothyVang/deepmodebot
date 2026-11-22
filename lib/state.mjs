import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** Where deepmodebot keeps its own state; DEEPMODEBOT_HOME overrides (tests). */
export const stateDir = () => process.env.DEEPMODEBOT_HOME || join(homedir(), ".deepmodebot");
const statePath = () => join(stateDir(), "state.json");
const logPath = () => join(stateDir(), "update.log");

export function readState() {
  try {
    return JSON.parse(readFileSync(statePath(), "utf8"));
  } catch {
    return { clients: [], autoUpdate: false };
  }
}

export function writeState(state) {
  mkdirSync(stateDir(), { recursive: true });
  const tmp = `${statePath()}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`);
  renameSync(tmp, statePath());
}

export function clearState() {
  rmSync(statePath(), { force: true });
}

/** Append a timestamped line to update.log, keeping the last 500 lines. */
export function log(message) {
  mkdirSync(stateDir(), { recursive: true });
  const line = `[${new Date().toISOString()}] ${message}\n`;
  appendFileSync(logPath(), line);
  const lines = readFileSync(logPath(), "utf8").split("\n");
  if (lines.length > 600) writeFileSync(logPath(), lines.slice(-500).join("\n"));
}

/** A lock so two hourly runs never overlap; stale after 30 minutes. */
export function withLock(fn) {
  mkdirSync(stateDir(), { recursive: true });
  const lock = join(stateDir(), "update.lock");
  if (existsSync(lock)) {
    const age = Date.now() - Number(readFileSync(lock, "utf8") || 0);
    if (age < 30 * 60_000) return { skipped: true };
  }
  writeFileSync(lock, String(Date.now()));
  try {
    return fn();
  } finally {
    rmSync(lock, { force: true });
  }
}
