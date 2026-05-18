# CLI Reference

The `runspec` binary ships with `pip install runspec`. It provides commands
for scaffolding, inspecting your config, emitting agent schemas, running a
live MCP server, and executing tools on jump boxes via SSH.

```
runspec <command> [options]
```

---

## runspec init

Scaffold a new `runspec.toml` and a language-appropriate code stub in the
current directory.

```bash
runspec init [--name <name>] [--lang <lang>]
```

| Flag | Default | Description |
|---|---|---|
| `--name` | current directory name | Name for the initial runnable |
| `--lang` | `python` | Language for the code stub: `python`, `typescript`, `javascript` |

If `runspec.toml` already exists, `init` exits with an error — it will not
overwrite or merge. If the code stub already exists, it is skipped with an
info message.

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

Also creates `deploy.py` (Python default):

```python
from runspec import parse


def main():
    args = parse()
    # your logic here


if __name__ == "__main__":
    main()
```

For a TypeScript stub:

```bash
runspec init --name deploy --lang typescript
```

Move both files inside your package directory (e.g. `mypkg/`) before
publishing so they are included as package data automatically.

---

## runspec local

List all runspec-aware runnables installed in this environment, with inline
validation. Also emits tool schemas in agent-ready formats.

```bash
runspec local [--format <fmt>] [--script <name>]
```

| Flag | Default | Description |
|---|---|---|
| `--format` | `text` | Output format: `text`, `json`, `mcp`, `openai`, `anthropic` |
| `--script` | all runnables | Runnable name to target (use with schema formats) |

Runnables must be installed (`pip install` or `pip install -e .`) to appear.
There is no filesystem walk — discovery uses `importlib.metadata`.

### Text output (default)

Shows installed runnables grouped by config file, with autonomy levels and
any config issues inline:

```bash
runspec local
```

```
Found 3 installed runnable(s):

  /home/user/project/mypkg/runspec.toml
    deploy       Deploy the application to an environment  [confirm]
    backup-logs  Back up application logs to S3            [manual]
    process      Process input files                       [confirm]

Issues:

  ℹ  'process' autonomy not declared — defaulting to 'confirm'
  ✗  'process.api-key' is required but has no description

Run 'runspec local --format mcp' to emit MCP tool schemas.
```

Exits with code 1 if any errors are found, so it can be used as a CI check:

```yaml
# .github/workflows/ci.yml
- name: Validate runspec
  run: runspec local
```

### Schema output

Emit all installed runnables as tool schemas for agent frameworks:

```bash
runspec local --format mcp          # MCP tool list (default schema format)
runspec local --format openai       # OpenAI tool calling format
runspec local --format anthropic    # Anthropic tool use format
runspec local --format json         # raw JSON — discovery data for tooling
```

Target a single runnable:

```bash
runspec local --format mcp --script deploy
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

Reads the runspec config from the current directory (walking up to find
`runspec.toml`), then starts a
[Model Context Protocol](https://github.com/modelcontextprotocol/specification)
server over stdin/stdout. Every installed runnable is exposed as an MCP tool.
When an agent calls a tool, `serve` runs the corresponding script and streams
back the output.

Zero extra dependencies — the protocol is JSON-RPC 2.0 newline-delimited
over stdin/stdout, which is plain stdlib.

### Subcommands

Runnables that declare subcommands (via `[<name>.commands.<subcommand>]`) are
automatically expanded into flat MCP tools with underscore-joined names:

```toml
[portal-api.commands.orders.commands.get-list]
description = "List orders"
autonomy    = "confirm"
```

Becomes the MCP tool `portal-api_orders_get-list`, with command
`[portal-api, orders, get-list, ...args]` assembled at invocation time.

### Host filtering

If a runnable declares a `hosts` field, `serve` checks the current machine's
hostname at startup. Tools that don't match are excluded from the MCP tool
list and not registered with the registry.

```toml
[parse-app-logs]
description = "Parse and summarise application logs"
autonomy    = "confirm"
hosts       = ["logserver-01", "logserver-02"]
```

On any other host, `parse-app-logs` is invisible.

### Privilege escalation (run_as)

The `run_as` field controls which user a tool runs as when invoked via
`runspec jump`. It is resolved by `serve` at startup against the current
hostname, then registered with the registry as a plain string.

```toml
[deploy]
run_as         = "oracle"
become_method  = "sudo"      # default — also: su, pbrun, dzdo
become_flags   = "-H"        # optional extra flags
```

Per-host and pattern-based resolution are supported — see `spec/SPEC.md`
for the full `run_as` table syntax.

### Environment variables set on every invocation

Before running a script, `serve` sets environment variables for every
argument declared in the spec:

```
RUNSPEC_<ARG_NAME_UPPERCASED>=<value>
```

Hyphens become underscores. Bool and flag types are `1` or `0`. Defaults
are always set, even when the caller did not pass the arg explicitly.

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
registers itself with a `runspec-registry` instance on startup.

```toml
# runspec.toml
[config]
registry  = "https://registry.internal:8080"
name      = "analytics-pipeline"
heartbeat = 30
```

`serve` sends a heartbeat every `heartbeat` seconds. On SIGTERM it
deregisters cleanly. If the registry restarts, the next heartbeat triggers
a full resend automatically.

### Connecting to Claude Desktop

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

On Windows:

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

`cwd` is the directory `serve` searches for your config file.

### Running as a service

```ini
# systemd unit
[Service]
ExecStart=/home/user/envs/analytics-pipeline/bin/runspec serve
WorkingDirectory=/home/user/projects/analytics
Restart=always
```

---

## runspec jump

List tools available on jump boxes, or run a tool on a specific jump box
via SSH.

```bash
runspec jump [<tool>] [options] [-- tool-args...]
```

Everything after `--` is passed directly to the tool.

| Flag | Description |
|---|---|
| `--host <host>` | Jump box to run on. Required for execution. |
| `--registry <url>` | Registry URL. Overrides `[config] registry`. |
| `--registry-key <key>` | API key for registry read endpoints. |
| `--registry-cert <path>` | CA certificate bundle for HTTPS registry. |
| `--user <user>` | SSH username. |
| `--ssh-key <file>` | Path to SSH private key. |
| `--no-host-key-check` | Skip SSH host key verification (insecure — use only on trusted networks). |
| `--format` | `text` (default) or `json` — listing mode only. |
| `--` | Separator: everything after is passed to the tool. |

Paramiko is required for execution: `pip install 'runspec[run]'`.

### List available tools

With no tool name, `runspec jump` lists tools and hosts from the registry:

```bash
# Registry URL from [config] registry in runspec.toml
runspec jump

