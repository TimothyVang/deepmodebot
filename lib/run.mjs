import { spawnSync } from "node:child_process";

const isWin = process.platform === "win32";
// cmd.exe needs quotes around anything with spaces or shell metacharacters.
const quote = (a) => (/^[\w@%+=:,./\\-]+$/.test(a) ? a : `"${String(a).replace(/"/g, '\\"')}"`);

/** First path of `cmd` on PATH, or undefined. */
export function which(cmd) {
  const r = spawnSync(isWin ? "where" : "which", [cmd], { encoding: "utf8", windowsHide: true });
  if (r.status !== 0) return undefined;
  return r.stdout.split(/\r?\n/).map((s) => s.trim()).find(Boolean);
}

/** Run a CLI and return { code, out } with stdout+stderr merged. Never throws. */
export function run(cmd, args = [], { timeout = 300_000 } = {}) {
  const opts = { encoding: "utf8", timeout, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] };
  // npm shims on Windows are .cmd files, which only start through a shell.
  const r = isWin ? spawnSync([cmd, ...args].map(quote).join(" "), { ...opts, shell: true }) : spawnSync(cmd, args, opts);
  const out = `${r.stdout ?? ""}${r.stderr ?? ""}${r.error ? String(r.error.message) : ""}`.trim();
  return { code: r.status ?? 1, out, stdout: (r.stdout ?? "").trim() };
}

/** Parse the JSON a CLI printed, tolerating banner lines before it. */
export function parseJson(out) {
  const start = out.search(/[[{]/);
  if (start < 0) return undefined;
  try {
    return JSON.parse(out.slice(start));
  } catch {
    return undefined;
  }
}
