# Agent Integration

runspec turns any runnable into something an agent can understand and safely
use — without any extra code beyond defining your interface in TOML.

---

## The problem runspec solves

Agents need to know three things about every tool they might call:

1. **What arguments does it take?** Types, required vs optional, valid values.
2. **What does it do?** Enough context to decide whether to call it.
3. **Can it run this automatically?** Or does it need to stop and ask a human first?

Without a structured interface, agents are guessing. With runspec, the answers
are machine-readable, always accurate, and derived from the same source the
CLI uses — so they can never drift.

---

## Emitting schemas

`runspec local --format mcp` converts your installed runnables into JSON Schema
tool definitions ready for any agent framework.

```bash
runspec local --format mcp
```

```json
{
  "tools": [
    {
      "name": "greet",
      "description": "Greet someone from the command line",
      "x-autonomy": "autonomous",
      "inputSchema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "loud": {
            "type": "boolean",
            "default": false
          },
          "times": {
            "type": "integer",
            "default": 1
          }
        },
        "required": ["name"]
      }
    }
  ]
}
```

The agent gets the full interface: argument names, types, defaults, which
args are required, and the autonomy level — all from the one place you
already maintain.

### Format options

```bash
runspec local --format mcp                     # MCP (default schema format)
runspec local --format openai                  # OpenAI tool calling
runspec local --format anthropic               # Anthropic tool use
runspec local --format mcp --script deploy     # one runnable only
```

---

## Autonomy control

The `x-autonomy` field in every emitted schema is how you declare what level
of trust agents should have when deciding whether to run a tool.

| Level | What it means for an agent |
|---|---|
| `autonomous` | Run freely — no confirmation needed |
| `confirm` | Stop and confirm with the user before running |
| `supervised` | Run, but hold the output for human review before acting on it |
| `manual` | Do not call this tool — hand off to a human entirely |

This is set in your spec:

```toml
[deploy]
description = "Deploy to production"
autonomy    = "manual"
autonomy-reason = "Irreversible — requires human sign-off"

[compress]
description = "Compress output files"
autonomy    = "autonomous"
```

And surfaces in the emitted schema:

```json
{
  "name": "deploy",
  "description": "Deploy to production",
  "x-autonomy": "manual",
  "x-autonomy-reason": "Irreversible — requires human sign-off",
  "inputSchema": { ... }
}
```

An agent framework that reads `x-autonomy` can enforce this automatically —
blocking `manual` tools, prompting before `confirm` tools, and running
`autonomous` tools freely.

### Per-argument autonomy

Autonomy can also be declared on individual arguments. The most restrictive
level wins — so a `confirm`-level runnable with a `manual`-level arg
is effectively `manual` when that arg is used:

```toml
[pipeline.args]
input   = {type = "path"}
api-key = {type = "str", env = "PIPELINE_API_KEY", autonomy = "manual"}
```

If an agent is about to pass `--api-key`, it should stop — even if the
runnable itself is `confirm`. The runspec Python library calculates the
effective autonomy for you:

```python
args = runspec.parse()
print(args.__autonomy__)   # "manual" if api-key was provided
```

---

## Discovery

`runspec local` finds all installed runspec-aware runnables and emits them
as tool schemas in one step.

```bash
runspec local --format mcp
```

`local` searches the current Python environment for any installed package
that lists `runspec` as a dependency. An agent that runs `runspec local`
sees every runspec-aware package installed in its environment — with no
per-tool configuration. Runnables must be installed (`pip install -e .`
or a full install) to appear.

```
Found 3 installed runnable(s):

  /home/user/project/mypkg/runspec.toml
    deploy       Deploy the application    [confirm]
    process      Process input files       [confirm]
    validate     Validate input data       [autonomous]

Run 'runspec local --format mcp' to emit MCP tool schemas.
```

With `--format mcp`, this becomes a complete tool list ready to hand to
an MCP server or agent framework — no per-tool setup, no skills files to
maintain.

---

## Environment variables for agents

The `env` field lets sensitive arguments be set via environment variables
rather than passed directly on the command line. Combined with
`autonomy = "manual"`, this keeps secrets out of agent reach entirely:

