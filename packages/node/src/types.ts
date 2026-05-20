import * as path from 'path';
import type { ArgSpec } from './models';
import { formatInvalidChoice } from './errors';

export type TypeCoercer = (value: unknown, spec: ArgSpec) => unknown;

const registry = new Map<string, TypeCoercer>();

export function registerType(name: string, coercer: TypeCoercer): void {
  registry.set(name, coercer);
}

export function coerce(value: unknown, spec: ArgSpec): unknown {
  const typeName = spec.type ?? 'str';
  const coercer = registry.get(typeName);
  if (!coercer) {
    throw new TypeError(
      `Unknown type '${typeName}' for argument '${spec.name}'. Registered types: ${[...registry.keys()].sort().join(', ')}\nRegister custom types with registerType().`,
    );
  }
  try {
    return coercer(value, spec);
  } catch (e) {
    throw new Error(
      `Cannot coerce value ${JSON.stringify(value)} to type '${typeName}' for argument '--${spec.name ?? '?'}': ${(e as Error).message}`,
    );
  }
}

export function listTypes(): string[] {
  return [...registry.keys()].sort();
}

function coerceStr(value: unknown): string {
  return String(value);
}

function coerceInt(value: unknown, spec: ArgSpec): number {
  const n = Number(value);
  if (!Number.isFinite(n) || !Number.isInteger(n)) {
    throw new Error(`invalid integer: ${JSON.stringify(value)}`);
  }
  checkRange(n, spec);
  return n;
}

function coerceFloat(value: unknown, spec: ArgSpec): number {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(`invalid number: ${JSON.stringify(value)}`);
  checkRange(n, spec);
  return n;
}

function coerceBool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    if (['true', '1', 'yes', 'on'].includes(value.toLowerCase())) return true;
    if (['false', '0', 'no', 'off'].includes(value.toLowerCase())) return false;
  }
  throw new Error(`Cannot interpret ${JSON.stringify(value)} as bool`);
}

function coerceFlag(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  return Boolean(value);
}

function coercePath(value: unknown): string {
  return path.resolve(String(value));
}

function coerceChoice(value: unknown, spec: ArgSpec): string {
  const v = String(value);
  const options = spec.options ?? [];
  if (options.length > 0 && !options.includes(v)) {
    throw new Error(formatInvalidChoice(v, options, spec.name ?? '?'));
  }
  return v;
}

function checkRange(value: number, spec: ArgSpec): void {
  if (spec.range) {
    const [min, max] = spec.range;
    if (value < min || value > max) {
      throw new Error(`Value ${value} is out of range [${min}, ${max}]`);
    }
  }
}

registerType('str', coerceStr);
registerType('int', coerceInt);
registerType('float', coerceFloat);
registerType('bool', coerceBool);
registerType('flag', coerceFlag);
registerType('path', coercePath);
registerType('choice', coerceChoice);
registerType('rest', (v) => (Array.isArray(v) ? v : []));
