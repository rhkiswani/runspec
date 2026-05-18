# runspec — Design Document

> A language-agnostic, TOML-based interface specification for anything runnable — scripts, applications, and MCP tools — that serves both human developers and AI agents without conversion.

> **Note (v0.7.0):** CLI command names were revised. `discover` → `local`, `run` → `jump`, `check` and `emit` absorbed into `local --format`. References below reflect the original design names and are preserved as historical record.

---

## What `runspec` Describes

`runspec` is not just for scripts. It describes the interface of **anything runnable**: a Python script, a shell command, a CLI application, an MCP tool, or a long-lived application that accepts inputs over time. From `runspec`'s perspective these are all the same thing — a runnable with a defined interface of inputs it accepts.

```
script        → runs once, exits, inputs are args
application   → long-lived, inputs arrive via UI or API
MCP tool      → runs on demand, inputs are tool call parameters
```

In `runspec.toml`, everything except `[config]` is a runnable. The name you choose — greeter, pipeline, send-report — is the only identifier needed.

---

## The Problem

Interface definitions for runnables are buried in code. `argparse` configs require reading Python. Click/Typer decorators are better but still code-first. And when AI agents need to invoke something as a tool, the interface has to be re-described in a separate "skills" file — duplicating what already exists.

**The insight:** interface definitions *are* skill descriptions. If you know something accepts `--input-file`, `--model`, and `--output-format [json|csv]`, you already know how to invoke it as an agent tool, render it as a form, or generate an implementation for it. The spec just needs to make that explicit.

---

## Problems with Existing Parsers

`runspec` is designed with these known pain points in mind.

### argparse
- Error messages are cryptic — tells you *what* failed but not *how to fix it*
- Help text formatting is rigid and ugly by default
- Mutually exclusive groups can't be nested — you can't say "A and B are exclusive, but if you pick B then C is required"
- No native environment variable support — bolted on manually per project
- Namespace is flat — no grouping of related args
- Subcommands are awkward to compose and share args between
- No deprecation support built in
- Testing requires mocking `sys.argv`
- No machine-readable schema without extra work

### Click
- Decorator order matters and silently produces wrong results if wrong
- Type system is custom and doesn't integrate with Python's native `typing`
- Composing commands across files gets complex fast

### Typer
- Tightly coupled to FastAPI's ecosystem thinking
- Type inference from function signatures breaks at edge cases
- Still code-first — you must read the code to understand the interface

### All of them
- Documentation lives separately and drifts from actual args
- No machine-readable schema without extra work
- No way for an agent to understand the interface without running the code
- Validation errors don't suggest corrections
- No enforced priority stack for value resolution

---

## The Solution

A single `runspec.toml` file — inside the package directory, shipping alongside the code — that:

1. Is readable by humans without tooling
2. Is readable by AI agents without conversion
3. Is parsed at runtime by the `runspec` library to build argument parsers
4. Drives form rendering inside agent chat interfaces
5. Controls whether an agent can run something autonomously or needs human approval
6. Can emit agent tool schemas (OpenAI, Anthropic, MCP, etc.) as a first-class feature
7. Works for any language — Python, Node, shell, Go, anything

### Entry Points Convention

The executable name must match the runspec runnable name — this is the one convention runspec requires. A runnable named `compress` in `runspec.toml` must have a corresponding `compress` entry point installed in the environment. The names are the join key between the packaging system and the spec.

```toml
# mypkg/runspec.toml
[compress]
description = "Compress images in a directory"

[greet]
description = "Greet someone from the command line"
```

This works with any language and any build system — the entry point mechanism is not Python-specific. Go binaries, Node scripts, shell scripts, and Python entry points all follow the same convention: the executable name is the runnable name.

### File Lookup Order

`runspec` finds its config depending on the execution context:

**Installed packages (production):**
- `runspec.toml` shipped inside the package directory and located via `importlib.metadata`
- Works for any installed package that declares `runspec` as a dependency

**Local development (`runspec serve --dev`):**
- Walk up from cwd until `.git/` is found — that is the project root
- Walk down one level from the project root, collect all `runspec.toml` files found
- `.git` is the only project boundary marker — language agnostic

**Single-package commands (`runspec run`, `check`, `emit`):**
- Walk up from cwd until `runspec.toml` is found
- Works naturally when you are in or below a package directory

One file per package, multiple runnables within it. No per-runnable sidecar files.

### Project-Wide Configuration

A `[config]` section sets project-wide defaults that apply to all scripts unless overridden:

```toml
[config]
autonomy-default = "confirm"   # autonomy when unspecified on a script
version          = "1"         # runspec spec version
```

