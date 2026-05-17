# runspec Format Specification

Version: 1  
Status: Draft

This document is the canonical definition of the runspec format.
All language pack implementations are tested against this specification.

---

## Overview

A runspec defines the interface of anything runnable — a script, application,
or MCP tool. It lives in one of two places:

1. `pyproject.toml` under `[tool.runspec]` (Python projects)
2. `runspec.toml` at the project root (all other projects)

The format is identical in both cases. The outer wrapper differs only in
how TOML nesting works.

---

## File Lookup Order

Implementations must search in this order, using the first match found:

1. `pyproject.toml` → `[tool.runspec]` section, cross-referenced with `[project.scripts]`
2. `runspec.toml` in the current directory
3. Walk up parent directories repeating 1 and 2
4. For installed packages: `runspec.toml` shipped as package data

---

## Top-Level Structure

```toml
[tool.runspec.config]         # optional project-wide defaults
[tool.runspec.<name>] # one section per runnable
```

In a standalone `runspec.toml`, omit the `tool.runspec` prefix:

```toml
[config]
[<name>]
```

---

## The `[config]` Section

Project-wide defaults. All fields are optional.

| Field | Type | Default | Description |
|---|---|---|---|
| `autonomy-default` | string | `"confirm"` | Autonomy when unspecified on a script |
| `lang` | string | — | Preferred language for `runspec generate` |
| `version` | string | `"1"` | runspec spec version |

---

## Runnable Definition

Runnables are defined directly under `[tool.runspec]` in `pyproject.toml`,
or at the top level of `runspec.toml`. The reserved name `config` is excluded.

```toml
[tool.runspec.<name>]
description     = "Human and agent readable description"  # recommended
autonomy        = "confirm"                               # optional
autonomy-reason = "Why this level was chosen"             # optional
output          = "text"                                  # optional
```

### `output`

Declares what the runnable writes to stdout. Used by agent frameworks and the
`runspec serve` layer to interpret the tool's response.

| Value | Meaning |
|---|---|
| `text` | Human-readable output (default) |
| `json` | Structured JSON — agent can parse and act on the response |
| `html` | HTML output (reserved for future UI use) |

Default when unspecified: `"text"`.

### Reserved Names

`config` is the only reserved name. A runnable cannot be named `config`.
`runspec check` will report an error if this name is used.

### Autonomy Levels

| Level | Meaning |
|---|---|
| `autonomous` | Agent runs freely, no confirmation needed |
| `confirm` | Agent must present intent and await human approval |
| `supervised` | Agent runs, human reviews output before it is acted on |
| `manual` | Agent cannot invoke — human only |

Default when unspecified: value of `[config] autonomy-default`, else `"confirm"`.

---

## Argument Definition

Arguments live under `[tool.runspec.<name>.args]`.

### Three levels of verbosity

**Bare value** — type and default inferred from the value:
```toml
verbose = false    # flag, default false
workers = 4        # int, default 4
```

**Inline table** — explicit fields on one line:
```toml
input-dir = {type = "path"}
quality   = {default = 85, range = [1, 100]}
format    = {options = ["json", "csv"], default = "json"}
```

**Full block** — for args needing prose descriptions:
```toml
[tool.runspec.<name>.args.quality]
default     = 85
range       = [1, 100]
description = "Controls output quality. Values below 60 rarely useful."
```

### Argument Fields

| Field | Type | Description |
|---|---|---|
| `type` | string | See Types section. Inferred if omitted. |
| `default` | any | Default value. Absence implies `required = true`. |
| `required` | bool | Explicit required flag. Inferred from missing default. |
| `description` | string | Human and agent readable. Doubles as form label. |
| `options` | array | Valid choices. Infers `type = "choice"`. |
| `range` | [min, max] | Valid range for numeric types. |
| `multiple` | bool | Accept multiple values (repeated flag style). |
| `delimiter` | string | Split a single value by this delimiter. |
| `short` | string | Short flag alias e.g. `"-v"`. |
| `env` | string | Environment variable fallback. |
| `deprecated` | string | Deprecation message shown on use. |
| `autonomy` | string | Per-arg autonomy override. Escalates if more restrictive. |
| `ui` | string | Form control hint. Inferred from type if omitted. |
| `meta` | table | Developer-defined metadata. Pass-through — runspec never interprets the contents. |

