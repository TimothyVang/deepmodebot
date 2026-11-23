// AG-UI 1.0 client for the deepmode live view: POST RunAgentInput to /agui, read `data:` frames, fold events into
// one snapshot, and answer interrupts with `resume`. No framework code here; React subscribes via useSyncExternalStore.

export type PlanStep = { id: string; title: string; status: 'pending' | 'active' | 'done' | 'blocked'; note?: string | null };
export type Visual = { kind: 'mermaid' | 'table' | 'markdown' | 'code' | 'image'; title?: string | null; body?: string | null; src?: string | null; claim?: string | null; cmd?: string | null; at?: string | null };
export type Item =
  | { id: string; type: 'message'; role: 'assistant' | 'user'; content: string }
  | { id: string; type: 'visual' | 'proof'; content: Visual };
export type Step = { name: string; start: number; end?: number };
export type Interrupt = { id: string; message?: string; reason?: string; expiresAt?: string; responseSchema?: { properties?: { answer?: { enum?: string[] } } } };
export type Status = 'connecting' | 'idle' | 'working' | 'waiting' | 'done' | 'down' | 'locked';
export type Snapshot = { status: Status; goal: string | null; plan: PlanStep[]; items: Item[]; steps: Step[]; pending: Interrupt | null; error?: string };

type Ev = { type: string; [k: string]: any };

const token = new URLSearchParams(location.search).get('t') || sessionStorage.getItem('liveViewToken');
if (token) sessionStorage.setItem('liveViewToken', token); // this tab only; survives a reload
history.replaceState(null, '', location.pathname); // keep the token out of history and screenshots
const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'X-Live-View-Token': token ?? '' };

let snap: Snapshot = { status: 'connecting', goal: null, plan: [], items: [], steps: [], pending: null };
const listeners = new Set<() => void>();
const messages = new Map<string, { role: 'assistant' | 'user'; content: string }>();
const activities = new Map<string, { activityType: string; content: Visual }>();
let order: string[] = [];
let threadId: string | null = null;

function emit(patch: Partial<Snapshot> = {}) {
  const items: Item[] = [];
  for (const id of order) {
    const m = messages.get(id);
    if (m) { items.push({ id, type: 'message', role: m.role, content: m.content }); continue; }
    const a = activities.get(id);
    if (a) items.push({ id, type: a.activityType === 'deepmode.proof' ? 'proof' : 'visual', content: a.content });
  }
  snap = { ...snap, ...patch, items };
  for (const l of listeners) l();
}
export const store = {
  subscribe(l: () => void) { listeners.add(l); return () => listeners.delete(l); },
  get: () => snap,
};
const track = (id: string) => { if (!order.includes(id)) order.push(id); };

// RFC 6902 subset: add / replace / remove, enough for STATE_DELTA.
function applyPatch<T>(doc: T, ops: { op: string; path: string; value?: unknown }[]): T {
  const next: any = structuredClone(doc);
  for (const op of ops) {
    const parts = op.path.split('/').slice(1).map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'));
    const key = parts.pop()!;
    let t = next;
    for (const p of parts) t = t[Array.isArray(t) ? Number(p) : p];
    const k: any = Array.isArray(t) ? (key === '-' ? t.length : Number(key)) : key;
    if (op.op === 'remove') { if (Array.isArray(t)) t.splice(k, 1); else delete t[k]; }
    else if (op.op === 'add' && Array.isArray(t)) t.splice(k, 0, op.value);
    else t[k] = op.value;
  }
  return next;
}

function onEvent(e: Ev) {
  switch (e.type) {
    case 'RUN_STARTED': if (!snap.pending) emit({ status: 'working' }); break;
    case 'MESSAGES_SNAPSHOT':
      messages.clear();
      for (const m of e.messages) { messages.set(m.id, { role: m.role, content: m.content ?? '' }); track(m.id); }
      emit(); break;
    case 'TEXT_MESSAGE_START': messages.set(e.messageId, { role: e.role, content: '' }); track(e.messageId); break;
    case 'TEXT_MESSAGE_CONTENT': { const m = messages.get(e.messageId); if (m) m.content += e.delta; emit(); break; }
    case 'STATE_SNAPSHOT': emit({ goal: e.snapshot?.goal ?? null, plan: e.snapshot?.plan ?? [] }); break;
    case 'STATE_DELTA': { const s = applyPatch({ goal: snap.goal, plan: snap.plan }, e.delta); emit(s); break; }
    case 'STEP_STARTED': emit({ steps: [...snap.steps, { name: e.stepName, start: e.timestamp ?? Date.now() }] }); break;
    case 'STEP_FINISHED': {
      const steps = snap.steps.slice();
      const i = steps.findLastIndex((x) => x.name === e.stepName && !x.end);
      if (i >= 0) steps[i] = { ...steps[i], end: e.timestamp ?? Date.now() };
      else steps.push({ name: e.stepName, start: e.timestamp, end: e.timestamp });
      emit({ steps }); break;
    }
    case 'ACTIVITY_SNAPSHOT': activities.set(e.messageId, { activityType: e.activityType, content: e.content }); track(e.messageId); emit(); break;
    case 'CUSTOM':
      if (e.name === 'deepmode.timeline' && Array.isArray(e.value)) { order = [...e.value, ...order.filter((id) => !e.value.includes(id))]; emit(); }
      if (e.name === 'deepmode.steps' && Array.isArray(e.value)) emit({ steps: e.value });
      break;
    case 'RUN_ERROR': emit({ status: 'down' }); break;
  }
}

async function run(resume?: unknown[]) {
  const body: Record<string, unknown> = { threadId, runId: crypto.randomUUID(), messages: [], state: {}, tools: [], context: [], forwardedProps: {} };
  if (resume) body.resume = resume;
  const res = await fetch('/agui', { method: 'POST', headers, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error(`the view answered ${res.status}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let finished: Ev | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, i); buf = buf.slice(i + 2);
      const data = frame.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trimStart()).join('\n');
      if (!data) continue;
      const e = JSON.parse(data) as Ev;
      if (e.type === 'RUN_FINISHED') finished = e;
      onEvent(e);
    }
  }
  return finished;
}

async function loop(resume?: unknown[]) {
  for (let backoff = 500; ; ) {
    try {
      const fin = await run(resume);
      resume = undefined; backoff = 500;
      if (fin?.outcome?.type === 'interrupt') { emit({ pending: fin.outcome.interrupts[0], status: 'waiting' }); return; }
      emit({ pending: null, ...(fin?.outcome?.type === 'success' ? { status: 'done' as const } : {}) });
    } catch { emit({ status: 'down' }); }
    await new Promise((r) => setTimeout(r, backoff));
    backoff = Math.min(backoff * 2, 8000);
  }
}

/** Answer the waiting question. AG-UI 1.0 ResumeEntry: status `resolved` with a payload, or `cancelled` without one. */
export function answer(value: string | null) {
  const it = snap.pending;
  if (!it) return;
  if (value !== null) { messages.set(`you_${it.id}`, { role: 'user', content: value }); track(`you_${it.id}`); } // the server records it too
  emit({ pending: null, status: 'working' });
  loop([{ interruptId: it.id, status: value === null ? 'cancelled' : 'resolved', ...(value === null ? {} : { payload: { answer: value } }) }]);
}

export async function connect() {
  try {
    const r = await fetch('/health', { headers });
    if (!r.ok) throw new Error('This page needs the link the agent printed. It carries a private token.');
    threadId = (await r.json()).threadId;
    emit({ status: 'idle' });
    loop();
  } catch (e) {
    emit({ status: 'locked', error: (e as Error).message });
  }
}
