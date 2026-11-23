import * as React from 'react';
import { CheckIcon, CircleAlertIcon, LoaderCircleIcon, MaximizeIcon, MoonIcon, SunIcon, TerminalIcon, CircleIcon, ListChecksIcon, ChevronDownIcon } from 'lucide-react';

import { answer, store, type Item, type PlanStep, type Snapshot, type Visual } from '@/lib/agui';
import { Markdown } from '@/lib/markdown';
import { Mermaid } from '@/components/mermaid';
import { Badge } from '@/components/ui/badge';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Button } from '@/components/ui/button';
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CodeBlock, CodeBlockContent, CodeBlockCopyButton, CodeBlockHeader, CodeBlockTitle, CodeBlockActions } from '@/components/ui/code-block';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Marker, MarkerContent } from '@/components/ui/marker';
import { Message, MessageContent, MessageHeader } from '@/components/ui/message';
import { MessageScroller, MessageScrollerButton, MessageScrollerContent, MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport } from '@/components/ui/message-scroller';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import { Trace, TraceCollapsible, TraceCollapsibleContent, TraceCollapsibleTrigger, TraceDescription, TraceIcon, TraceLine, TraceTitle } from '@/components/ui/trace';

const useSnap = () => React.useSyncExternalStore(store.subscribe, store.get);

// ---------- theme: dark by default, the choice is remembered per browser
function useTheme() {
  const [dark, setDark] = React.useState(() => document.documentElement.classList.contains('dark'));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle('dark', next);
    try { localStorage.setItem('liveViewTheme', next ? 'dark' : 'light'); } catch { /* storage blocked: keep it for this visit */ }
    setDark(next);
  };
  return { dark, toggle };
}

// ---------- header
const STATUS: Record<Snapshot['status'], { word: string; cls: string }> = {
  connecting: { word: 'Connecting…', cls: 'text-muted-foreground' },
  idle: { word: 'Ready', cls: 'text-muted-foreground' },
  working: { word: 'Working', cls: 'text-status-run' },
  waiting: { word: 'Waiting for you', cls: 'text-ask' },
  done: { word: 'Done', cls: 'text-status-ok' },
  down: { word: 'Reconnecting…', cls: 'text-destructive' },
  locked: { word: 'Link needed', cls: 'text-destructive' },
};
function StatusWord({ status }: { status: Snapshot['status'] }) {
  const s = STATUS[status];
  React.useEffect(() => { document.title = status === 'waiting' ? '● Your input · deepmode' : 'deepmode live'; }, [status]);
  return (
    <span className={`inline-flex items-center gap-2 text-sm font-medium ${s.cls}`} role="status" aria-live="polite">
      {status === 'working' ? <LoaderCircleIcon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <CircleIcon className="size-2 fill-current" aria-hidden />}
      {s.word}
    </span>
  );
}

// ---------- plan rail
function PlanIcon({ status }: { status: PlanStep['status'] }) {
  if (status === 'done') return <CheckIcon className="size-4 text-status-ok" />;
  if (status === 'active') return <LoaderCircleIcon className="size-4 animate-spin text-status-run motion-reduce:animate-none" />;
  if (status === 'blocked') return <CircleAlertIcon className="size-4 text-destructive" />;
  return <CircleIcon className="size-4 text-muted-foreground/60" />;
}
const dur = (ms: number) => (ms < 1000 ? `${ms} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 60000)} min`);

