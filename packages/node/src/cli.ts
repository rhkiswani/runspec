import * as fs from 'fs';
import * as path from 'path';
import { findConfig } from './finder';
import { loadRaw } from './loader';
import { inferScript } from './inference';
import type { ScriptSpec, ArgSpec } from './models';

// ── Entry point ───────────────────────────────────────────────────────────────

export function main(): void {
  const args = process.argv.slice(2);

  if (!args.length || args[0] === '-h' || args[0] === '--help') {
    printHelp();
    return;
  }

  const command = args[0];
  const rest = args.slice(1);

  const commands: Record<string, (args: string[]) => void> = {
    init: cmdInit,
    discover: cmdDiscover,
    check: cmdCheck,
    emit: cmdEmit,
    serve: cmdServe,
  };

  if (!(command in commands)) {
    console.log(`✗  Unknown command: ${command}`);
    console.log(`   Available commands: ${Object.keys(commands).join(', ')}`);
    process.exit(1);
  }

  commands[command](rest);
}

// ── Commands ──────────────────────────────────────────────────────────────────

function cmdInit(args: string[]): void {
  const nameFlag = getFlag(args, '--name');
  const langFlag = getFlag(args, '--lang') ?? 'typescript';

  const cwd = process.cwd();
  const runnableName = nameFlag ?? sanitizeName(path.basename(cwd));
  const runspecToml = path.join(cwd, 'runspec.toml');

  initRunspecToml(runspecToml, runnableName);
  initCodeStub(cwd, runnableName, langFlag);
}

function cmdDiscover(args: string[]): void {
  const fmt = getFlag(args, '--format') ?? 'text';

  const discovered = discoverLocal();

  if (!discovered.length) {
    console.log('No runspec-aware runnables found in this environment.');
    console.log("Create a runspec.toml inside your package directory and run 'runspec init' to get started.");
    return;
  }

  if (fmt === 'text') {
    printDiscoverText(discovered);
  } else if (fmt === 'json') {
    console.log(JSON.stringify(discovered, null, 2));
  } else if (['mcp', 'openai', 'anthropic'].includes(fmt)) {
    console.log(JSON.stringify(emitAll(discovered, fmt), null, 2));
  } else {
    console.log(`✗  Unknown format: ${fmt}`);
    console.log('   Available formats: text, json, mcp, openai, anthropic');
    process.exit(1);
  }
}

function cmdCheck(args: string[]): void {
  let configPath: string;

  try {
    ({ configPath } = findConfig(process.cwd()));
  } catch (e) {
    console.log((e as Error).message);
    process.exit(1);
  }

  const raw = loadRaw(configPath);
  const errors: string[] = [];
  const warnings: string[] = [];
  const ok: string[] = [];

  ok.push(`Config found: ${configPath}`);

  if ('config' in raw.runnables) {
    errors.push("'config' is a reserved name — rename your runnable to something else");
  }

  for (const [name, runnable] of Object.entries(raw.runnables)) {
    if (!runnable.description) {
      warnings.push(`'${name}' has no description — agents won't know what it does`);
    } else {
      ok.push(`'${name}' — description present`);
    }

    if (!runnable.autonomy) {
      warnings.push(`'${name}' autonomy not declared — will default to '${raw.config.autonomyDefault}'`);
    } else {
      ok.push(`'${name}' — autonomy: ${runnable.autonomy}`);
    }

    for (const [argName, arg] of Object.entries(runnable.args ?? {})) {
      if (!arg.description && arg.required) {
        warnings.push(`'${name}.${argName}' is required but has no description`);
      }
    }
  }

  for (const msg of ok) console.log(`  ✓  ${msg}`);
  for (const msg of warnings) console.log(`  ℹ  ${msg}`);
  for (const msg of errors) console.log(`  ✗  ${msg}`);

  if (errors.length) process.exit(1);
  else if (!warnings.length) console.log('\n  All checks passed.');
}

