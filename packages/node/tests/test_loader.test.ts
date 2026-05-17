import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { loadRaw } from '../src/loader';

function tmpDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'runspec-test-'));
}

afterEach(() => {
  // tmp dirs cleaned up by OS
});

// ── runspec.toml format ───────────────────────────────────────────────────────

test('loads simple runspec.toml', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[greet]
description = "Greet someone"
autonomy = "autonomous"

[greet.args]
name = {type = "str"}
loud = {default = false}
`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.runnables['greet']).toBeDefined();
  expect(raw.runnables['greet'].description).toBe('Greet someone');
  expect(raw.runnables['greet'].args['name'].type).toBe('str');
  expect(raw.runnables['greet'].args['loud'].default).toBe(false);
});

test('normalises hyphenated field names', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[deploy]
autonomy-reason = "Irreversible"
`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.runnables['deploy'].autonomyReason).toBe('Irreversible');
});

test('parses config section', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[config]
autonomy-default = "autonomous"
version = "1"

[greet]
description = "hi"
`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.config.autonomyDefault).toBe('autonomous');
  expect(raw.config.version).toBe('1');
});

test('config excluded from runnables', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[config]
autonomy-default = "confirm"

[greet]
description = "hi"
`);
  const raw = loadRaw(file, 'runspec');
  expect('config' in raw.runnables).toBe(false);
  expect('greet' in raw.runnables).toBe(true);
});

// ── pyproject.toml format ─────────────────────────────────────────────────────

test('loads pyproject.toml format', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'pyproject.toml');
  fs.writeFileSync(file, `
[project]
name = "myproject"

[tool.runspec.greet]
description = "Greet"
autonomy = "confirm"

[tool.runspec.greet.args]
name = {type = "str"}
`);
  const raw = loadRaw(file, 'pyproject');
  expect(raw.runnables['greet']).toBeDefined();
  expect(raw.runnables['greet'].args['name'].type).toBe('str');
});

test('reads entry points from pyproject.toml', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'pyproject.toml');
  fs.writeFileSync(file, `
[project.scripts]
greet = "myapp.greet:main"

[tool.runspec.greet]
description = "Greet"
`);
  const raw = loadRaw(file, 'pyproject');
  expect(raw.entryPoints['greet']).toBe('myapp.greet:main');
});

// ── arg normalisation ─────────────────────────────────────────────────────────

test('normalises bare value shorthand', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[greet]
description = "hi"

[greet.args]
loud = false
times = 1
`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.runnables['greet'].args['loud'].default).toBe(false);
  expect(raw.runnables['greet'].args['times'].default).toBe(1);
});

test('normalises range field', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[greet]
description = "hi"

[greet.args]
workers = {default = 4, range = [1, 32]}
`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.runnables['greet'].args['workers'].range).toEqual([1, 32]);
});

test('normalises group fields', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `
[pipeline]
description = "hi"

[pipeline.groups.formats]
exclusive = true
args = ["json", "csv"]
`);
  const raw = loadRaw(file, 'runspec');
  const group = raw.runnables['pipeline'].groups['formats'];
  expect(group.exclusive).toBe(true);
  expect(group.args).toEqual(['json', 'csv']);
});

// ── defaults ──────────────────────────────────────────────────────────────────

test('autonomy-default falls back to confirm', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'runspec.toml');
  fs.writeFileSync(file, `[greet]\ndescription = "hi"\n`);
  const raw = loadRaw(file, 'runspec');
  expect(raw.config.autonomyDefault).toBe('confirm');
});