### Autonomy Resolution Order

```
per-arg autonomy declared        ← most specific, always wins
  ↓ script-level autonomy declared
    ↓ [config] autonomy-default
      ↓ library default: "confirm" ← safe by default, opt-in to trust
```

The library hardcoded fallback is `"confirm"` — agents must be granted trust explicitly, never assume it.

### Value Resolution Priority Stack

For every argument, `runspec` resolves its value in this order — automatically, with no user code:

```
explicit CLI arg            ← highest priority
  ↓ environment variable
    ↓ config file value
      ↓ default in spec
        ↓ error: required   ← raises if nothing above matched
```

This is the correct behaviour every CLI tool should have. `runspec` enforces it from the spec so you never have to wire it up yourself.

---

## Format Design

### Core Principle: Default Aggressively

Most verbosity comes from spelling out things that can be inferred. `runspec` infers as much as possible so simple args stay simple.

### Inference Rules

| What you write | What gets inferred |
|---|---|
| `default = 85` | `type = "int"` |
| `default = "jpeg"` | `type = "str"` |
| `default = false` | `type = "flag"` (boolean switch) |
| `options = [...]` | `type = "choice"` |
| No default present | `required = true` |
| `type = "path"` only | `required = true` |

### Three Levels of Verbosity

**Level 1 — Bare value shorthand** (simplest args):
```toml
[compress.args]
verbose = false      # flag, defaults to off
workers = 4          # int arg, defaults to 4
```

**Level 2 — Inline table** (most args):
```toml
[compress.args]
input-dir  = {type = "path"}
quality    = {default = 85, range = [1, 100]}
format     = {options = ["jpeg", "png", "webp"], default = "jpeg"}
dry-run    = {default = false}
```

**Level 3 — Full block** (complex args that need prose):
```toml
[compress.args.quality]
default = 85
range = [1, 100]
description = """
Controls output file size vs. visual fidelity tradeoff.
Values below 60 are rarely useful. Ignored for PNG output.
"""
```

Simple args stay on one line. Complex args get the space they need. You never pay verbosity tax uniformly.

### The Package Convention

`runspec.toml` lives inside the package directory alongside the code. Build backends include it automatically — no extra configuration needed.

```
mypkg/
  __init__.py       ← (or equivalent for your language)
  compress.py
  greet.py
  runspec.toml      ← ships with the package, found via importlib.metadata
```

The complete `runspec.toml`:

```toml
[config]
autonomy-default = "confirm"
version          = "1"

[compress]
description = "Compress images in a directory"
autonomy    = "confirm"
autonomy-reason = "Overwrites files in place"

[compress.args]
input-dir = {type = "path"}
quality   = {default = 85, range = [1, 100]}
format    = {options = ["jpeg", "png", "webp"], default = "jpeg"}
dry-run   = {default = false}

[greet]
description = "Greet someone from the command line"
autonomy    = "autonomous"

[greet.args]
name  = {type = "str"}
loud  = {default = false}
times = {default = 1}
```

---

## The Vision

The spec comes first. The code follows.

Today, developers write code and then document its interface. `runspec` inverts that:

```
runspec.toml          ← written first, by a human or an agent
      ↓
runspec emit          ← generates tool schemas for agent frameworks
      ↓
runspec form          ← renders input form inside agent chat (MCP)
      ↓
autonomy check        ← can the agent run this, or does a human confirm?
      ↓
agent registers tool  ← calls the runnable with validated inputs
      ↓
runspec generate      ← agent writes the implementation (future)
```

This makes `runspec.toml` the single source of truth — documentation, validation contract, agent skill definition, form definition, and autonomy policy all in one file, written before a line of implementation exists.

---

## Implementation Strategy

### The CLI is the primary product

The most important artifact is the `runspec` command-line tool. It reads any project's `runspec.toml` and emits agent-ready schemas. This works regardless of what language the underlying script is written in.

Agent frameworks care about the schema, not the implementation. `runspec emit` is immediately useful to every agent ecosystem today.

### Why Node/TypeScript for the CLI

The dominant agent ecosystem right now is MCP (Model Context Protocol), which is Node/TypeScript native. Shipping the CLI as an npm package means:

- `npx runspec emit` works instantly, no install required
- It lives natively in the MCP ecosystem where agents are most active
- It distributes cross-platform without Python environment headaches for non-Python users

**This does not mean abandoning Python.** The CLI is Node because that's the right distribution vehicle for a language-agnostic tool. The Python runtime library (`pip install runspec`) is built alongside it for Python scripts specifically.