function cmdEmit(args: string[]): void {
  const scriptName = getFlag(args, '--script');
  const fmt = getFlag(args, '--format') ?? 'mcp';

  let configPath: string;

  try {
    ({ configPath } = findConfig(process.cwd()));
  } catch (e) {
    console.log((e as Error).message);
    process.exit(1);
  }

  const raw = loadRaw(configPath);
  const config = raw.config;

  let runnables = raw.runnables;
  if (scriptName) {
    if (!(scriptName in runnables)) {
      console.log(`✗  Runnable '${scriptName}' not found`);
      process.exit(1);
    }
    runnables = { [scriptName]: runnables[scriptName] };
  }

  const schema: Record<string, unknown> = {};
  for (const [name, runnable] of Object.entries(runnables)) {
    const inferred = inferScript(runnable, config.autonomyDefault);
    schema[name] = buildSchema(name, inferred, fmt);
  }

  const output = fmt === 'mcp' ? { tools: Object.values(schema) } : schema;
  console.log(JSON.stringify(output, null, 2));
}

function cmdServe(_args: string[]): void {
  const { serve } = require('./serve') as { serve: () => void };
  serve();
}

// ── Schema builder ────────────────────────────────────────────────────────────

export function buildSchema(name: string, script: ScriptSpec, fmt: string): Record<string, unknown> {
  const properties: Record<string, unknown> = {};
  const requiredArgs: string[] = [];

  for (const [argName, arg] of Object.entries(script.args ?? {})) {
    properties[argName] = argToJsonSchema(arg);
    if (arg.required) requiredArgs.push(argName);
  }

  const schema: Record<string, unknown> = {
    name,
    description: script.description ?? '',
    'x-autonomy': script.autonomy ?? 'confirm',
    'x-output': script.output ?? 'text',
    inputSchema: { type: 'object', properties },
  };

  if (requiredArgs.length) (schema['inputSchema'] as Record<string, unknown>)['required'] = requiredArgs;
  if (script.autonomyReason) schema['x-autonomy-reason'] = script.autonomyReason;

  return schema;
}

function argToJsonSchema(arg: ArgSpec): Record<string, unknown> {
  const typeMap: Record<string, string> = {
    str: 'string',
    int: 'integer',
    float: 'number',
    bool: 'boolean',
    flag: 'boolean',
    path: 'string',
    choice: 'string',
  };

  let prop: Record<string, unknown> = { type: typeMap[arg.type ?? 'str'] ?? 'string' };
  if (arg.description) prop['description'] = arg.description;
  if (arg.default !== undefined && arg.default !== null) prop['default'] = arg.default;
  if (arg.options) prop['enum'] = arg.options;
  if (arg.range) {
    prop['minimum'] = arg.range[0];
    prop['maximum'] = arg.range[1];
  }
  if (arg.multiple) prop = { type: 'array', items: prop };

  return prop;
}

// ── Discovery ─────────────────────────────────────────────────────────────────

function discoverLocal(): Array<{ source: string; runnable: string; spec: ScriptSpec }> {
  try {
    const { configPath } = findConfig(process.cwd());
    const raw = loadRaw(configPath);
    return Object.entries(raw.runnables).map(([name, spec]) => ({ source: configPath, runnable: name, spec }));
  } catch {
    return [];
  }
}

function emitAll(discovered: Array<{ source: string; runnable: string; spec: ScriptSpec }>, fmt: string): Record<string, unknown> {
  const tools = discovered.map((item) => buildSchema(item.runnable, item.spec, fmt));
  if (fmt === 'mcp') return { tools };
  return Object.fromEntries(tools.map((t) => [t['name'], t]));
}

function printDiscoverText(discovered: Array<{ source: string; runnable: string; spec: ScriptSpec }>): void {
  const bySource: Record<string, string[]> = {};
  for (const item of discovered) {
    (bySource[item.source] ??= []).push(item.runnable);
  }
  console.log(`Found ${discovered.length} runspec-aware runnable(s):\n`);
  for (const [source, runnables] of Object.entries(bySource)) {
    console.log(`  ${source}`);
    for (const r of runnables) console.log(`    • ${r}`);
  }
  console.log();
  console.log("Run 'runspec discover --format mcp' to emit MCP tool schemas.");
}

