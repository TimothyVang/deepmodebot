import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join } from 'node:path';
import { createLiveView } from '../plugins/deepmodebot/skills/deepmodebot/assets/live-view/agui.mjs';
import { decide, context } from '../plugins/deepmodebot/skills/deepmodebot/assets/live-view/autostart.mjs';

const AUTOSTART = new URL('../plugins/deepmodebot/skills/deepmodebot/assets/live-view/autostart.mjs', import.meta.url);
const AGUI = new URL('../plugins/deepmodebot/skills/deepmodebot/assets/live-view/agui.mjs', import.meta.url);

// AG-UI's own schemas (CI installs @ag-ui/core and zod with --no-save; the package itself has no dependencies).
let schemas = null;
try { schemas = await import('@ag-ui/core/schemas'); } catch {}
const PNG_1PX = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

async function start() {
    const lv = createLiveView();
    await new Promise((r) => lv.server.listen(0, '127.0.0.1', r));
    const base = `http://127.0.0.1:${lv.server.address().port}`;
    const H = { 'Content-Type': 'application/json', 'X-Live-View-Token': lv.token };
    const act = async (name, body) => {
        const r = await fetch(`${base}/act/${name}`, { method: 'POST', headers: H, body: JSON.stringify(body) });
        return { status: r.status, body: await r.json() };
    };
    /** One viewer run exactly as viewer.html builds it; resolves with every event once the stream ends. */
    const viewerRun = (resume) => {
        const input = { threadId: lv.threadId, runId: crypto.randomUUID(), messages: [], state: {}, tools: [], context: [], forwardedProps: {} };
        if (resume) input.resume = resume;
        if (schemas) schemas.RunAgentInputSchema.parse(input);
        return fetch(`${base}/agui`, { method: 'POST', headers: { ...H, Accept: 'text/event-stream' }, body: JSON.stringify(input) })
            .then(async (r) => {
                assert.equal(r.headers.get('content-type'), 'text/event-stream');
                const text = await r.text();
                return text.split('\n\n').filter(Boolean).map((f) => { assert.ok(f.startsWith('data: '), f); return JSON.parse(f.slice(6)); });
            });
    };
    return { lv, base, H, act, viewerRun, close: () => new Promise((r) => { lv.server.closeAllConnections(); lv.server.close(r); }) };
}

function assertAgUi(events, t) {
    if (!schemas) return t.diagnostic('AG-UI schema check skipped: npm install --no-save @ag-ui/core@1.0.5 zod to run it');
    for (const e of events) {
        const r = schemas.EventSchemas.safeParse(e);
        assert.ok(r.success, `${e.type} is not a valid AG-UI 1.0 event: ${r.error?.message}`);
    }
}

