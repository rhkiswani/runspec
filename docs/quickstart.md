# Quick Start

!!! note "Python guide"
    This guide uses Python. Node and Go quickstarts will be added when those
    implementations are available.

Get from zero to a working runnable in five steps.

---

## 1. Install

```bash
pip install runspec
```

---

## 2. Choose your config format

runspec supports two config formats. Use whichever fits your project.

=== "pyproject.toml"

    Best for Python projects — everything lives in one file.

    ```toml
    [project]
    name = "hello"
    version = "0.1.0"
    dependencies = ["runspec"]

    [project.scripts]
    greet = "hello.greet:main"  # wires the command to your function

    [tool.runspec.greet]
    description = "Greet someone from the command line"
    autonomy    = "autonomous"

    [tool.runspec.greet.args]
    name  = {type = "str"}
    loud  = {default = false}
    times = {default = 1}
    ```

=== "runspec.toml"

    Best for non-Python projects, monorepos, or when you want the interface
    spec separate from your package config.

    ```toml
    [greet]
    description = "Greet someone from the command line"
    autonomy    = "autonomous"

    [greet.args]
    name  = {type = "str"}
    loud  = {default = false}
    times = {default = 1}
    ```

    The TOML format is identical across Python, Node, and Go — only the
    setup step differs per language.

---

## 3. Write your runnable

Create `hello/greet.py`:

```python
from runspec import parse

def main():
    args = parse()
    message = f"Hello, {args.name}!"
    if args.loud:
        message = message.upper()
    for _ in range(args.times):
        print(message)
```

`parse()` finds your config automatically — no path required. It starts in
the directory your runnable lives in and walks up until it finds a
`pyproject.toml` with a `[tool.runspec]` section, or a `runspec.toml`.
This means it works from anywhere in your project without configuration.

---

## 4. Install and run

```bash
pip install -e .
greet --name Alice --loud --times 3
```

Expected output:

```
HELLO, ALICE!
HELLO, ALICE!
HELLO, ALICE!
```

**Explore your setup with the runspec CLI:**

```bash
runspec check        # validates your config and reports any issues
runspec discover     # finds all runspec-aware runnables in your environment
```

---

## 5. What you get for free

**Missing required argument:**

```bash
greet
```

```
✗  Missing required argument: --name
   'name' is required and has no default.
   Usage: greet --name <str>
```

**Wrong type:**

```bash
greet --name Alice --times abc
```

```
✗  Invalid value for --times: 'abc' is not a valid int
```

No argument parsing code. No error handling. Just your runnable and a TOML file.

**For humans — built-in help, for free:**

```bash
greet --help
```

```
Usage: greet --name <str> [--loud] [--times <int>]

Greet someone from the command line

Arguments:
  --name                 (str, required)
  --loud                 (flag, default: False)
  --times                (int, default: 1)

Autonomy: autonomous

  -h, --help    Show this message and exit
```

No help text written. No argument parser configured. runspec generates this
from your TOML definition automatically.

---

## 6. Make it available to AI agents

Every runnable declares an `autonomy` level — how much trust an AI agent
should have when deciding whether to run it automatically or ask a human first.

```toml
[tool.runspec.greet]
description = "Greet someone from the command line"
autonomy    = "autonomous"       # safe to run without asking

[tool.runspec.deploy]
description     = "Deploy to production"
autonomy        = "manual"
autonomy-reason = "Irreversible — requires human approval"

[tool.runspec.deploy.args]
environment = {options = ["staging", "production"]}
dry-run     = {default = false}
```

The four autonomy levels are:

| Level | Meaning |
|---|---|
| `autonomous` | Agent can run freely without asking |
| `confirm` | Agent should confirm with the user first |
| `supervised` | Human watches and can intervene |
| `manual` | Human must run this — agent must not |

Emit your runnables as an AI agent tool schema with a single command:

```bash
runspec emit --format mcp
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
          "name": { "type": "string" },
          "loud": { "type": "boolean", "default": false },
          "times": { "type": "integer", "default": 1 }
        },
        "required": ["name"]
      }
    },
    {
      "name": "deploy",
      "description": "Deploy to production",
      "x-autonomy": "manual",
      "x-autonomy-reason": "Irreversible — requires human approval",
      "inputSchema": {
        "type": "object",
        "properties": {
          "environment": { "type": "string", "enum": ["staging", "production"] },
          "dry-run": { "type": "boolean", "default": false }
        },
        "required": ["environment"]
      }
    }
  ]
}
```

The `x-autonomy` field travels with the schema — your agent framework knows
exactly which runnables it can call freely and which ones need a human in the loop.

---

## 7. The bigger picture — a composable ecosystem

Every runspec-aware package installed in your environment is automatically
discoverable. No integration code. No hand-written tool definitions.

```bash
runspec discover          # find every runspec-aware runnable installed here
runspec emit --format mcp # emit all of them as agent-ready tool schemas
```

Install a new runspec-aware package and it appears in `runspec discover`
automatically. Your agent's toolbox grows with every `pip install` — zero
glue code required.

This means:

- **Developers** define their interface once in TOML — they get a CLI,
  `--help`, validation, and agent schemas all from the same source
- **Agents** run `runspec discover` to find what's available, then
  `runspec emit` to get the schemas — no `skills.md`, no manual registration
- **Users** install packages and everything just works

---

## Next steps

- [Format Reference](format.md) — every field, every option
- [Python Library](python.md) — `parse()`, `load_spec()`, `RunSpec`, `Arg`
- [CLI](cli.md) — `runspec check`, `runspec discover`, `runspec emit`
- [Agent Integration](agents.md) — wiring runspec into your agent framework
