# runspec Format Specification

Version: 1  
Status: Draft

This document is the canonical definition of the runspec format.
All language pack implementations are tested against this specification.

---

## Overview

A runspec defines the interface of anything runnable — a script, application,
or MCP tool. It lives in `runspec.toml` inside the package directory, alongside
the code it describes.

```
mypkg/
  runspec.toml    ← lives here, not at the project root
```

This location means build backends include it automatically as package data,
and `importlib.metadata` can locate it after install — no extra configuration needed.

---

## File Lookup Order

Implementations must use the following lookup strategy depending on context:

**Installed packages:**
1. Locate via `importlib.metadata` — find `runspec.toml` in installed package files
2. Any package that declares `runspec` as a dependency is a candidate

**Local development (`runspec serve --dev`):**
1. Walk up from cwd until `.git/` is found — that is the project root
2. Walk down one level from the project root, collect all `runspec.toml` files found
3. Aggregate all runnables from all found configs into a unified tool list
4. If no `.git/` found, use cwd as the project root

**Single-package commands (`runspec run`, `check`, `emit`):**
1. Walk up from cwd, return the first `runspec.toml` found

---

## Top-Level Structure

```toml
[config]     # optional project-wide defaults
[<name>]     # one section per runnable
```

---

## The `[config]` Section

Project-wide defaults. All fields are optional.

| Field | Type | Default | Description |
|---|---|---|---|
| `autonomy-default` | string | `"confirm"` | Autonomy when unspecified on a script |
| `lang` | string | — | Preferred language for `runspec generate` |
| `version` | string | `"1"` | runspec spec version |
| `registry` | string | — | URL of the runspec-registry instance to heartbeat to |
| `name` | string | — | Instance name reported to the registry. Defaults to the venv directory name |
| `heartbeat` | int | `30` | Heartbeat interval in seconds |
| `heartbeat_data` | array | `[]` | Extra data to include in heartbeats. Supports `"system"` (pid, uptime) |

---

## Runnable Definition

Runnables are defined at the top level of `runspec.toml`. The reserved name
`config` is excluded — everything else is a runnable.

```toml
[<name>]
description     = "Human and agent readable description"  # recommended
autonomy        = "confirm"                               # optional
autonomy-reason = "Why this level was chosen"             # optional
output          = "text"                                  # optional
hosts           = ["host1", "host2"]                      # optional, see Remote Execution
run_as          = "username"                              # optional, see Remote Execution
become_method   = "sudo"                                  # optional, default "sudo"
become_flags    = "-H"                                    # optional
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

## Remote Execution

These fields control how `runspec exec` and compatible SSH clients run the tool on a remote host.

### `hosts`

Restricts a runnable to specific machines. `runspec serve` checks this against the
current hostname at startup — tools not matching are excluded from the MCP tool list
and not registered with the registry. Absent means available everywhere it is installed.

```toml
[parse-app-logs]
hosts = ["logserver-01", "logserver-02"]
```

### `run_as`

The user to run the command as on the remote host. Four forms are supported.

**1. Simple string** — same user on all hosts:
```toml
run_as = "oracle"
```

**2. Environment variable** — resolved by `runspec serve` at startup. Set per host
group via Ansible `group_vars` or equivalent config management:
```toml
run_as = "$ORACLE_RUN_AS"
```

**3. Per-host exact match**:
```toml
run_as.default = "oracle"
run_as.hosts."special-box-01" = "dba"
run_as.hosts."special-box-02" = ""    # no privilege escalation on this host
```

**4. Pattern matching** — Python `re.fullmatch()`, evaluated top to bottom,
first match wins (TOML insertion order preserved):
```toml
run_as.default = "oracle"
run_as.patterns."[lg]pexp[0-9]*" = "orasvc"
run_as.patterns."prod[0-9]*"     = "produser"
```

Forms 3 and 4 may be combined. Resolution order:

1. Exact match in `hosts`
2. First matching pattern in `patterns`
3. `default`
4. No privilege escalation

An empty string (`""`) explicitly means no privilege escalation for that host or pattern.

Invalid regex patterns cause `runspec serve` to exit with a clear error at startup.
`runspec check` also validates all patterns at check time.

`runspec serve` resolves `run_as` to a plain string before sending it to the registry.
The registry stores only the resolved value per instance — the table form never leaves
the local machine.

### `become_method`

The privilege escalation method. Default: `"sudo"`.

| Value | Command constructed |
|---|---|
| `sudo` | `sudo {flags} -u {user} {command} {args}` |
| `su` | `su {flags} -c "{command} {args}" {user}` |
| `pbrun` | `pbrun {flags} -u {user} {command} {args}` |
| `dzdo` | `dzdo {flags} -u {user} {command} {args}` |

Note: `su` uses a distinct syntax — the command and args are wrapped in a `-c` string.

### `become_flags`

Optional flags passed to the become method. Example: `"-H"` resets HOME to the target
user's home directory under `sudo`.

### Command building

Executing clients build the final remote command as follows. All interpolated values
must be shell-escaped (Python: `shlex.quote()`).

| `run_as` | `env` args | Command constructed |
|---|---|---|
| absent | absent | `{command} {args}` |
| absent | present | `KEY=val … {command} {args}` |
| present | absent | `{become_method} {become_flags} -u {user} {command} {args}` |
| present | present | `{become_method} {become_flags} -u {user} env KEY=val … {command} {args}` |

When both `run_as` and `env` fields are present, `env(1)` is used after privilege
escalation so that variables are set in the target user's process context. This avoids
requiring `sudo -E` or `env_keep` in sudoers, and requires no changes to `sshd_config`
on target hosts.

`su` uses its own syntax and does not follow the `-u` pattern — see the table above.

---

## Argument Definition

Arguments live under `[<name>.args]`.

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
[<name>.args.quality]
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

## Runtime Environment Variables

When `runspec serve` executes a tool, or when `runspec run` runs a tool locally,
all resolved argument values are injected as environment variables before the
process starts. This makes any runnable language — bash, Python, Node, or anything
else — work without a language-specific library.

### Naming convention

```
RUNSPEC_<ARG_NAME_UPPERCASED>
```

Hyphens and underscores in the arg name both become underscores. Examples:

| Arg name | Environment variable |
|---|---|
| `env` | `RUNSPEC_ENV` |
| `dry-run` | `RUNSPEC_DRY_RUN` |
| `input_file` | `RUNSPEC_INPUT_FILE` |
| `max-retries` | `RUNSPEC_MAX_RETRIES` |

### Serialisation

| Arg type | Value | Env var |
|---|---|---|
| `flag` | not passed (default false) | `0` |
| `flag` | passed | `1` |
| `bool` | `false` | `0` |
| `bool` | `true` | `1` |
| `str`, `int`, `float`, `path`, `choice` | any value | natural string form |
| `multiple = true` | list of values | newline-delimited string |

Defaults from the spec are always set, even when the caller did not pass the arg
explicitly. A required arg that was not provided is not set (this is a validation
error — the tool should never be reached).

### Reserved variables

`RUNSPEC_AGENT=1` is always set. Scripts can use it to switch between
human-readable and machine-readable output.

### Example

```toml
[backup-logs]
description = "Back up application logs"
autonomy    = "confirm"

