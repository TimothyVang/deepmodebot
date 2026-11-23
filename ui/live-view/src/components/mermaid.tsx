import * as React from 'react';

// Mermaid is large, so it loads from a pinned CDN build only when a diagram arrives (the server's CSP allows
// exactly this host). securityLevel 'strict' keeps agent-written diagrams from carrying script or HTML labels.
const MERMAID = 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';
let loaded: Promise<any> | null = null;
const cache = new Map<string, string>();
let seq = 0;

function load(dark: boolean) {
  loaded ??= import(/* @vite-ignore */ MERMAID).then((m) => {
    m.default.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: "'Geist Variable', ui-sans-serif, system-ui, sans-serif",
      themeVariables: dark
        ? { background: 'transparent', primaryColor: '#1f2328', primaryTextColor: '#ededed', primaryBorderColor: '#4b5563', lineColor: '#8b949e', secondaryColor: '#18181b', tertiaryColor: '#18181b', edgeLabelBackground: '#0a0a0a', clusterBkg: '#141414' }
        : { background: 'transparent', primaryColor: '#f4f4f5', primaryTextColor: '#18181b', primaryBorderColor: '#a1a1aa', lineColor: '#71717a', secondaryColor: '#fafafa', tertiaryColor: '#ffffff', edgeLabelBackground: '#ffffff' },
    });
    return m.default;
  });
  return loaded;
}

export function useMermaidSvg(source: string, dark: boolean) {
  const key = `${dark ? 'd' : 'l'}:${source}`;
  const [state, setState] = React.useState<{ svg?: string; error?: string }>(() => (cache.has(key) ? { svg: cache.get(key) } : {}));
  React.useEffect(() => {
    if (cache.has(key)) { setState({ svg: cache.get(key) }); return; }
    let live = true;
    load(dark)
      .then((m) => m.render(`mm${++seq}`, source))
      .then(({ svg }: { svg: string }) => { cache.set(key, svg); if (live) setState({ svg }); })
      .catch((e: Error) => live && setState({ error: e?.message ?? 'could not load the diagram renderer' }));
    return () => { live = false; };
  }, [key]);
  return state;
}

export function Mermaid({ source, dark, className }: { source: string; dark: boolean; className?: string }) {
  const { svg, error } = useMermaidSvg(source, dark);
  if (error) return (
    <div className="space-y-2 text-sm">
      <p className="text-destructive">This diagram could not be drawn: {error}</p>
      <pre className="overflow-auto rounded-lg bg-muted p-3 font-mono text-xs">{source}</pre>
    </div>
  );
  if (!svg) return <div className="h-40 animate-pulse rounded-lg bg-muted" aria-label="Drawing the diagram" />;
  // Mermaid's own output under securityLevel 'strict' (sanitized by its DOMPurify pass).
  return <div className={className} dangerouslySetInnerHTML={{ __html: svg }} />;
}
