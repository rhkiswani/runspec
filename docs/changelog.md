# Changelog

All notable changes to runspec are documented here.

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