// ── Init helpers ──────────────────────────────────────────────────────────────

function sanitizeName(raw: string): string {
  const s = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return s || 'myscript';
}

function initRunspecToml(filePath: string, name: string): void {
  if (fs.existsSync(filePath)) {
    console.log(`✗  ${path.basename(filePath)} already exists — already initialized`);
    console.log(`   Edit ${path.basename(filePath)} directly to add more runnables.`);
    process.exit(1);
  }
  const content = `[${name}]\ndescription = "Describe what ${name} does"\nautonomy    = "confirm"\n\n[${name}.args]\n# example = {type = "str", description = "An example argument"}\n`;
  writeAndVerify(filePath, content, null);
  console.log(`  ✓  Created runspec.toml with [${name}] runnable`);
}

function initCodeStub(dir: string, name: string, lang: string): void {
  const templates: Record<string, { ext: string; content: (n: string) => string }> = {
    typescript: {
      ext: '.ts',
      content: (n) =>
        `import { parse } from 'runspec';\n\nfunction main(): void {\n  const args = parse();\n  // your logic here\n}\n\nmain();\n`,
    },
    javascript: {
      ext: '.js',
      content: (n) =>
        `const { parse } = require('runspec');\n\nfunction main() {\n  const args = parse();\n  // your logic here\n}\n\nmain();\n`,
    },
    python: {
      ext: '.py',
      content: (n) =>
        `from runspec import parse\n\n\ndef main():\n    args = parse()\n    # your logic here\n\n\nif __name__ == "__main__":\n    main()\n`,
    },
  };

  const template = templates[lang];
  if (!template) {
    console.log(`✗  Unknown --lang: ${lang}`);
    console.log(`   Supported: typescript, javascript, python`);
    process.exit(1);
  }

  const filePath = path.join(dir, name + template.ext);
  if (fs.existsSync(filePath)) {
    console.log(`  ℹ  ${path.basename(filePath)} already exists — skipped`);
  } else {
    fs.writeFileSync(filePath, template.content(name), 'utf-8');
    console.log(`  ✓  Created ${path.basename(filePath)}`);
  }

  console.log("     Move both files inside your package directory before publishing.");
  console.log("     Run 'runspec check' to validate.");
}

function writeAndVerify(filePath: string, content: string, original: string | null): void {
  fs.writeFileSync(filePath, content, 'utf-8');
  try {
    const { parse } = require('smol-toml') as { parse: (s: string) => unknown };
    parse(content);
  } catch (e) {
    if (original !== null) fs.writeFileSync(filePath, original, 'utf-8');
    else fs.unlinkSync(filePath);
    console.log('✗  Generated invalid TOML — this is a bug, please report it');
    console.log(`   ${(e as Error).message}`);
    process.exit(1);
  }
}

// ── Arg parser helper ─────────────────────────────────────────────────────────

function getFlag(args: string[], flag: string): string | undefined {
  const idx = args.indexOf(flag);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return undefined;
}

// ── Help ──────────────────────────────────────────────────────────────────────

function printHelp(): void {
  console.log(`runspec — interface specification for anything runnable

Usage:
  runspec <command> [options]

Commands:
  init        Create runspec.toml and a code stub
  discover    Find all runspec-aware runnables in this environment
  check       Validate this project's runspec setup
  emit        Emit tool schemas for agent frameworks
  serve       Start the MCP stdio server for this environment

Options for init:
  --name      Runnable name (default: current directory name)
  --lang      Language for code stub: typescript (default), javascript, python

Options for discover:
  --format    Output format: text (default), json, mcp, openai, anthropic

Options for emit:
  --script    Runnable name to emit (all runnables if omitted)
  --format    Output format: mcp (default), openai, anthropic

Examples:
  runspec init
  runspec init --name myapp
  runspec init --name myapp --lang javascript
  runspec discover
  runspec discover --format mcp
  runspec check
  runspec emit --script deploy --format mcp
  runspec emit --format openai`);
}
