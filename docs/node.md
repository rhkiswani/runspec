# Node Library

The Node package (`runspec-node`) brings the same interface specification to Node.js
and TypeScript projects. Install it, call `parse()`, and you get a fully validated,
type-coerced argument object back — same spec format, same CLI, same MCP server.

---

## Installation

```bash
npm install runspec-node
```

**Node 18+.** One runtime dependency: `smol-toml` (TOML parsing — Node has no
stdlib TOML parser). TypeScript types are bundled — no separate `@types/` package.

---

## parse()

```typescript
import { parse } from 'runspec-node';

const args = parse();
```

That's the whole call. runspec finds your config, resolves the runnable name,
parses `process.argv`, validates, coerces, and returns a `ParsedArgs`.

### Signature

```typescript
function parse(opts?: ParseOptions): ParsedArgs

interface ParseOptions {
  scriptName?: string;  // runnable name — inferred from config if omitted
  argv?: string[];      // override process.argv.slice(2)
  cwd?: string;         // start directory for config search (default: process.cwd())
}
```

### What it does

1. Walks up from `cwd` to find `runspec.toml`
2. Infers the runnable name from the script filename
3. Applies inference rules to fill in `type` and `required`
4. Resolves any subcommand from `argv`
5. Intercepts `--help` / `-h` and prints usage, then exits
6. Parses `argv` into raw values
7. Applies environment variable fallbacks
8. Applies spec defaults
9. Validates individual args, then group constraints
10. Coerces values to native JavaScript types
11. Returns a `ParsedArgs`

### Errors

| Exception | When |
|---|---|
| `RunSpecError` | No config found, runnable not in spec, reserved name used |
| `MissingRequiredArg` | A required arg was not provided |
| `InvalidChoice` | Value not in declared `options` |
| `OutOfRange` | Numeric value outside declared `range` |
| `UnknownArg` | An arg was passed that isn't in the spec |
| `GroupViolation` | A group constraint was violated |

All errors inherit from `RunSpecError`. Error messages are human-first — they
include what was expected, what was received, and a fuzzy suggestion where possible.

### Testing

Pass `argv` directly to test without touching `process.argv`:

```typescript
import { parse } from 'runspec-node';

test('greet with --loud', () => {
  const args = parse({ argv: ['--name', 'Alice', '--loud'] });
  expect(args['name']).toBe('Alice');
  expect(args['loud']).toBe(true);
});
```

---

## ParsedArgs

`parse()` returns a `ParsedArgs` — a plain object where argument values are already
coerced to their native JavaScript types.

### Accessing arguments

Hyphens in arg names become underscores. Access them by key:

```typescript
const args = parse();

const name = args['name'] as string;
const workers = args['workers'] as number;
const inputDir = args['input_dir'] as string;   // --input-dir → input_dir
const format = args['format'] as string;
const tags = (args['tag'] as string[]) ?? [];   // multiple=true → string[]
const dryRun = args['dry_run'] as boolean;
```

Unlike the Python library, there is no transparent proxy — `args['name']` IS the
coerced string value, not a wrapper. Cast to the TypeScript type you expect.

**Helper function pattern:**

```typescript
function get<T>(args: ParsedArgs, key: string): T {
  return args[key] as T;
}

const name = get<string>(args, 'name');
const workers = get<number>(args, 'workers');
```

### Metadata attributes

`ParsedArgs` carries context about the invocation using dunder keys:

| Attribute | Type | Description |
|---|---|---|
| `__script__` | `string` | Name of the runnable (e.g. `"deploy"`) |
| `__source__` | `string` | Path to the config file that was loaded |
| `__command__` | `string \| undefined` | Active subcommand, if any |
| `__autonomy__` | `string` | Effective autonomy level for this invocation |
| `__agent__` | `boolean` | `true` when called via `runspec serve` (agent context) |
| `__spec__` | `ScriptSpec` | Full inferred spec — args, groups, description, etc. |

```typescript
const args = parse();

console.log(args['__script__']);    // "deploy"
console.log(args['__command__']);   // "run"  (if a subcommand was matched)
console.log(args['__autonomy__']);  // "confirm"
console.log(args['__agent__']);     // true when called by an agent via runspec serve
console.log(args['__source__']);    // "/home/user/project/runspec.toml"
```

`__autonomy__` reflects the most restrictive level across the runnable, its args,
and any per-arg overrides. Use it to gate behaviour in agent workflows:

```typescript
if (args['__autonomy__'] === 'manual') {
  console.error('This runnable requires human operation.');
  process.exit(1);
}
```

`__agent__` is `true` when the runnable is called via `runspec serve` — set by the
`RUNSPEC_AGENT=1` environment variable that the serve layer injects:

```typescript
const isAgent = args['__agent__'] as boolean;

if (isAgent) {
  console.log(JSON.stringify({ status: 'deployed', env: args['env'] }));
} else {
  console.log(`✓ Deployed to ${args['env']}`);
}
```

---

## loadSpec()

```typescript
import { loadSpec } from 'runspec-node';

const spec = loadSpec();              // current directory
const spec = loadSpec({ scriptName: 'deploy', cwd: '/path/to/project' });
```

