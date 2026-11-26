import { closeSync, cpSync, existsSync, lstatSync, openSync, readdirSync, readSync, rmSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const NEVER_PRUNE_DIRS = new Set(["node_modules"]);
const IGNORED = new Set(["__pycache__", ".pytest_cache", "node_modules", "bun.lock"]);
const isIgnoredFile = (name) =>
  IGNORED.has(name) ||
  name.endsWith(".pyc") ||
  name.includes(".bak") ||
  (name.endsWith(".py") && (name.startsWith("test_") || name.endsWith("_test.py")));

function listFiles(root, { includeIgnored = false } = {}) {
  const out = new Map();
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      if (NEVER_PRUNE_DIRS.has(name)) continue;
      if (!includeIgnored && isIgnoredFile(name)) continue;
      const p = join(dir, name);
      const st = lstatSync(p);
      if (st.isSymbolicLink()) continue;
      if (st.isDirectory()) walk(p);
      else if (st.isFile()) out.set(relative(root, p).split(sep).join("/"), p);
    }
  };
  if (existsSync(root)) walk(root);
  return out;
}

const CHUNK_BYTES = 64 * 1024;

function filesEqual(pa, pb, size) {
  if (size === 0) return true;
  const fa = openSync(pa, "r");
  const fb = openSync(pb, "r");
  const bufA = Buffer.allocUnsafe(Math.min(size, CHUNK_BYTES));
  const bufB = Buffer.allocUnsafe(Math.min(size, CHUNK_BYTES));
  try {
    let offset = 0;
    while (offset < size) {
      const toRead = Math.min(CHUNK_BYTES, size - offset);
      const na = readSync(fa, bufA, 0, toRead, offset);
      const nb = readSync(fb, bufB, 0, toRead, offset);
      if (na !== nb || !bufA.subarray(0, na).equals(bufB.subarray(0, nb))) return false;
      if (na === 0) break;
      offset += na;
    }
    return true;
  } finally {
    closeSync(fa);
    closeSync(fb);
  }
}

function pruneEmptyDirs(dir, root) {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = lstatSync(p);
    if (!st.isSymbolicLink() && st.isDirectory()) pruneEmptyDirs(p, root);
  }
  if (dir !== root && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
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
    if (!pa || !pb) {
      diffs.push(rel);
    } else {
      const sa = statSync(pa).size;
      const sb = statSync(pb).size;
      if (sa !== sb || !filesEqual(pa, pb, sa)) diffs.push(rel);
    }
    if (diffs.length >= limit) break;
  }
  return diffs;
}

/**
 * Make dst an exact copy of src by overwriting files in place.
 * Used when a running app holds the folder open so it cannot be renamed or replaced.
 */
export function mirror(src, dst) {
  // Filter on the path inside src only: the package itself lives under node_modules.
  const skip = (p) => {
    const rel = relative(src, p);
    if (!rel) return false;
    const parts = rel.split(/[\\/]/);
    const base = parts[parts.length - 1];
    return isIgnoredFile(base) || parts.some((part) => IGNORED.has(part));
  };
  cpSync(src, dst, { recursive: true, force: true, filter: (p) => !skip(p) });
  const keep = listFiles(src);
  for (const [rel, p] of listFiles(dst, { includeIgnored: true })) if (!keep.has(rel)) rmSync(p, { force: true });
  pruneEmptyDirs(dst, dst);
}
