# gen-ui

**Use when:** a wall of Markdown text is the wrong medium for talking to a human (ranked `/suggest` audits, `grill` decision frontiers, `self-grill` Prosecutor gap/overclaim heatmaps, `tournament` 12-lens brackets, multi-option comparisons, or architecture walkthroughs), OR when building an agent-driven product interface using Google's open **A2UI (`1.0`)** declarative UI protocol (`https://a2ui.org/`, `https://github.com/a2ui-project/a2ui`).

Agents default to terminal-era walls of text or unsafe model-authored HTML/JS. **gen-ui** fixes both:
1. **Speak UI to the human:** compile structured agent findings, decisions, and `/deep` prompts into a schema-validated **A2UI v1.0 payload (`surface.a2ui.json`)** plus a **self-contained interactive HTML cockpit (`index.html`)** inside `<root>/.scratch/gen-ui/<slug>/`.
2. **Build production agentic UIs with A2UI v1.0 ("data, not code"):** agents emit flat, ID-referenced component blueprints (`updateComponents`) and bound state (`updateDataModel`) validated against a client-owned `catalog.json`, rendered natively across React, Lit, Angular, Flutter, SwiftUI, and Jetpack Compose with zero arbitrary code execution across trust or A2A boundaries.

Pair with `skill://frontend-ui` (`references/playbook/04a-agent-ui.md`) for styling/accessibility rules and `skill://agent-harnesses` (`references/protocols.md`) for A2A, AG-UI, and MCP transport wiring.

## When to speak UI vs prose

- **Stay in concise Markdown** when the answer is `< 10` lines, one linear explanation, or a single yes/no question.
- **Generate an interactive `gen-ui` cockpit (`assets/gen-ui/gen_ui.py`)** when:
  - `/suggest` returns multi-item ranked `P0`/`P1`/`P2` gaps, overclaims, and copy-paste `/deep` prompts (`prompt_tools.py suggest --ui`).
  - `grill` or `tournament` surfaces `3+` coupled architectural decisions, trade-off matrices, or killed-flaw scar tables where the human benefits from interactive filtering and 1-click decision overrides.
  - `self-grill` Prosecutor audits expose multi-file risk heatmaps, missing tests, or overclaim receipts.
  - The user asks to visualize architecture, compare designs, or "gen UI / build UI to talk to me".
- **Build an in-app A2UI v1.0 surface** when the user's application needs dynamic, personalized agent responses (forms, booking cards, approval flows, live metric feeds) rendered with the host app's own design-system widgets.

## Procedure

1. **Define or select the trusted component catalog (`catalog.json`).**
   - Every A2UI v1.0 surface binds to a `catalogId` with JSON Schema properties per allowed widget (`Card`, `Column`, `Row`, `Text`, `Button`, `MetricTile`, or domain cards like `FlightCard`).
   - Never allow raw HTML/script execution in catalog components; unknown component types fail closed at compile/validation time or degrade cleanly to text.
   - When using **A2UI Express** (`<a2ui> ... </a2ui>` with `$/path` bindings) or a fast System-1 selector model, generate the prompt skill directly from `catalog.json` via the A2UI Agent SDK (Python, TypeScript, or Dart).
   Done when the allowed component catalog and JSON Schema contract are fixed before UI generation.

2. **Emit flat adjacency-list components + separated data model.**
   - Follow the A2UI `1.0` wire split:
     - `createSurface`: `{"version": "1.0", "createSurface": {"surfaceId": "...", "catalogId": "..."}}`
     - `updateComponents`: flat array of `{id, component, child|children, ...}` starting at `"id": "root"`. Flat IDs let LLMs stream incrementally and patch one node by ID without deep-nested JSON breakage.
     - `updateDataModel`: `{"version": "1.0", "updateDataModel": {"surfaceId": "...", "path": "/", "value": {...}}}`. Bind dynamic values via RFC 6901 JSON Pointers (`{"@path": "/metrics/overclaims"}` in v1.0) so sensitive server state can bind on the client without passing raw secrets through the model.
   - For local `deepmodebot` human cockpits, run the contained generator (writes only inside `<root>/.scratch/gen-ui/<slug>/`):
     ```bash
     python -B "<this installed skill>/assets/gen-ui/gen_ui.py" from-suggest --root "<project-root>" --slug suggest --json
     python -B "<this installed skill>/assets/gen-ui/gen_ui.py" from-grill --root "<project-root>" --slug grill --json
     python -B "<this installed skill>/assets/gen-ui/gen_ui.py" render --root "<project-root>" --slug custom --stdin --json <<'EOF'
     {"title": "Architecture Decision Cockpit", "decisions": [...], "findings": [...]}
     EOF
     ```
   Done when `surface.a2ui.json` (and `index.html` for local cockpits) is emitted inside `.scratch/gen-ui/<slug>/` or the app's transport stream.

3. **Choose the right transport & MCP Apps hybrid pattern (when building apps).**
   - **A2UI over AG-UI / A2A / WebSockets:** full streaming conversational generative UI across orchestrator and remote subagents.
   - **Pattern 1 — A2UI over MCP (`application/a2ui+json`, `a2ui://` URI):** return A2UI JSON as an MCP Resource (`resources/read` for static zero-LLM forms) or embedded `CallToolResult` resource (`tools/call` for dynamic tool views) so the host renders native widgets with zero iframe clash.
   - **Pattern 2 — MCP Apps inside A2UI:** wrap bespoke stateful canvases (WebGL/3D, games, seat maps) inside a custom A2UI iframe wrapper component; sync only macro key-states (`action` -> `updateDataModel`), never micro-state polling.
   - **Pattern 3 — A2UI inside MCP Apps:** bundle `<a2ui-surface>` + `@modelcontextprotocol/ext-apps` `AppBridge` inside an MCP App iframe to bring dynamic generative controls to legacy or non-A2UI hosts.
   Done when transport and sandbox boundaries match the host's capabilities.

4. **Validate wire safety and verify the rendered surface.**
   - Run deterministic A2UI v1.0 validation on every generated bundle:
     ```bash
     python -B "<this installed skill>/assets/gen-ui/gen_ui.py" validate-a2ui --file "<project-root>/.scratch/gen-ui/<slug>/surface.a2ui.json" --json
     ```
   - Confirm `valid: true` (unique flat IDs, `root` present, acyclic `child`/`children` graph, zero orphans, allowlisted catalog components, resolvable `@path` pointers, and zero `<script>`/`javascript:` injection).
   - For interactive HTML cockpits or web A2UI renderers (`@a2ui/react`, `@a2ui/lit`, `@a2ui/angular`), verify in a real browser (`Operate` surface mode, OKLCH role tokens, keyboard focus, working filters, and valid `renderer_to_agent` v1.0 `action` payload export so human choices round-trip back into the session). Link the clickable file path for the user; pass `--open` only when interactive viewing is helpful.
   Done when `validate-a2ui` exits `0` and the rendered UI is verified free of console, layout, or escaping defects.

**Done when** the A2UI v1.0 surface passes schema, cycle, pointer, and script-injection validation, renders cleanly in native widgets or the contained interactive cockpit, and gives the human a faster decision/inspection loop than prose alone.
