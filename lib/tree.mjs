import { cpSync, existsSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const IGNORED = new Set(["__pycache__", ".pytest_cache", "node_modules"]);

function listFiles(root) {
  const out = new Map();
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      if (IGNORED.has(name) || name.endsWith(".pyc")) continue;
      const p = join(dir, name);
      const st = statSync(p);
      if (st.isDirectory()) walk(p);
      else out.set(relative(root, p).split(sep).join("/"), p);
    }
  };
  if (existsSync(root)) walk(root);
  return out;
}

/** Relative paths that are missing, extra, or different between src and dst (up to `limit`). */
export function treeDiffs(src, dst, limit = 5) {
  if (!existsSync(dst)) return ["<not installed>"];
  const a = listFiles(src);
  const b = listFiles(dst);
  const diffs = [];
  for (const rel of [...new Set([...a.keys(), ...b.keys()])].sort()) {
    const pa = a.get(rel);
    const pb = b.get(rel);
    if (!pa || !pb || statSync(pa).size !== statSync(pb).size || !readFileSync(pa).equals(readFileSync(pb))) {
      diffs.push(rel);
      if (diffs.length >= limit) break;
    }
  }
  return diffs;
}

/**
 * Make dst an exact copy of src by overwriting files in place.
 * Used when a running app holds the folder open so it cannot be renamed or replaced.
 */
export function mirror(src, dst) {
  // Filter on the path inside src only: the package itself lives under node_modules.
  const skip = (p) => relative(src, p).split(/[\\/]/).some((part) => IGNORED.has(part));
  cpSync(src, dst, { recursive: true, force: true, filter: (p) => !skip(p) });
  const keep = listFiles(src);
  for (const [rel, p] of listFiles(dst)) if (!keep.has(rel)) rmSync(p, { force: true });
}
