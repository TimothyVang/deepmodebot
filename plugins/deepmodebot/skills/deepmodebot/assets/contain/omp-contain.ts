// omp tool_call hook: block write/edit/ast_edit calls whose target path is outside the project root.
// Enforces deepmodebot's "Contain the work" rule. Install: copy to ~/.omp/agent/hooks/pre/ (all sessions) or
// <repo>/.omp/hooks/pre/ (one repo), or pass `--hook <this file>` for one run.
// Roots = the worktree holding the session cwd plus its main checkout (they differ in a linked worktree, e.g. one
// under <root>/.worktrees/ or an Orca workspace), or the cwd outside git. Also allowed: omp session resources
// (local://, artifact://, agent://, proc://, xd://, out://, conflict://, cfg://) and `extraWriteRoots` in a root's
// .deepmodebot.json (only paths the user named). eval is not covered.
// Rule approval (../rules/rule_ledger.py): in a repo whose owner turned it on, write/edit/ast_edit on agent rule
// files or the ledger are blocked, and so are bash commands that write them; the owner-only
// `rules init|approve|reject|rotate` commands are blocked everywhere. Other bash commands pass.
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const WRITE_TOOLS: Record<string, true> = { write: true, edit: true, ast_edit: true };
const SESSION_URL = /^(local|artifact|agent|proc|xd|out|conflict|cfg):\/\//i;
const HEADER = /^\[(.+)#[0-9A-Za-z]+\]$/; // a copied [path#TAG] header: omp strips the wrapper before writing
const EDIT_TAG = /#[0-9A-Za-z]{4}$/; // the hashline edit tool reports its target as `path#TAG`
const ANY_URL = /^[a-z][a-z0-9+.-]*:\/\//i;
const caseless = process.platform === "win32" || process.platform === "darwin";
const RULES_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "rules");
const RULE_LEDGER = path.join(RULES_DIR, "rule_ledger.py");
const LEDGER_REL = path.join(".deepmodebot", "rules", "ledger.json");
const PYTHONS: [string, string[]][] =
	process.platform === "win32"
		? [["py", ["-3", "-B"]], ["python3", ["-B"]], ["python", ["-B"]]]
		: [["python3", ["-B"]], ["python", ["-B"]]];
const RULES = loadRuleSpec();

interface ToolCallEvent {
	toolName: string;
	input?: Record<string, unknown>;
}

type ToolCallResult = { block: true; reason: string } | undefined;

interface HookApi {
	on(event: "tool_call", handler: (event: ToolCallEvent, ctx: { cwd?: string }) => Promise<ToolCallResult>): void;
}

// Absolute form of a path as omp would open it: `~` is the home folder, anything relative hangs off cwd.
function absolute(p: string, cwd: string): string {
	const expanded = p === "~" || p.startsWith("~/") || p.startsWith("~\\") ? path.join(os.homedir(), p.slice(1)) : p;
	return path.resolve(cwd, expanded);
}

function real(p: string): string {
	let resolved = path.resolve(p);
	try {
		resolved = fs.realpathSync.native(resolved);
	} catch {
		// Target may not exist yet; resolve its nearest existing parent so symlinked parents still count.
		const parent = path.dirname(resolved);
		if (parent !== resolved) resolved = path.join(real(parent), path.basename(resolved));
	}
	return caseless ? resolved.toLowerCase() : resolved;
}

function inside(p: string, root: string): boolean {
	const rel = path.relative(root, p);
	if (rel === "") return true;
	if (rel === ".." || rel.startsWith(".." + path.sep)) return false;
	return !path.isAbsolute(rel);
}

// The worktree holding cwd first, then the main checkout.
function projectRoots(cwd: string): string[] {
	try {
		const [toplevel, common] = execFileSync(
			"git",
			["-C", cwd, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
			{ encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "ignore"], windowsHide: true },
		)
			.split(/\r?\n/)
			.map(line => line.replace(/[\\/]+$/, ""));
		if (!toplevel || !common) return [cwd];
		return path.basename(common) === ".git" ? [toplevel, path.dirname(common)] : [toplevel];
	} catch {
		return [cwd];
	}
}

function allowedRoots(roots: string[]): string[] {
	const allowed = [...roots];
	for (const root of roots) {
		try {
			const config: unknown = JSON.parse(fs.readFileSync(path.join(root, ".deepmodebot.json"), "utf8"));
			const extra = config && typeof config === "object" && "extraWriteRoots" in config ? config.extraWriteRoots : undefined;
			if (!Array.isArray(extra)) continue;
			for (const p of extra) {
				if (typeof p === "string") allowed.push(absolute(p, root));
			}
		} catch {}
	}
	return allowed.map(real);
}

function targets(input: Record<string, unknown>): string[] {
	const out: string[] = [];
	if (typeof input.path === "string") out.push(input.path);
	if (Array.isArray(input.paths)) for (const p of input.paths) if (typeof p === "string") out.push(p);
	return out
		.map(p => (HEADER.exec(p.trim())?.[1] ?? p.trim()).replace(EDIT_TAG, ""))
		.filter(p => p.length > 0 && !SESSION_URL.test(p));
}

