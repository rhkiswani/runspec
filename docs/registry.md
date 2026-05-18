# runspec-registry

A lightweight HTTP registry for runspec agents.

When `runspec serve` starts on a host it registers itself here. The registry tracks which tools are available, on which hosts, and with what execution metadata. Clients (Chainlit apps, orchestrators, CI pipelines) query the registry to discover agents and route `runspec jump` calls.

## Install

```bash
pip install runspec-registry
```

## Start the server

```bash
runspec-registry
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `8765` | Bind port |
| `--api-key` | — | API key for write endpoints |
| `--ssl-keyfile` | — | TLS private key path |
| `--ssl-certfile` | — | TLS certificate path |
| `--purge-interval` | `60` | Seconds between stale-instance sweeps |
| `--reload` | — | Auto-reload (development only) |

## API reference

### Write endpoints

These require `X-API-Key` header when `--api-key` is set.

**Register an agent**
```
POST /instances
{
  "instance_id": "uuid",
  "name": "analytics-pipeline",
  "version": "0.4.0",
  "host": "prod-host-01"
}
```

**Send heartbeat**
```
POST /instances/{id}/heartbeat
{}
```

Optionally include system data if `heartbeat_data = ["system"]` is set in `runspec.toml`:
```
POST /instances/{id}/heartbeat
{
  "system": { "pid": 12345, "uptime": 3600 }
}
```

The registry responds with `{"status": "ack"}` or `{"status": "refresh"}` to request a tool list resync.

**Update tool list**
```
POST /instances/{id}/tools
{
  "tools": [ ...MCP tool schemas with x-command, x-run-as, x-become-method... ]
}
```

**Deregister**
```
DELETE /instances/{id}
```

### Read endpoints

No authentication required.

**List all tools**
```
GET /tools
```
Returns each tool once with a `hosts` list showing which instances offer it and their execution metadata.

**Get a specific tool**
```
GET /tools/{name}
```

**List live instances**
```
GET /instances
```

**Health check**
```
GET /health
→ {"status": "ok"}
```

## Authentication

```bash
# Start registry with a key
runspec-registry --api-key mysecretkey

# Agents register with the matching key
runspec serve --registry http://myserver:8765 --registry-key mysecretkey

# runspec jump also accepts the key
runspec jump deploy --host prod-01 --registry http://myserver:8765 --registry-key mysecretkey
```

## TLS

```bash
# Start with TLS
runspec-registry --ssl-certfile cert.pem --ssl-keyfile key.pem

# Agents connecting with a self-signed CA cert
runspec serve --registry https://myserver:8765 --registry-cert ca.pem
```

## Heartbeat and stale purge

Agents send heartbeats on an interval set in `runspec.toml` (default 30 seconds). The registry marks instances stale after 3 missed heartbeats and removes them during the next purge sweep (`--purge-interval`, default 60 seconds).

To include system telemetry in heartbeats:

```toml
[config]
heartbeat = 30
heartbeat_data = ["system"]   # includes pid and uptime
```

## How it fits together

```
runspec serve           →  registers + heartbeats  →  runspec-registry
runspec jump --host …   →  queries /tools/{name}   →  runspec-registry
                        →  SSHes to jump box and runs the tool
```

The registry is stateless between restarts — agents re-register on their next heartbeat cycle, so a registry restart is non-disruptive.
