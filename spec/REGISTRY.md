# runspec-registry Protocol

Version: 1

This document defines the HTTP protocol between a `runspec serve` agent client
and a `runspec-registry` master server.

---

## Overview

The registry is a lightweight presence-and-discovery service. Agents register
themselves on startup, send periodic heartbeats, and deregister on clean shutdown.
The registry can request a fresh tool listing from any registered agent.

The protocol is JSON over HTTP. All request and response bodies are
`application/json`.

---

## Endpoints

All paths are relative to the registry base URL configured in `[config]`:

```toml
[config]
registry = "https://registry.example.com"
```

The agent appends each path to this base URL verbatim — no trailing slash is
added to the base URL.

| Direction       | Method | Path            | Purpose                          |
|-----------------|--------|-----------------|----------------------------------|
| Agent → Master  | POST   | `/register`     | Agent announces itself           |
| Agent → Master  | POST   | `/heartbeat`    | Liveness ping; response may carry instructions |
| Agent → Master  | POST   | `/tools`        | Agent posts its current tool list |
| Agent → Master  | POST   | `/deregister`   | Agent announces clean shutdown   |

---

## Session identity

Every request from the same `runspec serve` process carries the same
`agent_id` — a UUID-4 generated at process start. The `agent_id` is opaque
to the agent; the registry uses it as a session key.

---

## Register

Called once on startup, before the MCP loop begins accepting connections.

### Request

```
POST /register
Content-Type: application/json
```

```json
{
  "agent_id":   "550e8400-e29b-41d4-a716-446655440000",
  "name":       "my-pipeline",
  "version":    "1",
  "tools_seq":  1
}
```

| Field      | Type   | Description |
|------------|--------|-------------|
| `agent_id` | string | UUID-4, unique per process lifetime |
| `name`     | string | Human-readable name for this agent (from `--name` flag or `[config] name`) |
| `version`  | string | Spec version string from `[config]` (default `"1"`) |
| `tools_seq`| int    | Tool list sequence number. Always `1` in protocol version 1. Reserved for future hot-reload. |

The agent does **not** send the tool list in the register message. The registry
sends a `refresh` heartbeat response if it wants the tools immediately.

### Response

```json
{ "status": "ok" }
```

On error the registry returns a 4xx or 5xx HTTP status. The agent logs the
error and continues running — registration failure does not abort the MCP server.

---

## Heartbeat

Sent on a fixed interval. The interval is configured in `[config]`:

```toml
[config]
heartbeat = 30   # seconds between heartbeats (default: 30)
```

### Request

```
POST /heartbeat
Content-Type: application/json
```

Minimal packet (default — no `heartbeat_data` configured):

```json
{
  "agent_id":  "550e8400-e29b-41d4-a716-446655440000",
  "tools_seq": 1
}
```

With `heartbeat_data = ["system"]`:

```json
{
  "agent_id":  "550e8400-e29b-41d4-a716-446655440000",
  "tools_seq": 1,
  "system": {
    "pid":    12345,
    "uptime": 142
  }
}
```

`uptime` is seconds since the agent process started.

`heartbeat_data` values:

| Value      | Fields added             | Notes |
|------------|--------------------------|-------|
| `system`   | `system.pid`, `system.uptime` | Process-level liveness data |
| `activity` | _(reserved)_             | Future use — call counts, last-called timestamps |

### Response

```json
{ "status": "ack" }
```

or

```json
{ "status": "refresh" }
```

`ack` — no action required.

`refresh` — the registry wants the agent's current tool list. The agent
immediately sends a `/tools` request.

On any network error or non-2xx response the agent logs the failure and
continues. It does not deregister on heartbeat failure.

---

## Tools

Sent in response to a `refresh` heartbeat response, or on any future event
that triggers a tool-list change (none in v1).

### Request

```
POST /tools
Content-Type: application/json
```

```json
{
  "agent_id":  "550e8400-e29b-41d4-a716-446655440000",
  "tools_seq": 1,
  "tools": [
    {
      "name":        "deploy",
      "description": "Deploy to production",
      "x-autonomy":  "manual",
      "inputSchema": {
        "type": "object",
        "properties": {
          "environment": { "type": "string", "enum": ["staging", "production"] },
          "dry-run":     { "type": "boolean", "default": false }
        },
        "required": ["environment"]
      }
    }
  ]
}
```

The `tools` array is identical to the output of `runspec local --format mcp`
for this project. The registry can cache it and serve it to discovery clients.

### Response

```json
{ "status": "ok" }
```

---

## Deregister

Sent on clean shutdown (SIGTERM received). Best-effort — the agent does not
retry on failure. The registry treats agents that miss heartbeats as offline
regardless.

### Request

```
POST /deregister
Content-Type: application/json
```

```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Response

```json
{ "status": "ok" }
```

---

## Config reference

All registry settings live under `[config]` in `runspec.toml`:

```toml
[config]
registry       = "https://registry.example.com"  # required to enable registration
heartbeat      = 30                               # seconds (default: 30)
heartbeat_data = ["system"]                       # optional; omit for minimal packets
```

These can be overridden at invocation time:

```bash
runspec serve --registry https://registry.example.com --name my-pipeline
```

`--registry` overrides `[config] registry`.
`--name` overrides the auto-derived server name.

---

## Agent state machine

```
start
  │
  ▼
register ──────────────────────────────────┐
  │ ok (or error — continue anyway)        │
  ▼                                        │
MCP loop (accepting tool calls)            │
  │                                        │
  ├─── every heartbeat interval ───────────┤
  │      POST /heartbeat                   │
  │      ├── ack  → nothing               │
  │      └── refresh → POST /tools        │
  │                                        │
SIGTERM                                    │
  │                                        │
  ▼                                        │
deregister (best-effort)                   │
  │                                        │
stop ◄─────────────────────────────────────┘
```

---

## v1 constraints and future notes

- **`tools_seq` is always `1` in v1.** The field is included in all messages
  as a placeholder for future hot-reload support (reloading `runspec.toml`
  without restarting the process). In v1, the TOML is read once at startup
  and never reloaded.

- **No challenge/response authentication in v1.** The registry URL is treated
  as a shared secret. TLS is assumed for production deployments.

- **`activity` heartbeat data is reserved** and not emitted in v1. The field
  name is allocated to avoid a future breaking change.

- **Offline handling is the registry's responsibility.** The agent does not
  attempt to re-register after a failed heartbeat. The registry decides when
  to mark an agent offline based on missed heartbeats.
