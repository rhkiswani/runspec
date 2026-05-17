# Format Reference

The runspec format is TOML. It is identical across Python, Node, and Go —
only the setup step differs per language.

---

## File Formats

runspec looks for configuration in two places. Use whichever fits your project.

=== "pyproject.toml"

    For Python projects. Runnables live under `[tool.runspec]`.

    ```toml
    [tool.runspec.config]
    autonomy-default = "confirm"

    [tool.runspec.greet]
    description = "Greet someone"
    autonomy    = "autonomous"

    [tool.runspec.greet.args]
    name = {type = "str"}
    loud = {default = false}
    ```

=== "runspec.toml"

    For all other projects, or when you want the interface spec separate
    from your package config. Runnables are top-level sections.

    ```toml
    [config]
    autonomy-default = "confirm"

    [greet]
    description = "Greet someone"
    autonomy    = "autonomous"

    [greet.args]
    name = {type = "str"}
    loud = {default = false}
    ```

**File lookup order:** runspec searches from the calling runnable's directory
and walks up parent directories until it finds a match. This means a single
`runspec.toml` at the root of a monorepo serves all runnables beneath it.

---

## The `[config]` Section

Project-wide defaults. All fields are optional.

| Field | Type | Default | Description |
|---|---|---|---|
| `autonomy-default` | string | `"confirm"` | Autonomy level when not declared on a runnable |
| `lang` | string | — | Preferred language for code generation |
| `version` | string | `"1"` | runspec spec version |

```toml
[config]
autonomy-default = "confirm"
lang             = "python"
version          = "1"
```

---

## Runnable Definition

Everything under `[tool.runspec]` except `[config]` is a runnable.
The name you choose is the command users type.

```toml
[tool.runspec.deploy]
description     = "Deploy to production"       # recommended
autonomy        = "manual"                     # optional
autonomy-reason = "Irreversible operation"     # optional
```

### Autonomy Levels

Declares how much trust AI agents should have when deciding whether to run
this runnable automatically or hand off to a human.

| Level | Meaning |
|---|---|
| `autonomous` | Agent runs freely, no confirmation needed |
| `confirm` | Agent must confirm with the user first |
| `supervised` | Agent runs, human reviews output before it is acted on |
| `manual` | Human only — agent must not invoke this |

If not declared, falls back to `autonomy-default` in `[config]`, then `"confirm"`.

---

## Argument Definition

Arguments live under `[tool.runspec.<name>.args]`.

### Three levels of verbosity

**Bare value** — type and default inferred from the value:

```toml
[greet.args]
verbose = false    # flag, default false
workers = 4        # int, default 4
label   = "main"   # str, default "main"
```

**Inline table** — explicit fields on one line:

```toml
[greet.args]
input-dir = {type = "path"}
quality   = {default = 85, range = [1, 100]}
format    = {options = ["json", "csv"], default = "json"}
```

**Full block** — for args that need prose descriptions or many fields:

```toml
[greet.args.quality]
default     = 85
range       = [1, 100]
description = "Output quality. Values below 60 are rarely useful."
```

### Argument Fields

| Field | Type | Description |
|---|---|---|
| `type` | string | Argument type. Inferred from `default` or `options` if omitted. |
| `default` | any | Default value. Absence implies `required = true`. |
| `required` | bool | Override required inference explicitly. |
| `description` | string | Shown in `--help` and agent tool schemas. |
| `options` | array | Valid choices. Infers `type = "choice"`. |
| `range` | [min, max] | Valid range for numeric types. |
| `multiple` | bool | Accept the flag multiple times, returns a list. |
| `delimiter` | string | Split a single value by this character. |
| `short` | string | Short flag alias, e.g. `"-v"`. |
| `env` | string | Environment variable fallback. |
| `deprecated` | string | Message shown when this arg is used. |
| `autonomy` | string | Per-arg autonomy override. Most restrictive level wins. |
| `ui` | string | Form control hint. Inferred from type if omitted. |
| `meta` | table | Developer-defined pass-through metadata. runspec never interprets this. |

---

## Inference Rules

When fields are omitted, runspec infers them. Rules are applied in this order:

| Condition | Inference |
|---|---|
| `options = [...]` present | `type = "choice"` |
| `default = true` or `false` | `type = "flag"` |
| `default = <integer>` | `type = "int"` |
| `default = <float>` | `type = "float"` |
| `default = <string>` | `type = "str"` |
| No `default`, no `required = false` | `required = true` |
| `type = "path"` with no default | `required = true` |

!!! note
    `options` is checked before `default` — if both are present, `type = "choice"` wins.
    Bool is checked before int — `false` and `true` are flags, not integers.

---

## Types

| Type | Description |
|---|---|
| `str` | Unicode string |
| `int` | Integer |
| `float` | Floating point number |
| `bool` | Boolean (`true` / `false`) |
| `flag` | Boolean switch — presence on the command line means `true` |
| `path` | File system path |
| `choice` | One of a declared set of `options` |

Language packs may register additional types. See the [Python Library](python.md)
docs for `register_type()`.

---

## Value Resolution Order

For every argument, values are resolved in this order:

1. Explicit CLI argument — highest priority
2. Environment variable (if `env` declared)
3. Default from spec
4. Error — if nothing matched and `required = true`

---

## Environment Variable Fallbacks

The `env` field lets an argument read its value from an environment variable
when nothing is passed on the command line. This is the same resolution order
as the table above — env sits between CLI and default.

```toml
[deploy.args]
server  = {type = "str",  env = "DEPLOY_SERVER"}
api-key = {type = "str",  env = "DEPLOY_API_KEY",  autonomy = "manual"}
region  = {type = "str",  env = "AWS_REGION",       default = "us-east-1"}
dry-run = {default = false}
```

