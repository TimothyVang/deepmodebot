// Git guard for omp: a pre-tool hook. Install to .omp/hooks/pre/ (project) or ~/.omp/agent/hooks/pre/ (user),
// together with git-guard-patterns.txt in the same folder. Blocks matching commands in the bash tool
// and in eval cells, which can also run shell commands.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const patternFile = join(dirname(fileURLToPath(import.meta.url)), "git-guard-patterns.txt");

// A rule blocks a command; a rule with a branch blocks it only while that branch is checked out.
interface Rule {
	command: RegExp;
	branch?: RegExp;
}

function loadRules(): Rule[] | undefined {
	let text: string;
	try {
		text = readFileSync(patternFile, "utf8");
	} catch {
		return undefined;
	}
	const rules: Rule[] = [];
	for (const line of text.split(/\r?\n/)) {
		const trimmed = line.trimStart();
		if (trimmed === "" || trimmed.startsWith("#")) continue;
		const branchRule = /^@branch +([^ ]+) +(.+)$/.exec(trimmed);
		if (branchRule) rules.push({ branch: new RegExp(`^(${branchRule[1]})$`), command: new RegExp(branchRule[2], "m") });
		else rules.push({ command: new RegExp(line, "m") });
	}
	return rules;
}

function checkedOutBranch(cwd: string): string | undefined {
	try {
		const out = execFileSync("git", ["symbolic-ref", "--short", "-q", "HEAD"], {
			cwd,
			encoding: "utf8",
			timeout: 5_000,
			stdio: ["ignore", "pipe", "ignore"],
			windowsHide: true,
		});
		return out.trim() || undefined;
	} catch {
		return undefined;
	}
}

function unquote(token: string): string {
	if (token.length >= 2 && ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'")))) {
		return token.slice(1, -1);
	}
	return token;
}

function resolveEffectiveCwd(line: string, matchStart: number, matchText: string, baseCwd: string): string {
	let cwd = resolve(baseCwd || process.cwd());
	const before = line.slice(0, matchStart);
	const cdRe = /(?:^|[;&|(\s])cd +(?:-L|-P +)*("[^"]*"|'[^']*'|[^ ;&|)]+)/g;
	let cdMatch: RegExpExecArray | null;
	while ((cdMatch = cdRe.exec(before)) !== null) {
		const target = unquote(cdMatch[1]);
		if (target && target !== "-") cwd = resolve(cwd, target);
	}
	const gitCRe = /\bgit\b(?: +[^ ;&|]+)*? +-C +("[^"]*"|'[^']*'|[^ ;&|]+)/g;
	let cMatch: RegExpExecArray | null;
	while ((cMatch = gitCRe.exec(matchText)) !== null) {
		const target = unquote(cMatch[1]);
		if (target) cwd = resolve(cwd, target);
	}
	return cwd;
}

const watched: Record<string, string> = { bash: "command", eval: "code" };

export default function gitGuard(pi: {
	on(
		event: "tool_call",
		handler: (event: { toolName: string; input?: Record<string, unknown> }, ctx?: { cwd?: string }) => unknown,
	): void;
}): void {
	pi.on("tool_call", (event, ctx) => {
		const field = watched[event.toolName];
		if (!field) return;
		const rules = loadRules();
		if (!rules) return { block: true, reason: `git guard: cannot read ${patternFile}; blocking until it is restored.` };
		const inputCwd = typeof event.input?.cwd === "string" && event.input.cwd.trim() ? event.input.cwd.trim() : "";
		const baseCwd = inputCwd || ctx?.cwd || process.cwd();
		// One line at a time, as grep does in git-guard.sh: arguments must not run on into the next command.
		// A backslash-newline continues the command on the next line; tabs normalize to spaces so patterns stay portable.
		const lines = String(event.input?.[field] ?? "")
			.replace(/\\\r?\n/g, " ")
			.replace(/\t/g, " ")
			.split(/\r?\n/);
		const branchCache = new Map<string, string | undefined>();
		for (const rule of rules) {
			for (const rawLine of lines) {
				const line = rawLine.replace(/(-m|--message)(=| +)("[^"]*"|'[^']*')/g, '$1 ""');
				if (/^ *(grep|rg) +[^;&|`$]*$/.test(line)) continue;
				const hit = rule.command.exec(line);
				if (!hit) continue;
				if (rule.branch) {
					const targetCwd = resolveEffectiveCwd(line, hit.index, hit[0], baseCwd);
					let branch: string | undefined;
					if (branchCache.has(targetCwd)) {
						branch = branchCache.get(targetCwd);
					} else {
						branch = checkedOutBranch(targetCwd);
						branchCache.set(targetCwd, branch);
					}
					if (!branch || !rule.branch.test(branch)) continue;
				}
				const isRewardHack = /^ *(--(gate-)?min-|--skip-|--bypass-gate|--require-spark-receipt|--gate-mode|sqlite3|rm|del|unlink|reward_guard\.py)/.test(hit[0]) || /--no-verify| -n( |$)/.test(hit[0]);
				return {
					block: true,
					reason: isRewardHack
						? `Blocked by anti-reward-hacking guard: "${hit[0].trim()}" weakens a test/fidelity gate, skips verification, or tampers with provenance ledgers.`
						: `Blocked by the git guard: "${hit[0]}" can destroy work or rewrite shared history. ` +
							"Use a safe form instead (git stash, a new branch, git push --force-with-lease to your own feature branch, " +
							"a PR for the default branch), or ask the user to run it themselves.",
				};
			}
		}
	});
}
