#!/usr/bin/env bun
/**
 * Zero-dependency universal app-automation relay + MCP 2.0 (2026-07-28) stdio bridge starter.
 * Port of omp's browser-relay architecture (observe -> act(id) -> waitFor -> loopback multiplexing daemon).
 *
 * Usage:
 *   bun relay_server.ts --self-test           # Run built-in end-to-end loopback + MCP 2.0 proof
 *   bun relay_server.ts --serve-relay         # Start loopback multiplexing daemon + endpoint file
 *   bun relay_server.ts --mcp                 # Run MCP 2.0 (2026-07-28 + legacy) stdio server
 *
 * To port to a real app: replace `DemoAppAdapter` with an adapter implementing `AppAdapter`
 * (see references/adapter-cookbook.md for Electron/CDP, Windows UIA, macOS AX, Linux AT-SPI2, PTY, IPC).
 */
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as readline from "node:readline";

export interface ObservationEntry {
  id: number;
  role: string;
  name?: string;
  value?: string | number;
  description?: string;
  keyshortcuts?: string;
  states: string[];
  bounds?: [number, number, number, number];
}

export interface Observation {
  targetId: string;
  location: string;
  title?: string;
  revision: number;
  viewport: { width: number; height: number; scale?: number };
  elements: ObservationEntry[];
  text?: string;
}

export interface TargetInfo {
  targetId: string;
  title: string;
  location: string;
  owned: boolean;
}

const ACTIONS = ["click", "fill", "press", "select", "check", "uncheck", "scroll", "invoke"] as const;

export interface ActRequest {
  targetId: string;
  revision: number;
  id: number;
  op: (typeof ACTIONS)[number];
  value?: string;
  key?: string;
}

export interface AppAdapter {
  readonly appName: string;
  listTargets(filter?: string): Promise<TargetInfo[]>;
  observe(targetId: string, includeText?: boolean): Promise<Observation>;
  act(req: ActRequest): Promise<{ ok: boolean; revision: number; detail?: string }>;
  waitFor(targetId: string, textContains: string, timeoutMs?: number): Promise<{ matched: boolean; revision: number }>;
}

/** Reference in-memory adapter used by `--self-test` and as a clean contract template. */
export class DemoAppAdapter implements AppAdapter {
  readonly appName = "demo-app";
  private revision = 1;
  private query = "";
  private submitted = false;
  private readonly changes = new EventTarget();

  private get status() {
    return this.submitted ? `Submitted: ${this.query}` : "Ready";
  }

  async listTargets(filter?: string): Promise<TargetInfo[]> {
    const all: TargetInfo[] = [{ targetId: "win-1", title: "Demo App", location: "app://main", owned: true }];
    return filter ? all.filter((t) => t.title.toLowerCase().includes(filter.toLowerCase())) : all;
  }

  async observe(targetId: string, includeText = true): Promise<Observation> {
    if (targetId !== "win-1") throw new Error(`Unknown targetId: ${targetId}`);
    const elements: ObservationEntry[] = [
      { id: 1, role: "textbox", name: "Query", value: this.query, states: ["enabled"] },
      { id: 2, role: "button", name: "Submit", states: this.query ? ["enabled"] : ["disabled"] },
    ];
    if (this.submitted) {
      elements.push({ id: 3, role: "status", name: this.status, states: [] });
    }
    return {
      targetId,
      location: "app://main",
      title: "Demo App",
      revision: this.revision,
      viewport: { width: 1280, height: 800, scale: 1 },
      elements,
      text: includeText ? this.status : undefined,
    };
  }

  async act(req: ActRequest): Promise<{ ok: boolean; revision: number; detail?: string }> {
    if (req.targetId !== "win-1") throw new Error(`Unknown targetId: ${req.targetId}`);
    if (req.revision !== this.revision) {
      throw new Error(`STALE_REVISION: expected ${this.revision}, got ${req.revision} — re-observe first`);
    }
    if (req.id === 1 && req.op === "fill") {
      this.query = req.value ?? "";
      this.submitted = false;
    } else if (req.id === 2 && (req.op === "click" || req.op === "invoke")) {
      if (!this.query) throw new Error("Submit is disabled");
      this.submitted = true;
    } else {
      throw new Error(`Unsupported action ${req.op} on element id=${req.id}`);
    }
    this.revision++;
    this.changes.dispatchEvent(new Event("change"));
    return { ok: true, revision: this.revision };
  }

