# Python Library

The Python library is the reference implementation. Install it, call `parse()`,
and you get a fully validated, type-coerced `RunSpec` object back.

---

## Installation

```bash
pip install runspec
```

**Python 3.10+.** Zero runtime dependencies on Python 3.11+. On 3.10, `tomli`
is installed automatically as the only dependency.

---

## parse()

```python
import runspec

args = runspec.parse()
```

That's the whole call. runspec finds your config, resolves the runnable name,
parses `sys.argv`, validates, coerces, and returns a `RunSpec`.

### Signature

```python
def parse(
    script_name: str | None = None,
    argv: list[str] | None = None,
) -> RunSpec
```

| Parameter | Description |
|---|---|
| `script_name` | Override the runnable name. Inferred from `sys.argv[0]` if omitted. |
| `argv` | Override `sys.argv`. Uses `sys.argv[1:]` if omitted. Useful for testing. |

### What it does

1. Walks up from the current directory to find `runspec.toml`
2. Infers the runnable name from `sys.argv[0]`
3. Applies inference rules to fill in `type` and `required`
4. Resolves any subcommand from `argv`
5. Intercepts `--help` / `-h` and prints usage, then exits
6. Parses `argv` into raw values
7. Applies environment variable fallbacks
8. Applies spec defaults
9. Validates individual args, then group constraints
10. Coerces values to native Python types
11. Returns a `RunSpec`

### Errors

| Exception | When |
|---|---|
| `FileNotFoundError` | No config file found in the directory tree |
| `RunSpecError` | Runnable not found in config |
| `MissingRequiredArg` | A required arg was not provided |
| `InvalidChoice` | Value not in declared `options` |
| `OutOfRange` | Numeric value outside declared `range` |
| `UnknownArg` | An arg was passed that isn't in the spec |
| `GroupViolation` | A group constraint was violated |

All errors inherit from `RunSpecError` so you can catch the base class if needed.
Error messages are human-first — they include what was expected, what was received,
and a fuzzy suggestion where possible.

### Testing

Pass `argv` directly to test your runnable without touching `sys.argv`:

```python
def test_greet_loud():
    args = runspec.parse(argv=["--name", "Alice", "--loud"])
    assert args.name == "Alice"
    assert args.loud is True
```

---

## RunSpec

`parse()` returns a `RunSpec` — an argument namespace with full spec metadata.

### Accessing arguments

Hyphens in arg names become underscores. Access them as attributes:

```python
args = runspec.parse()

print(args.name)          # str value
print(args.workers)       # int value
print(args.input_dir)     # pathlib.Path value
print(args.format)        # str, one of declared options
```

### Metadata attributes

`RunSpec` carries context about the invocation. These use dunder names to avoid
collisions with your arg names:

| Attribute | Type | Description |
|---|---|---|
| `__script__` | `str` | Name of the runnable (e.g. `"deploy"`) |
| `__source__` | `Path` | Path to the config file that was loaded |
| `__command__` | `str \| None` | Active subcommand, if any |
| `__autonomy__` | `str` | Effective autonomy level for this invocation |
| `__agent__` | `bool` | `True` when called via `runspec serve` (agent context) |
| `__spec__` | `dict` | Raw spec dict — args, groups, description, etc. |
| `__groups__` | `list[Group]` | Validated group definitions |

```python
args = runspec.parse()

print(args.__script__)    # "deploy"
print(args.__command__)   # "run"  (if a subcommand was matched)
print(args.__autonomy__)  # "confirm"
print(args.__agent__)     # True when called by an agent via runspec serve
print(args.__source__)    # PosixPath('/home/user/project/mypkg/runspec.toml')
```

`__autonomy__` reflects the most restrictive level across the runnable, its args,
and any per-arg overrides. Use it to gate behaviour in agent workflows:

```python
args = runspec.parse()

if args.__autonomy__ == "manual":
    raise SystemExit("This runnable requires human operation.")
```

`__agent__` is `True` when the runnable is called via `runspec serve` — set by
the `RUNSPEC_AGENT=1` environment variable that the serve layer injects. Use it
to switch output format for agent consumers:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "deployed", "env": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

---

## Arg

Every argument is an `Arg` — a value plus its full spec metadata. You rarely
need to think about this: `Arg` is transparent and behaves as its native type
in expressions.

### Transparent value access

`Arg` implements the Python data model so it works without unwrapping:

```python
# Arithmetic
total = args.batch_size * args.workers    # int * int
scaled = args.quality / 100              # int / int → float
items = args.workers + 2

# Boolean
if args.dry_run:                         # flag arg
    print("Dry run — no writes")

# String
print(f"Format: {args.format!r}")        # uses __repr__
print(f"Quality: {args.quality:03d}")    # uses __format__

# Iteration (multiple=true args return a list)
for tag in args.tag:
    print(tag)

# Range and indexing
for i in range(args.workers):            # uses __index__
    ...

# Path methods (path args are pathlib.Path)
for file in args.input_dir.glob("*.csv"):
    ...
if args.output.is_dir():
    ...
```

### Arg fields

Every `Arg` carries its full spec:

