import * as fs from 'fs';
import * as path from 'path';
import { parse as parseTOML } from 'smol-toml';

export function findConfig(start?: string): { configPath: string; format: 'pyproject' | 'runspec' } {
  let dir = path.resolve(start ?? process.cwd());

  while (true) {
    const pyproject = path.join(dir, 'pyproject.toml');
    if (fs.existsSync(pyproject) && hasRunspecSection(pyproject)) {
      return { configPath: pyproject, format: 'pyproject' };
    }

    const runspecToml = path.join(dir, 'runspec.toml');
    if (fs.existsSync(runspecToml)) {
      return { configPath: runspecToml, format: 'runspec' };
    }

    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  throw new Error(
    "No runspec configuration found.\nExpected one of:\n  - pyproject.toml with [tool.runspec] section\n  - runspec.toml\n\nRun 'runspec check' to validate your project setup.",
  );
}

export function findScriptName(configPath: string, format: 'pyproject' | 'runspec'): string | undefined {
  if (format !== 'pyproject') return undefined;

  try {
    const content = fs.readFileSync(configPath, 'utf-8');
    const data = parseTOML(content) as Record<string, unknown>;
    const argv1 = process.argv[1] ?? '';
    const caller = path.basename(argv1, path.extname(argv1));
    if (!caller) return undefined;

    const projectScripts = (data as any)?.project?.scripts ?? {};
    if (caller in projectScripts) return caller;

    const poetryScripts = (data as any)?.tool?.poetry?.scripts ?? {};
    if (caller in poetryScripts) return caller;

    return caller;
  } catch {
    return undefined;
  }
}

function hasRunspecSection(pyprojectPath: string): boolean {
  try {
    const content = fs.readFileSync(pyprojectPath, 'utf-8');
    const data = parseTOML(content) as Record<string, unknown>;
    return 'runspec' in ((data as any)?.tool ?? {});
  } catch {
    return false;
  }
}
