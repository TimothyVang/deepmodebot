import * as React from 'react';
import { CodeBlock, CodeBlockContent } from '@/components/ui/code-block';

// Agent text is untrusted. This renders a small Markdown subset straight to React elements (never innerHTML),
// so nothing the agent writes can become markup: paragraphs, lists, headings, **bold**, `code`, [links](https://…), ``` fences.

function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let n = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}-${n++}`;
    if (m[1] !== undefined) out.push(<code key={k} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{m[1]}</code>);
    else if (m[2] !== undefined) out.push(<strong key={k} className="font-semibold text-foreground">{m[2]}</strong>);
    else out.push(<a key={k} href={m[4]} target="_blank" rel="noopener noreferrer" className="underline underline-offset-3 hover:text-foreground">{m[3]}</a>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks: React.ReactNode[] = [];
  String(source ?? '').split('```').forEach((chunk, ci) => {
    if (ci % 2) {
      const nl = chunk.indexOf('\n');
      blocks.push(
        <CodeBlock key={`c${ci}`} size="sm"><CodeBlockContent>{nl >= 0 ? chunk.slice(nl + 1) : chunk}</CodeBlockContent></CodeBlock>,
      );
      return;
    }
    let list: string[] = [];
    const flush = (k: string) => {
      if (!list.length) return;
      blocks.push(<ul key={k} className="ml-5 list-disc space-y-1">{list.map((l, i) => <li key={i}>{inline(l, `${k}-${i}`)}</li>)}</ul>);
      list = [];
    };
    chunk.split('\n').forEach((line, li) => {
      const k = `${ci}-${li}`;
      const item = /^\s*(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
      if (item) { list.push(item[1]); return; }
      flush(`l${k}`);
      if (!line.trim()) return;
      const h = /^#{1,4}\s+(.*)$/.exec(line);
      blocks.push(h ? <p key={k} className="font-semibold text-foreground">{inline(h[1], k)}</p> : <p key={k}>{inline(line, k)}</p>);
    });
    flush(`l${ci}-end`);
  });
  return <div className={className ?? 'space-y-2'}>{blocks}</div>;
}
