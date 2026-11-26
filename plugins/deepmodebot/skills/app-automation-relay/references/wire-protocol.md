# Relay wire protocol

`assets/relay_server.ts` defines `AppAdapter`, `Observation`, `ActRequest`, and both transports. The observation shape is adapted from omp's browser `tab-protocol.ts`; it is not a compatible CDP endpoint.

| Local RPC `op` | `args` | Result |
|---|---|---|
| `targets` | `{filter?}` | `{targetId, title, location, owned}[]` |
| `observe` | `{targetId, includeText?}` | Target revision, viewport, visible entries `{id, role, name?, value?, states}`, optional text |
| `act` | `{targetId, revision, id, op, value?, key?}` | `{ok, revision}`; a stale revision fails without dispatch |
| `waitFor` | `{targetId, textContains, timeoutMs?}` | `{matched, revision}`; a timeout is not success |

## Running the starter

- `bun assets/relay_server.ts --mcp`: newline-delimited JSON-RPC on stdio. With no `DMB_RELAY_PORT`, the process owns its adapter. In the starter this is a demo form. Exposed tools end in `_targets`, `_observe`, `_act`, and `_wait`. `server/discover` supports the `2026-07-28` protocol; legacy clients can use `initialize`.
- `bun assets/relay_server.ts --serve-relay`: provision a fresh shared secret in `DMB_RELAY_TOKEN` first. The daemon binds `127.0.0.1:0` and prints the URL and announcement path. The announcement contains the port, PID and app name, **not** the token. Never put the token in argv, tool arguments, or logs.
- For shared access, start `--mcp` with the selected `DMB_RELAY_PORT` and the same secret. Alternatively, POST `{"op":"targets","args":{}}` to `/rpc` with JSON content type and bearer authorization. Success returns `{ok:true,result}`; rejected operations return `{ok:false,error}`. `/healthz` also requires authentication. Stop the daemon you started after clients disconnect.
- `--self-test` uses a private ephemeral port and secret, writes no discovery file, and checks the state from a separate MCP process. It needs only Bun; it does not install or register a plugin in a host app.

## Porting to a shared native app

Pin the adapter to the explicitly selected target. Keep one app attachment and serialize revision checks with mutations. Never persist a native element pointer or an ID across revisions. Use target notifications for invalidation and waits; if the API only supports polling, bound the interval, timeout and snapshot size.

When clients must automatically share and release a native handle, add per-client leases tied to a live connection. On final disconnect, release only resources the relay owns. Do not rely on a PID or announcement alone to establish identity or ownership. The starter uses explicit port selection and process lifetime, not lease discovery or automatic shutdown.
