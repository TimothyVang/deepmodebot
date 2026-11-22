import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { stateDir } from "./state.mjs";

export const TASK_NAME = "DeepmodebotAutoUpdate";
const CRON_TAG = "# deepmodebot-auto-update";

/** Replace (or drop, when line is undefined) the tagged deepmodebot line in a crontab. */
export function cronWithLine(crontab, line) {
  const kept = crontab.split("\n").filter((l) => l.trim() && !l.includes(CRON_TAG));
  if (line) kept.push(`${line} ${CRON_TAG}`);
  return kept.length ? `${kept.join("\n")}\n` : "";
}

/** Register an hourly `deepmodebot update --quiet` that never opens a window. */
export function enableAutoUpdate({ run, node, bin }) {
  if (process.platform === "win32") {
    // wscript runs node hidden; a bare node task would flash a console every hour.
    mkdirSync(stateDir(), { recursive: true });
    const vbs = join(stateDir(), "auto-update.vbs");
    writeFileSync(vbs, `CreateObject("WScript.Shell").Run """${node}"" ""${bin}"" update --quiet", 0, False\r\n`);
    const r = run("schtasks", ["/Create", "/F", "/SC", "HOURLY", "/TN", TASK_NAME, "/TR", `wscript.exe //B //Nologo "${vbs}"`]);
    return { ok: r.code === 0, detail: r.code === 0 ? `scheduled task ${TASK_NAME} (hourly)` : r.out.slice(0, 300) };
  }
  const current = run("crontab", ["-l"]);
  const next = cronWithLine(current.code === 0 ? current.out : "", `17 * * * * "${node}" "${bin}" update --quiet`);
  const tmp = join(stateDir(), "crontab.tmp");
  mkdirSync(stateDir(), { recursive: true });
  writeFileSync(tmp, next);
  const r = run("crontab", [tmp]);
  rmSync(tmp, { force: true });
  return { ok: r.code === 0, detail: r.code === 0 ? "cron entry (hourly at :17)" : r.out.slice(0, 300) };
}

export function disableAutoUpdate({ run }) {
  if (process.platform === "win32") {
    run("schtasks", ["/Delete", "/F", "/TN", TASK_NAME]);
    rmSync(join(stateDir(), "auto-update.vbs"), { force: true });
    return;
  }
  const current = run("crontab", ["-l"]);
  if (current.code !== 0) return;
  const tmp = join(stateDir(), "crontab.tmp");
  writeFileSync(tmp, cronWithLine(current.out, undefined));
  run("crontab", [tmp]);
  rmSync(tmp, { force: true });
}
