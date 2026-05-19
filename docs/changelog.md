# Changelog

All notable changes to runspec are documented here.

---

## 0.8.7 — 2026-05-19

### Changed

**`runspec init --example` now scaffolds two runnables: `clean` and `scan`.**
A single `runspec.toml` demonstrates both an autonomous read-only tool and a
confirm-gated destructive tool — the minimal dual-entrypoint pattern.

`clean` — finds and optionally deletes stale temp files (`autonomy = "confirm"`).
`scan`  — read-only scan, reports what `clean` would delete (`autonomy = "autonomous"`, `output = "json"`).

Both stubs are created (`clean.py`, `scan.py`) and both entry points are wired
when `--write-project` is used. The `--name` flag is silently ignored when
`--example` is active; names are always `clean` and `scan`.

**Demo prep commands** are printed after every `--example` init:

```
Demo (stage some stale files first):
  touch -t 202401010000 report.tmp cache.tmp session.tmp

  scan                    # read-only — lists stale files
  scan --format json      # agent-ready output
  clean --delete          # destructive — triggers confirmation
```

---

## 0.8.6 — 2026-05-19

### Fixed

**mypy strict compliance** — three type errors resolved:

- `__fspath__` return type: `os.fspath(Any)` returns `Any`; added `cast(str, ...)`
  so the declared `str` return type is satisfied.
- `project_root_arg` null guard: `Path / None` is unsupported; replaced with
  `project_root_arg or ".."`.
- E501 line-length: minimal Python stub template split to stay under 200 chars.

---

## 0.8.5 — 2026-05-19

### Fixed

**`runspec local --format mcp/json/openai/anthropic` excludes non-callable
runnables.** A runnable without a registered entry point was previously
included in schema output, which would cause agents to try to invoke a
command that doesn't exist. Format outputs now silently filter to callable
runnables only. The text listing still shows all runnables with the
`[not callable]` warning.

---

## 0.8.4 — 2026-05-19

### Changed

