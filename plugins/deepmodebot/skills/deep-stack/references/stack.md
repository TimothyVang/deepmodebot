# Default stack for web, SaaS, and AI apps (2026)

Layer-by-layer opinionated TypeScript/web-app defaults distilled from 2026 talks, each with its reason and source date. When two entries conflict, the newer date wins. An existing project's stack always beats these defaults. For general relational monoliths, free-tier Postgres 18 (Neon/Supabase + Drizzle), PaaS deploys (Render/Railway/Fly), or deciding single-package vs monorepo, see `skill://software-architecture`. Tools that appeared only in paid sponsor segments are excluded.

Vendor relationships worth knowing: several Convex and Orgo recommendations came from sources with a commercial tie to those companies. Weigh them with that in mind and prefer evidence from your own prototype.

---

## 1. Web framework
- **Default: SvelteKit.** Agents write it well, and the resulting apps are fast. It compiles to vanilla JS with a small runtime (Svelte 5 runes) and no virtual DOM (2026-10-01, 2026-07-02).
- Thin training data is not a blocker. Scaffold a SvelteKit project and the code itself becomes the agent's context. Agents can search the web. Add the Svelte team's official agent skills file (2026-03-24).
- The ecosystem is enough. shadcn has a Svelte port, Tailwind carries over, and a vendor's plain JS package fills gaps when no SvelteKit package exists. Have the agent write whatever is missing (2026-03-24).
- Next.js habits transfer: file routing (`src/routes/about/+page.svelte`), SSR, data loading, prerendering (2026-03-24).
- **Alternative: Next.js**, when it fits better or the team prefers it (2026-10-01). It was the default until early 2026 (2026-01-23).
- **Portable Next.js on Vite / Workers: `vinext`** (`cloudflare/vinext`, MIT). Reimplements the Next.js App & Pages Router surface on Vite so Next.js apps deploy to Cloudflare Workers or standalone Node (`HOST`, not `HOSTNAME`) without platform lock-in; run `npx vinext check` before migrating (2026-11-26).
- **TanStack Start:** avoid while it is a release candidate. Production work needs stable releases (2026-01-23).
- **One-off API routes inside Next.js:** Elysia on Bun, mounted at `app/api/[[...slugs]]/route.ts`, with an Eden client in `lib/eden.ts` for end-to-end types. Not a main backend (2026-01-23).

## 2. Mobile / desktop / monorepo
- **Mobile: Expo + React Native** for cross-platform. Use Swift when Android is not needed (2026-07-02).
- **Desktop: Electron** wrapping the web app (2026-07-02).
- **Start with a Turborepo monorepo when shipping multiple apps or shared packages.** The agent sees the whole codebase, and every client shares one backend and one UI library (2026-07-02, 2026-01-23). For a single deployable with no shared code, keep a single-package repo per `skill://software-architecture/references/monorepos.md`.

## 3. Styling / UI
- **Tailwind v4 + shadcn/ui.** Start from shadcn/ui's New Project page: choose Base UI components, a style, radius, and theme, then run the generated `bunx` command (2026-01-23).
- **Alternative Base UI system: `@cloudflare/kumo`** (`cloudflare/kumo`, MIT) when targeting Base UI with built-in agent CLI docs (`npx @cloudflare/kumo ls` / `doc <Component>`) (2026-11-26).
- Design tooling (Paper, Mobbin) is in §11.

## 4. Backend / database
- **Default backend: Convex.** The whole backend is code (schema, functions, scheduling), so agents can build it the way they build infrastructure with Terraform. It is type-safe and real-time by default, and it covers webhooks (HTTP actions), cron, scheduled and background jobs, and queues. Set up with `npx convex dev` (2026-01-23, 2026-07-02, 2026-10-01).
- Convex combines server and database: queries read, mutations write, actions call external services (2026-07-02).
- **Integrate through Convex components.** Give the agent the component's link and ask it to set the integration up with that component. Available components include Stripe, Polar, Autumn, Dodo Payments, Workflow (durable flows with retries), Workpool (queues and parallel work), Cloudflare R2, Resend, WorkOS, PostHog, and Browserbase. Agents set these up reliably (2026-01-23 to 2026-10-01).
- **Effect (Effect-TS) for any standalone service that is not Convex.** Its typed errors make failure handling explicit, and agents make it easy to learn. An MCP server or a payments service are good fits (2026-07-02, 2026-10-01).
- **Postgres: PlanetScale.** Works well with Effect and can be reached through Cloudflare Hyperdrive (2026-07-02, 2026-10-01).
- **Avoid client-to-database designs** such as Supabase with row-level security as the only guard. Keep a server between the client and the data (2026-07-02).

## 5. Auth
- **Default: WorkOS.** Enterprise-ready: org invites, SSO, and compliance needs such as SOC 2, and agents integrate it well (2026-07-02, 2026-10-01).
- Earlier view, now superseded: Clerk is the simplest, Better Auth has a Convex component, WorkOS for enterprise. Any of the three works (2026-01-23).

