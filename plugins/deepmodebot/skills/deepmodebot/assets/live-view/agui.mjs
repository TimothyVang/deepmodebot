#!/usr/bin/env node
// deepmodebot live view: an AG-UI 1.0 server the agent drives from the command line, and a viewer page that shows
// the human the plan, progress, messages, visuals and proof, and lets them answer the agent's questions.
//
//   node agui.mjs serve [--port N] [--open]          start (prints the viewer URL); one per project folder
//   node agui.mjs say "<markdown>"                    a message from the agent
//   node agui.mjs plan <file.json|-> | --goal "<g>" "<step>"...   the plan (state snapshot)
//   node agui.mjs status <stepId> <pending|active|done|blocked> ["note"]   one step's status (state delta)
//   node agui.mjs step start|finish "<name>"          a progress step
//   node agui.mjs visual <mermaid|table|markdown|code|image> <file|-> [--title "<t>"]   a visual
//   node agui.mjs proof "<claim>" --evidence <file> [--cmd "<command that produced it>"]   evidence for a claim
//   node agui.mjs ask "<question>" [--choices "a|b|c"] [--timeout 900]   ask the human; prints {status:resolved,payload:{answer}} or {status:cancelled}
//   node agui.mjs done ["<summary>"]                  finish the run
//   node agui.mjs stop                                 stop the server
//
// Wire protocol (AG-UI 1.0, https://docs.ag-ui.com/spec/1.0): the viewer POSTs a RunAgentInput to /agui and reads
// `data: <event>\n\n` frames. Plan = STATE_SNAPSHOT/STATE_DELTA, progress = STEP_*, messages = TEXT_MESSAGE_*,
// visuals and proof = ACTIVITY_SNAPSHOT (activityType deepmode.visual / deepmode.proof). A question ends the run with
// RUN_FINISHED outcome {type:"interrupt"}; the answer comes back as RunAgentInput.resume on the next run.
// Local only: binds 127.0.0.1, every request needs the session token, nothing is sent anywhere else.