**`runspec local` validates entry points.** A runnable in `runspec.toml`
that has no corresponding entry point registered in `pyproject.toml` (or
whose `pip install` hasn't been re-run) is now flagged as an error:

```
✗  'myrunnable' entry point not registered — add to [project.scripts]
   in pyproject.toml and re-run pip install
```

The runnable is also marked `[not callable]` in the listing. `runspec local`
exits with code 1 when any unregistered entry points are found.

**Terminology.** "installed runnables" is replaced with "runspec
runnable(s)" throughout — the package is installed, but individual
runnables may not be callable until their entry point is wired up.

---

## 0.8.3 — 2026-05-19

### Fixed

**`parse()` never produces a traceback.** All expected error conditions
now print a clean, human-readable message and exit with code 1:

- **Missing required argument** — `✗  Missing required argument: --name`
- **Invalid choice** — `✗  Invalid value for --format: 'xml' / Expected one of: text, json`
- **Invalid type** — e.g. passing `abc` for an `int` arg
- **No `runspec.toml` found** — `No runspec.toml found. Run 'runspec init'...`

Previously these conditions raised `RunSpecError` or `FileNotFoundError`
and showed a Python traceback if the caller didn't catch them. `parse()`
now handles these internally, matching the behaviour of `argparse.parse_args()`.

**Generated stubs** now also wrap `parse()` in a `try/except` as a
belt-and-suspenders guard for unexpected errors in the stub's own code.

---

## 0.8.2 — 2026-05-19

### Fixed

**Missing value for non-flag argument now exits cleanly.** Running
`clean --format` (or any `--arg` that expects a value but gets none)
previously produced an ugly traceback as the parser passed `True` to
the coercer. It now prints a clean message and exits 1:

```
✗  --format requires a value. Expected one of: text, json
```

---

## 0.8.1 — 2026-05-19

### Fixed

**`Arg` proxy completeness** — three missing dunder methods that caused
silent failures or ugly exceptions:

- `__fspath__` — `Arg` now satisfies `os.PathLike`. Passing a path-type
  arg directly to `Path.glob()`, `open()`, or any function that calls
  `os.fspath()` works without wrapping in `str()`. Fixes a `TypeError`
  introduced by a Python 3.13 change to `Path.glob()`. Non-path args
  raise a clean `TypeError` from `os.fspath` rather than a traceback.
- `__hash__` — `Arg` can now be used in sets and as dict keys. Previously,
  defining `__eq__` without `__hash__` caused Python to silently set
  `__hash__ = None`, making any `Arg` unhashable.
- `__getitem__` — index and slice access works on `multiple=true` list
  args: `args.files[0]`, `args.files[1:3]`.

---

## 0.8.0 — 2026-05-19

### Added

**`runspec init --example`** generates a full working runnable instead of a
minimal skeleton. The scaffold is a stale temp-file cleaner that demonstrates
all five runspec arg types (`path`, `str`, `int`, `choice`, `flag`) and
`autonomy = "confirm"`. The generated Python stub works immediately after
`pip install -e .` — no editing required to run it:

```bash
runspec init --example
touch -t 202401010000 report.tmp cache.tmp   # stage some old files
pip install -e .
clean                                         # dry run — lists matches
clean --format json                           # agent-ready output
clean --delete                                # autonomy kicks in
```

**`runspec init --write-project`** scaffolds the full Python project alongside
the runspec files. Writes `pyproject.toml` and `__init__.py` one level up from
the current directory (the right place when you are inside your package
directory), so `pip install -e .` works immediately with no manual wiring:

```bash
mkdir myproject && mkdir myproject/mypkg && cd myproject/mypkg
runspec init --write-project
cd ..
pip install -e .
runspec local   # discovers mypkg immediately
```

Supply an explicit path to place `pyproject.toml` elsewhere:

```bash
runspec init --write-project /path/to/project
```

If a `pyproject.toml` already exists at the target, the file is left untouched
and the `[project.scripts]` entry to add is printed instead.

Both flags compose freely:

```bash
runspec init --example --write-project   # full demo + full project scaffold
```

**Install reminder** is now printed on every `runspec init` run, along with the
exact `[project.scripts]` entry needed to wire the runnable into pip.

---

## 0.7.0 — 2026-05-18

### Changed

**CLI renamed.** `discover` → `local`, `run` → `jump`. The `check` and `emit`
commands are absorbed into `local`.

**`runspec local`** lists every installed runspec-aware runnable with inline
validation, and exits with code 1 if any errors are found — usable as a CI
check. Schema emission is via `--format`:

```bash
runspec local                        # text listing + validation
runspec local --format mcp           # emit MCP tool schemas
runspec local --format mcp --script deploy   # single runnable
```

**`runspec jump`** replaces `runspec run`. Without a tool name, it queries the
registry and lists available tools and hosts. With a tool name and `--host`, it
SSHes to the jump box and runs the tool — everything after `--` goes to the
remote command:

```bash
runspec jump                                        # list from [config] registry
runspec jump --registry http://registry:8080       # list from explicit registry
runspec jump deploy --host jumpbox-01 -- --env prod
```

**Subcommand flattening in `runspec serve`.** Runnables with nested `.commands`
are expanded into flat MCP tools with underscore-joined names:

```toml
[portal-api.commands.orders.commands.get-list]
description = "List orders"
```

Becomes MCP tool `portal-api_orders_get-list`. The command path is prepended
to argv at invocation time.

**Script discovery in `runspec serve`** is now venv-bin only. Scripts must be
installed (`pip install` or `pip install -e .`). The previous fallback that
searched the TOML directory and guessed file extensions has been removed.

---

## 0.6.0 — 2026-05-18

### Changed

**`runspec init` now generates a code stub alongside `runspec.toml`.** Running
`runspec init --name greet` creates both `runspec.toml` and `greet.py` (Python CLI)
or `greet.ts` (Node CLI) with `parse()` already wired up. A `--lang` flag lets you
override the language from either CLI:

```bash
runspec init --name greet                      # .py from Python CLI, .ts from Node CLI
runspec init --name greet --lang typescript    # .ts from either CLI
runspec init --name greet --lang javascript    # .js from either CLI
runspec init --name greet --lang python        # .py from either CLI
```

If the stub file already exists it is skipped — `runspec.toml` still fails fast if it
already exists.

**Node: pyproject.toml support removed.** The Node package no longer reads
`[tool.runspec.*]` from `pyproject.toml`. `runspec.toml` inside the package directory
is the only supported format, matching Python since 0.5.0.

---

## 0.5.0 — 2026-05-18

### Added

**Recursive dev-mode discovery** — `runspec serve --dev` and `runspec run --dev`
now scan the full directory tree under the nearest `.git` root (previously
only one level deep). A monorepo with `packages/python/mypkg/runspec.toml`
is found automatically. The walk skips `.venv`, `__pycache__`, `node_modules`,
`dist`, `build`, and all hidden directories.

### Changed

**`runspec.toml` is now the sole supported format.** The option to read
runspec configuration from `pyproject.toml` (under `[tool.runspec.*]`) has
been removed. All documentation, specs, and examples have been updated to
reflect this.

---

## 0.3.0 — 2026-05-17

### Added

**`runspec-node`** — full Node.js/TypeScript implementation of the runspec library.
Install via `npm install runspec-node`. Ships with the same `parse()`, `loadSpec()`,
`registerType()`, all five CLI commands (`init`, `check`, `discover`, `emit`, `serve`),
and the MCP stdio server. Node 18, 20, and 22 supported.

See the [Node Library](node.md) reference for full details.

---

**`runspec init`** — scaffold a `runspec.toml` in the current directory.
Available in both the Python and Node packages.

```bash
runspec init              # uses current directory name as the runnable name
runspec init --name deploy
```

Refuses if `runspec.toml` already exists. Prints a reminder to move the file
inside your package directory before publishing.
See the [CLI reference](cli.md#runspec-init) for full details.

---

## 0.2.0 — 2026-05-17

### Added

**`runspec serve`** — live MCP stdio server. Start it from your project
directory and connect any MCP-compatible agent (Claude Desktop, Cursor,
or your own agent loop) via `claude_desktop_config.json`. Zero extra
dependencies — the protocol is JSON-RPC 2.0 over stdin/stdout.

```json
{
  "mcpServers": {
    "my-pipeline": {
      "command": "/path/to/venv/bin/runspec",
      "args": ["serve"],
      "cwd": "/path/to/project"
    }
  }
}
```

See the [CLI reference](cli.md#runspec-serve) and
[Agent Integration](agents.md#live-mcp-server) guide for full details.

---

**`output` field on runnables** — declares what a runnable writes to stdout.

```toml
[process]
output = "json"   # agent can parse stdout as structured data
```

| Value | Meaning |
|---|---|
| `text` | Human-readable output (default) |
| `json` | Structured JSON — agent can parse and act on the response |
| `html` | Reserved for future UI use |

Surfaces as `x-output` in all emitted schemas so agent frameworks can
interpret the response without guessing.

---

**`args.__agent__`** — `RunSpec` exposes `__agent__: bool`. It is `True`
when the runnable is called via `runspec serve`. Use it to switch output
format for agent vs human callers:

```python
args = runspec.parse()

if args.__agent__:
    print(json.dumps({"status": "ok", "deployed_to": str(args.env)}))
else:
    print(f"✓ Deployed to {args.env}")
```

---

**Installed package discovery** — `runspec discover` now scans the current
Python environment for packages that list `runspec` as a dependency. No
registration step required — ship a `runspec.toml` in your package data
and it appears automatically.

---

## 0.1.1 — 2026-05-17

Fixed the Documentation link on the PyPI project page (previously a dead link).

---

## 0.1.0 — 2026-05-17

Initial release. Full `parse()` pipeline: config discovery, inference,
validation, coercion, and `RunSpec` return. Supports groups, subcommands,
autonomy levels, custom types, and `--help` interception. CLI commands:
`check`, `discover`, `emit`. Python 3.10–3.13, zero runtime dependencies
on 3.11+.