### Building approach for a Python-first developer

The Node CLI will be built incrementally with AI assistance. The core logic — reading TOML, applying inference rules, emitting JSON schemas — is straightforward and well-defined. Python knowledge transfers directly: the concepts are identical, only the syntax differs.

The Python library comes first since that's where confidence is highest. The Node CLI follows, sharing the same spec and inference rules. Both are tested against the same `runspec.toml` fixtures.

---

## The Discovery Binary

The single most important feature for agent adoption is zero-friction discovery. When a developer adds `runspec` as a dependency, a `runspec` command appears automatically in their environment's `bin/` (Unix) or `Scripts/` (Windows) folder — no extra steps, no new conventions to learn.

This is standard Python entry point behaviour, declared once in runspec's own packaging:

```toml
# runspec's own pyproject.toml
[project.scripts]
runspec = "runspec.cli:main"
```

Every agent framework knows to look for executables. The `runspec` binary is the universal entry point for everything — discovery, emit, check, and future commands.

### `runspec discover`

Walks every installed package in the current environment using `importlib.metadata`, finds all `runspec.toml` files shipped as package data, and returns a unified view:

```bash
runspec discover
# Found 3 runspec-aware packages:
#   mypkg         2 runnables  (compress, fetch-data)
#   otherpkg      1 runnable   (transform)
#   localproject  4 runnables  (build, test, deploy, lint)

runspec discover --format mcp       # unified MCP tool manifest, ready to register
runspec discover --format json      # machine-readable for agents that parse directly
runspec discover --format openai    # OpenAI tool definitions for all runnables
```

For local projects (not installed), `runspec discover` also checks the current directory for `runspec.toml` and merges results. Installed packages and local projects are treated identically from the agent's perspective.

### `runspec check`

Validates that a project is correctly set up for discovery before publishing:

```bash
runspec check
# ✓ runspec.toml found
# ✓ declared as package data
# ✓ all scripts reference valid entry points
# ✗ compress runnable missing 'description' field
# ✗ fetch-data autonomy not declared — will default to "confirm"
```

Designed to run in CI. Catches problems before they reach users or agents.

### Shipping `runspec.toml` as package data

For installed packages to be discoverable, `runspec.toml` must live inside the package directory and be declared as package data. `runspec check` validates this. The file location:

```
mypackage/
  __init__.py
  compress.py
  runspec.toml    ← ships with the package, found via importlib.resources
```

At runtime, `runspec` locates it without any path assumptions:

```python
from importlib.resources import files
spec = files("mypackage").joinpath("runspec.toml")
```

This works inside virtual environments, system installs, and compiled wheels — anywhere Python packages live.

### The full agent startup flow

```
agent starts up
      ↓
runs: runspec discover --format mcp
      ↓
runspec checks installed packages + current directory
      ↓
emits unified MCP tool manifest
      ↓
agent registers all tools in one shot
      ↓
new package installed → agent runs discover again → tools appear
```

One command. One output. No agent-specific configuration required from the developer.

---

## Agent Tool Export

The primary CLI feature:

```bash
npx runspec emit --script compress --format openai      # OpenAI tool JSON schema
npx runspec emit --script compress --format anthropic   # Anthropic tool spec
npx runspec emit --script compress --format mcp         # MCP tool definition
npx runspec emit --format mcp                           # emit all scripts
```

Example MCP output for the compress script:

```json
{
  "name": "compress",
  "description": "Compress images in a directory",
  "inputSchema": {
    "type": "object",
    "properties": {
      "input-dir": { "type": "string", "description": "Path (required)" },
      "quality":   { "type": "integer", "default": 85, "minimum": 1, "maximum": 100 },
      "format":    { "type": "string", "enum": ["jpeg", "png", "webp"], "default": "jpeg" },
      "dry-run":   { "type": "boolean", "default": false }
    },
    "required": ["input-dir"]
  }
}
```

Because the spec is unambiguous TOML, no interpretation is needed — an agent can also read `runspec.toml` directly without any tooling at all.

---

## Runtime Usage

### Python scripts

```python
from runspec import parse

args = parse()            # finds runspec config automatically
print(args.quality)       # typed, validated, defaults applied
```

The Python library handles type coercion, required field validation, range checks, choice validation, flag handling, and error messages.

### Shell scripts

```bash
# parse args and export as environment variables
eval $(npx runspec parse compress "$@")
echo $QUALITY
```

### Any other language

Read `runspec.toml` directly with any TOML library and implement validation inline — or call `npx runspec parse` and consume the output.

---

## The `RunSpec` Object — Rich by Design