| Field | Type | Description |
|---|---|---|
| `value` | `Any` | Resolved, coerced value |
| `name` | `str` | Arg name as declared in spec |
| `type` | `str` | Type name (`"str"`, `"int"`, `"path"`, etc.) |
| `required` | `bool` | Whether the arg is required |
| `default` | `Any` | Default value from spec |
| `description` | `str \| None` | Description from spec |
| `options` | `list \| None` | Valid choices for `choice` type |
| `range` | `tuple \| None` | `(min, max)` for numeric types |
| `multiple` | `bool` | Whether the arg accepts multiple values |
| `delimiter` | `str \| None` | Split character for delimiter-separated values |
| `short` | `str \| None` | Short flag alias (e.g. `"-v"`) |
| `env` | `str \| None` | Environment variable name |
| `deprecated` | `str \| None` | Deprecation message |
| `autonomy` | `str \| None` | Per-arg autonomy override |
| `ui` | `str \| None` | Form control hint |
| `meta` | `dict \| None` | Developer-defined pass-through metadata |
| `source` | `str` | Where the value came from: `"cli"`, `"env"`, `"default"` |

Access any field directly:

```python
print(args.format.options)      # ['json', 'csv', 'parquet']
print(args.quality.range)       # (1, 100)
print(args.api_key.env)         # 'PIPELINE_API_KEY'
print(args.name.source)         # 'cli' | 'env' | 'default'
```

### source

`source` tells you where each value came from:

```python
if args.api_key.source == "default":
    print("Warning: using default API key — set PIPELINE_API_KEY for production")
```

### meta

`meta` is a pass-through dict for developer-defined data. runspec never
validates or interprets it. A common use case is associating choice values
with lookup data needed at runtime:

```toml
[deploy.args.server]
options = ["web-01", "web-02", "db-01"]

[deploy.args.server.meta]
web-01 = {datacenter = "us-east", tier = "web"}
web-02 = {datacenter = "us-west", tier = "web"}
db-01  = {datacenter = "eu-central", tier = "db"}
```

```python
args = runspec.parse()
info = args.server.meta[args.server.value]
print(info["datacenter"])   # "us-east"
```

The lookup data lives in the same place as the arg definition — no separate
config files, no hardcoded mappings in code.

---

## load_spec()

```python
def load_spec(script_name: str | None = None) -> RunSpec
```

Loads the spec without parsing `sys.argv`. Returns a `RunSpec` with default
values only — no CLI args applied.

Use it for introspection, tooling, and code generation:

```python
spec = runspec.load_spec("deploy")

print(spec.__script__)           # "deploy"
for name, arg in spec._args.items():
    print(f"{name}: {arg.type} (required={arg.required})")
```

This is what `runspec local --format mcp` uses internally — load the spec,
then serialise to JSON.

---

## register_type()

```python
def register_type(name: str, coercer: Callable[[Any, dict], Any]) -> None
```

Register a custom type. The coercer receives the raw string value and the
full arg spec dict, and returns the coerced Python value.

```python
import json
import runspec
from pathlib import Path

runspec.register_type(
    "json-file",
    lambda v, arg: json.loads(Path(v).read_text())
)
```

Then in your spec:

```toml
[pipeline.args]
config = {type = "json-file"}
```

The coercer is called during `parse()` after validation passes. Raise
`ValueError` from your coercer to produce a clean error message.

```python
def coerce_port(raw: str, arg: dict) -> int:
    port = int(raw)
    if not (1 <= port <= 65535):
        raise ValueError(f"{port} is not a valid port number")
    return port

runspec.register_type("port", coerce_port)
```

---

## Errors

All runspec exceptions inherit from `RunSpecError`:

```python
from runspec.errors import (
    RunSpecError,       # base class
    MissingRequiredArg,
    InvalidChoice,
    OutOfRange,
    UnknownArg,
    GroupViolation,
    AutonomyViolation,
)
```

Error messages include context, expected values, and fuzzy suggestions:

```
✗  Missing required argument: --input
   Type: path
   Tip: set environment variable PIPELINE_INPUT as an alternative

✗  Invalid value for --format: 'yml'
   Expected one of: json, csv, parquet
   Got: 'yml'

   Did you mean: json?
```

Catch the base class when you want to handle all runspec errors uniformly:

```python
try:
    args = runspec.parse()
except runspec.errors.RunSpecError as e:
    print(e)
    raise SystemExit(1)
```

---

## Complete example

```toml
# mypkg/runspec.toml
[process]
description = "Process input files"
autonomy    = "confirm"

[process.args]
input    = {type = "path"}
format   = {options = ["json", "csv"], default = "json"}
workers  = {default = 4, range = [1, 16]}
dry-run  = {default = false}
verbose  = {default = false, short = "-v"}
api-key  = {type = "str", env = "PROCESS_API_KEY", autonomy = "manual"}
tag      = {type = "str", multiple = true}
```

```python
import runspec

args = runspec.parse()

# All of these work without unwrapping
if args.dry_run:
    print(f"[dry run] would process {args.input}")
    raise SystemExit(0)

for i in range(args.workers):
    chunk = load_chunk(args.input, i, args.workers)
    result = process(chunk, format=str(args.format))

if args.verbose:
    print(f"Tags: {', '.join(args.tag)}")
    print(f"Ran as: {args.__script__} (autonomy={args.__autonomy__})")
```
