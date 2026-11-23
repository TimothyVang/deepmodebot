#!/usr/bin/env node
// UserPromptSubmit hook: deepmodebot uses its live view on its own, with no command to type.
// On the first real prompt in a project it starts `agui.mjs serve --open` (the browser opens once, when the server
// starts); on every prompt it tells the agent the view is live and to use it (references/techniques/live-view.md).
// Off switches: DEEPMODE_LIVE_VIEW=off (or 0/false/no) in the environment, or a `.scratch/live-view/off` file in the
// project. Never runs in the home folder or a filesystem root. Fails open: any problem prints nothing and exits 0.

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, parse, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const AGUI = join(HERE, 'agui.mjs');
const TRIVIAL = /^\s*(hi|hello|hey|thanks|thank you|ok|okay|yes|no|y|n|k|lol|stop|cancel)\b[\s!.?]*$/i;

/** Pure decision, for tests: should this prompt use (and maybe start) the live view? */
export function decide({ prompt = '', cwd = '', env = process.env, home = homedir() } = {}) {
    const off = String(env.DEEPMODE_LIVE_VIEW ?? '').trim().toLowerCase();
    if (['off', '0', 'false', 'no'].includes(off)) return { use: false, why: 'turned off by DEEPMODE_LIVE_VIEW' };
    if (!cwd) return { use: false, why: 'no project folder' };
    const root = resolve(cwd);
    if (root === resolve(home) || root === parse(root).root) return { use: false, why: 'not inside a project folder' };
    if (existsSync(join(root, '.scratch', 'live-view', 'off'))) return { use: false, why: 'turned off for this project' };
    const text = String(prompt).trim();
    if (!text || TRIVIAL.test(text)) return { use: false, why: 'trivial prompt' };
    return { use: true, root };
}

async function healthy(root) {
    const f = join(root, '.scratch', 'live-view', 'session.json');
    if (!existsSync(f)) return null;
    try {
        const s = JSON.parse(readFileSync(f, 'utf8'));
        const r = await fetch(`http://127.0.0.1:${s.port}/health`, { headers: { 'X-Live-View-Token': s.token }, signal: AbortSignal.timeout(600) });
        return r.ok ? s : null;
    } catch { return null; }
}

async function ensureRunning(root) {
    const running = await healthy(root);
    if (running) return { session: running, started: false };
    const scratch = join(root, '.scratch');
    mkdirSync(join(scratch, 'live-view'), { recursive: true });
    if (!existsSync(join(scratch, '.gitignore'))) writeFileSync(join(scratch, '.gitignore'), '*\n'); // deepmodebot's self-ignored scratch
    const args = [AGUI, 'serve', ...(process.env.DEEPMODE_LIVE_VIEW_NO_OPEN ? [] : ['--open'])]; // tests and headless runs skip the browser
    const child = spawn(process.execPath, args, { cwd: root, detached: true, stdio: 'ignore', windowsHide: true });
    child.unref();
    for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 100));
        const s = await healthy(root);
        if (s) return { session: s, started: true };
    }
    return { session: null, started: false };
}

export function context({ url, started }, agui = AGUI) {
    return [
        `deepmode live view is ${started ? 'now open in the human\'s browser' : 'running'}: ${url}`,
        'Use it by default for this task, following references/techniques/live-view.md in skill://deepmodebot: set the goal and plan,',
        'explain with visuals (mermaid, tables, screenshots) and short messages, ask real choices in the page, and back every "works" claim with a proof card.',
        'Skip it only for a one-line answer. Run from the project root:',
        `node "${agui}" plan|status|step|say|visual|proof|ask|done …  (the human sees each call immediately; the terminal reply still carries the full report)`,
    ].join('\n');
}

async function main() {
    let input = {};
    try { input = JSON.parse(readFileSync(0, 'utf8') || '{}'); } catch {}
    const cwd = process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd();
    const d = decide({ prompt: input.prompt ?? '', cwd });
    if (!d.use) return;
    const { session, started } = await ensureRunning(d.root);
    if (!session) return;
    process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: context({ url: session.url, started }) } }));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    main().catch(() => {}).finally(() => process.exit(0));
}