`parse()` doesn't return a simple bag of values. It returns a `RunSpec` object where every argument carries its full metadata alongside its value. This makes the parsed result a runtime source of truth — not just for the current script, but for any tool that wants to introspect, emit, or scaffold from it.

```python
args = runspec.parse()

# Simple value access — works exactly like argparse
args.quality              # 85

# But each arg also knows itself
args.quality.type         # "int"
args.quality.range        # (1, 100)
args.quality.description  # "JPEG quality level"
args.quality.required     # False
args.quality.default      # 85
args.quality.source       # "cli" | "env" | "config" | "default"

# The full spec is available on the object
args.__script__           # "compress"
args.__source__           # Path("mypkg/runspec.toml")
args.__groups__           # list of Group objects
args.__spec__             # full raw parsed spec dict
```

Args behave transparently as their native type — `args.quality + 10` works, `if args.dry_run` works — because `Arg` implements `__int__`, `__str__`, `__bool__`, and `__eq__`. You never have to unwrap.

This richness is what makes future capabilities natural:

```python
runspec.emit(args, format="mcp")       # generate tool schema from live result
runspec.describe(args)                 # human-readable summary for an agent
runspec.scaffold(args, "new_script.py") # generate script skeleton from spec
```

### `Arg` class

```python
class Arg:
    value: Any           # the resolved value
    type: str            # "int" | "str" | "float" | "bool" | "path" | "choice" | "flag"
    required: bool
    default: Any
    description: str | None
    options: list | None    # valid choices
    range: tuple | None     # (min, max) for numeric types
    short: str | None       # e.g. "-q"
    env: str | None         # environment variable name
    deprecated: bool
    source: str             # where the value came from
```

### `Group` class

```python
class Group:
    name: str
    type: str            # see group types below
    args: list[str]      # names of args in this group
    condition: str | None  # for conditional groups — name of the triggering arg
```

---

## Argument Groups

Groups are a property of the script, not individual args. They are validated in a second pass after individual arg validation, which means they can be added or extended without touching the core arg logic.

### Group types

**Mutually exclusive** — at most one arg from the group may be provided:
```toml
[compress.groups.output-type]
exclusive = true
args = ["format", "raw"]
```

**Mutually inclusive** — if any arg in the group is provided, all must be:
```toml
[compress.groups.auth]
inclusive = true
args = ["username", "password"]
```

**At least one** — one or more from the group must be provided:
```toml
[compress.groups.input]
at-least-one = true
args = ["input-dir", "input-file", "input-glob"]
```

**Exactly one** — strictly one must be provided, not zero, not two:
```toml
[compress.groups.mode]
exactly-one = true
args = ["fast", "balanced", "quality"]
```

**Conditional requirement** — if one arg is provided, others become required:
```toml
[compress.groups.upload]
if = "upload"
requires = ["bucket", "region"]
```

Groups can reference the same arg from multiple group definitions, enabling complex real-world constraints without nesting complexity.

---

## Autonomy Control

Every runnable in a `runspec.toml` declares how much trust an agent has to invoke it. This is a first-class field — not a convention or a comment — so every agent framework, form renderer, and human reading the spec knows exactly what approval is required.

### Autonomy levels

**`autonomous`** — agent runs freely, no confirmation needed. Safe, read-only, or reversible operations. Fetching data, reading files, transforming content.

**`confirm`** — agent presents what it intends to do and waits for human approval before running. The right default for anything that writes, deletes, or sends.

**`supervised`** — agent runs but a human must review the output before it's acted on. Useful for "draft this email" where generation is fine but sending needs eyes.

**`manual`** — agent cannot invoke this at all. Human only. Financial transactions, destructive operations, anything requiring legal sign-off.

### Escalation rule

The most restrictive level wins. If a script is `confirm` but a provided arg is `manual`, the whole invocation becomes `manual`. An agent can never talk itself into more trust than the spec allows.

### In the spec

Set at the script level as a default, overridable per arg:

```toml
[delete-files]
description   = "Permanently delete files matching a pattern"
autonomy      = "confirm"
autonomy-reason = "Destructive — permanently removes files, cannot be undone"

[delete-files.args]
pattern  = {type = "path", description = "Glob pattern to match"}
force    = {default = false, autonomy = "manual"}      # escalates the whole call
dry-run  = {default = false, autonomy = "autonomous"}  # always safe
```

### In emitted schemas

```json
{
  "name": "delete-files",
  "x-autonomy": "confirm",
  "x-autonomy-reason": "Destructive — permanently removes files, cannot be undone"
}
```