# Explicit registry URL
runspec jump --registry https://registry.internal:8080

# JSON output for tooling or agents
runspec jump --registry https://registry.internal:8080 --format json
```

```
Tools available via https://registry.internal:8080:

  deploy                   Deploy the application
                           hosts: jumpbox-eu-01, jumpbox-us-01
  backup-logs              Back up logs to S3
                           hosts: jumpbox-eu-01
  parse-errors             Parse error logs
                           hosts: jumpbox-eu-01, jumpbox-eu-02
```

### Run a tool on a jump box

```bash
# Run deploy on jumpbox-eu-01
runspec jump deploy --host jumpbox-eu-01 -- --env prod

# With explicit registry
runspec jump deploy --host jumpbox-eu-01 \
    --registry https://registry.internal:8080 \
    -- --env prod

# With SSH user and key
runspec jump deploy --host jumpbox-eu-01 --user deploy \
    --ssh-key ~/.ssh/id_deploy -- --env prod
```

### What jump does

1. Queries the registry: `GET /tools/<name>` — finds the host entry for `--host`
2. Reads `x-command`, `x-run-as`, `x-become-method`, `x-become-flags` from that entry
3. Builds the remote command with privilege escalation
   (e.g. `sudo -u oracle /usr/local/bin/deploy --env prod`)
4. Opens an SSH connection and runs the command
5. Streams stdout and stderr to your terminal in real time
6. Exits with the remote process's exit code

The `run_as` and privilege escalation values were resolved by `runspec serve`
on the jump box at startup — they reflect per-host resolution and pattern
matching. `runspec jump` does not re-resolve them.

### Registry URL from config

If `[config] registry` is set in a `runspec.toml` found by walking up from
the current directory, `runspec jump` uses it automatically:

```toml
[config]
registry = "https://registry.internal:8080"
```

---

## Bash runnables

Any executable script — bash, Python, Node, Ruby, or anything else — can be
a first-class runspec runnable.

### Structure

Place the script and a `runspec.toml` in the same directory:

```
backup-logs/
  runspec.toml
  backup-logs.sh
```

```toml
[backup-logs]
description = "Back up application logs to S3"
autonomy    = "confirm"

[backup-logs.args]
env     = {type = "choice", options = ["prod", "staging"], description = "Target environment"}
days    = {type = "int", default = 7, description = "Days of logs to retain"}
dry-run = {type = "flag", description = "Print what would happen without doing it"}
```

### Reading arguments

`serve` sets all argument values as `RUNSPEC_*` environment variables
before running the script:

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

| Arg name | Variable | Value when true | Value when false |
|---|---|---|---|
| `env` | `RUNSPEC_ENV` | the string value | — |
| `days` | `RUNSPEC_DAYS` | the number as a string | — |
| `dry-run` | `RUNSPEC_DRY_RUN` | `1` | `0` |
| `verbose` | `RUNSPEC_VERBOSE` | `1` | `0` |

Hyphens become underscores. `RUNSPEC_AGENT=1` is always set.

### Script discovery

`runspec serve` looks in the venv `bin/` directory — exact name match,
`.exe` on Windows. This is how Python and Node entry points are found after
`pip install` or `npm install`.

Scripts must be installed to be found. If you have existing scripts
elsewhere, a thin wrapper is the migration path:

```bash
#!/usr/bin/env bash
# backup-oracle — lives in the runspec project, calls the original
exec /opt/legacy-scripts/backup-oracle.sh "$@"
```

---

## Usage in agent workflows

```bash
# 0. Scaffold a config (new projects)
runspec init --name myapp

# 1. Check your config and see what's installed
runspec local

# 2. Preview what schemas will be emitted
runspec local --format mcp

# 3. Start the live MCP server
runspec serve
```

To wire it into Claude Desktop, point the MCP server config at `runspec serve`
(see above). The agent connects once at startup and calls tools as needed.

For jump box execution from a terminal or agent subprocess:

```bash
# See what's available across all jump boxes
runspec jump

# Run a tool on a specific jump box
runspec jump deploy --host jumpbox-eu-01 -- --env prod
```
