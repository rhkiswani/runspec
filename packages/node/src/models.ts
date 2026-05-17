export interface RawConfig {
  autonomyDefault: string;
  lang?: string;
  version: string;
}

export interface ArgSpec {
  name: string;
  type?: string;
  required?: boolean;
  default?: unknown;
  description?: string;
  options?: string[];
  range?: [number, number];
  multiple?: boolean;
  delimiter?: string;
  short?: string;
  env?: string;
  deprecated?: string;
  autonomy?: string;
  ui?: string;
  meta?: Record<string, unknown>;
}

export interface GroupSpec {
  name: string;
  args: string[];
  exclusive?: boolean;
  inclusive?: boolean;
  atLeastOne?: boolean;
  exactlyOne?: boolean;
  condition?: string;
  requires?: string[];
}

export interface ScriptSpec {
  name: string;
  description?: string;
  autonomy?: string;
  autonomyReason?: string;
  output?: string;
  args: Record<string, ArgSpec>;
  groups: Record<string, GroupSpec>;
  commands: Record<string, ScriptSpec>;
}

export interface RawSpec {
  config: RawConfig;
  runnables: Record<string, ScriptSpec>;
  entryPoints: Record<string, string>;
}

export interface ParsedArgs {
  [key: string]: unknown;
  readonly __agent__: boolean;
  readonly __script__: string;
  readonly __command__: string | undefined;
  readonly __autonomy__: string;
  readonly __source__: string;
  readonly __spec__: ScriptSpec;
}
