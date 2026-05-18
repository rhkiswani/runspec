import * as fs from 'fs';
import * as path from 'path';

export function findConfig(start?: string): { configPath: string } {
  let dir = path.resolve(start ?? process.cwd());

  while (true) {
    const runspecToml = path.join(dir, 'runspec.toml');
    if (fs.existsSync(runspecToml)) {
      return { configPath: runspecToml };
    }

    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  throw new Error(
    "No runspec configuration found.\nExpected runspec.toml inside your package directory.\n\nRun 'runspec init' to create one.",
  );
}
