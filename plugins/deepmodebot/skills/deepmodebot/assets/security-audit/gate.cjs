#!/usr/bin/env node
// Turns a security-audit run into a PR verdict.
// Usage: node gate.cjs <output-dir> <skill-dir> [fail-at] [block-on-unvalidated] [accepted-file]
// Prints the PR comment (Markdown) to stdout. Exit 1 blocks the PR: a confirmed finding at or
// above fail-at, an invalid or missing findings.json, or (when enabled) any needs_validation lead.
// accepted-file lists fingerprints a reviewer accepted, one per line as `<fingerprint> # <reason>`;
// those never block and are shown as accepted.
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const RANK = { informational: 0, low: 1, medium: 2, high: 3, critical: 4 };
const MARKER = "<!-- deepmodebot-security-audit -->";

function cell(text) {
  return String(text ?? "").replace(/\r?\n/g, " ").replace(/\|/g, "\\|").slice(0, 300);
}

function code(text) {
  return cell(text).replace(/`/g, "'");
}

function parseBoolArg(raw) {
  const lowered = String(raw ?? "").trim().toLowerCase();
  if (lowered === "true" || lowered === "1" || lowered === "yes") return true;
  if (lowered === "false" || lowered === "0" || lowered === "no") return false;
  return null;
}

function severityRank(record) {
  const raw = String(record && record.severity && record.severity.overall_severity || "").trim().toLowerCase();
  // Fail closed on missing or unrecognized severity so malformed findings cannot slip past the gate.
  return raw in RANK ? RANK[raw] : RANK.critical;
}

function where(record) {
  const steps = Array.isArray(record.trace) ? record.trace : [];
  const sink = steps.find((s) => s && s.kind === "sink") || steps[steps.length - 1];
  return sink ? `\`${code(sink.file)}:${code(sink.line)}\`` : "";
}

function main() {
  const [outDir, skillDir, failAtArg = "high", blockArg = "true", acceptedFile] = process.argv.slice(2);
  if (!outDir || !skillDir) {
    console.error("Usage: node gate.cjs <output-dir> <skill-dir> [fail-at] [block-on-unvalidated] [accepted-file]");
    return 2;
  }
  const failAt = failAtArg.toLowerCase();
  if (!(failAt in RANK)) {
    console.error(`fail-at must be one of ${Object.keys(RANK).join(", ")}`);
    return 2;
  }
  const blockOnUnvalidated = parseBoolArg(blockArg);
  if (blockOnUnvalidated === null) {
    console.error("block-on-unvalidated must be true or false");
    return 2;
  }
  const lines = [MARKER, "## Security audit"];
  const findingsPath = path.join(outDir, "findings.json");

  // Fail closed: a missing or invalid result blocks, so a broken audit can't pass a PR.
  if (!fs.existsSync(findingsPath)) {
    lines.push("", "**Blocked:** the audit produced no `findings.json`. See the job log.");
    console.log(lines.join("\n"));
    return 1;
  }
  const check = spawnSync(process.execPath, [path.join(skillDir, "validate-findings.cjs"), findingsPath], {
    encoding: "utf8",
    timeout: 60_000,
  });
  if (check.error || check.status !== 0) {
    const out = `${check.stdout || ""}${check.stderr || ""}${check.error ? `\n${check.error.message}` : ""}`.trim().slice(0, 3000);
    lines.push("", "**Blocked:** `findings.json` failed validation.", "", "```", out, "```");
    console.log(lines.join("\n"));
    return 1;
  }

  let records;
  try {
    records = JSON.parse(fs.readFileSync(findingsPath, "utf8"));
  } catch (err) {
    lines.push("", `**Blocked:** could not parse \`findings.json\` (${cell(err && err.message)}).`);
    console.log(lines.join("\n"));
    return 1;
  }
  if (!Array.isArray(records)) {
    lines.push("", "**Blocked:** `findings.json` must be a JSON array.");
    console.log(lines.join("\n"));
    return 1;
  }
  const confirmed = records
    .filter((r) => r && r.verdict === "confirmed")
    .sort((a, b) => severityRank(b) - severityRank(a));
  const accepted = new Map();
  if (acceptedFile && fs.existsSync(acceptedFile)) {
    for (const raw of fs.readFileSync(acceptedFile, "utf8").split(/\r?\n/)) {
      const [fingerprint, ...reason] = raw.split("#");
      if (fingerprint.trim()) accepted.set(fingerprint.trim(), reason.join("#").trim() || "no reason given");
    }
  }
  const open = (r) => !accepted.has(r.fingerprint);
  const leads = records.filter((r) => r && r.verdict === "needs_validation");
  const rejected = records.filter((r) => r && r.verdict === "rejected");
  const blocking = confirmed.filter((r) => open(r) && severityRank(r) >= RANK[failAt]);
  const blockingLeads = blockOnUnvalidated ? leads.filter(open) : [];

  let status = {};
  const metaPath = path.join(outDir, "run-metadata.json");
  if (fs.existsSync(metaPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(metaPath, "utf8"));
      status = parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      status = {};
    }
  }

  // An unfinished audit proves nothing about the code it didn't reach, so it blocks too.
  const incomplete = status.run_status !== "complete";
  const blocked = incomplete || blocking.length > 0 || blockingLeads.length > 0;
  lines.push(
    "",
    blocked ? "**Blocked.**" : "**Passed.**",
    `${confirmed.length} confirmed (${blocking.length} at or above ${failAt}), ${leads.length} need validation, ${rejected.length} rejected.`,
  );
  if (incomplete) {
    lines.push(`The audit did not finish: run status \`${code(status.run_status || "missing")}\`${status.incomplete_reason ? ` (${cell(status.incomplete_reason)})` : ""}. Rerun it, with a larger AUDIT_AGENTS or AUDIT_BUDGET_USD if it ran out.`);
  }
  if (confirmed.length) {
    lines.push("", "| Severity | Finding | Where | Fix |", "|---|---|---|---|");
    for (const r of confirmed) {
      const sev = code(r.severity && r.severity.overall_severity || "unknown");
      lines.push(`| ${sev} | ${cell(r.title)} | ${where(r)} | ${cell(r.remediation && r.remediation.strategy)} |`);
    }
  }
  if (leads.length) {
    lines.push("", `Needs validation (no severity until someone confirms or rejects it)${blockOnUnvalidated ? "; each one blocks until it is fixed or accepted" : ""}:`, "");
    for (const r of leads) {
      const blocker = Array.isArray(r.blockers) && r.blockers.length ? ` Blocked on: ${cell(typeof r.blockers[0] === "string" ? r.blockers[0] : JSON.stringify(r.blockers[0]))}` : "";
      lines.push(`- ${cell(r.title)} ${where(r)} (\`${code(r.fingerprint)}\`).${blocker}`);
    }
  }
  const acceptedHere = records.filter((r) => r && accepted.has(r.fingerprint));
  if (acceptedHere.length) {
    lines.push("", "Accepted by a reviewer (not blocking):", "");
    for (const r of acceptedHere) lines.push(`- ${cell(r.title)} (\`${code(r.fingerprint)}\`): ${cell(accepted.get(r.fingerprint))}`);
  }
  console.log(lines.join("\n"));
  return blocked ? 1 : 0;
}

process.exit(main());