test('a full session streams valid AG-UI 1.0 events: plan, progress, messages, visuals, proof, question, answer, finish', async (t) => {
    const s = await start();
    t.after(s.close);
    const run1 = s.viewerRun();
    await new Promise((r) => setTimeout(r, 50)); // the viewer is connected before the agent speaks
    await s.act('plan', { goal: 'Ship the live view', steps: ['Design', { id: 'build', title: 'Build' }, 'Prove'] });
    await s.act('status', { id: 's1', status: 'done', note: 'AG-UI events chosen' });
    await s.act('status', { id: 'build', status: 'active' });
    await s.act('step', { phase: 'start', name: 'Write the server' });
    await s.act('say', { text: 'Here is how the pieces fit together:' });
    await s.act('visual', { kind: 'mermaid', title: 'Flow', body: 'flowchart LR\n agent-->server-->viewer' });
    await s.act('visual', { kind: 'table', title: 'Events', body: JSON.stringify([{ event: 'STATE_SNAPSHOT', shows: 'plan' }]) });
    await s.act('visual', { kind: 'image', title: 'Screenshot', src: PNG_1PX });
    await s.act('visual', { activityType: 'deepmode.proof', kind: 'code', title: 'tests pass', claim: 'tests pass', cmd: 'npm test', body: 'ℹ pass 12' });
    await s.act('step', { phase: 'finish', name: 'Write the server' });
    const asked = s.act('ask', { question: 'Ship it?', choices: ['yes', 'not yet'] });

    const ev1 = await run1;
    assertAgUi(ev1, t);
    assert.equal(ev1[0].type, 'RUN_STARTED');
    const last = ev1.at(-1);
    assert.equal(last.type, 'RUN_FINISHED');
    assert.equal(last.runId, ev1[0].runId);
    assert.equal(last.outcome.type, 'interrupt');
    const [interrupt] = last.outcome.interrupts;
    assert.equal(interrupt.message, 'Ship it?');
    assert.deepEqual(interrupt.responseSchema.properties.answer.enum, ['yes', 'not yet']);
    const types = ev1.map((e) => e.type);
    for (const ty of ['MESSAGES_SNAPSHOT', 'STATE_SNAPSHOT', 'STATE_DELTA', 'STEP_STARTED', 'STEP_FINISHED', 'TEXT_MESSAGE_START', 'TEXT_MESSAGE_CONTENT', 'TEXT_MESSAGE_END', 'ACTIVITY_SNAPSHOT']) {
        assert.ok(types.includes(ty), `missing ${ty}`);
    }
    assert.ok(types.indexOf('TEXT_MESSAGE_START') < types.indexOf('TEXT_MESSAGE_CONTENT') && types.indexOf('TEXT_MESSAGE_CONTENT') < types.indexOf('TEXT_MESSAGE_END'));
    const delta = ev1.find((e) => e.type === 'STATE_DELTA');
    assert.deepEqual(delta.delta[0], { op: 'replace', path: '/plan/0/status', value: 'done' });
    const acts = ev1.filter((e) => e.type === 'ACTIVITY_SNAPSHOT');
    assert.deepEqual(acts.map((a) => a.content.kind), ['mermaid', 'table', 'image', 'code']);
    assert.equal(acts.at(-1).activityType, 'deepmode.proof');

    // The human answers: a new run resumes the interrupt; the agent's `ask` returns the answer.
    const resume = [{ interruptId: interrupt.id, status: 'resolved', payload: { answer: 'yes' } }];
    if (schemas) resume.forEach((r) => schemas.ResumeEntrySchema.parse(r));
    const run2 = s.viewerRun(resume);
    const answer = await asked;
    assert.deepEqual(answer.body, { status: 'resolved', payload: { answer: 'yes' } });
    await s.act('status', { id: 's3', status: 'done' });
    await s.act('done', { summary: 'Shipped.' });
    const ev2 = await run2;
    assertAgUi(ev2, t);
    assert.equal(ev2[0].type, 'RUN_STARTED');
    assert.notEqual(ev2[0].runId, ev1[0].runId, 'a resume is a new run');
    assert.deepEqual(ev2.at(-1).outcome, { type: 'success' });
    const snap = ev2.find((e) => e.type === 'MESSAGES_SNAPSHOT');
    assert.ok(snap.messages.some((m) => m.role === 'user' && m.content === 'yes'), 'the answer is part of the conversation');
    const state = ev2.find((e) => e.type === 'STATE_SNAPSHOT').snapshot;
    assert.deepEqual(state.plan.map((p) => p.status), ['done', 'active', 'pending']);
});

