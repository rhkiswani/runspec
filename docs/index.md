# runspec

**A TOML-based interface specification for anything runnable.**

Define your runnable's interface once in TOML. Get a CLI, validation,
`--help`, and agent-ready schemas — all from the same source, with no extra code.

## Install

```bash
pip install runspec
```

## Define your interface

!!! note "Python examples"
    The examples below use Python. Node and Go examples are on the way.

```toml
[project.scripts]
greet = "hello.greet:main"   # Python-specific — see Node/Go docs for equivalent

[tool.runspec.greet]         # runspec picks up the same name
description = "Greet someone from the command line"
autonomy    = "autonomous"

[tool.runspec.greet.args]
name  = {type = "str"}
loud  = {default = false}
times = {default = 1}
```

The name `greet` in `[project.scripts]` is what you type on the command line.
The matching `[tool.runspec.greet]` section is where you define its interface.
The `runspec.toml` format is identical across all languages.

## Use it in your runnable

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

That's it. runspec handles the rest.

## What you get

- **Type coercion** — arguments arrive as native Python types, no casting needed
- **Validation** — missing required args and bad values produce clear, human-friendly errors
- **Inference** — types and required flags are inferred from defaults where possible
- **Built-in `--help`** — usage and argument descriptions generated automatically, no code required
- **Autonomy control** — declare how much trust AI agents should have when running each runnable, from `autonomous` to `manual`
- **Automatic discovery** — any runspec-aware package installed in your environment is instantly findable with `runspec discover`
- **Agent-ready schemas** — emit all your runnables as tool schemas for AI agents with a single command
- **Self-describing results** — parsed args carry their full spec metadata, enabling code generation, logging, and generic tooling without re-reading TOML
- **Config validation** — `runspec check` catches problems in your TOML before your users do
- **Language-agnostic** — the spec is TOML, implementations exist for multiple languages

## For developers

Define your interface in TOML and your users get a fully documented, validated
CLI with no argument parsing code written.

## For AI agents

Once an agent knows to run `runspec discover`, every runspec-aware runnable
installed in the environment is available — no registration, no hand-written
tool definitions.

```bash
runspec discover          # find every runspec-aware runnable in this environment
runspec emit --format mcp # emit all of them as agent-ready tool schemas
```

Every `pip install` of a runspec-aware package is a new capability.
No `skills.md`. No glue code. Just TOML that the developer was going to write anyway.