```toml
[deploy.args]
server  = {type = "str",  env = "DEPLOY_SERVER"}
api-key = {type = "str",  env = "DEPLOY_API_KEY", autonomy = "manual"}
region  = {type = "str",  env = "AWS_REGION", default = "us-east-1"}
```

The operator sets the environment variables. The agent calls the runnable
with zero args. The runnable gets the values it needs. The agent never
sees or touches the secrets.

This pattern works in any environment where you can set variables before
the agent runs — CI/CD pipelines, container orchestration, Ansible, Docker
Compose, system services.

```bash
# Agent calls this — no args needed
deploy
```

```bash
# Operator sets these — agent never touches them
export DEPLOY_SERVER=web-01
export DEPLOY_API_KEY=<secret>
```

---

## Checking before running

Before an agent calls a runnable, it can inspect the schema to decide
whether it's allowed to proceed:

```python
import json, subprocess

schemas = json.loads(subprocess.check_output(["runspec", "local", "--format", "mcp"]))

for tool in schemas["tools"]:
    autonomy = tool.get("x-autonomy", "confirm")
    if autonomy == "manual":
        print(f"  {tool['name']}: skip — requires human operator")
    elif autonomy == "confirm":
        print(f"  {tool['name']}: ask user first")
    else:
        print(f"  {tool['name']}: ok to run")
```

---

## Live MCP server

`runspec serve` starts a [Model Context Protocol](https://github.com/modelcontextprotocol/specification)
stdio server that exposes every runnable in your environment as a callable
tool. This is the recommended way to connect any MCP-compatible agent —
Claude Desktop, Cursor, or your own agent loop — to your runnables.

```bash
runspec serve
```

The server reads your runspec config, advertises each runnable as an MCP tool,
and runs the corresponding script when the agent calls it. No separate MCP
server to write or maintain.

### Connecting Claude Desktop

Add an entry to `claude_desktop_config.json` — typically at
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS
or `%APPDATA%\Claude\claude_desktop_config.json` on Windows:

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

The key (`"analytics-pipeline"`) is the display name shown in Claude Desktop.
`cwd` is the directory `serve` searches for your runspec config — set it to
your project root.

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

Each virtual environment is its own MCP server. If you have multiple projects,
add one entry per environment — each exposes only its own runnables.

### What the agent sees

The agent receives tool definitions with full argument schemas, descriptions,
and autonomy levels — everything from your TOML. Calling a tool runs the
script and returns its stdout. On non-zero exit, the tool returns an error
with the exit code, stdout, and stderr intact.

### Agent-aware output

Scripts called via `serve` receive `RUNSPEC_AGENT=1` in their environment.
Read it through `args.__agent__` to switch between human and machine output:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "ok", "deployed_to": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

---

## Practical patterns

### Start a live MCP server

```bash
# Start serving the current project's runnables
runspec serve
```

Wire it into Claude Desktop once — every runnable in your config is
immediately available as a tool.

### Validate before exposing

Run `runspec local` in CI before deploying. It lists installed runnables and
reports missing descriptions, undeclared autonomy levels, and required args
without descriptions — all things that degrade agent behaviour. Exits with
code 1 if errors are found.

```yaml
# .gitlab-ci.yml / GitHub Actions
- name: Validate runspec
  run: runspec local
```

### Emit schemas for inspection

```bash
# Preview exactly what the agent will see
runspec local --format mcp

# Emit for a specific framework
runspec local --format openai
```

---

## What agents see

A well-specified runnable gives an agent everything it needs without any
extra documentation:

| Spec field | Agent use |
|---|---|
| `description` | Decides whether this is the right tool |
| `args[].description` | Knows what value to pass |
| `args[].type` | Passes the right type |
| `args[].options` | Picks from valid choices |
| `args[].required` | Knows what it must provide |
| `args[].default` | Knows what happens if it doesn't provide |
| `args[].env` | Knows there's an env var fallback |
| `x-autonomy` | Decides whether to run or ask first |
| `x-autonomy-reason` | Explains to the user why confirmation is needed |
| `x-output` | Knows whether to display output as text or parse it as JSON |

The more of these you fill in, the more reliably an agent can use your
runnable without human help.

!!! tip
    Run `runspec local` to see exactly which fields are missing. The output
    maps directly to gaps in what agents can infer.