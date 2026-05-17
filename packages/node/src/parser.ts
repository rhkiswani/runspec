import * as path from 'path';
import { findConfig, findScriptName } from './finder';
import { loadRaw } from './loader';
import { inferScript, effectiveAutonomy } from './inference';
import { coerce } from './types';
import { validateArgs, validateGroups, raiseIfErrors } from './validator';
import { RunSpecError } from './errors';
import type { ParsedArgs, ScriptSpec, ArgSpec } from './models';

export interface ParseOptions {
  scriptName?: string;
  argv?: string[];
  cwd?: string;
}

export function parse(opts: ParseOptions = {}): ParsedArgs {
  const { scriptName, argv: argvOverride, cwd } = opts;

  const { configPath, format } = findConfig(cwd);
  const raw = loadRaw(configPath, format);
  const config = raw.config;

  const name = scriptName ?? findScriptName(configPath, format) ?? inferFromArgv();
  if (!name) throw new RunSpecError('✗  Could not determine runnable name. Pass scriptName option.');
  if (name === 'config') throw new RunSpecError("✗  'config' is a reserved name in runspec.\n   Rename your runnable.");

  if (!(name in raw.runnables)) {
    const available = Object.keys(raw.runnables).join(', ') || '(none)';
    throw new RunSpecError(`✗  Runnable '${name}' not found.\n   Available: ${available}\n   Config: ${configPath}`);
  }

  const rawScript = inferScript(raw.runnables[name], config.autonomyDefault);

  let argv = argvOverride ?? process.argv.slice(2);
  let activeScript = rawScript;
  let activeCommand: string | undefined;

  const commands = rawScript.commands ?? {};
  if (Object.keys(commands).length > 0 && argv.length > 0 && argv[0] in commands) {
    activeCommand = argv[0];
    activeScript = commands[argv[0]];
    argv = argv.slice(1);
  }

  if (argv.includes('--help') || argv.includes('-h')) {
    printHelp(name, activeScript, activeCommand);
    process.exit(0);
  }

  let parsedValues = parseArgv(argv, activeScript.args ?? {});
  parsedValues = applyEnv(parsedValues, activeScript.args ?? {});
  parsedValues = applyDefaults(parsedValues, activeScript.args ?? {});

  raiseIfErrors(validateArgs(parsedValues, activeScript.args ?? {}));
  raiseIfErrors(validateGroups(parsedValues, activeScript.groups ?? {}));

  const coercedValues = coerceValues(parsedValues, activeScript.args ?? {});

  const autonomy = effectiveAutonomy(
    activeScript.autonomy ?? config.autonomyDefault,
    parsedValues,
    activeScript.args ?? {},
  );

  const agent = ['1', 'true', 'yes'].includes((process.env['RUNSPEC_AGENT'] ?? '').toLowerCase());

  return {
    ...coercedValues,
    __agent__: agent,
    __script__: name,
    __command__: activeCommand,
    __autonomy__: autonomy,
    __source__: configPath,
    __spec__: activeScript,
  } as ParsedArgs;
}

export function loadSpec(opts: ParseOptions = {}): ParsedArgs {
  return parse({ ...opts, argv: [] });
}

function inferFromArgv(): string {
  const argv1 = process.argv[1] ?? '';
  return path.basename(argv1, path.extname(argv1)) || 'unknown';
}

function parseArgv(argv: string[], argSpecs: Record<string, ArgSpec>): Record<string, unknown> {
  const nameMap: Record<string, string> = {};
  const shortMap: Record<string, string> = {};

  for (const [name, spec] of Object.entries(argSpecs)) {
    const norm = name.replace(/-/g, '_');
    nameMap[`--${name}`] = norm;
    nameMap[`--${norm}`] = norm;
    if (spec.short) shortMap[spec.short] = norm;
  }

  const result: Record<string, unknown> = {};
  for (const name of Object.keys(argSpecs)) {
    result[name.replace(/-/g, '_')] = undefined;
  }

  let i = 0;
  while (i < argv.length) {
    const token = argv[i];

    if (token.startsWith('--') && token.includes('=')) {
      const eqIdx = token.indexOf('=');
      const key = token.slice(0, eqIdx);
      const value = token.slice(eqIdx + 1);
      const norm = nameMap[key];
      if (norm) {
        const hyphenName = norm.replace(/_/g, '-');
        const spec = argSpecs[hyphenName] ?? argSpecs[norm] ?? {};
        result[norm] = appendOrSet(result[norm], value, spec);
      }
      i++;
      continue;
    }

    const norm = nameMap[token] ?? shortMap[token];
    if (norm) {
      const hyphenName = norm.replace(/_/g, '-');
      const spec = argSpecs[hyphenName] ?? argSpecs[norm] ?? {};
      const argType = spec.type ?? 'str';

      if (argType === 'flag') {
        result[norm] = true;
        i++;
      } else if (i + 1 < argv.length && !argv[i + 1].startsWith('-')) {
        const raw = argv[i + 1];
        const delimiter = spec.delimiter;
        const parsed: string | string[] = delimiter ? raw.split(delimiter) : raw;
        result[norm] = appendOrSet(result[norm], parsed, spec);
        i += 2;
      } else {
        result[norm] = true;
        i++;
      }
      continue;
    }

    i++;
  }

  return result;
}