## 6. Payments
- **Plain subscriptions: Stripe**, through the Convex Stripe component (2026-01-23 to 2026-07-02).
- **Credits, usage-based billing, top-ups: Autumn**, through the Convex Autumn component (2026-07-02).
- Polar and Dodo Payments have Convex components but are not default picks (2026-02-04).

## 7. AI app tooling
- **Vercel AI SDK** for building agents (2026-01-23).
- **Claude Agent SDK** for running Claude Code instances inside a sandbox, for coding agents or assistants (2026-01-23).
- **Composio** as the tool and integration layer (Gmail, Calendar, Slack, GitHub, Sheets, Shopify). Create a tool-router session per user ID and pass its tools to AI SDK `streamText` (2026-01-23).
- **OpenRouter** as the inference provider behind a usage ledger (2026-07-02).
- **Durable TypeScript workflows & agents:** `vercel/workflow` (Apache-2.0, `withWorkflow` + `npx workflow web` local UI, portable across Vercel, Postgres, or custom Worlds), `vercel/eve` (Apache-2.0, filesystem-first durable agents under `agent/`), and `cloudflare/agents` (MIT, hibernating per-user/room Stateful Agents on SQLite Durable Objects with `@callable()` RPC and built-in MCP/WebMCP) (2026-11-26).
- **Guardrailed Generative UI: `vercel-labs/json-render`** (Apache-2.0). Constrain model-streamed UIs to a Zod-typed `defineCatalog` + `defineRegistry` (`@json-render/react`, `@json-render/svelte`, `@json-render/shadcn`, `@json-render/mcp`) rather than executing raw generated code (2026-11-26).
- **Multi-channel bots & stream recovery:** `vercel/chat` (MIT, write-once bot adapters for Slack, Teams, Discord, GitHub, Linear) and `vercel/resumable-stream` (MIT, Redis/Valkey pubsub SSE resumption for serverless routes without sticky load balancers) (2026-11-26).

## 8. Sandboxes / agent computers
- **Daytona** for agent sandboxes. Strong developer experience; each agent can get a computer with a browser (2026-01-23, 2026-07-02).
- **Orgo** for giving each agent its own computer (2026-10-01). It replaced Daytona for that job. The name comes from auto-captions, so confirm it [INFERENCE: Orgo].
- **Ephemeral microVMs & edge workspaces:** `@vercel/sandbox` (`vercel/sandbox`, Apache-2.0 Firecracker microVMs with OIDC auth, filesystem snapshot/restore, and Workflow step serialization) or `@cloudflare/computer` (`cloudflare/computer`, MIT Durable Object SQLite virtual filesystem projected via FUSE into Containers or Dynamic Workers) (2026-11-26).

## 9. Deployment
- **Default: Vercel**, with Turborepo, for production, staging, services, and admin sites (2026-07-02).
- **Cloudflare only as a whole stack:** Workers + Workers Static Assets (never scaffold legacy Pages templates for new apps), R2, D1, Hyperdrive, SQLite Durable Objects (`cloudflare/agents`), Workflows, and Email, driven via `cloudflare/cf` or `wrangler.jsonc` (`wrangler types`, secrets via `wrangler secret put` — see `skill://cloud-devsecops/references/cloudflare-edge.md`). If any part of the app is on Cloudflare, keep the rest there too; otherwise use Vercel (2026-10-01, updated 2026-11-26).
- Avoid raw AWS, GCP, and Azure. Use managed layers such as Convex, Vercel, and PlanetScale (2026-07-02).
- Railway for a separate server plus Postgres is superseded by PlanetScale and Cloudflare (2026-01-23, 2026-10-01).

## 10. Analytics / observability / review / email
- **Sentry + PostHog** for errors and analytics. Tell the agent every error must be traceable with them (2026-07-02). PostHog also has a Convex component (2026-10-01).
- **Email: Resend**, through its Convex component (2026-01-23 to 2026-07-02). Agent email can run on Cloudflare Email (2026-10-01).
- **Code review:** an AI reviewer on every PR, looping the agent on its findings until clean. deepmodebot does this with its pr-review technique (`skill://deepmodebot/references/techniques/pr-review.md`).
- **Issue tracking: Linear**, connected over MCP. Assign a ticket to a cloud agent so a fix PR exists before a human reads the bug (2026-10-01).

## 11. Dev tools
- **opensrc** (from Vercel). Fetches a package's or repo's source into the project so agents read real code, which matters for new libraries and new versions. Usage:
  1. Run `npx opensrc <package | github-url>`.
  2. It creates a gitignored `opensrc/` folder with `sources.json`, `settings.json`, and `repos/github.com/...`.
  3. Prompt the agent to look under `opensrc/` for the library and show how to use the feature in this codebase.

  Prefer it to a docs MCP or pasted docs: the code is the best context (2026-04-03).