test('a viewer that connects late gets everything as snapshots, including a waiting question', async (t) => {
    const s = await start();
    t.after(s.close);
    await s.act('plan', { goal: 'g', steps: ['a'] });
    await s.act('say', { text: 'said before anyone watched' });
    await s.act('step', { phase: 'start', name: 'build' });
    await s.act('step', { phase: 'finish', name: 'build' });
    await s.act('visual', { kind: 'markdown', body: '**hi**' });
    const asked = s.act('ask', { question: 'Which one?' });
    await new Promise((r) => setTimeout(r, 30));
    const ev = await s.viewerRun();
    assertAgUi(ev, t);
    assert.equal(ev.find((e) => e.type === 'MESSAGES_SNAPSHOT').messages[0].content, 'said before anyone watched');
    assert.equal(ev.filter((e) => e.type === 'ACTIVITY_SNAPSHOT').length, 1);
    const timeline = ev.find((e) => e.type === 'CUSTOM' && e.name === 'deepmode.timeline');
    assert.equal(timeline.value.length, 2, 'the message and the visual, in the order they were shown');
    assert.ok(timeline.value[0].startsWith('msg_') && timeline.value[1].startsWith('act_'));
    const trace = ev.find((e) => e.type === 'CUSTOM' && e.name === 'deepmode.steps');
    assert.equal(trace.value.length, 1, 'the activity trace reaches a late viewer');
    assert.equal(trace.value[0].name, 'build'); assert.ok(trace.value[0].end >= trace.value[0].start);
    const fin = ev.at(-1);
    assert.equal(fin.outcome.type, 'interrupt');
    const id = fin.outcome.interrupts[0].id;
    const ev2 = s.viewerRun([{ interruptId: id, status: 'cancelled' }]);
    assert.deepEqual((await asked).body, { status: 'cancelled' });
    await s.act('done', {});
    await ev2;
});