  async waitFor(targetId: string, textContains: string, timeoutMs = 5000): Promise<{ matched: boolean; revision: number }> {
    if (targetId !== "win-1") throw new Error(`Unknown targetId: ${targetId}`);
    if (this.status.includes(textContains)) return { matched: true, revision: this.revision };
    const { promise, resolve } = Promise.withResolvers<{ matched: boolean; revision: number }>();
    const finish = (matched: boolean) => {
      clearTimeout(timer);
      this.changes.removeEventListener("change", changed);
      resolve({ matched, revision: this.revision });
    };
    const changed = () => { if (this.status.includes(textContains)) finish(true); };
    const timer = setTimeout(() => finish(false), Math.min(Math.max(0, timeoutMs), 60_000));
    this.changes.addEventListener("change", changed);
    return promise;
  }
}

function dispatch(adapter: AppAdapter, op: string, a: Record<string, unknown>) {
  if (op === "targets" && (a.filter === undefined || typeof a.filter === "string")) return adapter.listTargets(a.filter);
  if (typeof a.targetId !== "string" || !a.targetId) throw new Error("targetId is required");
  if (op === "observe" && (a.includeText === undefined || typeof a.includeText === "boolean")) {
    return adapter.observe(a.targetId, a.includeText);
  }
  if (op === "waitFor" && typeof a.textContains === "string" && a.textContains.length &&
      (a.timeoutMs === undefined || (typeof a.timeoutMs === "number" && Number.isInteger(a.timeoutMs) && a.timeoutMs >= 0 && a.timeoutMs <= 60_000))) {
    return adapter.waitFor(a.targetId, a.textContains, a.timeoutMs);
  }
  if (op === "act") {
    const action = ACTIONS.find((name) => name === a.op);
    if (action && typeof a.id === "number" && Number.isSafeInteger(a.id) && a.id > 0 &&
        typeof a.revision === "number" && Number.isSafeInteger(a.revision) && a.revision >= 0 &&
        (a.value === undefined || typeof a.value === "string") && (a.key === undefined || typeof a.key === "string")) {
      return adapter.act({ targetId: a.targetId, revision: a.revision, id: a.id, op: action, value: a.value, key: a.key });
    }
  }
  throw new Error(`Invalid relay operation or arguments: ${op}`);
}

export function startLoopbackRelay(adapter: AppAdapter, token = process.env.DMB_RELAY_TOKEN, announce = true) {
  if (!token) throw new Error("Set DMB_RELAY_TOKEN before starting a network relay");
  const srv = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    idleTimeout: 65,
    maxRequestBodySize: 1024 * 1024,
    async fetch(req) {
      if (req.headers.get("authorization") !== `Bearer ${token}`) {
        return new Response("unauthorized", { status: 401 });
      }
      const url = new URL(req.url);
      if (req.method === "GET" && url.pathname === "/healthz") {
        return Response.json({ ok: true, app: adapter.appName, pid: process.pid });
      }
      if (req.method === "POST" && url.pathname === "/rpc") {
        try {
          const body = (await req.json()) as { op: string; args?: Record<string, unknown> };
          const a = body.args ?? {};
          return Response.json({ ok: true, result: await dispatch(adapter, body.op, a) });
        } catch (err) {
          return Response.json({ ok: false, error: err instanceof Error ? err.message : String(err) }, { status: 400 });
        }
      }
      return new Response("not found", { status: 404 });
    },
  });
  let endpointFile: string | undefined;
  if (announce) {
    try {
      const dir = path.join(os.homedir(), ".dmb-relays", adapter.appName);
      fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      endpointFile = path.join(dir, `${process.pid}-${srv.port}`);
      const record = { pid: process.pid, port: srv.port, app: adapter.appName, tokenRequired: true };
      fs.writeFileSync(endpointFile, JSON.stringify(record), { mode: 0o600, flag: "wx" });
    } catch (err) {
      srv.stop(true);
      throw err;
    }
  }
  const stop = () => {
    srv.stop(true);
    if (endpointFile) fs.rmSync(endpointFile, { force: true });
  };
  return { server: srv, url: `http://127.0.0.1:${srv.port}`, endpointFile, stop };
}