// rule-paths.json, lowercased, for the cheap pre-check that decides whether rule_ledger.py needs to run at all.
function loadRuleSpec() {
	try {
		const spec = JSON.parse(fs.readFileSync(path.join(RULES_DIR, "rule-paths.json"), "utf8"));
		const low = (xs: unknown): string[] =>
			Array.isArray(xs) ? xs.map(x => String(x).toLowerCase().replace(/^\/+|\/+$/g, "")) : [];
		const names = low(spec.names);
		const dirs = low(spec.dirs);
		const files = low(spec.files);
		return {
			names: new Set(names),
			dirs: dirs.map(d => `/${d}/`),
			files: files.map(f => `/${f}`),
			hints: [...names, ...files, ...dirs, ...dirs.map(d => d.split("/")[0]), "deepmodebot", "rule_ledger"],
		};
	} catch {
		return undefined;
	}
}

function mayBeRulePath(abs: string): boolean {
	if (!RULES) return false;
	const p = abs.toLowerCase().replace(/\\/g, "/");
	return (
		RULES.names.has(p.slice(p.lastIndexOf("/") + 1)) ||
		p.includes("/.deepmodebot/rules") ||
		RULES.dirs.some(d => p.includes(d)) ||
		RULES.files.some(f => p.endsWith(f))
	);
}

// Whether the repo holding `abs` has an owner rule ledger (used only when Python is missing).
function ledgerNear(abs: string): boolean {
	let dir = path.dirname(abs);
	while (true) {
		if (fs.existsSync(path.join(dir, LEDGER_REL))) return true;
		if (fs.existsSync(path.join(dir, ".git"))) return false;
		const parent = path.dirname(dir);
		if (parent === dir) return false;
		dir = parent;
	}
}

// rule_ledger.py guard verdict: a deny reason, "" to allow, or null when no Python could run it.
function pythonGuard(request: { cwd: string; paths: string[]; command: string }): string | null {
	for (const [exe, prefix] of PYTHONS) {
		try {
			const out = execFileSync(exe, [...prefix, RULE_LEDGER, "guard"], {
				input: JSON.stringify(request),
				encoding: "utf8",
				timeout: 15_000,
				stdio: ["pipe", "pipe", "ignore"],
				windowsHide: true,
				env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
			});
			const verdict = JSON.parse(out);
			return verdict && verdict.block ? String(verdict.reason) : "";
		} catch (err) {
			if (err && typeof err === "object" && "code" in err && err.code === "ENOENT") continue;
			return "";
		}
	}
	return null;
}

function ruleBlock(cwd: string, paths: string[], command: string): ToolCallResult {
	const candidates = paths.filter(p => mayBeRulePath(absolute(p, cwd)));
	const lowered = command.toLowerCase();
	const shell = command !== "" && (RULES?.hints.some(h => lowered.includes(h)) ?? false);
	if (candidates.length === 0 && !shell) return undefined;
	const verdict = pythonGuard({ cwd, paths: candidates, command: shell ? command : "" });
	if (verdict === null) {
		if (!candidates.some(p => ledgerNear(absolute(p, cwd)))) return undefined;
		return { block: true, reason: "deepmodebot rule approval needs Python 3 on PATH to check rule files; install it, then retry." };
	}
	return verdict ? { block: true, reason: verdict } : undefined;
}

export default function (pi: HookApi): void {
	pi.on("tool_call", async (event, ctx) => {
		const cwd = ctx?.cwd ?? process.cwd();
		const input = event.input ?? {};
		if (event.toolName === "bash") {
			const runDir = typeof input.cwd === "string" && input.cwd.trim() ? absolute(input.cwd.trim(), cwd) : cwd;
			return ruleBlock(runDir, [], typeof input.command === "string" ? input.command : "");
		}
		if (!WRITE_TOOLS[event.toolName]) return;
		const roots = projectRoots(cwd);
		const root = roots[0];
		const allowed = allowedRoots(roots);
		for (const target of targets(input)) {
			// skill://, vault://, ssh:// and other non-session URLs resolve outside the root. A selector suffix
			// (archive.zip:member, db.sqlite:table) stays on the path: `..` in it must count against the target.
			if (!ANY_URL.test(target) && allowed.some(r => inside(real(absolute(target, cwd)), r))) continue;
			return {
				block: true,
				reason:
					`deepmodebot keeps all writes inside the project root ${root}. ${target} is outside it. ` +
					`Put scratch and temp files in ${path.join(root, ".scratch")} and worktrees in ${path.join(root, ".worktrees")}. ` +
					`If the user explicitly named this path, add it to extraWriteRoots in ${path.join(root, ".deepmodebot.json")}.`,
			};
		}
		return ruleBlock(cwd, targets(input).filter(t => !ANY_URL.test(t)), "");
	});
}
