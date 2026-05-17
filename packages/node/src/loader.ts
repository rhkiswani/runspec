import * as fs from 'fs';
import { parse as parseTOML } from 'smol-toml';
import type { RawConfig, RawSpec, ScriptSpec, ArgSpec, GroupSpec } from './models';

export function loadRaw(configPath: string, format: 'pyproject' | 'runspec'): RawSpec {
  const content = fs.readFileSync(configPath, 'utf-8');
  const data = parseTOML(content) as Record<string, unknown>;

  let raw: Record<string, unknown>;
  let entryPoints: Record<string, string> = {};

  if (format === 'pyproject') {
    raw = ((data as any)?.tool?.runspec ?? {}) as Record<string, unknown>;
    entryPoints = readEntryPoints(data);
  } else {
    raw = data;
  }

  const runnablesRaw: Record<string, Record<string, unknown>> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (key !== 'config' && typeof value === 'object' && value !== null && !Array.isArray(value)) {
      runnablesRaw[key] = value as Record<string, unknown>;
    }
  }

  return {
    config: normaliseConfig((raw['config'] ?? {}) as Record<string, unknown>),
    runnables: normaliseRunnables(runnablesRaw),
    entryPoints,
  };
}

function normaliseConfig(raw: Record<string, unknown>): RawConfig {
  return {
    autonomyDefault: (raw['autonomy-default'] as string | undefined) ?? 'confirm',
    lang: raw['lang'] as string | undefined,
    version: String(raw['version'] ?? '1'),
  };
}

function normaliseRunnables(raw: Record<string, Record<string, unknown>>): Record<string, ScriptSpec> {
  return Object.fromEntries(Object.entries(raw).map(([name, data]) => [name, normaliseScript(name, data)]));
}

function normaliseScript(name: string, raw: Record<string, unknown>): ScriptSpec {
  return {
    name,
    description: raw['description'] as string | undefined,
    autonomy: raw['autonomy'] as string | undefined,
    autonomyReason: raw['autonomy-reason'] as string | undefined,
    output: raw['output'] as string | undefined,
    args: normaliseArgs((raw['args'] ?? {}) as Record<string, unknown>),
    groups: normaliseGroups((raw['groups'] ?? {}) as Record<string, unknown>),
    commands: normaliseCommands((raw['commands'] ?? {}) as Record<string, Record<string, unknown>>),
  };
}

function normaliseArgs(raw: Record<string, unknown>): Record<string, ArgSpec> {
  return Object.fromEntries(
    Object.entries(raw).map(([name, value]) => {
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        return [name, normaliseArg(name, value as Record<string, unknown>)];
      }
      return [name, normaliseArg(name, { default: value })];
    }),
  );
}

function normaliseArg(name: string, raw: Record<string, unknown>): ArgSpec {
  return {
    name,
    type: (raw['type'] as string | undefined) ?? undefined,
    required: raw['required'] as boolean | undefined,
    default: raw['default'],
    description: raw['description'] as string | undefined,
    options: raw['options'] as string[] | undefined,
    range: raw['range'] as [number, number] | undefined,
    multiple: (raw['multiple'] as boolean | undefined) ?? false,
    delimiter: raw['delimiter'] as string | undefined,
    short: raw['short'] as string | undefined,
    env: raw['env'] as string | undefined,
    deprecated: raw['deprecated'] as string | undefined,
    autonomy: raw['autonomy'] as string | undefined,
    ui: raw['ui'] as string | undefined,
    meta: raw['meta'] as Record<string, unknown> | undefined,
  };
}

function normaliseGroups(raw: Record<string, unknown>): Record<string, GroupSpec> {
  return Object.fromEntries(
    Object.entries(raw).map(([name, data]) => {
      const g = data as Record<string, unknown>;
      return [
        name,
        {
          name,
          args: (g['args'] as string[]) ?? [],
          exclusive: (g['exclusive'] as boolean | undefined) ?? false,
          inclusive: (g['inclusive'] as boolean | undefined) ?? false,
          atLeastOne: (g['at-least-one'] as boolean | undefined) ?? false,
          exactlyOne: (g['exactly-one'] as boolean | undefined) ?? false,
          condition: g['if'] as string | undefined,
          requires: (g['requires'] as string[] | undefined) ?? [],
        } satisfies GroupSpec,
      ];
    }),
  );
}

function normaliseCommands(raw: Record<string, Record<string, unknown>>): Record<string, ScriptSpec> {
  return Object.fromEntries(Object.entries(raw).map(([name, data]) => [name, normaliseScript(name, data)]));
}

function readEntryPoints(data: Record<string, unknown>): Record<string, string> {
  const projectScripts = (data as any)?.project?.scripts;
  if (projectScripts && typeof projectScripts === 'object') return projectScripts as Record<string, string>;
  const poetryScripts = (data as any)?.tool?.poetry?.scripts;
  if (poetryScripts && typeof poetryScripts === 'object') return poetryScripts as Record<string, string>;
  return {};
}