test('local and authenticated: token required, wrong input refused, viewer served with a strict CSP', async (t) => {
    const s = await start();
    t.after(s.close);
    assert.equal((await fetch(`${s.base}/`)).status, 401);
    assert.equal((await fetch(`${s.base}/act/say`, { method: 'POST', body: '{"text":"x"}' })).status, 401);
    const page = await fetch(`${s.base}/?t=${s.lv.token}`);
    assert.equal(page.status, 200);
    assert.match(page.headers.get('content-security-policy'), /default-src 'self'/);
    assert.match(page.headers.get('content-security-policy'), /font-src 'self' data:/, 'the viewer inlines its font');
    const html = await page.clone().text().catch(() => null);
    if (html) assert.ok(!/<script[^>]+src="https?:/i.test(html), 'the viewer loads no remote script tags (Mermaid is imported on demand only)');
    assert.match(await page.text(), /deepmode live/);
    assert.equal((await fetch(`${s.base}/agui`, { method: 'POST', headers: s.H, body: '{}' })).status, 406, 'AG-UI runs must ask for an event stream');
    assert.equal((await s.act('visual', { kind: 'html', body: '<script>' })).status, 400);
    assert.equal((await s.act('visual', { kind: 'image', src: 'javascript:alert(1)' })).status, 400);
    assert.equal((await s.act('status', { id: 'nope', status: 'done' })).status, 404);
    assert.equal((await s.act('say', { text: '  ' })).status, 400);
    const asked = s.act('ask', { question: 'q' });
    await new Promise((r) => setTimeout(r, 20));
    assert.equal((await s.act('ask', { question: 'second' })).status, 409, 'one question at a time');
    const bad = await fetch(`${s.base}/agui`, { method: 'POST', headers: { ...s.H, Accept: 'text/event-stream' },
        body: JSON.stringify({ threadId: s.lv.threadId, runId: 'r', messages: [], resume: [{ interruptId: 'int_wrong', status: 'resolved' }] }) });
    assert.equal(bad.status, 400, 'a resume must answer the pending question');
    const ok = s.viewerRun();
    const id = (await ok).at(-1).outcome.interrupts[0].id;
    const fin = s.viewerRun([{ interruptId: id, status: 'resolved', payload: { answer: 'fine' } }]);
    assert.equal((await asked).body.payload.answer, 'fine');
    await s.act('done', {});
    await fin;
});

test('autostart decides: on for real work in a project, off by switch, never in the home folder', () => {
    const proj = mkdtempSync(join(tmpdir(), 'lv-proj-'));
    assert.equal(decide({ prompt: 'add a dark mode toggle to settings', cwd: proj, env: {} }).use, true);
    for (const p of ['thanks', 'ok', 'yes', '   ']) assert.equal(decide({ prompt: p, cwd: proj, env: {} }).use, false, p);
    for (const v of ['off', '0', 'false', 'no', 'OFF']) assert.equal(decide({ prompt: 'build it', cwd: proj, env: { DEEPMODE_LIVE_VIEW: v } }).use, false, v);
    assert.equal(decide({ prompt: 'build it', cwd: homedir(), env: {} }).use, false);
    mkdirSync(join(proj, '.scratch', 'live-view'), { recursive: true });
    writeFileSync(join(proj, '.scratch', 'live-view', 'off'), '');
    assert.equal(decide({ prompt: 'build it', cwd: proj, env: {} }).why, 'turned off for this project');
    rmSync(proj, { recursive: true, force: true });
    assert.match(context({ url: 'http://127.0.0.1:1/?t=x', started: true }), /now open in the human's browser.*\n.*live-view\.md/s);
});

test('autostart as a Claude Code hook: the first prompt starts the view, the next reuses it, nothing to type', async (t) => {
    const proj = mkdtempSync(join(tmpdir(), 'lv-hook-'));
    const env = { ...process.env, CLAUDE_PROJECT_DIR: proj, DEEPMODE_LIVE_VIEW_NO_OPEN: '1', DEEPMODE_LIVE_VIEW: '' };
    t.after(() => { spawnSync(process.execPath, [AGUI.pathname.replace(/^\/([A-Za-z]:)/, '$1'), 'stop'], { cwd: proj }); rmSync(proj, { recursive: true, force: true }); });
    const hook = (prompt) => spawnSync(process.execPath, [AUTOSTART.pathname.replace(/^\/([A-Za-z]:)/, '$1')], { input: JSON.stringify({ prompt, cwd: proj }), env, encoding: 'utf8', timeout: 15000 });
    const first = hook('refactor the billing module');
    assert.equal(first.status, 0, first.stderr);
    const ctx1 = JSON.parse(first.stdout).hookSpecificOutput;
    assert.equal(ctx1.hookEventName, 'UserPromptSubmit');
    assert.match(ctx1.additionalContext, /now open in the human's browser: http:\/\/127\.0\.0\.1:\d+\/\?t=/);
    const url = /http:\/\/127\.0\.0\.1:\d+\/\?t=\S+/.exec(ctx1.additionalContext)[0];
    assert.equal((await fetch(url)).status, 200, 'the view is really serving');
    const second = hook('now add tests for it');
    assert.match(JSON.parse(second.stdout).hookSpecificOutput.additionalContext, /^deepmode live view is running: /, 'reused, not restarted');
    assert.equal(hook('thanks').stdout, '', 'trivial prompts add nothing');
});

test('a question answered later than the slow-path threshold still returns clean JSON (heartbeat keeps HTTP alive)', { timeout: 20000 }, async (t) => {
    const s = await start();
    t.after(s.close);
    const asked = s.act('ask', { question: 'Take your time?', choices: ['yes', 'no'] });
    await new Promise((r) => setTimeout(r, 30));
    const ev = await s.viewerRun();
    const id = ev.find((e) => e.type === 'RUN_FINISHED').outcome.interrupts[0].id;
    await new Promise((r) => setTimeout(r, 1300)); // past the 1 s point where the server switches to headers + heartbeat
    const run2 = s.viewerRun([{ interruptId: id, status: 'resolved', payload: { answer: 'yes' } }]); // stays open until the agent finishes
    const out = await asked;
    assert.equal(out.status, 200);
    assert.deepEqual(out.body, { status: 'resolved', payload: { answer: 'yes' } });
    const q2 = s.act('ask', { question: 'q2', timeoutSec: 2 }); // stays open; times out on its own
    await new Promise((r) => setTimeout(r, 50));
    assert.equal((await s.act('ask', { question: 'q3' })).status, 409, 'errors still surface as HTTP errors, not as a heartbeat');
    assert.equal((await q2).body.status, 'cancelled', 'an unanswered question times out cleanly through the slow path');
    await s.act('done', { summary: 'ok' });
    await run2;
});