import { createServer as createHttpServer } from 'node:http';
import { randomBytes, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, appendFileSync, writeFileSync, rmSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MAX_BODY = 8 * 1024 * 1024;
const MAX_IMAGE = 6 * 1024 * 1024;
export const VISUAL_KINDS = ['mermaid', 'table', 'markdown', 'code', 'image'];
const STATUSES = ['pending', 'active', 'done', 'blocked'];
const IMAGE_TYPES = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml' };

const sessionDir = (cwd = process.cwd()) => join(cwd, '.scratch', 'live-view');
const sessionFile = (cwd) => join(sessionDir(cwd), 'session.json');

// ---------------------------------------------------------------- the server

/**
 * @param {{ token?: string, logFile?: string|null, now?: () => number }} [opts]
 * @returns {{ server: import('node:http').Server, token: string, threadId: string }}
 */
export function createLiveView({ token = randomBytes(18).toString('base64url'), logFile = null, now = Date.now } = {}) {
    const threadId = `thread_${randomUUID()}`;
    const viewerHtml = readFileSync(join(HERE, 'viewer.html'), 'utf8');
    /** Everything the agent has shown, so a viewer that (re)connects gets snapshots. */
    const history = { messages: [], state: { goal: null, plan: [] }, activities: new Map() };
    let current = null; // { runId, res } — the open SSE run, if a viewer is connected
    let pendingAsk = null; // { interrupt, resolve } — a question waiting for the human

    const stamp = (e) => ({ ...e, timestamp: now() });
    const log = (e) => { if (logFile) try { appendFileSync(logFile, `${JSON.stringify(e)}\n`); } catch {} };
    const send = (e) => {
        const ev = stamp(e);
        log(ev);
        if (current && !current.res.writableEnded) current.res.write(`data: ${JSON.stringify(ev)}\n\n`);
        return ev;
    };
    const finishRun = (outcome) => {
        if (!current) return;
        const { runId, res } = current;
        const ev = stamp({ type: 'RUN_FINISHED', threadId, runId, outcome });
        log(ev);
        res.write(`data: ${JSON.stringify(ev)}\n\n`);
        res.end();
        current = null;
    };

    // ---- agent actions → AG-UI events (the only place events are built)
    const actions = {
        say({ text }) {
            const messageId = `msg_${randomUUID()}`;
            const body = String(text ?? '').trim();
            if (!body) throw httpError(400, 'say needs text');
            history.messages.push({ id: messageId, role: 'assistant', content: body });
            send({ type: 'TEXT_MESSAGE_START', messageId, role: 'assistant' });
            for (const chunk of body.match(/[\s\S]{1,2000}/g)) send({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta: chunk });
            send({ type: 'TEXT_MESSAGE_END', messageId });
            return { messageId };
        },
        plan({ goal = null, steps = [] }) {
            if (!Array.isArray(steps)) throw httpError(400, 'plan steps must be a list');
            const plan = steps.map((s, i) => {
                const o = typeof s === 'string' ? { title: s } : s;
                const status = STATUSES.includes(o.status) ? o.status : 'pending';
                return { id: String(o.id ?? `s${i + 1}`), title: String(o.title ?? '').slice(0, 300), status, note: o.note ? String(o.note).slice(0, 500) : null };
            });
            history.state = { goal: goal ? String(goal).slice(0, 500) : history.state.goal, plan };
            send({ type: 'STATE_SNAPSHOT', snapshot: history.state });
            return { steps: plan.length };
        },
        status({ id, status, note = null }) {
            if (!STATUSES.includes(status)) throw httpError(400, `status must be one of ${STATUSES.join(', ')}`);
            const i = history.state.plan.findIndex((s) => s.id === String(id));
            if (i < 0) throw httpError(404, `no plan step "${id}"`);
            history.state.plan[i] = { ...history.state.plan[i], status, note: note ? String(note).slice(0, 500) : history.state.plan[i].note };
            send({ type: 'STATE_DELTA', delta: [
                { op: 'replace', path: `/plan/${i}/status`, value: status },
                { op: 'replace', path: `/plan/${i}/note`, value: history.state.plan[i].note },
            ] });
            return { id, status };
        },
        step({ phase, name }) {
            if (!['start', 'finish'].includes(phase) || !name) throw httpError(400, 'step needs start|finish and a name');
            send({ type: phase === 'start' ? 'STEP_STARTED' : 'STEP_FINISHED', stepName: String(name).slice(0, 200) });
            return { ok: true };
        },
        visual({ kind, title = null, body = null, src = null, activityType = 'deepmode.visual', claim = null, cmd = null }) {
            if (activityType === 'deepmode.visual' && !VISUAL_KINDS.includes(kind)) throw httpError(400, `visual kind must be one of ${VISUAL_KINDS.join(', ')}`);
            if (src && !/^data:image\/(png|jpeg|webp|gif|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(src)) throw httpError(400, 'image src must be a base64 data URL');
            const messageId = `act_${randomUUID()}`;
            const content = { kind, title: title ? String(title).slice(0, 200) : null, body: body == null ? null : String(body), src, claim, cmd, at: new Date(now()).toISOString() };
            history.activities.set(messageId, { activityType, content });
            send({ type: 'ACTIVITY_SNAPSHOT', messageId, activityType, content, replace: true });
            return { messageId };
        },
        ask({ question, choices = [], timeoutSec = 900 }) {
            const q = String(question ?? '').trim();
            if (!q) throw httpError(400, 'ask needs a question');
            if (pendingAsk) throw httpError(409, 'a question is already waiting for the human');
            const id = `int_${randomUUID()}`;
            const opts = (Array.isArray(choices) ? choices : []).map(String).filter(Boolean).slice(0, 8);
            const interrupt = {
                id, reason: 'input_required', message: q,
                responseSchema: opts.length ? { type: 'object', properties: { answer: { type: 'string', enum: opts } }, required: ['answer'] }
                    : { type: 'object', properties: { answer: { type: 'string' } }, required: ['answer'] },
                expiresAt: new Date(now() + timeoutSec * 1000).toISOString(),
            };
            return new Promise((resolveAsk) => {
                const timer = setTimeout(() => { if (pendingAsk?.interrupt.id === id) { pendingAsk = null; resolveAsk({ status: 'cancelled', reason: 'timeout' }); } }, timeoutSec * 1000);
                timer.unref?.();
                pendingAsk = { interrupt, resolve: (r) => { clearTimeout(timer); resolveAsk(r); } };
                finishRun({ type: 'interrupt', interrupts: [interrupt] }); // no viewer: it sees the question when it connects
            });
        },
        done({ summary = null }) {
            if (summary) actions.say({ text: summary });
            finishRun({ type: 'success' });
            return { ok: true };
        },
    };

    // ---- a viewer run (POST /agui with RunAgentInput)
    function startRun(input, res) {
        const runId = typeof input.runId === 'string' && input.runId ? input.runId : `run_${randomUUID()}`;
        if (Array.isArray(input.resume) && input.resume.length) {
            const r = input.resume.find((x) => x?.interruptId === pendingAsk?.interrupt.id);
            if (pendingAsk && !r) throw httpError(400, 'resume must answer the pending interrupt');
            if (pendingAsk && r) {
                const p = pendingAsk;
                pendingAsk = null;
                const answered = r.status === 'resolved'; // AG-UI 1.0 ResumeEntry.status: resolved | cancelled
                if (answered && r.payload?.answer != null) history.messages.push({ id: `you_${p.interrupt.id}`, role: 'user', content: String(r.payload.answer).slice(0, 4000) });
                p.resolve(answered ? { status: 'resolved', payload: r.payload ?? null } : { status: 'cancelled' });
            }
        }
        if (current) finishRun({ type: 'success' }); // one viewer at a time; a newer tab takes over
        res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
        current = { runId, res };
        res.on('close', () => { if (current?.res === res) current = null; });
        send({ type: 'RUN_STARTED', threadId, runId });
        // Catch the viewer up: everything shown so far, as snapshots.
        send({ type: 'MESSAGES_SNAPSHOT', messages: history.messages });
        send({ type: 'STATE_SNAPSHOT', snapshot: history.state });
        for (const [messageId, a] of history.activities) send({ type: 'ACTIVITY_SNAPSHOT', messageId, activityType: a.activityType, content: a.content, replace: true });
        if (pendingAsk) finishRun({ type: 'interrupt', interrupts: [pendingAsk.interrupt] });
    }

    const server = createHttpServer(async (req, res) => {
        try {
            const url = new URL(req.url, 'http://127.0.0.1');
            const authed = req.headers['x-live-view-token'] === token || url.searchParams.get('t') === token;
            if (req.method === 'GET' && url.pathname === '/') {
                if (!authed) throw httpError(401, 'open the viewer with the URL printed by `agui.mjs serve`');
                res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                    'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'" });
                return res.end(viewerHtml);
            }
            if (!authed) throw httpError(401, 'missing or wrong session token');
            if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, { ok: true, threadId, viewer: Boolean(current), waiting: pendingAsk?.interrupt.message ?? null });
            if (req.method === 'POST' && url.pathname === '/agui') {
                if (!/text\/event-stream/.test(req.headers.accept ?? '')) throw httpError(406, 'AG-UI runs stream: send Accept: text/event-stream');
                const input = await readJson(req);
                if (input.threadId && input.threadId !== threadId) throw httpError(409, `this view serves ${threadId}`);
                return startRun(input, res);
            }
            if (req.method === 'POST' && url.pathname.startsWith('/act/')) {
                const name = url.pathname.slice('/act/'.length);
                if (!Object.hasOwn(actions, name)) throw httpError(404, `unknown action ${name}`);
                const out = await actions[name](await readJson(req));
                return json(res, 200, out ?? { ok: true });
            }
            throw httpError(404, 'not found');
        } catch (err) {
            if (!res.headersSent) json(res, err.status ?? 500, { error: err.status ? err.message : 'internal error' });
            else res.end();
        }
    });
    return { server, token, threadId, actions };
}

function httpError(status, message) { return Object.assign(new Error(message), { status }); }
function json(res, status, body) { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)); }
function readJson(req) {
    return new Promise((resolveBody, reject) => {
        let size = 0; const chunks = [];
        req.on('data', (c) => { size += c.length; if (size > MAX_BODY) { reject(httpError(413, 'body too large')); req.destroy(); } else chunks.push(c); });
        req.on('end', () => { try { resolveBody(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}); } catch { reject(httpError(400, 'body must be JSON')); } });
        req.on('error', reject);
    });
}