function Plan({ snap }: { snap: Snapshot }) {
  const done = snap.plan.filter((p) => p.status === 'done').length;
  const pct = snap.plan.length ? Math.round((done / snap.plan.length) * 100) : 0;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="plan-h" className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between text-sm">
          <h2 id="plan-h" className="font-medium">Plan</h2>
          <span className="text-muted-foreground tabular-nums">{snap.plan.length ? `${done} of ${snap.plan.length} done` : 'No plan yet'}</span>
        </div>
        <Progress value={pct} aria-label={`Plan ${pct}% done`} />
        <Trace className="gap-2.5">
          {snap.plan.map((p) => (
            <TraceLine key={p.id} status={p.status === 'blocked' ? 'error' : p.status === 'pending' ? 'pending' : undefined} className="items-start">
              <TraceIcon className="mt-0.5"><PlanIcon status={p.status} /></TraceIcon>
              <span className="flex min-w-0 flex-col">
                <TraceTitle className={`whitespace-normal ${p.status === 'active' ? 'font-medium text-foreground' : p.status === 'done' ? 'text-muted-foreground' : ''}`}>{p.title}</TraceTitle>
                {p.note ? <TraceDescription className="text-xs">{p.note}</TraceDescription> : null}
                <span className="sr-only">({p.status})</span>
              </span>
            </TraceLine>
          ))}
        </Trace>
      </section>
      <section aria-labelledby="act-h" className="flex flex-col gap-3">
        <h2 id="act-h" className="text-sm font-medium">Activity</h2>
        {snap.steps.length ? (
          <Trace>
            {snap.steps.slice().reverse().map((s, i) => (
              <TraceLine key={`${s.name}-${s.start}-${i}`} status={s.end ? undefined : 'running'}>
                <TraceIcon>{s.end ? <TerminalIcon /> : <LoaderCircleIcon className="animate-spin motion-reduce:animate-none" />}</TraceIcon>
                <TraceTitle>{s.end ? `Ran ${s.name}` : `Running ${s.name}`}</TraceTitle>
                {s.end ? <TraceDescription className="tabular-nums">{dur(s.end - s.start)}</TraceDescription> : null}
              </TraceLine>
            ))}
          </Trace>
        ) : <p className="text-sm text-muted-foreground">Nothing has run yet</p>}
      </section>
    </div>
  );
}

