# Cloudflare Workers, Durable Objects, Agents, and Edge Security (2026)

Distilled from Cloudflare's official permissive engineering repositories (`cloudflare/skills` Apache-2.0, `cloudflare/agents` MIT, `cloudflare/computer` MIT, `cloudflare/cloudflare-os` Apache-2.0, `cloudflare/vinext` MIT, `cloudflare/capnweb` MIT, `cloudflare/workers-oauth-provider` MIT, `cloudflare/cf` Apache-2.0, `cloudflare/workerd` Apache-2.0, `cloudflare/cloudflared` Apache-2.0), checked 2026-11-26. Recheck current limits and compatibility flags against installed package schemas (`node_modules/wrangler/config-schema.json`) and `https://developers.cloudflare.com` before deploying.

## 1. CLI, Configuration, and Binding Types

- **`cf` vs Wrangler:** For greenfield projects, repos with `cloudflare.config.ts`, or repos with no Cloudflare config yet, use the agentic **`cf` CLI** (`cloudflare/cf`, Apache-2.0: `cf cli search`, `cf schema`, condensed JSON output when piped to agents). When a repo already has `wrangler.jsonc`, `wrangler.json`, or `wrangler.toml` (and no `cloudflare.config.ts`), run the repo's local Wrangler version via its package manager scripts rather than adding `cf` or upgrading Wrangler unprompted.
- **Prefer `wrangler.jsonc` over `wrangler.toml`** on new Wrangler projects: newer Cloudflare config fields are JSON-only while JSONC preserves inline rationale comments.
- **Compatibility baseline:** Set `compatibility_date` to today's `YYYY-MM-DD` on new Workers and include `"compatibility_flags": ["nodejs_compat"]` whenever dependencies use `node:crypto`, `node:buffer`, or `node:stream`.
- **Never hand-write `interface Env`:** Run `wrangler types` after every binding change and type default handlers with `satisfies ExportedHandler<Env>`. Hand-maintained `Env` interfaces drift silently from deployed bindings.
- **Secrets never live in `vars`:** Put non-secret config in `vars`; store credentials exclusively via `wrangler secret put <NAME>` (and gitignored `.dev.vars` / `.env` locally). `static_sec_audit.py` (`wrangler-vars-secret`) blocks plaintext secret keys in `wrangler.*`.

## 2. Web Frameworks and Static Assets on Workers