---

## Inference Rules

Implementations must apply these rules in order:

| Condition | Inference |
|---|---|
| `default = <integer>` | `type = "int"` |
| `default = <float>` | `type = "float"` |
| `default = <string>` | `type = "str"` |
| `default = true` or `default = false` | `type = "flag"` |
| `options = [...]` present | `type = "choice"` |
| No `default` and no explicit `required = false` | `required = true` |
| `type = "path"` with no default | `required = true` |

---

## Types

| runspec type | Description |
|---|---|
| `str` | Unicode string |
| `int` | Integer |
| `float` | Floating point number |
| `bool` | Boolean (true/false) |
| `flag` | Boolean switch — presence means true |
| `path` | File system path |
| `choice` | One of a declared set of options |

Language packs may register additional types via the type registry.

---

## Value Resolution Order

For every argument, implementations must resolve the value in this order:

1. Explicit CLI argument — highest priority
2. Environment variable (if `env` declared)
3. Config file value (future)
4. Default from spec
5. Error: required — if nothing above matched and `required = true`

---

## Groups

Groups define relationships between arguments.
They live under `[tool.runspec.<name>.groups.<group-name>]`.

### Group Types

**Mutually exclusive** — at most one arg from the group may be provided:
```toml
[tool.runspec.<name>.groups.output]
exclusive = true
args      = ["format", "raw"]
```

**Mutually inclusive** — if any arg is provided, all must be:
```toml
[tool.runspec.<name>.groups.auth]
inclusive = true
args      = ["username", "password"]
```

**At least one** — one or more must be provided:
```toml
[tool.runspec.<name>.groups.input]
at-least-one = true
args         = ["input-file", "input-dir", "input-glob"]
```

**Exactly one** — strictly one must be provided:
```toml
[tool.runspec.<name>.groups.mode]
exactly-one = true
args        = ["fast", "balanced", "quality"]
```

**Conditional** — if one arg is provided, others become required:
```toml
[tool.runspec.<name>.groups.upload]
if       = "upload"
requires = ["bucket", "region"]
```

### Escalation Rule

The most restrictive autonomy level wins across all provided args.
An agent can never escalate beyond what the spec allows.

---

## Subcommands

Subcommands live under `[tool.runspec.<name>.commands.<subcommand>]`.
Each subcommand has its own `args`, `groups`, `autonomy`, and `description`.

```toml
[tool.runspec.pipeline.commands.run]
description = "Run the pipeline"
autonomy    = "confirm"

[tool.runspec.pipeline.commands.run.args]
input = {type = "path"}

[tool.runspec.pipeline.commands.validate]
description = "Validate without running"
autonomy    = "autonomous"
```

---

## Form Control Inference

When `ui` is not declared, implementations should infer the form control:

| Type / Property | Default control |
|---|---|
| `str` | Text input |
| `int` or `float` | Number input |
| `path` | File/directory picker |
| `bool` or `flag` | Checkbox |
| `options` ≤ 4 items | Radio group |
| `options` > 4 items | Dropdown |
| `range` present | Slider |
| `multiple = true` | Multi-select |

---

## Emitted Schema Fields

When emitting to agent formats, implementations must include:

- `name` — runnable name
- `description` — runnable description
- `x-autonomy` — autonomy level
- `x-autonomy-reason` — reason if provided
- `x-output` — output type (`"text"` if not declared)
- `inputSchema` — JSON Schema object of all arguments

---

## Compliance

All implementations are tested against the fixtures in
`tests/integration/fixtures/`. A conforming implementation must produce
output that matches the canonical JSON in `tests/integration/compliance/`
for every fixture.