function appendOrSet(current: unknown, value: unknown, spec: ArgSpec): unknown {
  if (spec.multiple) {
    if (Array.isArray(value)) return [...((current as unknown[]) ?? []), ...value];
    return [...((current as unknown[]) ?? []), value];
  }
  return value;
}

function applyEnv(parsed: Record<string, unknown>, argSpecs: Record<string, ArgSpec>): Record<string, unknown> {
  const result = { ...parsed };
  for (const [name, spec] of Object.entries(argSpecs)) {
    const norm = name.replace(/-/g, '_');
    if ((result[norm] === null || result[norm] === undefined) && spec.env) {
      const envVal = process.env[spec.env];
      if (envVal !== undefined) result[norm] = envVal;
    }
  }
  return result;
}

function applyDefaults(parsed: Record<string, unknown>, argSpecs: Record<string, ArgSpec>): Record<string, unknown> {
  const result = { ...parsed };
  for (const [name, spec] of Object.entries(argSpecs)) {
    const norm = name.replace(/-/g, '_');
    if ((result[norm] === null || result[norm] === undefined) && spec.default !== undefined && spec.default !== null) {
      result[norm] = spec.default;
    }
  }
  return result;
}

function coerceValues(parsed: Record<string, unknown>, argSpecs: Record<string, ArgSpec>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(argSpecs)) {
    const norm = name.replace(/-/g, '_');
    const value = parsed[norm];
    if (value === null || value === undefined) {
      result[norm] = undefined;
      continue;
    }
    try {
      result[norm] = coerce(value, spec);
    } catch (e) {
      throw new RunSpecError(`✗  ${(e as Error).message}`);
    }
  }
  return result;
}

export function printHelp(name: string, script: ScriptSpec, command?: string): void {
  const fullName = command ? `${name} ${command}` : name;
  const args = script.args ?? {};

  const usageParts = [fullName];
  for (const [argName, spec] of Object.entries(args)) {
    const flag = `--${argName}`;
    if (spec.type === 'flag') {
      usageParts.push(`[${flag}]`);
    } else if (spec.required) {
      usageParts.push(`${flag} <${spec.type ?? 'str'}>`);
    } else {
      usageParts.push(`[${flag} <${spec.type ?? 'str'}>]`);
    }
  }

  console.log(`Usage: ${usageParts.join(' ')}`);
  if (script.description) console.log(`\n${script.description}`);

  if (Object.keys(args).length > 0) {
    console.log('\nArguments:');
    for (const [argName, spec] of Object.entries(args)) {
      const flag = `  --${argName}`;
      const parts: string[] = [];
      if (spec.type === 'flag') parts.push('flag');
      else parts.push(spec.type ?? 'str');
      if (spec.required) parts.push('required');
      else if (spec.default !== undefined && spec.default !== null) parts.push(`default: ${spec.default}`);
      if (spec.options) parts.push(`one of: ${spec.options.join(', ')}`);
      const meta = `(${parts.join(', ')})`;
      if (spec.description) console.log(`${flag.padEnd(24)} ${spec.description}  ${meta}`);
      else console.log(`${flag.padEnd(24)} ${meta}`);
    }
  }

  if (script.autonomy) {
    console.log(`\nAutonomy: ${script.autonomy}`);
    if (script.autonomyReason) console.log(`  ${script.autonomyReason}`);
  }

  console.log('\n  -h, --help    Show this message and exit');
}