- **Package-bundled docs (`node_modules/<pkg>/docs`):** Packages such as `workflow`, `eve`, and `chat` ship version-matched docs inside `node_modules/`; read those local files alongside `opensrc` before hitting the web (2026-11-26).
- **portless** (`vercel-labs/portless`, Apache-2.0). Replaces colliding `:3000` ports across parallel git worktrees and agents with stable HTTPS `<branch>.<app>.localhost` URLs (`portless run <cmd>`, `PORTLESS=0` to bypass, `portless doctor --json`) so OAuth callbacks, cookies, and browser tests stay isolated (2026-11-26).
- **emulate** (`vercel-labs/emulate`, Apache-2.0). `npx emulate` runs local stateful drop-in API emulators on `127.0.0.1:4000–4014` (Vercel, GitHub, Google, Slack, Resend, Stripe with real `Stripe-Signature`, Clerk, Linear, Twilio, and offline OpenAI/Anthropic/Gemini streams) for CI and no-network sandboxes (2026-11-26).
- **dev3000 (`d3k`)** (`vercel-labs/dev3000`, MIT) & **lat.md** (`vercel-labs/lat.md`, MIT). `d3k` records a unified cursor-paged timeline (`d3k events --after <cursor>`) across server logs, browser console, uncaught exceptions, and redacted CDP network requests; `lat.md` maintains a checked markdown codebase graph (`lat check`) when flat `AGENTS.md` files outgrow a large repo (2026-11-26).
- **Paper**, a Figma alternative that works well with agents and has an MCP (2026-10-01).
- **Mobbin** for design inspiration; it has an MCP (2026-10-01).
- **Wispr Flow** for voice prompting. Spoken prompts carry more detail than typed ones (2026-10-01).
- **Ghostty** as the terminal (2026-01-23).
- The per-feature flow is this skill's ship loop (`SKILL.md`): worktree per feature, service-layer build, proof, reviewed PR.

## 12. Harnesses and models
- **A meta-harness** (T3 Code) that runs Claude Code, Cursor, and OpenCode and dispatches agents to several machines. Threads settle when their PR merges (2026-10-01).
- **Claude Code as a CLI**, including over SSH on new machines (2026-10-01).
- **Codex app** for computer use, research, 3D work, and hardware projects (2026-10-01).
- **Cursor and Devin cloud agents**, triggered from Linear (2026-10-01).
- Stay loyal to no subscription. Use whichever lab currently gives the most capacity for the price (2026-10-01).
- **Models (Oct 2026):** Opus 5.5 as the main model for instruction following and long tasks; GPT-6 Astra for deep research and understanding a codebase. Expect this to change within months (2026-10-01).

---

## System design for AI apps (2026-07-02)
- Every tool choice trades scalability, reliability, performance, and cost. Name the trade.
- Build on managed layers (Convex, Vercel, PlanetScale) over raw cloud. Their developer and agent experience is better, and they scale by raising the plan.
- **Never let the client talk to the database.** Always client → server → database → server → client, or keys leak through the network tab.
- Choose tools agents know well and that are configured as code.
- Monorepo layout: web (SvelteKit), mobile (Expo, or Swift if iOS only), desktop (Electron around the web app), a shared UI library, one backend.
- **Run agent and chat work as durable processes** so it continues when the user leaves: Convex Workflow, Workpool for queues, components for integrations.
- **Split out a separate service** when code touches one surface, does one job, has no foothold across the codebase, could have its own owner, or the main backend is getting too big. This is judgment, not a formula; the model can propose the split.

Example architecture:
- Clients: web, desktop, mobile, internal admin site.
- Source of truth: Convex with components.
- Services in the monorepo: an Effect inference and payments service with its own PlanetScale ledger and OpenRouter for inference; an Effect messaging service.
- Agents: one sandbox computer each, with a browser.
- Auth WorkOS, billing Autumn, observability Sentry + PostHog, deploy Vercel.
- Accepted trade-off: cost. One backend would be cheaper; separate services buy isolation.

---

## Superseded
| Was | Date | Now | Date |
|---|---|---|---|
| Next.js main frontend, Elysia for API routes | 2026-01-23 | SvelteKit default, Next.js sometimes | 2026-03-24 to 2026-10-01 |
| Clerk simplest, Better Auth possible, WorkOS for enterprise | 2026-01-23 | WorkOS default | 2026-07-02, 2026-10-01 |
| Stripe only | 2026-01-23 | Stripe for subscriptions, Autumn for credits | 2026-07-02 |
| Railway for servers + Postgres | 2026-01-23 | PlanetScale; Cloudflare whole stack or Vercel | 2026-10-01 |
| Daytona for agent computers | 2026-07-02 | Orgo for agent computers | 2026-10-01 |
| Opus 4.5 + GPT-5.2 / Codex | 2026-01-23 | Opus 5.5 main, GPT-6 Astra for deep work | 2026-10-01 |
| Cursor editor + Claude Code CLI | 2026-01-23 | Meta-harness; cloud agents from Linear | 2026-10-01 |
| Docs MCP / pasted docs | rejected | opensrc | 2026-04-03 |
| Human review after an AI score threshold | 2026-01-23 | Agent loops on AI review until clean (deepmodebot: pr-review) | 2026-10-01 |
