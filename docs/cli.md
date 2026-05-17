# CLI Reference

The `runspec` binary ships with `pip install runspec`. It provides three
commands for checking your config, discovering runnables, and emitting
agent schemas.

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
2. **Installed** — scans installed packages for runspec-aware entry points

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

## Usage in agent workflows

The typical workflow for giving an agent access to your runnables:

```bash
# 1. Check your config is complete
runspec check

# 2. See what would be emitted
runspec emit

# 3. Feed to an agent framework
runspec emit --format mcp > tools.json
```

Or skip step 2 and pipe directly:

```bash
runspec emit | your-mcp-server --tools-stdin
```

For a multi-project environment, `discover` emits everything at once:

```bash
runspec discover --format mcp | your-mcp-server --tools-stdin
```

An agent that can run `runspec discover` at startup sees every runspec-aware
runnable installed in its environment — without any per-tool configuration.