The `x-` prefix is the JSON Schema extension convention. Agents that understand `runspec` honour it. Agents that don't ignore it safely — graceful degradation by design.

### Autonomy error messages

When an agent attempts to exceed its autonomy level:

```
✗  Cannot run delete-files autonomously
   Autonomy level: confirm
   Reason: Destructive — permanently removes files, cannot be undone

   Awaiting human confirmation...
```

---

## Form Rendering

A `runspec` spec contains everything needed to render an input form inside an agent chat interface — no separate UI schema required. MCP is actively developing chat-native form support; `runspec` is designed to map directly onto it.

### How arg types map to form controls

| Arg type / property | Default form control |
|---|---|
| `type = "str"` | Text input |
| `type = "int"` or `type = "float"` | Number input |
| `type = "path"` | File / directory picker |
| `type = "bool"` or `type = "flag"` | Checkbox |
| `options = [...]` ≤ 4 items | Radio group |
| `options = [...]` > 4 items | Dropdown |
| `range = [min, max]` | Slider |
| `multiple = true` | Multi-select or tag input |
| `type = "str"`, long description | Textarea |

`required` drives form validation. `default` pre-fills the field. `description` becomes the field label and tooltip. `range` sets slider bounds. Groups become form sections or drive conditional field visibility.

### The `ui` hint

When the inferred control isn't what you want, override it explicitly:

```toml
[compress.args]
input-dir = {type = "path", ui = "file-picker"}
quality   = {default = 85, range = [1, 100], ui = "slider"}
format    = {options = ["jpeg", "png", "webp"], ui = "radio"}
notes     = {type = "str", ui = "textarea"}
```

If `ui` is omitted, the default is inferred from the type and properties. The hint is only needed to override that inference — same principle as everywhere else in `runspec`.

### Autonomy drives form behaviour

The `autonomy` level maps directly to how the form behaves:

| Autonomy | Form behaviour |
|---|---|
| `autonomous` | No form shown — agent fills inputs and runs without asking |
| `confirm` | Form shown pre-run — human reviews inputs and submits |
| `supervised` | Form shown, output shown — human approves result before it's acted on |
| `manual` | Form always shown — agent cannot submit, human must |

One field in the spec controls both the agent's trust level and the user's experience of being asked. No separate configuration.

---

## Supported Argument Features

- `type` — str, int, float, bool, path, choice, flag (see Type System below)
- `default` — any TOML-native value; type inferred from it if `type` omitted
- `required` — inferred from missing default, or explicit
- `options` — list of valid choices (infers `type = "choice"`)
- `range` — `[min, max]` for numeric types (int or float)
- `multiple` — accept multiple values; repeated flag style by default
- `delimiter` — split a single value by delimiter e.g. `","` for `--fields id,name,email`
- `short` — short flag alias, e.g. `short = "-v"`
- `env` — environment variable fallback, e.g. `env = "PIPELINE_API_KEY"`
- `description` — human and agent readable, doubles as form field label
- `deprecated` — warn on use with a migration message
- `autonomy` — per-arg override of the script-level autonomy level
- `ui` — form control hint, inferred from type if omitted
- Groups — mutual exclusion, inclusion, conditional requirements (see above)
- Subcommands — via `commands` key on a script section

---

## Type System

### Core types

These are the types the `runspec` spec understands. They are language-agnostic strings — the spec declares intent, the language pack handles coercion.

| Type | Declared as | Inferred when |
|---|---|---|
| String | `type = "str"` | `default = "value"` |
| Integer | `type = "int"` | `default = 42` |
| Float | `type = "float"` | `default = 3.14` |
| Boolean | `type = "bool"` | `default = true` / `default = false` |
| Flag | `type = "flag"` | `default = false` (presence = true) |
| Path | `type = "path"` | — must be explicit |
| Choice | `type = "choice"` | `options = [...]` present |

### The core/language-pack split

Types are declared as strings in the spec. What happens to those strings at runtime — coercion, validation, native object construction — is the responsibility of a language pack. This is a deliberate architectural boundary.

```
runspec (core)
  → reads the spec
  → applies inference rules
  → knows type names as strings
  → emits schemas
  → handles discovery
  → no coercion, no native types

runspec-python (language pack)
  → registers coercers for each type
  → turns "path" into pathlib.Path
  → turns "int" into Python int with range check
  → turns "float" into Python float
  → turns "bool" / "flag" into Python bool
  → turns "str" into Python str
```

This means other language runtimes can implement the same contract:

```
runspec-node    → str→string, int→number, path→string, bool→boolean
runspec-go      → str→string, int→int64, path→string, bool→bool
runspec-rust    → (future)
```

