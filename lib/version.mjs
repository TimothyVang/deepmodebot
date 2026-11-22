/** Parse a plain release version "1.2.3"; a prerelease ("0.0.0-stage") or anything else is undefined. */
export function parseRelease(v) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(v ?? "").trim());
  return m ? m.slice(1, 4).map(Number) : undefined;
}

function compare(a, b) {
  for (let i = 0; i < 3; i += 1) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

/**
 * Decide whether `update` may install the registry's latest manifest over the running version.
 * Only a stable release, newer than the current one, that ships the deepmodebot command. A placeholder
 * (npm's first-publish "0.0.0-stage" had no bin) or a downgrade is refused, so the hourly task can never
 * replace a working install with something that has no command.
 */
export function upgradeDecision(current, latest, bin = "deepmodebot") {
  const want = parseRelease(latest?.version);
  if (!want) return { install: false, reason: `latest is ${latest?.version ?? "unknown"}, not a release` };
  const have = parseRelease(current);
  if (have && compare(want, have) <= 0) return { install: false, reason: `already ${current}` };
  const bins = typeof latest.bin === "string" ? { [latest.name ?? bin]: latest.bin } : latest.bin ?? {};
  if (!bins[bin]) return { install: false, reason: `${latest.version} has no ${bin} command` };
  return { install: true, reason: `${current} -> ${latest.version}` };
}