// ---------- visuals
function DataTable({ body }: { body: string }) {
  let rows: unknown;
  try { rows = JSON.parse(body); } catch { rows = String(body).trim().split(/\r?\n/).map((l) => l.split(',')); }
  if (Array.isArray(rows) && rows.length && !Array.isArray(rows[0]) && typeof rows[0] === 'object') {
    const cols = Object.keys(rows[0] as object);
    rows = [cols, ...(rows as Record<string, unknown>[]).map((r) => cols.map((c) => r[c]))];
  }
  if (!Array.isArray(rows) || !rows.length) return <p className="text-sm text-muted-foreground">Empty table</p>;
  const [head, ...rest] = rows as unknown[][];
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead><tr>{head.map((c, i) => <th key={i} scope="col" className="border-b px-3 py-2 text-left text-xs font-medium text-muted-foreground">{String(c)}</th>)}</tr></thead>
        <tbody>{rest.map((r, i) => <tr key={i} className="border-b last:border-0">{r.map((c, j) => <td key={j} className="px-3 py-2.5 align-top">{String(c ?? '')}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function VisualCard({ v, dark, onZoom }: { v: Visual; dark: boolean; onZoom: (v: Visual) => void }) {
  const zoomable = v.kind === 'mermaid' || v.kind === 'image';
  if (v.kind === 'code') return (
    <CodeBlock>
      {v.title ? <CodeBlockHeader><CodeBlockTitle>{v.title}</CodeBlockTitle><CodeBlockActions><CodeBlockCopyButton value={v.body ?? ''} /></CodeBlockActions></CodeBlockHeader> : null}
      <CodeBlockContent className="max-h-96">{v.body ?? ''}</CodeBlockContent>
    </CodeBlock>
  );
  return (
    <Card size="sm" className="w-full">
      {v.title || zoomable ? (
        <CardHeader>
          <CardTitle>{v.title}</CardTitle>
          {zoomable ? <CardAction><Button variant="ghost" size="sm" onClick={() => onZoom(v)}><MaximizeIcon data-icon="inline-start" />View larger</Button></CardAction> : null}
        </CardHeader>
      ) : null}
      <CardContent>
        {v.kind === 'mermaid' ? <Mermaid source={v.body ?? ''} dark={dark} className="flex justify-center overflow-auto [&_svg]:h-auto [&_svg]:max-w-full" />
          : v.kind === 'image' && v.src && /^data:image\//.test(v.src) ? <button type="button" className="block w-full cursor-zoom-in rounded-lg" onClick={() => onZoom(v)}><img src={v.src} alt={v.title ?? 'Screenshot'} className="w-full rounded-lg" /></button>
          : v.kind === 'table' ? <DataTable body={v.body ?? ''} />
          : <Markdown source={v.body ?? ''} className="space-y-2 text-sm leading-relaxed" />}
      </CardContent>
    </Card>
  );
}

// Proof as a trace line: the claim, what proved it, and the evidence one click away.
function Proof({ v }: { v: Visual }) {
  const at = v.at ? new Date(v.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
  return (
    <Trace>
      <TraceCollapsible>
        <TraceCollapsibleTrigger className="min-h-11 items-start py-1 text-foreground">
          <TraceLine className="items-start text-foreground">
            <TraceIcon className="mt-0.5"><span className="flex size-4 items-center justify-center rounded-full bg-status-ok text-background"><CheckIcon className="size-3" strokeWidth={3} /></span></TraceIcon>
            <span className="flex min-w-0 flex-col">
              <TraceTitle className="whitespace-normal font-medium text-foreground">{v.claim ?? v.title}</TraceTitle>
              {v.cmd ? <TraceDescription className="text-xs">Proven by <code className="font-mono">{v.cmd}</code>{at ? ` · ${at}` : ''}</TraceDescription> : null}
            </span>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent>
          {v.kind === 'image' && v.src ? <img src={v.src} alt={`Evidence: ${v.claim ?? v.title}`} className="mt-2 rounded-lg" />
            : (
              <CodeBlock size="sm" className="mt-2">
                <CodeBlockHeader><CodeBlockTitle>Evidence</CodeBlockTitle><CodeBlockActions><CodeBlockCopyButton value={v.body ?? ''} /></CodeBlockActions></CodeBlockHeader>
                <CodeBlockContent className="max-h-80">{v.body ?? ''}</CodeBlockContent>
              </CodeBlock>
            )}
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  );
}

function StoryItem({ it, dark, onZoom }: { it: Item; dark: boolean; onZoom: (v: Visual) => void }) {
  if (it.type === 'message' && it.role === 'user') return (
    <Message align="end">
      <MessageContent>
        <MessageHeader className="justify-end">You answered</MessageHeader>
        <Bubble><BubbleContent>{it.content}</BubbleContent></Bubble>
      </MessageContent>
    </Message>
  );
  if (it.type === 'message') return (
    <Message>
      <MessageContent>
        <Bubble variant="ghost"><BubbleContent className="text-[0.95rem] leading-relaxed text-foreground/90"><Markdown source={it.content} /></BubbleContent></Bubble>
      </MessageContent>
    </Message>
  );
  if (it.type === 'proof') return <Proof v={it.content} />;
  return <VisualCard v={it.content} dark={dark} onZoom={onZoom} />;
}

// ---------- the question: the one standout moment, where a chat composer would sit
function Ask({ snap }: { snap: Snapshot }) {
  const p = snap.pending;
  const [text, setText] = React.useState('');
  const first = React.useRef<HTMLButtonElement | HTMLTextAreaElement | null>(null);
  React.useEffect(() => { setText(''); first.current?.focus({ preventScroll: true }); }, [p?.id]);
  if (!p) return null;
  const opts = p.responseSchema?.properties?.answer?.enum ?? [];
  const until = p.expiresAt ? new Date(p.expiresAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : null;
  return (
    <section aria-labelledby="ask-k" className="animate-in fade-in-0 slide-in-from-bottom-2 rounded-xl border border-ask/60 bg-ask-tint p-4 shadow-[0_8px_30px_-8px] shadow-ask/30 duration-200 motion-reduce:slide-in-from-bottom-0">
      <p id="ask-k" className="text-sm font-medium text-ask">The agent needs your decision</p>
      <Markdown source={p.message ?? ''} className="mt-1 space-y-1 text-base leading-snug text-foreground" />
      {opts.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {opts.map((o, i) => (
            <Button key={o} ref={i === 0 ? (first as React.Ref<HTMLButtonElement>) : undefined} variant={i === 0 ? 'default' : 'outline'} className="h-11 px-4" onClick={() => answer(o)}>{o}</Button>
          ))}
        </div>
      ) : (
        <form className="mt-3 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) answer(text.trim()); }}>
          <label htmlFor="free" className="sr-only">Your answer</label>
          <Textarea id="free" ref={first as React.Ref<HTMLTextAreaElement>} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer" className="min-h-20 bg-background"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && text.trim()) answer(text.trim()); }} />
          <div><Button type="submit" className="h-11 px-4" disabled={!text.trim()}>Send answer</Button></div>
        </form>
      )}
      <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{until ? `Answer by ${until}` : ''}</span>
        <Button variant="link" size="sm" className="h-9 px-1 text-muted-foreground hover:text-foreground" onClick={() => answer(null)}>Skip, let the agent decide</Button>
      </div>
    </section>
  );
}

// ---------- page
export default function App() {
  const snap = useSnap();
  const { dark, toggle } = useTheme();
  const [zoom, setZoom] = React.useState<Visual | null>(null);
  const [planOpen, setPlanOpen] = React.useState(false);
  const done = snap.plan.filter((p) => p.status === 'done').length;

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex shrink-0 items-center gap-3 border-b px-4 py-3 sm:px-6">
        <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-foreground text-sm font-semibold text-background" aria-hidden>d</div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-tight">deepmode</p>
          <p className="truncate text-sm text-muted-foreground">{snap.goal ?? 'Waiting for the agent to set a goal'}</p>
        </div>
        <StatusWord status={snap.status} />
        <Button variant="ghost" size="icon" className="size-11" onClick={toggle} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>
          {dark ? <SunIcon /> : <MoonIcon />}
        </Button>
      </header>

      <div className="@container flex min-h-0 flex-1">
        <div className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col @3xl:flex-row">
          {/* Plan: a sidebar when there is room, a collapsible bar when there is not */}
          <aside aria-label="Plan and progress" className="hidden w-80 shrink-0 overflow-y-auto border-r px-6 py-6 @3xl:block">
            <Plan snap={snap} />
          </aside>
          <Collapsible open={planOpen} onOpenChange={setPlanOpen} className="shrink-0 border-b @3xl:hidden">
            <CollapsibleTrigger className="flex min-h-11 w-full items-center gap-3 px-4 text-sm">
              <ListChecksIcon className="size-4 text-muted-foreground" aria-hidden />
              <span className="font-medium">Plan</span>
              <span className="text-muted-foreground tabular-nums">{snap.plan.length ? `${done} of ${snap.plan.length} done` : 'No plan yet'}</span>
              <ChevronDownIcon className={`ml-auto size-4 transition-transform ${planOpen ? 'rotate-180' : ''}`} aria-hidden />
            </CollapsibleTrigger>
            <CollapsibleContent className="max-h-[50dvh] overflow-y-auto px-4 pb-4"><Plan snap={snap} /></CollapsibleContent>
          </Collapsible>

          <main aria-label="What the agent is showing you" className="flex min-h-0 min-w-0 flex-1 flex-col">
            <MessageScrollerProvider autoScroll>
              <MessageScroller className="min-h-0 flex-1">
                <MessageScrollerViewport aria-label="The agent's story so far">
                  <MessageScrollerContent className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 sm:px-8">
                    {snap.status === 'locked' ? (
                      <p className="py-16 text-center text-sm text-muted-foreground">{snap.error}</p>
                    ) : snap.items.length === 0 ? (
                      <p className="py-16 text-center text-sm text-muted-foreground">When the agent starts working, its plan, explanations, diagrams and proof appear here, in order.</p>
                    ) : snap.items.map((it) => (
                      <MessageScrollerItem key={it.id} messageId={it.id} scrollAnchor={it.type === 'message' && it.role === 'user'}>
                        <StoryItem it={it} dark={dark} onZoom={setZoom} />
                      </MessageScrollerItem>
                    ))}
                    {snap.status === 'done' ? <Marker variant="separator"><MarkerContent>Run finished</MarkerContent></Marker> : null}
                  </MessageScrollerContent>
                </MessageScrollerViewport>
                <MessageScrollerButton />
              </MessageScroller>
            </MessageScrollerProvider>
            {snap.pending ? <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4 sm:px-8"><Ask snap={snap} /></div> : null}
          </main>
        </div>
      </div>

      <Dialog open={!!zoom} onOpenChange={(o) => !o && setZoom(null)}>
        <DialogContent className="max-h-[92dvh] overflow-auto sm:max-w-[min(96vw,1400px)]">
          <DialogTitle>{zoom?.title ?? 'Visual'}</DialogTitle>
          {zoom?.kind === 'mermaid' ? <Mermaid source={zoom.body ?? ''} dark={dark} className="flex justify-center [&_svg]:h-auto [&_svg]:w-full [&_svg]:max-w-none" />
            : zoom?.src ? <img src={zoom.src} alt={zoom.title ?? 'Screenshot'} className="w-full rounded-lg" /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