### The install experience

For Python developers, this split is invisible. `pip install runspec` installs both core and `runspec-python` together — one install, full native type experience, nothing to think about:

```bash
pip install runspec          # core + runspec-python, full Python experience
pip install runspec[cli]     # core + CLI only, no Python runtime (for non-Python projects)
```

Future language packs install separately and integrate via the same type registry:

```bash
npm install runspec-node     # Node type coercion (future)
go get github.com/runspec/runspec-go  # Go type coercion (future)
```

### What `runspec-python` gives you

```python
args = parse()

args.input       # pathlib.Path — resolved, absolute
args.quality     # int — range-checked, arithmetic works
args.ratio       # float — range-checked
args.dry_run     # bool — True/False from flag presence
args.format      # str — validated against options list
args.tag         # list[str] — from multiple = true
args.fields      # list[str] — split by delimiter automatically

# Path methods work directly
args.input.is_dir()
args.input.glob("*.jpg")

# Numeric arithmetic works directly
chunks = total // args.workers
scaled = args.ratio * 100
```

### The type registry

Language packs register coercers into a shared registry. Custom types are supported through the same mechanism:

```python
import runspec

# Built-in — registered by runspec-python automatically
runspec.type_registry["int"]   = lambda v, arg: int(v)
runspec.type_registry["float"] = lambda v, arg: float(v)
runspec.type_registry["path"]  = lambda v, arg: Path(v).resolve()
runspec.type_registry["bool"]  = lambda v, arg: v.lower() in ("true", "1", "yes")
runspec.type_registry["flag"]  = lambda v, arg: bool(v)
runspec.type_registry["str"]   = lambda v, arg: str(v)

# Custom type — registered by the developer
runspec.register_type(
    "json-file",
    lambda v, arg: json.loads(Path(v).read_text())
)
```

Then in the spec:

```toml
[process.args]
config = {type = "json-file"}   # reads and parses JSON automatically
```

Custom types are validated by `runspec check` against registered types in the current environment — if a type isn't registered, it's flagged before anything runs.

### Cross-language type equivalence

The same spec runs against different language runtimes — each gets native types:

| runspec type | Python | Node | Go |
|---|---|---|---|
| `str` | `str` | `string` | `string` |
| `int` | `int` | `number` | `int64` |
| `float` | `float` | `number` | `float64` |
| `bool` / `flag` | `bool` | `boolean` | `bool` |
| `path` | `pathlib.Path` | `string` | `string` |
| `choice` | `str` (validated) | `string` (validated) | `string` (validated) |

---

## Error Messages

`runspec` errors are designed to be human-first. Instead of argparse's terse output:

```
error: argument --format: invalid choice: 'tiff'
```

`runspec` says:

```
✗  Invalid value for --format: 'tiff'
   Expected one of: jpeg, png, webp
   Got: tiff

   Did you mean: jpeg?
```

Fuzzy matching on typos is implemented via `difflib` from the Python standard library — no extra dependency. Every error includes what was expected, what was received, and a suggestion where possible.

---

## Design Principles

1. **Spec first, code follows** — the runspec is the source of truth
2. **Describes anything runnable** — scripts, apps, and MCP tools are all the same thing
3. **The discovery binary is the contract with agents** — `runspec discover` is the universal entry point
4. **Zero new conventions for developers** — add `runspec` as a dependency, everything else is automatic
5. **The CLI is the primary product** — emit agent schemas for any project
6. **Zero dependencies** for core — language packs are optional installs
7. **One line for simple args, full block only when needed**
8. **Inference over declaration** — don't make users repeat themselves
9. **Rich objects over raw values** — the parsed result knows itself
10. **Two-pass validation** — args first, groups second; keeps both extensible
11. **Enforced priority stack** — CLI → env → config → default, always
12. **Autonomy is declared, not assumed** — safe by default (`confirm`), opt-in to trust
13. **The spec is the form** — no separate UI schema needed for chat-native interfaces
14. **Types are declared as intent, coerced by language packs** — core stays language-agnostic
15. **Extensible type registry** — custom types are first-class, not hacks
16. **Errors that help** — what failed, what was expected, what to try instead
17. **Language agnostic** — the format works for Python, shell, Node, or anything

---

## Open Questions

- [ ] Which agent schema formats to support at launch: MCP + OpenAI + Anthropic, or MCP only?
- [ ] Should `runspec generate` use templates per language or be fully AI-driven?
- [ ] What signals determine which packaged example best matches a given spec?
- [ ] How should runtime detection handle version constraints (e.g. python3.11+ required)?
- [ ] Should generated code be written to disk automatically or previewed first?
- [ ] How do `ui` hints interact with MCP's evolving form specification — track MCP's spec or define our own and map to it?
- [ ] Should custom type registration be per-project (in `runspec.toml`) or code-only (via `runspec.register_type()`)?
- [ ] How does `runspec check` validate custom types — against registered types at check time, or against a declared list in the spec?

