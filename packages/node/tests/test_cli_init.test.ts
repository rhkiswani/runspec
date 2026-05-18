import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { execFileSync } from 'child_process';

const CLI = path.resolve(__dirname, '../bin/runspec.js');

function tmpDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'runspec-init-test-'));
}

function runInit(dir: string, extraArgs: string[] = []): { stdout: string; stderr: string } {
  try {
    const stdout = execFileSync('node', [CLI, 'init', ...extraArgs], { cwd: dir, encoding: 'utf-8' });
    return { stdout, stderr: '' };
  } catch (e: any) {
    return { stdout: e.stdout ?? '', stderr: e.stderr ?? '' };
  }
}

test('creates runspec.toml and .ts stub by default', () => {
  const dir = tmpDir();
  const { stdout } = runInit(dir, ['--name', 'greet']);
  expect(fs.existsSync(path.join(dir, 'runspec.toml'))).toBe(true);
  expect(fs.existsSync(path.join(dir, 'greet.ts'))).toBe(true);
  expect(stdout).toContain('Created runspec.toml');
  expect(stdout).toContain('Created greet.ts');
});

test('runspec.toml contains the runnable name', () => {
  const dir = tmpDir();
  runInit(dir, ['--name', 'deploy']);
  const toml = fs.readFileSync(path.join(dir, 'runspec.toml'), 'utf-8');
  expect(toml).toContain('[deploy]');
});

test('typescript stub imports parse from runspec', () => {
  const dir = tmpDir();
  runInit(dir, ['--name', 'greet']);
  const ts = fs.readFileSync(path.join(dir, 'greet.ts'), 'utf-8');
  expect(ts).toContain("import { parse } from 'runspec'");
  expect(ts).toContain('function main()');
  expect(ts).toContain('main();');
});

test('--lang javascript generates .js stub', () => {
  const dir = tmpDir();
  runInit(dir, ['--name', 'greet', '--lang', 'javascript']);
  expect(fs.existsSync(path.join(dir, 'greet.js'))).toBe(true);
  const js = fs.readFileSync(path.join(dir, 'greet.js'), 'utf-8');
  expect(js).toContain("require('runspec')");
  expect(js).toContain('main();');
});

test('--lang python generates .py stub', () => {
  const dir = tmpDir();
  runInit(dir, ['--name', 'greet', '--lang', 'python']);
  expect(fs.existsSync(path.join(dir, 'greet.py'))).toBe(true);
  const py = fs.readFileSync(path.join(dir, 'greet.py'), 'utf-8');
  expect(py).toContain('from runspec import parse');
  expect(py).toContain('if __name__ == "__main__"');
});

test('does not overwrite existing stub', () => {
  const dir = tmpDir();
  const stubPath = path.join(dir, 'greet.ts');
  fs.writeFileSync(stubPath, '// existing\n', 'utf-8');
  const { stdout } = runInit(dir, ['--name', 'greet']);
  expect(fs.readFileSync(stubPath, 'utf-8')).toBe('// existing\n');
  expect(stdout).toContain('already exists — skipped');
});

test('fails if runspec.toml already exists', () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, 'runspec.toml'), '[greet]\n', 'utf-8');
  const { stdout } = runInit(dir, ['--name', 'greet']);
  expect(stdout).toContain('already exists');
  expect(fs.existsSync(path.join(dir, 'greet.ts'))).toBe(false);
});

test('unknown --lang exits with error', () => {
  const dir = tmpDir();
  const { stdout } = runInit(dir, ['--name', 'greet', '--lang', 'ruby']);
  expect(stdout).toContain('Unknown --lang');
});