Loads the spec without parsing `process.argv`. Returns a `ParsedArgs` with default
values only — no CLI args applied. Accepts the same `ParseOptions` as `parse()`.

Use it for introspection, tooling, and code generation:

```typescript
import { loadSpec } from 'runspec-node';
import type { ScriptSpec } from 'runspec-node';

const spec = loadSpec({ scriptName: 'deploy' });
const scriptSpec = spec['__spec__'] as ScriptSpec;

for (const [name, arg] of Object.entries(scriptSpec.args)) {
  console.log(`${name}: ${arg.type} (required=${arg.required})`);
}
```

---

## registerType()

```typescript
import { registerType, listTypes } from 'runspec-node';

function registerType(name: string, coercer: (value: unknown) => unknown): void
function listTypes(): string[]
```

Register a custom type. The coercer receives the raw value and returns the coerced
value. Throw an error to produce a clean message.

```typescript
import * as fs from 'fs';
import { registerType } from 'runspec-node';

registerType('json-file', (v) => JSON.parse(fs.readFileSync(v as string, 'utf-8')));

registerType('port', (v) => {
  const port = Number(v);
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error(`${v} is not a valid port number`);
  return port;
});
```

Then in your spec:

```toml
[server.args]
config = {type = "json-file"}
port   = {type = "port", default = 8080}
```

---

## Errors

```typescript
import {
  RunSpecError,       // base class
  MissingRequiredArg,
  InvalidChoice,
  OutOfRange,
  UnknownArg,
  GroupViolation,
  AutonomyViolation,
} from 'runspec-node';
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

```typescript
try {
  const args = parse();
} catch (e) {
  if (e instanceof RunSpecError) {
    console.error(e.message);
    process.exit(1);
  }
  throw e;
}
```

---

## CLI

The `runspec` binary is included in `runspec-node`. Use it via `npx` in any project
that has `runspec-node` installed:

```bash
npx runspec init                   # scaffold runspec.toml + code stub
npx runspec local                  # list installed runnables and validate config
npx runspec local --format mcp     # emit MCP tool schemas
npx runspec serve                  # start the MCP stdio server
```

Or install globally for direct access:

```bash
npm install -g runspec-node
runspec local
```

The CLI is identical to the Python version and reads the same `runspec.toml` format.
If both `runspec` (Python) and `runspec-node` are installed, either binary works.

See the [CLI reference](cli.md) for full documentation of all commands.

---

## MCP server

`runspec serve` starts a JSON-RPC 2.0 MCP stdio server for your project. It reads
your `runspec.toml`, exposes all runnables as tool schemas, and executes them when
an agent calls a tool.

**How it finds scripts:**

The Node serve command looks in `node_modules/.bin/` relative to your config file.
Any package you install that declares a `bin` entry appears there automatically. Name
your runnable the same as the binary it wraps.

```
project/
  runspec.toml             # [process] runnable defined here
  node_modules/
    .bin/
      process              # ← runspec serve finds this and runs it
```

**Connect Claude Desktop or any MCP client:**

=== "Via npx (no global install required)"

    ```json
    {
      "mcpServers": {
        "my-tools": {
          "command": "npx",
          "args": ["--yes", "runspec-node", "serve"],
          "cwd": "/path/to/project"
        }
      }
    }
    ```

=== "Global install"

    ```json
    {
      "mcpServers": {
        "my-tools": {
          "command": "runspec",
          "args": ["serve"],
          "cwd": "/path/to/project"
        }
      }
    }
    ```

=== "Project local (package.json scripts)"

    ```json
    {
      "mcpServers": {
        "my-tools": {
          "command": "npm",
          "args": ["run", "serve"],
          "cwd": "/path/to/project"
        }
      }
    }
    ```

    With `"serve": "runspec serve"` in your `package.json` scripts.

**Long-running service (systemd user unit):**

```ini
[Unit]
Description=runspec MCP server

[Service]
Type=simple
ExecStart=/usr/local/bin/runspec serve
WorkingDirectory=/path/to/project
Restart=on-failure

[Install]
WantedBy=default.target
```

---

## Complete example

```toml
# runspec.toml
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

```typescript
import { parse } from 'runspec-node';

const args = parse();

const input = args['input'] as string;
const format = args['format'] as string;
const workers = args['workers'] as number;
const dryRun = args['dry_run'] as boolean;
const verbose = args['verbose'] as boolean;
const tags = (args['tag'] as string[]) ?? [];
const isAgent = args['__agent__'] as boolean;

if (dryRun) {
  console.log(`[dry run] would process ${input} as ${format}`);
  process.exit(0);
}

// ... process the input ...

if (isAgent) {
  console.log(JSON.stringify({ status: 'done', format, workers }));
} else {
  if (verbose) console.log(`Processed ${input} with ${workers} workers`);
  if (tags.length) console.log(`Tags: ${tags.join(', ')}`);
}
```

Running it:

```bash
node dist/process.js --input data.csv --workers 8 --tag etl --tag prod
```

Or from an agent via `runspec serve` — no code change needed. The `__agent__` flag
controls the output format automatically.
