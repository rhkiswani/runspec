import { validateArgs, validateGroups, raiseIfErrors } from '../src/validator';
import { RunSpecError } from '../src/errors';
import type { ArgSpec, GroupSpec } from '../src/models';

function argSpec(overrides: Partial<ArgSpec> = {}): ArgSpec {
  return { name: 'test', ...overrides } as ArgSpec;
}

function groupSpec(overrides: Partial<GroupSpec> = {}): GroupSpec {
  return { name: 'g', args: [], ...overrides } as GroupSpec;
}

// ── validateArgs ──────────────────────────────────────────────────────────────

test('passes when required arg present', () => {
  const errors = validateArgs({ name: 'Alice' }, { name: argSpec({ name: 'name', required: true }) });
  expect(errors).toHaveLength(0);
});

test('errors when required arg missing', () => {
  const errors = validateArgs({ name: undefined }, { name: argSpec({ name: 'name', required: true }) });
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain('--name');
});

test('passes when optional arg missing', () => {
  const errors = validateArgs({ verbose: undefined }, { verbose: argSpec({ name: 'verbose', required: false }) });
  expect(errors).toHaveLength(0);
});

test('error message includes type', () => {
  const errors = validateArgs(
    { input: undefined },
    { input: argSpec({ name: 'input', required: true, type: 'path' }) },
  );
  expect(errors[0]).toContain('path');
});

test('error message includes env tip when env set', () => {
  const errors = validateArgs(
    { apiKey: undefined },
    { apiKey: argSpec({ name: 'api-key', required: true, env: 'API_KEY' }) },
  );
  expect(errors[0]).toContain('API_KEY');
});

// ── validateGroups ────────────────────────────────────────────────────────────

test('exclusive: passes when one provided', () => {
  const errors = validateGroups({ format: 'json', raw: undefined }, { g: groupSpec({ args: ['format', 'raw'], exclusive: true }) });
  expect(errors).toHaveLength(0);
});

test('exclusive: errors when two provided', () => {
  const errors = validateGroups({ format: 'json', raw: true }, { g: groupSpec({ args: ['format', 'raw'], exclusive: true }) });
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain('Conflicting');
});

test('inclusive: passes when all provided', () => {
  const errors = validateGroups(
    { apiKey: 'x', apiEndpoint: 'y' },
    { g: groupSpec({ args: ['apiKey', 'apiEndpoint'], inclusive: true }) },
  );
  expect(errors).toHaveLength(0);
});

test('inclusive: errors when partial', () => {
  const errors = validateGroups(
    { apiKey: 'x', apiEndpoint: undefined },
    { g: groupSpec({ args: ['apiKey', 'apiEndpoint'], inclusive: true }) },
  );
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain('Incomplete');
});

test('atLeastOne: passes when one provided', () => {
  const errors = validateGroups({ a: 'x', b: undefined }, { g: groupSpec({ args: ['a', 'b'], atLeastOne: true }) });
  expect(errors).toHaveLength(0);
});

test('atLeastOne: errors when none provided', () => {
  const errors = validateGroups({ a: undefined, b: undefined }, { g: groupSpec({ args: ['a', 'b'], atLeastOne: true }) });
  expect(errors).toHaveLength(1);
});

test('exactlyOne: passes when exactly one provided', () => {
  const errors = validateGroups({ a: 'x', b: undefined }, { g: groupSpec({ args: ['a', 'b'], exactlyOne: true }) });
  expect(errors).toHaveLength(0);
});

test('exactlyOne: errors when none provided', () => {
  const errors = validateGroups({ a: undefined, b: undefined }, { g: groupSpec({ args: ['a', 'b'], exactlyOne: true }) });
  expect(errors).toHaveLength(1);
});

test('exactlyOne: errors when two provided', () => {
  const errors = validateGroups({ a: 'x', b: 'y' }, { g: groupSpec({ args: ['a', 'b'], exactlyOne: true }) });
  expect(errors).toHaveLength(1);
});

// ── raiseIfErrors ─────────────────────────────────────────────────────────────

test('raiseIfErrors does not throw on empty list', () => {
  expect(() => raiseIfErrors([])).not.toThrow();
});

test('raiseIfErrors throws RunSpecError with all messages', () => {
  expect(() => raiseIfErrors(['error one', 'error two'])).toThrow(RunSpecError);
});

test('raiseIfErrors message joins errors', () => {
  try {
    raiseIfErrors(['first', 'second']);
    fail('should have thrown');
  } catch (e) {
    expect((e as Error).message).toContain('first');
    expect((e as Error).message).toContain('second');
  }
});
