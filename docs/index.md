# runspec

**A TOML-based interface specification for anything runnable.**

Define your runnable's interface once in `pyproject.toml` or `runspec.toml`.
Get validation, type coercion, and rich error messages for free.
Make any runnable available to AI agents — with a single command.

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
- **Agent-ready** — emit your runnable's interface as a tool schema for AI agents
- **Language-agnostic** — the spec is TOML, implementations exist for multiple languages