/** Dual-era MCP 2.0 (2026-07-28 + legacy 2025/2024) stdio server wrapping any AppAdapter. */
export async function handleMcpRequest(adapter: AppAdapter, msg: { id?: unknown; method?: string; params?: Record<string, unknown> }) {
  const SERVER_INFO = { name: `${adapter.appName}-relay`, version: "2.0.0" };
  const SUPPORTED = ["2026-07-28", "2025-11-25", "2025-03-26", "2024-11-05"];
  const params = msg.params ?? {};
  const meta = (params._meta && typeof params._meta === "object" ? params._meta : null) as Record<string, unknown> | null;
  const claimed = typeof meta?.["io.modelcontextprotocol/protocolVersion"] === "string" ? meta["io.modelcontextprotocol/protocolVersion"] : null;
  if (claimed && claimed !== "2026-07-28") {
    return { error: { code: -32022, message: `Unsupported protocol version: ${claimed}`, data: { supportedProtocolVersions: SUPPORTED } } };
  }
  const modern = claimed === "2026-07-28" || msg.method === "server/discover";
  const wrap = (res: Record<string, unknown>) =>
    modern ? { result: { resultType: "result", ...res, _meta: { "io.modelcontextprotocol/serverInfo": SERVER_INFO } } } : { result: res };
  const p = adapter.appName.replace(/[^a-z0-9_]/gi, "_");
  const tools = [
    { name: `${p}_targets`, description: `List attachable ${adapter.appName} targets.`, inputSchema: { type: "object", properties: { filter: { type: "string" } } } },
    { name: `${p}_observe`, description: `Observe structured interactive elements with ephemeral IDs.`, inputSchema: { type: "object", properties: { targetId: { type: "string" } }, required: ["targetId"] } },
    { name: `${p}_act`, description: "Act on an element in the observed revision.", inputSchema: { type: "object", properties: { targetId: { type: "string" }, revision: { type: "integer" }, id: { type: "integer" }, op: { type: "string", enum: ACTIONS }, value: { type: "string" }, key: { type: "string" } }, required: ["targetId", "revision", "id", "op"] } },
    { name: `${p}_wait`, description: `Wait for target text/state predicate.`, inputSchema: { type: "object", properties: { targetId: { type: "string" }, textContains: { type: "string" }, timeoutMs: { type: "integer" } }, required: ["targetId", "textContains"] } },
  ];
  if (msg.method === "server/discover") {
    return wrap({ protocolVersion: "2026-07-28", supportedProtocolVersions: SUPPORTED, capabilities: { tools: {} }, serverInfo: SERVER_INFO });
  }
  if (msg.method === "initialize") {
    const reqVer = typeof params.protocolVersion === "string" && SUPPORTED.includes(params.protocolVersion) ? params.protocolVersion : "2025-11-25";
    return { result: { protocolVersion: reqVer, capabilities: { tools: {} }, serverInfo: SERVER_INFO } };
  }
  if (!modern && msg.method === "ping") return { result: {} };
  if (msg.method === "tools/list") {
    return wrap(modern ? { tools, ttlMs: 300_000, cacheScope: "global" } : { tools });
  }
  if (msg.method === "tools/call") {
    const name = String(params.name ?? "");
    const a = (params.arguments && typeof params.arguments === "object" ? params.arguments : {}) as Record<string, unknown>;
    try {
      const op = name.startsWith(`${p}_`) ? name.slice(p.length + 1) : "";
      if (!["targets", "observe", "act", "wait"].includes(op)) return { error: { code: -32602, message: `Unknown tool: ${name}` } };
      const val = await dispatch(adapter, op === "wait" ? "waitFor" : op, a);
      return wrap({ content: [{ type: "text", text: JSON.stringify(val) }], isError: false });
    } catch (err) {
      return wrap({ content: [{ type: "text", text: err instanceof Error ? err.message : String(err) }], isError: true });
    }
  }
  return { error: { code: -32601, message: `Method not found: ${msg.method}` } };
}

function loopbackClient(appName: string, port: number, token: string | undefined): AppAdapter {
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) throw new Error("Expected a loopback port and DMB_RELAY_TOKEN");
  const rpc = async <T>(op: string, args: object): Promise<T> => {
    const res = await fetch(`http://127.0.0.1:${port}/rpc`, {
      method: "POST", redirect: "error", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ op, args }), signal: AbortSignal.timeout(65_000),
    });
    if (res.status === 401) throw new Error("Relay authorization failed");
    const data = await res.json() as { ok: true; result: T } | { ok: false; error: string };
    if (!data.ok) throw new Error(data.error);
    if (!res.ok) throw new Error(`Relay HTTP ${res.status}`);
    return data.result;
  };
  return {
    appName, listTargets: (filter) => rpc("targets", { filter }),
    observe: (targetId, includeText) => rpc("observe", { targetId, includeText }),
    act: (req) => rpc("act", req),
    waitFor: (targetId, textContains, timeoutMs) => rpc("waitFor", { targetId, textContains, timeoutMs }),
  };
}