---

## Project Status

Design phase complete. Core ideas, strategy, and build order are settled. Ready to begin implementation with the Python library.

| Feature | Build now | Design for now, implement later |
|---|---|---|
| `Arg` class with full metadata | ✓ | |
| `Group` class on `RunSpec` | ✓ | |
| `[config]` section with autonomy default | ✓ | |
| Inference rules | ✓ | |
| Priority stack (CLI → env → config → default) | ✓ | |
| Individual arg validation | ✓ | |
| Autonomy levels on `RunSpec` and `Arg` | ✓ | |
| Helpful error messages with fuzzy suggestions | ✓ | |
| `runspec discover` binary | ✓ | |
| `runspec check` validation command | ✓ | |
| `runspec emit` schema generation | ✓ | |
| Type registry architecture | ✓ | |
| `runspec-python` language pack | ✓ | |
| Subcommands via `commands` key | ✓ | |
| Autonomy enforcement in runtime | | ✓ |
| Group validation logic | | ✓ |
| Conditional requirements | | ✓ |
| Config file fallback (third tier) | | ✓ |
| Form rendering / `ui` hint support | | ✓ |
| MCP chat-native form emission | | ✓ |
| `runspec-node` language pack | | ✓ |
| `runspec-go` language pack | | ✓ |
| `runspec generate` | | ✓ |

---

## Repository Structure

### Mono-repo on GitHub

The project lives in a single GitHub repository at `github.com/JasonFinestone/runspec`. A mono-repo is the right choice because the entire value of runspec depends on all language packs implementing the same spec identically — a change to an inference rule is one commit that updates core, all language packs, and all tests atomically. Multi-repo would cause constant drift.

GitHub is chosen over GitLab for ecosystem fit — npm, PyPI, and pkg.go.dev all have native GitHub integrations, GitHub Actions handles matrix builds across languages cleanly, and open source discoverability is better there.

### Directory layout

```
runspec/
│
├── spec/
│   └── SPEC.md                  ← canonical runspec format specification
│                                   all language packs are tested against this
├── packages/
│   ├── python/                  ← runspec + runspec-python (primary, built first)
│   │   ├── runspec/
│   │   │   ├── __init__.py
│   │   │   ├── finder.py        ← locates config file
│   │   │   ├── loader.py        ← reads and normalises TOML
│   │   │   ├── inference.py     ← applies inference rules
│   │   │   ├── validator.py     ← validates args and groups
│   │   │   ├── types.py         ← type registry and runspec-python coercers
│   │   │   ├── models.py        ← Arg, Group, RunSpec classes
│   │   │   ├── parser.py        ← entry point, builds RunSpec from sys.argv
│   │   │   └── cli.py           ← discover, check, emit commands
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   ├── node/                    ← runspec-node (stub, future)
│   │   ├── src/
│   │   │   └── index.ts
│   │   ├── tests/
│   │   ├── package.json
│   │   └── README.md
│   │
│   └── go/                      ← runspec-go (stub, future)
│       ├── runspec.go
│       ├── go.mod
│       ├── tests/
│       └── README.md
│
├── tests/
│   └── integration/
│       ├── fixtures/             ← shared TOML configs all packs run against
│       │   ├── simple.toml
│       │   ├── inference.toml
│       │   ├── groups.toml
│       │   ├── autonomy.toml
│       │   ├── subcommands.toml
│       │   └── complex.toml
│       └── compliance/           ← every pack must pass every fixture
│
├── .github/
│   ├── workflows/
│   │   ├── python.yml            ← lint, test, type-check on Python changes
│   │   ├── node.yml              ← stub, activates when node/ is built
│   │   ├── go.yml                ← stub, activates when go/ is built
│   │   └── integration.yml       ← compliance suite across all packs
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── README.md
├── CONTRIBUTING.md
└── SPEC.md                       ← symlink or copy of spec/SPEC.md
```

### Working relationship

- Design and implement in Python first — readable, testable, the reference implementation
- Node and Go follow the same logic translated to their idioms
- The compliance suite verifies all packs agree on every fixture
- Python is reviewed collaboratively; Node and Go are kept in line against the compliance tests
- IDE: PyCharm / IntelliJ IDEA with Claude Code for agentic assistance

### Build sequence