// ---------------------------------------------------------------- the CLI

function arg(args, name, fallback = null) { const i = args.indexOf(name); return i >= 0 && i + 1 < args.length ? args.splice(i, 2)[1] : fallback; }
function readInput(p) { return p === '-' ? readFileSync(0, 'utf8') : readFileSync(resolve(p), 'utf8'); }

async function call(action, body) {
    const s = existsSync(sessionFile()) ? JSON.parse(readFileSync(sessionFile(), 'utf8')) : null;
    if (!s) throw new Error('no live view running here: start one with `node agui.mjs serve`');
    const res = await fetch(`http://127.0.0.1:${s.port}/act/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Live-View-Token': s.token }, body: JSON.stringify(body) });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(out.error ?? `HTTP ${res.status}`);
    return out;
}

function openBrowser(url) {
    const [cmd, args] = process.platform === 'win32' ? ['cmd', ['/c', 'start', '""', url]] : process.platform === 'darwin' ? ['open', [url]] : ['xdg-open', [url]];
    spawn(cmd, args, { stdio: 'ignore', detached: true, windowsHide: true }).unref();
}

export async function main(argv) {
    const [cmd, ...args] = argv;
    switch (cmd) {
        case 'serve': {
            const port = Number(arg(args, '--port', '0'));
            const open = args.includes('--open');
            mkdirSync(sessionDir(), { recursive: true });
            const { server, token, threadId } = createLiveView({ logFile: join(sessionDir(), 'events.jsonl') });
            await new Promise((r) => server.listen(port, '127.0.0.1', r));
            const url = `http://127.0.0.1:${server.address().port}/?t=${token}`;
            writeFileSync(sessionFile(), JSON.stringify({ port: server.address().port, token, threadId, pid: process.pid, url }), { mode: 0o600 });
            const stop = () => { try { rmSync(sessionFile(), { force: true }); } catch {} process.exit(0); };
            process.on('SIGINT', stop); process.on('SIGTERM', stop);
            console.log(JSON.stringify({ url, threadId, events: join(sessionDir(), 'events.jsonl') }));
            if (open) openBrowser(url);
            return; // keep serving
        }
        case 'say': return print(await call('say', { text: args.join(' ') === '-' ? readInput('-') : args.join(' ') }));
        case 'plan': {
            const goal = arg(args, '--goal');
            const steps = args.length === 1 && (args[0] === '-' || args[0].endsWith('.json')) ? JSON.parse(readInput(args[0])) : args;
            return print(await call('plan', Array.isArray(steps) ? { goal, steps } : steps));
        }
        case 'status': return print(await call('status', { id: args[0], status: args[1], note: args[2] ?? null }));
        case 'step': return print(await call('step', { phase: args[0], name: args.slice(1).join(' ') }));
        case 'visual': {
            const title = arg(args, '--title');
            const [kind, file] = args;
            if (kind === 'image') {
                const p = resolve(file);
                const type = IMAGE_TYPES[extname(p).toLowerCase()];
                if (!type) throw new Error(`image must be one of ${Object.keys(IMAGE_TYPES).join(' ')}`);
                const buf = readFileSync(p);
                if (buf.length > MAX_IMAGE) throw new Error('image is over 6 MB');
                return print(await call('visual', { kind, title, src: `data:${type};base64,${buf.toString('base64')}` }));
            }
            return print(await call('visual', { kind, title, body: readInput(file) }));
        }
        case 'proof': {
            const evidence = arg(args, '--evidence');
            const command = arg(args, '--cmd');
            const claim = args.join(' ');
            if (!claim || !evidence) throw new Error('proof needs a claim and --evidence <file>');
            const p = resolve(evidence);
            const type = IMAGE_TYPES[extname(p).toLowerCase()];
            const body = type ? null : readFileSync(p, 'utf8').slice(0, 20000);
            const src = type ? `data:${type};base64,${readFileSync(p).toString('base64')}` : null;
            return print(await call('visual', { activityType: 'deepmode.proof', kind: type ? 'image' : 'code', title: claim, claim, cmd: command, body, src }));
        }
        case 'ask': {
            const choices = (arg(args, '--choices') ?? '').split('|').map((s) => s.trim()).filter(Boolean);
            const timeoutSec = Number(arg(args, '--timeout', '900'));
            return print(await call('ask', { question: args.join(' '), choices, timeoutSec }));
        }
        case 'done': return print(await call('done', { summary: args.join(' ') || null }));
        case 'stop': {
            const s = existsSync(sessionFile()) ? JSON.parse(readFileSync(sessionFile(), 'utf8')) : null;
            if (!s) return print({ stopped: false, reason: 'not running' });
            try { process.kill(s.pid); } catch {}
            rmSync(sessionFile(), { force: true });
            return print({ stopped: true });
        }
        default:
            console.error('usage: node agui.mjs serve|say|plan|status|step|visual|proof|ask|done|stop  (see the header of agui.mjs)');
            process.exitCode = 2;
    }
}
function print(o) { console.log(JSON.stringify(o)); }

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    main(process.argv.slice(2)).catch((e) => { console.error(e.message); process.exitCode = 1; });
}
