# CLI Reference

The `runspec` binary ships with `pip install runspec`. It provides commands
for scaffolding, checking your config, discovering runnables, emitting agent
schemas, running a live MCP server, and executing tools locally or on remote
hosts.

```
runspec <command> [options]
```

---

## runspec init

Scaffold a new `runspec.toml` in the current directory with a starter runnable ready to fill in.

```bash
runspec init [--name <name>]
```

| Flag | Default | Description |
|---|---|---|
| `--name` | current directory name | Name for the initial runnable |

If `runspec.toml` already exists, `init` exits with an error and lists the existing
runnables — it will not overwrite or merge.

### Example

```bash
runspec init --name deploy
```

Creates `runspec.toml`:

```toml
[deploy]
description = "Describe what deploy does"
autonomy    = "confirm"

[deploy.args]
# example = {type = "str", description = "An example argument"}
```

Move the file inside your package directory (e.g. `mypkg/runspec.toml`) before
publishing so it is included as package data automatically.

Then fill in the description, declare your args, and run `runspec check` to validate.

---

## runspec check

Validate the current project's runspec setup. Run it after writing or
updating your config to catch problems early.

```bash
runspec check
```

Checks performed:

- Config file found (searches up from the current directory)
- No reserved names (`config` is reserved)
- Every runnable has a `description` (agents need this)
- Every runnable has an `autonomy` level declared
- Required args without descriptions (agents won't know what to pass)
- `run_as` patterns are valid Python `re.fullmatch()` expressions

### Example output

```
  ✓  Config found: /home/user/project/mypkg/runspec.toml
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

1. **Local** — searches up from the current directory for `runspec.toml`
2. **Installed** — finds packages in the current Python environment that list `runspec` as a dependency, then locates their `runspec.toml`

### Making your package discoverable

When another developer `pip install`s your package, `discover` will find it
automatically if you ship `runspec.toml` inside your Python package directory
(not at the project root). Modern build backends (flit, hatch, setuptools)
include files inside the package directory automatically — no extra configuration needed:

```
mypackage/
  __init__.py
  runspec.toml     ← inside the package, auto-included as package data
```

If your package is installed in editable mode (`pip install -e .`), discovery
searches package subdirectories of the source directory automatically.

### Formats

**text** (default) — human-readable summary:

```bash
runspec discover
```

```
Found 3 runspec-aware runnable(s):

  /home/user/project/mypkg/runspec.toml
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
    "source": "/home/user/project/mypkg/runspec.toml",
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
runspec serve [options]
```

| Flag | Description |
|---|---|
| `--dev` | Development mode: aggregate all `runspec.toml` files under the nearest `.git` root. Registry disabled. |
| `--registry <url>` | Registry URL. Overrides `[config] registry`. |
| `--name <name>` | Instance name. Overrides `[config] name`. |
| `--registry-key <key>` | API key for registry write endpoint authentication. |
| `--registry-cert <path>` | Custom CA certificate bundle for HTTPS verification. |

Reads the runspec config from the current directory, then starts a
[Model Context Protocol](https://github.com/modelcontextprotocol/specification)
server over stdin/stdout. The server exposes every runnable as an MCP tool.
When an agent calls a tool, `serve` runs the corresponding script and streams
back the output.

Zero extra dependencies — the protocol is JSON-RPC 2.0 newline-delimited
over stdin/stdout, which is plain stdlib.

### Host filtering

If a runnable declares a `hosts` field, `serve` checks the current machine's
hostname at startup. Tools that don't match are silently excluded from the MCP
tool list and not sent to the registry. This lets you keep a single shared
`runspec.toml` across a fleet while each host only exposes the tools relevant
to it.

```toml
[parse-app-logs]
description = "Parse and summarise application logs"
autonomy    = "confirm"
hosts       = ["logserver-01", "logserver-02"]
```

On any other host, `parse-app-logs` is invisible.

### Privilege escalation (run_as)

The `run_as` field controls which user a tool runs as when invoked remotely
via `runspec run`. It is resolved by `serve` at startup against the current
hostname, then registered with the registry as a plain string — so the
resolution logic never leaves the local machine.

```toml
[deploy]
run_as         = "oracle"
become_method  = "sudo"      # default — also: su, pbrun, dzdo
become_flags   = "-H"        # optional extra flags
```

Per-host and pattern-based resolution are supported — see `spec/SPEC.md` for
the full `run_as` table syntax. Invalid regex patterns cause `serve` to exit
with a clear error at startup, and `runspec check` validates them too.

### Environment variables set on every tool invocation

Before running a script, `serve` sets environment variables for every
argument declared in the spec:

```
RUNSPEC_<ARG_NAME_UPPERCASED>=<value>
```

Hyphens become underscores. Bool and flag types are `1` or `0`. Defaults
from the spec are always set, even when the caller did not pass the arg
explicitly.

`RUNSPEC_AGENT=1` is always set. Scripts can use it to switch between
human-readable and machine-readable output:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "ok", "deployed_to": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

### Registry integration

When `--registry` is set (or `[config] registry` is configured), `serve`
registers itself with a `runspec-registry` instance on startup. The registry
is a read-only catalog — it stores tool specs and host information but cannot
execute anything. Any HTTP client on the network can query it to discover what
tools are available and where.

```toml
# runspec.toml
[config]
registry  = "https://registry.internal:8080"
name      = "analytics-pipeline"
heartbeat = 30
```

`serve` sends a heartbeat every `heartbeat` seconds to keep its entry active.
On SIGTERM it deregisters cleanly. If the registry restarts and loses state,
the next heartbeat response triggers a full tool list resend automatically.

### Server name

The server identifies itself by the virtual environment directory name:

```
/home/user/envs/analytics-pipeline/  →  server name: "analytics-pipeline"
/home/user/envs/data-pipeline/       →  server name: "data-pipeline"
```

Override it with `--name` or in your config.

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

## runspec run

Run a tool locally or on a remote host via SSH.

```bash
runspec run [<tool>] [options] [-- tool-args...]
```

Everything after `--` is passed directly to the tool. Everything before it
is interpreted by `runspec run`.

| Flag | Description |
|---|---|
| `--dev` | Development mode: discover tools from all `runspec.toml` files under the nearest `.git` root. Scripts resolved from venv bin/ first, then the TOML directory. |
| `--host <host>` | Remote host to run on. Triggers SSH mode. |
| `--registry <url>` | Registry URL for remote mode. Overrides `[config] registry`. |
| `--registry-key <key>` | API key for registry read endpoints. |
| `--registry-cert <path>` | CA certificate bundle for HTTPS registry. |
| `--user <user>` | SSH username. |
| `--ssh-key <file>` | Path to SSH private key. |
| `--no-host-key-check` | Skip SSH host key verification (insecure — use only on trusted networks). |

Paramiko is required for remote execution: `pip install 'runspec[run]'`.

### List available tools

With no tool name, `runspec run` lists what is available:

```bash
# From the local runspec.toml
runspec run

# From a registry
runspec run --registry https://registry.internal:8080
```

```
Local tools:

  deploy                   Deploy the application to an environment
  backup-logs              Back up application logs to S3
  parse-errors             Parse error logs and return a summary
```

### Local mode

Without `--host`, the tool runs on the current machine as the current user.
No privilege escalation — if you need to run as a different user, wrap the
call yourself:

```bash
runspec run deploy -- --env prod
sudo -u oracle runspec run backup-logs -- --days 14
```

`runspec run` reads `runspec.toml` to find the tool, then locates its
installed executable from the venv `bin/` directory. All resolved argument
values are available to the script as `RUNSPEC_*` environment variables.

Use `--dev` when the script is not yet installed — it looks in the venv `bin/`
first, then falls back to the TOML directory for scripts under development.

### Remote mode

With `--host`, `runspec run` queries the registry for that host's tool
configuration, then SSHes and runs the command — applying any `run_as` and
`become_method` that `runspec serve` resolved and registered for that host.

```bash
# Run deploy on server-01, passing args after --
runspec run deploy --host server-01 -- --env prod

# Explicit registry URL
runspec run deploy --host server-01 \
    --registry https://registry.internal:8080 \
    -- --env prod

# With a specific SSH user and key
runspec run deploy --host server-01 --user deploy --ssh-key ~/.ssh/id_deploy \
    -- --env prod
```

The registry URL can also be set in your local `runspec.toml`:

```toml
[config]
registry = "https://registry.internal:8080"
```

### What remote mode does

1. Queries the registry: `GET /tools/<name>` — finds the host entry for `--host`
2. Reads `x-command`, `x-run-as`, `x-become-method`, `x-become-flags` from that entry
3. Builds the remote command with privilege escalation (e.g. `sudo -u oracle /usr/local/bin/deploy --env prod`)
4. Opens an SSH connection and runs the command
5. Streams stdout and stderr to your terminal in real time
6. Exits with the remote process's exit code

The `run_as` and privilege escalation values were resolved by `runspec serve`
on that host at startup — they reflect per-host resolution, pattern matching,
and env var expansion. `runspec run` does not re-resolve them.

---

## Bash runnables

Any executable script — bash, Python, Node, Ruby, or anything else — can be
a first-class runspec runnable. The runspec spec defines the interface;
`runspec serve` handles discovery, registration, and argument injection.

### Structure

Place the script and a `runspec.toml` in the same directory:

```
backup-logs/
  runspec.toml
  backup-logs.sh
```

```toml
# runspec.toml
[backup-logs]
description = "Back up application logs to S3"
autonomy    = "confirm"

[backup-logs.args]
env     = {type = "choice", options = ["prod", "staging"], description = "Target environment"}
days    = {type = "int", default = 7, description = "Days of logs to retain"}
dry-run = {type = "flag", description = "Print what would happen without doing it"}
```

### Reading arguments

Before running the script, `runspec serve` (and `runspec run`) set all
resolved argument values as `RUNSPEC_*` environment variables. The script
reads them directly — no library, no parsing, no `eval`:

```bash
#!/bin/bash
set -euo pipefail

if [ "$RUNSPEC_DRY_RUN" = "1" ]; then
    echo "Would sync $RUNSPEC_DAYS days of $RUNSPEC_ENV logs"
    exit 0
fi

aws s3 sync "/var/log/app/$RUNSPEC_ENV" "s3://logs-$RUNSPEC_ENV" \
    --delete \
    --exclude "*.tmp"

echo "Backed up $RUNSPEC_DAYS days of $RUNSPEC_ENV logs"
```

### Environment variable convention

| Arg name | Variable | Arg type | Value when true | Value when false |
|---|---|---|---|---|
| `env` | `RUNSPEC_ENV` | `str` / `choice` | the string value | — |
| `days` | `RUNSPEC_DAYS` | `int` | the number as a string | — |
| `dry-run` | `RUNSPEC_DRY_RUN` | `flag` | `1` | `0` |
| `verbose` | `RUNSPEC_VERBOSE` | `bool` | `1` | `0` |

Hyphens become underscores. `RUNSPEC_AGENT=1` is always set.
Defaults from the spec are always present — the script never receives an unset
variable for a declared arg.

### Script discovery

`runspec serve` and `runspec run` use identical discovery logic:

**Production mode** (no `--dev`): looks in the venv `bin/` only — exact name
match, `.exe` on Windows. This is how Python and Node entry points are found
after `pip install` or `npm install`.

**Development mode** (`--dev`): looks in the venv `bin/` first, then falls back
to the directory containing the `runspec.toml` as a convenience for scripts
that are not yet installed. This avoids requiring `pip install -e .` during
early development.

Arbitrary paths elsewhere on the filesystem are not supported.

This is intentional — it keeps tool collections self-contained, version
controlled, and auditable. If you have existing scripts scattered across
`/opt/scripts/` or similar, the migration path is to copy them into a proper
project directory with a `runspec.toml` and commit everything together. Most
scripts need changes to read `$RUNSPEC_*` variables anyway, so the migration
is a natural part of adding runspec support. If you want to keep calling your
original scripts unchanged, a thin wrapper is fine:

```bash
#!/usr/bin/env bash
# backup-oracle — lives in the runspec project, calls the original
exec /opt/legacy-scripts/backup-oracle.sh "$@"
```

### Running a bash runnable

The workflow is identical to Python or Node:

```bash
# Start the MCP server (bash script is exposed as a tool)
cd backup-logs/
runspec serve

# Run it locally
runspec run backup-logs -- --env staging

# Run it on a remote host
runspec run backup-logs --host logserver-01 -- --env prod
```

From an agent's perspective, a bash runnable looks identical to a Python or
Node runnable. The registry, the MCP tool schema, and the `runspec run`
interface are the same regardless of the language the script is written in.

---

## Usage in agent workflows

The typical workflow for giving an agent access to your runnables:

```bash
# 0. Scaffold a config (new projects)
runspec init --name myapp

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