Start Python only. Node and Go stubs exist from day one so the structure is correct, but they are empty. The compliance fixture suite is written alongside the Python implementation — when Node and Go are built later, the tests are already waiting for them.

---

## Future Vision — `runspec generate`

> This section captures aspirational ideas for future exploration. None of this is in scope for the initial build. It is recorded here because it shapes decisions made today.

The long-term ambition is a `generate` command that takes a `runspec.toml` and produces a working implementation — not just a skeleton, but running code — in whatever language is available on the current machine. The human writes the spec. The agent writes the code.

### The three generation strategies

When `runspec generate` is invoked, it selects a strategy based on what's available:

```
Strategy 1 — Adapt a packaged example
  A matching reference implementation exists in the runspec library.
  The agent modifies it to fit the spec exactly.
  Fastest. Most reliable. Preferred when available.

Strategy 2 — Generate from scratch
  No matching example exists.
  The agent reads the spec — script description, arg names, types,
  descriptions, groups — and writes a full implementation.
  Language chosen based on what runtimes are detected on the machine.

Strategy 3 — Fill a template
  A language template exists but needs logic filled in.
  The agent or human completes the scaffolding.
  Middle ground between full generation and blank canvas.
```

The agent picks the best available strategy automatically, or the user can force one:

```bash
npx runspec generate --script compress              # auto strategy
npx runspec generate --script compress --from-example
npx runspec generate --script compress --lang python
npx runspec generate --script compress --template
```

### The spec as a brief

The `runspec.toml` contains everything an agent needs to write a correct implementation:

- The script's purpose (`description`)
- Every input it accepts, its type, its constraints, its meaning
- Which args are required, which are optional, what the defaults are
- Relationships between args (groups)
- Environment variable fallbacks

An agent reading this has enough context to write a working script without any additional instruction. The richer the spec, the better the generated code.

### Runtime detection

`runspec generate` inspects the current machine before choosing a language:

```
Detected runtimes → python3, node
Preferred order   → user config, then project convention, then popularity
Chosen language   → python3
```

If the project already contains Python files, Python wins. If it's a Node project, Node wins. If nothing is detected, the user is prompted.

### Packaged examples library

The library ships with a growing collection of reference implementations — common script patterns in multiple languages that the agent can adapt:

```
examples/
  file-processor/
    python/    ← reads files, processes, writes output
    node/
    bash/
  api-caller/
    python/    ← authenticates, calls an API, handles errors
    node/
  data-transformer/
    python/    ← reads structured data, transforms, emits
```

When a spec's description and arg shape closely match a packaged example, that example becomes the starting point. The agent adapts it rather than generating from scratch — more reliable, more idiomatic, less hallucination risk.

### The fully agentic loop

The complete vision, with no human in the loop after the spec is written:

```
runspec.toml written          ← human or agent defines the interface
      ↓
runspec generate              ← agent selects strategy and language
      ↓
implementation written        ← agent produces working code
      ↓
runspec emit --format mcp     ← agent tool schema generated
      ↓
tool registered in MCP server ← script is now an agent-callable tool
      ↓
agent calls the tool          ← end-to-end, spec to execution
```

The spec is written once. Everything else is derived from it.

### Why this matters

Today, building an agent tool requires: writing the script, writing the argument parser, writing the MCP tool definition, keeping all three in sync. `runspec generate` collapses that to: write the spec, run one command.

This is the version of `runspec` that makes the tool genuinely transformative rather than merely convenient.

---

## Open Questions

- [ ] Subcommand structure — nested script sections or a `commands` key?
- [ ] Which agent schema formats to support at launch: MCP + OpenAI + Anthropic, or MCP only?
- [ ] Should `runspec generate` use templates per language or be fully AI-driven?
- [ ] What signals determine which packaged example best matches a given spec?
- [ ] How should runtime detection handle version constraints (e.g. python3.11+ required)?
- [ ] Should generated code be written to disk automatically or previewed first?
- [ ] How do `ui` hints interact with MCP's evolving form specification — should we track MCP's spec or define our own and map to it?
- [ ] Should `autonomy = "confirm"` be the default when no autonomy is declared, or should unspecified mean `autonomous`?
- [ ] Should language packs be required to return rich metadata objects (like Python's `Arg` dataclass, which carries value + full spec metadata) or just correctly typed values? Python's `args.times.default`, `args.format.options` etc. are powerful but may be hard to replicate idiomatically in Go or Node. Decision needed before the spec locks down the language pack contract.

---

## Project Status

Early design phase. Core ideas and strategy are settled. Build order defined. Implementation not started.
