# CLI Reference

The `runspec` binary ships with `pip install runspec`. It provides four
commands for checking your config, discovering runnables, emitting agent
schemas, and running a live MCP server.

```
runspec <command> [options]
```

---

## runspec check

Validate the current project's runspec setup. Run it after writing or
updating your config to catch problems early.

```bash
runspec check
```

Checks performed:

- Config file found (searches up from the current directory)
- `[project.scripts]` present (needed for agent auto-discovery)
- No reserved names (`config` is reserved)
- Every runnable has a `description` (agents need this)
- Every runnable has an `autonomy` level declared
- Required args without descriptions (agents won't know what to pass)

### Example output

```
  ✓  Config found: /home/user/project/pyproject.toml
  ✓  [project.scripts] found — 2 entry point(s)
  ✓  'deploy' — description present
  ✓  'deploy' — autonomy: manual
  ✓  'process' — description present
  ℹ  'process' autonomy not declared — will default to 'confirm'
  ℹ  'process.api-key' is required but has no description

  All checks passed.
```

`✓` passes, `ℹ` warnings, `✗` errors. Exits with code 1 if any errors are found.

---

## runspec discover

Find all runspec-aware runnables in the current environment.

```bash
runspec discover [--format text|json|mcp|openai|anthropic]
```

| Flag | Default | Description |
|---|---|---|
| `--format` | `text` | Output format |

Discovers runnables in two places:

1. **Local** — searches up from the current directory for `pyproject.toml` or `runspec.toml`
2. **Installed** — finds packages in the current Python environment that list `runspec` as a dependency, then locates their spec

### Making your package discoverable

When another developer `pip install`s your package, `discover` will find it
automatically if:

- You ship a standalone `runspec.toml` inside your Python package directory,
  **and** declare it as package data in `pyproject.toml`:

```
mypackage/
  __init__.py
  runspec.toml     ← inside the package, not at the project root
```

```toml
# pyproject.toml
[tool.setuptools.package-data]
mypackage = ["runspec.toml"]
```

If your package is installed in editable mode (`pip install -e .`), discovery
works automatically with either `runspec.toml` or `[tool.runspec]` in
`pyproject.toml` — no special packaging needed.

### Formats

**text** (default) — human-readable summary:

```bash
runspec discover
```

```
Found 3 runspec-aware runnable(s):

  /home/user/project/pyproject.toml
    • deploy
    • process
    • validate

Run 'runspec discover --format mcp' to emit MCP tool schemas.
```

**json** — raw discovery data, useful for tooling:

```bash
runspec discover --format json
```

```json
[
  {
    "source": "/home/user/project/pyproject.toml",
    "runnable": "deploy",
    "spec": { ... }
  }
]
```

**mcp / openai / anthropic** — emit all discovered runnables as tool schemas in one step:

```bash
runspec discover --format mcp
```

This is the fastest path to making everything in an environment available to an agent —
one command, all runnables, ready to paste into an MCP server or tool call config.

---

## runspec emit

Emit a tool schema for one or all runnables in the current project.

```bash
runspec emit [--script <name>] [--format mcp|openai|anthropic]
```

| Flag | Default | Description |
|---|---|---|
| `--script` | all runnables | Name of a specific runnable to emit |
| `--format` | `mcp` | Output schema format |

### Emit all runnables

```bash
runspec emit
```

Emits every runnable in the current config as MCP tool schemas:

```json
{
  "tools": [
    {
      "name": "process",
      "description": "Process input files",
      "x-autonomy": "confirm",
      "inputSchema": {
        "type": "object",
        "properties": {
          "input": {
            "type": "string",
            "description": "Input file path"
          },
          "format": {
            "type": "string",
            "enum": ["json", "csv", "parquet"],
            "default": "json"
          },
          "workers": {
            "type": "integer",
            "default": 4,
            "minimum": 1,
            "maximum": 32
          },
          "dry-run": {
            "type": "boolean",
            "default": false
          }
        },
        "required": ["input"]
      }
    }
  ]
}
```

### Emit one runnable

```bash
runspec emit --script deploy
runspec emit --script deploy --format openai
```

### Schema fields

Every emitted tool includes:

| Field | Source |
|---|---|
| `name` | Runnable name from spec |
| `description` | `description` field — shown to agents |
| `x-autonomy` | Effective autonomy level |
| `x-autonomy-reason` | `autonomy-reason` field, if declared |
| `x-output` | `output` field — `"text"` if not declared |
| `inputSchema` | JSON Schema for all args |

The `x-autonomy` extension field is how agents know whether they need to
confirm with the user before running a tool. Frameworks that understand it
can enforce autonomy automatically.

### Format differences

All three formats use the same `inputSchema` structure. The difference is
the top-level wrapper:

| Format | Wrapper |
|---|---|
| `mcp` | `{ "tools": [...] }` |
| `openai` | `{ "<name>": { ... }, ... }` |
| `anthropic` | `{ "<name>": { ... }, ... }` |

---

## runspec serve

Start a live MCP stdio server for the current environment.

```bash
runspec serve
```

Reads the runspec config from the current directory, then starts a
[Model Context Protocol](https://github.com/modelcontextprotocol/specification)
server over stdin/stdout. The server exposes every runnable as an MCP tool.
When an agent calls a tool, `serve` runs the corresponding script in the same
virtual environment and streams back the output.

Zero extra dependencies — the protocol is JSON-RPC 2.0 newline-delimited
over stdin/stdout, which is plain stdlib.

### Server name

The server identifies itself by the virtual environment directory name:

```
/home/user/envs/analytics-pipeline/  →  server name: "analytics-pipeline"
/home/user/envs/data-pipeline/       →  server name: "data-pipeline"
```

Override it in your config:

```toml
# runspec.toml or pyproject.toml [tool.runspec.config]
[config]
name = "my-pipeline"
```

### Connecting to Claude Desktop

Add an entry to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "analytics-pipeline": {
      "command": "/home/user/envs/analytics-pipeline/bin/runspec",
      "args": ["serve"],
      "cwd": "/home/user/projects/analytics"
    }
  }
}
```

On Windows, use the `.exe` path:

```json
{
  "mcpServers": {
    "analytics-pipeline": {
      "command": "C:\\envs\\analytics-pipeline\\Scripts\\runspec.exe",
      "args": ["serve"],
      "cwd": "C:\\projects\\analytics"
    }
  }
}
```

`cwd` is the directory `serve` searches for your config file. Set it to your
project root.

### What the agent sees

When a Claude (or any MCP-compatible agent) connects, it receives tool
definitions for every runnable in your config — argument names, types,
descriptions, required fields, and autonomy levels. Calling a tool runs the
script and returns its stdout.

If the script exits non-zero, the tool returns `isError: true` with the exit
code, stdout, and stderr — so the agent has full context on what went wrong.

The `RUNSPEC_AGENT=1` environment variable is set for every script invocation
via `serve`. Your runnable can read this via `args.__agent__` to switch to
machine-readable output:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "ok", "deployed_to": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

### Running as a service

`serve` reads from stdin and writes to stdout — it stays alive until stdin
closes. For persistent deployments, run it under a process supervisor:

```ini
# supervisord.conf
[program:analytics-mcp]
command=/home/user/envs/analytics-pipeline/bin/runspec serve
directory=/home/user/projects/analytics
autostart=true
autorestart=true
```

```ini
# systemd unit
[Service]
ExecStart=/home/user/envs/analytics-pipeline/bin/runspec serve
WorkingDirectory=/home/user/projects/analytics
Restart=always
```

---

## Usage in agent workflows

The typical workflow for giving an agent access to your runnables:

```bash
# 1. Check your config is complete
runspec check

# 2. Preview what schemas will be emitted
runspec emit

# 3. Start the live MCP server
runspec serve
```

To wire it into Claude Desktop, point the MCP server config at `runspec serve`
(see above). The agent connects once at startup and calls tools as needed —
no tool list files to maintain, no restart required when you add runnables.

For a multi-project environment, `discover` emits everything at once:

```bash
runspec discover --format mcp
```

An agent that runs `discover` at startup sees every runspec-aware runnable
installed in its environment — without any per-tool configuration.