- **Workers + Static Assets, never new Pages projects:** Deploy full-stack apps and SPAs to **Cloudflare Workers** with [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/). Do not scaffold legacy Cloudflare Pages templates, Pages deploy commands, or Pages presets for new applications.
- **Next.js on Workers -> `vinext` (`cloudflare/vinext`, MIT):** Default to `vinext` (Vite-based Next.js API reimplementation) over OpenNext for new Next.js apps targeting Workers (`pnpm create vinext-app@latest` or `npx vinext check && npx vinext init`).
  - Known `vinext` constraints to verify per app: `"use cache"` / Partial Prerendering is partial; native addons (`sharp`, `resvg`, `satori`, `@napi-rs/canvas`) can fail in Vite RSC dev mode even when prod builds work; standalone Node output reads `HOST` (not Next.js's `HOSTNAME`, avoiding Linux `$HOSTNAME` collisions); `bun build --compile` binaries must resolve `outDir` via `path.dirname(process.execPath)`.

## 3. Workers Runtime, Memory, and Concurrency Rules

- **128 MB isolate memory limit — stream, don't buffer:** Never call `await response.text()` or `await request.arrayBuffer()` on large or unbounded payloads. Pass `response.body` directly (`new Response(response.body, response)`) or pipe through a `TransformStream` driven inside `ctx.waitUntil(...)`.
- **Zod >= 4.5.0 on Workers:** Older Zod releases retain substantially more heap per schema and trigger Worker OOMs; pin `zod >= 4.5.0`.
- **Zero module-scope request state:** A single Worker isolate handles concurrent requests. Storing user IDs, auth headers, or per-request buffers in module globals leaks state across tenants. Pass state explicitly or scope via `AsyncLocalStorage`.
- **Never destructure `ctx`:** `const { waitUntil } = ctx; waitUntil(p)` loses the `ExecutionContext` `this` binding and throws `Illegal invocation` at runtime (`slop_gate` / `dmb-gate` `workers-ctx-destructure`). Always call `ctx.waitUntil(p)`.
- **No floating promises:** Every async side effect must be `await`ed before returning or registered with `ctx.waitUntil(...)` (30 s post-response budget); unattached promises are dropped or swallow errors.
- **Use in-process bindings, never the Cloudflare REST API from a Worker:** Access KV, R2, D1, Queues, Durable Objects, and Workflows via `env.<BINDING>` (zero network hop, zero bearer token). Never call `fetch("https://api.cloudflare.com/client/v4/...")` for bound resources.
- **Regional DB placement:** Hyperdrive pools connections to Postgres (e.g. PlanetScale/Neon) but does **not** move Worker execution near the database. Configure Smart Placement or an explicit region hint when handlers issue sequential queries to a regional DB.
- **Fail closed on errors:** Avoid `ctx.passThroughOnException()` (fail-open origin bypass that masks crashes); catch explicitly, log structured JSON (`console.error(JSON.stringify(...))`), and return a controlled error response.

## 4. Durable Objects, Stateful Agents, and Sandboxes

- **Class inheritance & binding access:** Platform classes (`DurableObject`, `WorkerEntrypoint`, `WorkflowEntrypoint`, `Agent`) **must** use `extends` (e.g. `extends DurableObject<Env>` from `"cloudflare:workers"`), never legacy `implements DurableObject` (`workers-legacy-implements-do`). Inside classes, read bindings via `this.env.X` and state via `this.ctx` (not legacy `this.state`); inside module handlers (`fetch`, `queue`, `scheduled`), read `env.X`.
- **SQLite-backed Durable Objects & `cloudflare/agents` (MIT):** Declare new DO classes under `migrations[].new_sqlite_classes` in `wrangler.jsonc`. `Agent<Env, State>` (`npm i agents`) gives hibernating per-user/session/room actors (`$0` idle compute), `@callable()` typed RPC, `useAgent` client state sync, scheduled tasks, Workflows, and built-in MCP server/client + WebMCP support.
- **Sandboxed agent compute (`cloudflare/computer` MIT & `@cloudflare/sandbox`):**
  - `@cloudflare/computer` stores an authoritative virtual filesystem in DO SQLite (`@cloudflare/dofs`) and projects it into three `workspace.runtime` backends: a Linux Container FUSE mount (`computerd` synced over `capnweb`), a Dynamic Worker isolate shell, or a Dynamic Worker ESM `Codemode` runner.
  - Keep Worker `@cloudflare/sandbox` npm versions strictly matched to container image tags (never mix stable `@cloudflare/sandbox` with `cloudflare/sandbox:next`).
- **Capability Gatekeepers (`cloudflare/cloudflare-os`, Apache-2.0):** Default agent and user-generated app ("Gadget") sandboxes to zero ambient credentials. Introduce specific external resources per task through narrow Gatekeeper bindings, and isolate untrusted UI in CSP-locked sandboxed iframes communicating only over `postMessage` Cap'n Web RPC (`cloudflare/capnweb`).

## 5. Edge Security, OAuth, and Local Runtime Verification

- **Constant-time secret checks:** Generate tokens with `crypto.randomUUID()` / `crypto.getRandomValues()`. Before `crypto.subtle.timingSafeEqual(a, b)`, `SHA-256`-digest both inputs to fixed 32-byte buffers so length differences never leak via early return.
- **MCP OAuth on Workers:** Use `cloudflare/workers-oauth-provider` (MIT) with PKCE, strict `aud`/`iss` validation, and Cloudflare Zero Trust / `cloudflared` tunnels for private origin reachability without public ports.
- **Local runtime tests & Local Explorer:** Test Workers inside `workerd` with `@cloudflare/vitest-plugin` (replaces `@cloudflare/vitest-pool-workers`). Because the Vitest plugin auto-injects `nodejs_compat`, still verify `wrangler.jsonc` declares `"nodejs_compat"` explicitly. During `wrangler dev` / `cf dev`, inspect and seed local KV, R2, D1, SQLite DOs, Workflows, and request traces at `/cdn-cgi/local/explorer` before sprinkling debug logs.
