# Changelog

All notable changes to runspec are documented here.

---

## 0.2.0 — 2026-05-17

### Added

**`runspec serve`** — live MCP stdio server. Start it from your project
directory and connect any MCP-compatible agent (Claude Desktop, Cursor,
or your own agent loop) via `claude_desktop_config.json`. Zero extra
dependencies — the protocol is JSON-RPC 2.0 over stdin/stdout.

```json
{
  "mcpServers": {
    "my-pipeline": {
      "command": "/path/to/venv/bin/runspec",
      "args": ["serve"],
      "cwd": "/path/to/project"
    }
  }
}
```

See the [CLI reference](cli.md#runspec-serve) and
[Agent Integration](agents.md#live-mcp-server) guide for full details.

---

**`output` field on runnables** — declares what a runnable writes to stdout.

```toml
[process]
output = "json"   # agent can parse stdout as structured data
```

| Value | Meaning |
|---|---|
| `text` | Human-readable output (default) |
| `json` | Structured JSON — agent can parse and act on the response |
| `html` | Reserved for future UI use |

Surfaces as `x-output` in all emitted schemas so agent frameworks can
interpret the response without guessing.

---

**`args.__agent__`** — `RunSpec` exposes `__agent__: bool`. It is `True`
when the runnable is called via `runspec serve`. Use it to switch output
format for agent vs human callers:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "ok", "deployed_to": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

---

**Installed package discovery** — `runspec discover` now scans the current
Python environment for packages that list `runspec` as a dependency. No
registration step required — ship a `runspec.toml` in your package data
and it appears automatically.

---

## 0.1.1 — 2026-05-17

Fixed the Documentation link on the PyPI project page (previously a dead link).

---

## 0.1.0 — 2026-05-17

Initial release. Full `parse()` pipeline: config discovery, inference,
validation, coercion, and `RunSpec` return. Supports groups, subcommands,
autonomy levels, custom types, and `--help` interception. CLI commands:
`check`, `discover`, `emit`. Python 3.10–3.13, zero runtime dependencies
on 3.11+.
