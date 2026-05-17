import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';
import { spawnSync } from 'child_process';
import { findConfig } from './finder';
import { loadRaw } from './loader';
import { inferScript } from './inference';
import { buildSchema } from './cli';

const MCP_PROTOCOL_VERSION = '2024-11-05';
const ERR_PARSE = -32700;
const ERR_METHOD_NOT_FOUND = -32601;
const ERR_INVALID_PARAMS = -32602;

export function serve(): void {
  let configPath: string;
  let format: 'pyproject' | 'runspec';

  try {
    ({ configPath, format } = findConfig(process.cwd()));
  } catch (e) {
    process.stderr.write(`runspec serve: ${(e as Error).message}\n`);
    process.exit(1);
  }

  const raw = loadRaw(configPath, format);
  const config = raw.config;

  const tools: Record<string, Record<string, unknown>> = {};
  const argSpecs: Record<string, Record<string, unknown>> = {};

  for (const [name, runnable] of Object.entries(raw.runnables)) {
    const inferred = inferScript(runnable, config.autonomyDefault);
    tools[name] = buildSchema(name, inferred, 'mcp');
    argSpecs[name] = inferred.args ?? {};
  }

  const serverName = serverNameFromConfig(config as unknown as Record<string, unknown>);
  const binDir = path.join(path.dirname(configPath), 'node_modules', '.bin');

  mcpLoop(tools, argSpecs, binDir, serverName);
}

function mcpLoop(
  tools: Record<string, Record<string, unknown>>,
  argSpecs: Record<string, Record<string, unknown>>,
  binDir: string,
  serverName: string,
): void {
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

  rl.on('line', (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    let request: Record<string, unknown>;
    try {
      request = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      writeMsg({ jsonrpc: '2.0', id: null, error: { code: ERR_PARSE, message: 'Parse error' } });
      return;
    }

    const response = dispatch(request, tools, argSpecs, binDir, serverName);
    if (response !== null) writeMsg(response);
  });
}

function dispatch(
  request: Record<string, unknown>,
  tools: Record<string, Record<string, unknown>>,
  argSpecs: Record<string, Record<string, unknown>>,
  binDir: string,
  serverName: string,
): Record<string, unknown> | null {
  const method = (request['method'] as string) ?? '';
  const reqId = request['id'];

  if (reqId === undefined || reqId === null) return null;

  if (method === 'initialize') return handleInitialize(reqId, serverName);
  if (method === 'tools/list') return handleToolsList(reqId, tools);
  if (method === 'tools/call') {
    return handleToolsCall(reqId, (request['params'] ?? {}) as Record<string, unknown>, tools, argSpecs, binDir);
  }

  return { jsonrpc: '2.0', id: reqId, error: { code: ERR_METHOD_NOT_FOUND, message: `Method not found: ${method}` } };
}

function handleInitialize(reqId: unknown, serverName: string): Record<string, unknown> {
  const version = '0.3.0';
  return {
    jsonrpc: '2.0',
    id: reqId,
    result: {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: { tools: {} },
      serverInfo: { name: serverName, version },
    },
  };
}

function handleToolsList(reqId: unknown, tools: Record<string, Record<string, unknown>>): Record<string, unknown> {
  return { jsonrpc: '2.0', id: reqId, result: { tools: Object.values(tools) } };
}

function handleToolsCall(
  reqId: unknown,
  params: Record<string, unknown>,
  tools: Record<string, Record<string, unknown>>,
  argSpecs: Record<string, Record<string, unknown>>,
  binDir: string,
): Record<string, unknown> {
  const name = (params['name'] as string) ?? '';
  const args = (params['arguments'] as Record<string, unknown>) ?? {};

  if (!(name in tools)) {
    return { jsonrpc: '2.0', id: reqId, error: { code: ERR_INVALID_PARAMS, message: `Unknown tool: ${name}` } };
  }

  const cmd = findScript(name, binDir);
  if (!cmd) {
    return {
      jsonrpc: '2.0',
      id: reqId,
      result: {
        content: [{ type: 'text', text: `Script not found in ${binDir}: ${name}` }],
        isError: true,
      },
    };
  }

  const argv = argsToArgv(args, argSpecs[name] ?? {});
  const env = { ...process.env, RUNSPEC_AGENT: '1' };

  const result = spawnSync(cmd, argv, { encoding: 'utf-8', env });

  if (result.status === 0) {
    return {
      jsonrpc: '2.0',
      id: reqId,
      result: { content: [{ type: 'text', text: result.stdout ?? '' }], isError: false },
    };
  }

  const parts = [`exit_code: ${result.status ?? 'unknown'}`];
  if (result.stdout) parts.push(`stdout:\n${result.stdout.trimEnd()}`);
  if (result.stderr) parts.push(`stderr:\n${result.stderr.trimEnd()}`);

  return {
    jsonrpc: '2.0',
    id: reqId,
    result: { content: [{ type: 'text', text: parts.join('\n') }], isError: true },
  };
}

function argsToArgv(args: Record<string, unknown>, argSpecs: Record<string, unknown>): string[] {
  const argv: string[] = [];

  for (const [argName, spec] of Object.entries(argSpecs)) {
    const s = spec as Record<string, unknown>;
    let value = args[argName] ?? args[argName.replace(/-/g, '_')];
    if (value === null || value === undefined) continue;

    const flag = `--${argName}`;
    const argType = (s['type'] as string) ?? 'str';

    if (argType === 'flag') {
      if (value) argv.push(flag);
    } else if (s['multiple'] && Array.isArray(value)) {
      for (const item of value) argv.push(flag, String(item));
    } else {
      argv.push(flag, String(value));
    }
  }

  return argv;
}

function findScript(name: string, binDir: string): string | null {
  const candidate = path.join(binDir, name);
  if (fs.existsSync(candidate)) return candidate;
  const candidateExe = path.join(binDir, name + '.exe');
  if (fs.existsSync(candidateExe)) return candidateExe;
  return null;
}

function serverNameFromConfig(config: Record<string, unknown>): string {
  const name = config['name'];
  if (name && typeof name === 'string') return name;
  return path.basename(path.dirname(process.execPath));
}

function writeMsg(response: Record<string, unknown>): void {
  process.stdout.write(JSON.stringify(response) + '\n');
}