function serveStdio(adapter: AppAdapter) {
  const reply = (id: unknown, body: object) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, ...body }) + "\n");
  readline.createInterface({ input: process.stdin, crlfDelay: Infinity }).on("line", async (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch {
      reply(null, { error: { code: -32700, message: "Parse error" } });
      return;
    }
    if (msg?.jsonrpc !== "2.0" || typeof msg.method !== "string" ||
        (msg.id !== undefined && typeof msg.id !== "number" && typeof msg.id !== "string")) {
      reply(null, { error: { code: -32600, message: "Invalid request" } });
      return;
    }
    if (msg.id === undefined) return;
    try { reply(msg.id, await handleMcpRequest(adapter, msg)); } catch {
      reply(msg.id, { error: { code: -32603, message: "Internal error" } });
    }
  });
}

async function selfTest(adapter: DemoAppAdapter) {
  const token = crypto.randomUUID();
  const h = startLoopbackRelay(adapter, token, false);
  try {
    assert.equal((await fetch(`${h.url}/healthz`)).status, 401);
    const client = loopbackClient(adapter.appName, h.server.port!, token);
    const [{ targetId }] = await client.listTargets();
    const before = await client.observe(targetId);
    const idFor = (obs: Observation, role: string) => {
      const el = obs.elements.find((entry) => entry.role === role);
      assert.ok(el, `Missing ${role}`);
      return el.id;
    };
    const click = { targetId, revision: before.revision, id: idFor(before, "button"), op: "click" } as const;
    await client.act({ ...click, id: idFor(before, "textbox"), op: "fill", value: "hello" });
    await assert.rejects(client.act(click), /STALE_REVISION/);
    const next = await client.observe(targetId);
    const status = "Submitted: hello";
    assert.equal((await client.waitFor(targetId, status, 0)).matched, false);
    const [waited, acted] = await Promise.all([
      client.waitFor(targetId, status, 2000),
      client.act({ ...click, revision: next.revision, id: idFor(next, "button") }),
    ]);
    assert.equal(acted.ok, true);
    assert.deepEqual(waited, { matched: true, revision: acted.revision });

    const version = "2026-07-28";
    const _meta = { "io.modelcontextprotocol/protocolVersion": version, "io.modelcontextprotocol/clientCapabilities": {} };
    const frames = [
      { id: 1, method: "server/discover", params: { _meta } },
      { id: 2, method: "tools/call", params: { _meta, name: "demo_app_observe", arguments: { targetId } } },
    ].map((frame) => JSON.stringify({ jsonrpc: "2.0", ...frame }) + "\n");
    const child = Bun.spawn([process.execPath, import.meta.path, "--mcp"], {
      env: { ...process.env, DMB_RELAY_PORT: String(h.server.port), DMB_RELAY_TOKEN: token },
      stdin: new Blob(frames), stdout: "pipe", stderr: "inherit", timeout: 5000,
    });
    const [stdout, exit] = await Promise.all([new Response(child.stdout).text(), child.exited]);
    assert.equal(exit, 0, "MCP child did not exit cleanly");
    const replies = stdout.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(replies.length, frames.length);
    assert.ok(replies.every((frame) => frame.jsonrpc === "2.0" && frame.result?.resultType === "result"));
    assert.equal(replies.find((r) => r.id === 1)?.result.protocolVersion, version);
    const result = replies.find((r) => r.id === 2)?.result;
    assert.equal(result?.isError, false);
    const observed: Observation = JSON.parse(result.content[0].text);
    assert.equal(observed.text, status);
    assert.equal(observed.revision, acted.revision);
    console.log(`OK: loopback + stale revision + waitFor; stdio server/discover ${version}; ${status} (revision ${observed.revision})`);
  } finally {
    h.stop();
  }
}

if (import.meta.main) {
  const adapter = new DemoAppAdapter();
  const mode = process.argv[2];
  if (mode === "--self-test") {
    await selfTest(adapter);
  } else if (mode === "--mcp") {
    const port = process.env.DMB_RELAY_PORT;
    serveStdio(port === undefined ? adapter : loopbackClient(adapter.appName, Number(port), process.env.DMB_RELAY_TOKEN));
  } else if (mode === "--serve-relay") {
    const h = startLoopbackRelay(adapter);
    process.once("SIGINT", h.stop);
    process.once("SIGTERM", h.stop);
    console.log(JSON.stringify({ url: h.url, endpointFile: h.endpointFile }));
  } else {
    console.error("Usage: bun relay_server.ts --self-test | --serve-relay | --mcp");
    process.exitCode = mode === "--help" ? 0 : 2;
  }
}
