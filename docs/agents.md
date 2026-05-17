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

`runspec emit` converts your spec into JSON Schema tool definitions ready
for any agent framework.

```bash
runspec emit
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
runspec emit                          # MCP (default)
runspec emit --format openai          # OpenAI tool calling
runspec emit --format anthropic       # Anthropic tool use
runspec emit --script deploy          # one runnable only
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

`runspec discover` finds every runspec-aware runnable in the current
environment — not just the local project.

```bash
runspec discover --format mcp
```

This is the agent startup pattern: one command, all tools, no per-tool
configuration. An agent that runs this at startup automatically sees every
runspec-aware package installed in its Python environment.

```
Found 4 runspec-aware runnable(s):

  /home/user/project/pyproject.toml
    • deploy
    • process
    • validate

  /home/user/.venv/lib/python3.12/site-packages/datatool/pyproject.toml
    • convert
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

schemas = json.loads(subprocess.check_output(["runspec", "emit", "--format", "mcp"]))

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

## Practical patterns

### Give an agent a tool list

```bash
# Write once, use anywhere
runspec emit --format mcp > tools.json

# Or pipe directly
runspec emit | your-mcp-server --tools-stdin
```

### Agent startup discovery

```bash
# Everything in this environment, one command
runspec discover --format mcp | your-mcp-server --tools-stdin
```

### Validate before exposing

Run `runspec check` in CI before deploying. It catches missing descriptions,
undeclared autonomy levels, and required args without descriptions — all
things that degrade agent behaviour.

```yaml
# .gitlab-ci.yml / GitHub Actions
- name: Validate runspec
  run: runspec check
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

The more of these you fill in, the more reliably an agent can use your
runnable without human help.

!!! tip
    Run `runspec check` to see exactly which fields are missing. The check
    output maps directly to gaps in what agents can infer.