[backup-logs.args]
env     = {type = "choice", options = ["prod", "staging"]}
days    = {type = "int", default = 7}
dry-run = {type = "flag", default = false}
```

```bash
#!/bin/bash
# env vars are already set and validated — no parsing needed
if [ "$RUNSPEC_DRY_RUN" = "1" ]; then
    echo "Would back up $RUNSPEC_DAYS days of $RUNSPEC_ENV logs"
    exit 0
fi
aws s3 sync "/var/log/app/$RUNSPEC_ENV" "s3://logs-$RUNSPEC_ENV" \
    --delete --include "*.log"
```

---

## Groups

Groups define relationships between arguments.
They live under `[<name>.groups.<group-name>]`.

### Group Types

**Mutually exclusive** — at most one arg from the group may be provided:
```toml
[<name>.groups.output]
exclusive = true
args      = ["format", "raw"]
```

**Mutually inclusive** — if any arg is provided, all must be:
```toml
[<name>.groups.auth]
inclusive = true
args      = ["username", "password"]
```

**At least one** — one or more must be provided:
```toml
[<name>.groups.input]
at-least-one = true
args         = ["input-file", "input-dir", "input-glob"]
```

**Exactly one** — strictly one must be provided:
```toml
[<name>.groups.mode]
exactly-one = true
args        = ["fast", "balanced", "quality"]
```

**Conditional** — if one arg is provided, others become required:
```toml
[<name>.groups.upload]
if       = "upload"
requires = ["bucket", "region"]
```

### Escalation Rule

The most restrictive autonomy level wins across all provided args.
An agent can never escalate beyond what the spec allows.

---

## Subcommands

Subcommands live under `[<name>.commands.<subcommand>]`.
Each subcommand has its own `args`, `groups`, `autonomy`, and `description`.

```toml
[pipeline.commands.run]
description = "Run the pipeline"
autonomy    = "confirm"

[pipeline.commands.run.args]
input = {type = "path"}

[pipeline.commands.validate]
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

## Registry Integration

`runspec serve` can register with a `runspec-registry` instance to make tools
discoverable across a fleet. The registry is a read-only catalog — it stores
tool specs and host information but cannot execute anything.

### What serve registers

On connect, `runspec serve` sends:

- Instance ID (UUID, generated at startup)
- Hostname of the current machine
- Instance name and version
- Per tool: name, description, full command path, resolved `run_as`, `become_method`,
  `become_flags`, and the full input schema

Tools excluded by the `hosts` field are not sent.

### Heartbeat

Sent every `heartbeat` seconds. If the registry responds `"refresh"`, serve resends
the full tool list. On SIGTERM, serve sends a deregister message before exiting.

### CLI flags

| Flag | Description |
|---|---|
| `--registry <url>` | Registry URL. Overrides `[config] registry`. |
| `--name <name>` | Instance name. Overrides `[config] name`. |
| `--registry-key <key>` | API key for write endpoint authentication. |
| `--registry-cert <path>` | Custom CA certificate bundle for HTTPS verification. |

---

## Compliance

All implementations are tested against the fixtures in
`tests/integration/fixtures/`. A conforming implementation must produce
output that matches the canonical JSON in `tests/integration/compliance/`
for every fixture.