### CI/CD pattern

Set variables once at the project level — your pipeline file stays identical
across every project, and each project controls its own behaviour through
environment variables:

=== "GitLab CI"

    ```yaml
    # .gitlab-ci.yml — shared across all projects
    deploy:
      script: deploy --dry-run $DRY_RUN
    ```

    In **Project → Settings → CI/CD → Variables**, set:

    ```
    DEPLOY_SERVER  = web-01
    DEPLOY_API_KEY = <secret>
    AWS_REGION     = eu-west-1
    ```

=== "GitHub Actions"

    ```yaml
    - name: Deploy
      run: deploy
      env:
        DEPLOY_SERVER: web-01
        DEPLOY_API_KEY: ${{ secrets.DEPLOY_API_KEY }}
        AWS_REGION: eu-west-1
    ```

=== "Ansible"

    ```yaml
    - name: Deploy application
      command: deploy
      environment:
        DEPLOY_SERVER: "{{ deploy_server }}"
        DEPLOY_API_KEY: "{{ vault_deploy_api_key }}"
        AWS_REGION: "{{ aws_region }}"
    ```

The runnable itself never changes. Environment variables act as the interface
between the runnable and whatever system is calling it.

### .env files

For local development, a `.env` file alongside your project works the same way.
Most shells and tools (`direnv`, `python-dotenv`, `dotenvx`) load `.env`
automatically — so developers get zero-arg invocation locally with the same
runnable that runs in CI.

```bash
# .env (never commit secrets)
DEPLOY_SERVER=web-01
AWS_REGION=us-east-1
```

!!! tip
    Combine `env` with `autonomy = "manual"` on secrets like API keys.
    The arg is still read from the environment, but agents are blocked from
    setting or passing it directly — the value must come from the operator.

---

## Groups

Groups define relationships between arguments and are validated after
individual arguments pass.

```toml
[tool.runspec.<name>.groups.<group-name>]
exclusive = true
args      = ["format", "raw"]
```

### Group Types

**Exclusive** — at most one arg from the group may be provided:

```toml
[pipeline.groups.output-format]
exclusive = true
args      = ["format", "raw"]
```

**Inclusive** — if any arg is provided, all must be:

```toml
[pipeline.groups.auth]
inclusive = true
args      = ["api-key", "api-endpoint"]
```

**At least one** — one or more from the group must be provided:

```toml
[pipeline.groups.input]
at-least-one = true
args         = ["input-file", "input-dir", "input-glob"]
```

**Exactly one** — strictly one must be provided:

```toml
[pipeline.groups.mode]
exactly-one = true
args        = ["fast", "balanced", "quality"]
```

**Conditional** — if a trigger arg is provided, other args become required:

```toml
[pipeline.groups.upload]
if       = "upload"
requires = ["bucket", "region"]
```

---

## Subcommands

Subcommands live under `[tool.runspec.<name>.commands.<subcommand>]`.
Each subcommand has its own `args`, `groups`, `autonomy`, and `description`.

```toml
[pipeline]
description = "Process and validate data pipeline files"
autonomy    = "confirm"

[pipeline.commands.run]
description     = "Run the pipeline"
autonomy        = "confirm"
autonomy-reason = "Writes output files and may call external APIs"

[pipeline.commands.run.args]
input   = {type = "path"}
dry-run = {default = false}

[pipeline.commands.validate]
description = "Validate without running"
autonomy    = "autonomous"

[pipeline.commands.validate.args]
input  = {type = "path"}
strict = {default = false}
```

---

## Developer Metadata

The `meta` field lets you attach arbitrary structured data to any argument.
runspec passes it through untouched — it never validates or interprets the contents.

A common use case is associating choice values with lookup data you need at runtime:

```toml
[deploy.args.server]
options = ["web-01", "web-02", "db-01"]

[deploy.args.server.meta]
web-01 = {datacenter = "us-east", tier = "web"}
web-02 = {datacenter = "us-west", tier = "web"}
db-01  = {datacenter = "eu-central", tier = "db"}
```

In your code:

```python
args = parse()
info = args.server.meta[args.server.value]
print(info["datacenter"])   # "us-east"
```

This keeps lookup data in the same place as the argument definition — no
separate config files, no hardcoded mappings in code.

---

## Complete Example

A realistic runnable using most features:

```toml
[config]
autonomy-default = "confirm"

[pipeline]
description = "Process and validate data pipeline files"
autonomy    = "confirm"

[pipeline.commands.run]
description     = "Run the pipeline against one or more input files"
autonomy        = "confirm"
autonomy-reason = "Writes output files and may call external APIs"

[pipeline.commands.run.args]
input      = {type = "path"}
format     = {options = ["json", "csv", "parquet"], default = "json"}
workers    = {default = 4, range = [1, 32]}
batch-size = {default = 1000, range = [1, 100000]}
dry-run    = {default = false}
verbose    = {default = false, short = "-v"}
api-key    = {type = "str", env = "PIPELINE_API_KEY", autonomy = "manual"}
tag        = {type = "str", multiple = true}
fields     = {type = "str", multiple = true, delimiter = ","}

[pipeline.commands.run.groups.input-format]
exclusive = true
args      = ["format", "raw"]

[pipeline.commands.run.groups.api-auth]
inclusive = true
args      = ["api-key", "api-endpoint"]

[pipeline.commands.validate]
description = "Validate pipeline config and input files without running"
autonomy    = "autonomous"

[pipeline.commands.validate.args]
input  = {type = "path"}
schema = {type = "path"}
strict = {default = false}
format = {options = ["json", "csv", "parquet"], default = "json"}
```
