"""
cli.py — The runspec command-line interface.

Commands:
    runspec init    [--name <name>] [--lang python|typescript|javascript] [--example]
    runspec local   [--format text|json|mcp|openai|anthropic] [--script <name>]
    runspec serve   [--dev] [--registry <url>] [--name <name>] ...
    runspec jump    [<tool>] [--host <host>] [--registry <url>] [-- tool-args...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    """Entry point for the runspec CLI binary."""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return

    command = args[0]
    rest = args[1:]

    commands = {
        "init": cmd_init,
        "local": cmd_local,
        "serve": cmd_serve,
        "jump": cmd_jump,
    }

    if command not in commands:
        print(f"✗  Unknown command: {command}")
        print(f"   Available commands: {', '.join(commands)}")
        sys.exit(1)

    commands[command](rest)


def cmd_local(args: list[str]) -> None:
    """List installed runnables with inline validation, or emit schemas."""
    fmt = _get_flag(args, "--format", default="text")
    script_name = _get_flag(args, "--script")

    discovered = _deduplicate(_discover_installed())

    if script_name:
        discovered = [d for d in discovered if d["runnable"] == script_name]

    if not discovered:
        print("No runspec-aware runnables found in this environment.")
        print("Install a package that declares 'runspec' as a dependency,")
        print("or run 'pip install -e .' from your project directory.")
        return

    if fmt == "text":
        _print_local_text(discovered)
    elif fmt == "json":
        print(json.dumps(discovered, indent=2, default=str))
    elif fmt in ("mcp", "openai", "anthropic"):
        schema = _emit_all(discovered, fmt)
        print(json.dumps(schema, indent=2, default=str))
    else:
        print(f"✗  Unknown format: {fmt}")
        print("   Available formats: text, json, mcp, openai, anthropic")
        sys.exit(1)


def cmd_serve(args: list[str]) -> None:
    """Start the MCP stdio server for this environment."""
    from runspec.serve import serve

    registry_url = _get_flag(args, "--registry")
    name = _get_flag(args, "--name")
    registry_key = _get_flag(args, "--registry-key")
    registry_cert = _get_flag(args, "--registry-cert")
    dev = "--dev" in args
    serve(registry_url=registry_url, name=name, registry_key=registry_key, registry_cert=registry_cert, dev=dev)


def cmd_jump(args: list[str]) -> None:
    """List or run tools on a jump box via SSH."""
    from runspec.run import list_registry_tools, run_remote

    if "--" in args:
        sep = args.index("--")
        runspec_args = args[:sep]
        tool_args = args[sep + 1 :]
    else:
        runspec_args = args
        tool_args = []

    host = _get_flag(runspec_args, "--host")
    registry = _get_flag(runspec_args, "--registry")
    registry_key = _get_flag(runspec_args, "--registry-key")
    registry_cert = _get_flag(runspec_args, "--registry-cert")
    ssh_user = _get_flag(runspec_args, "--user")
    ssh_key = _get_flag(runspec_args, "--ssh-key")
    no_host_key_check = "--no-host-key-check" in runspec_args
    fmt = _get_flag(runspec_args, "--format", default="text")

    tool_name = next((a for a in runspec_args if not a.startswith("-")), None)

    if tool_name is None:
        # No tool name — list available tools from registry
        if not registry:
            # Try local config for registry URL
            from runspec.finder import find_config
            from runspec.loader import load_raw

            try:
                config_path = find_config(Path.cwd())
                raw = load_raw(config_path)
                registry = raw["config"].get("registry")
            except FileNotFoundError:
                pass

        if not registry:
            print("✗  --registry <url> is required to list jump box tools")
            print("   Or set [config] registry in your runspec.toml")
            sys.exit(1)

        tools = list_registry_tools(registry, api_key=registry_key, cert=registry_cert)
        if not tools:
            print("No tools found in registry.")
            return

        if fmt == "json":
            print(json.dumps(tools, indent=2))
            return

        print(f"Tools available via {registry}:\n")
        for t in tools:
            hosts_str = ", ".join(t.get("hosts", []))
            desc = t.get("description") or ""
            print(f"  {t['name']:<24} {desc}")
            if hosts_str:
                print(f"  {'':24} hosts: {hosts_str}")
        return

    if not host:
        print("✗  --host <host> is required to run on a jump box")
        sys.exit(1)

    effective_registry = registry
    if not effective_registry:
        from runspec.finder import find_config
        from runspec.loader import load_raw

        try:
            config_path = find_config(Path.cwd())
            raw = load_raw(config_path)
            effective_registry = raw["config"].get("registry")
        except FileNotFoundError:
            pass

    if not effective_registry:
        print("✗  --registry is required for jump box execution (or set [config] registry in runspec.toml)")
        sys.exit(1)

    rc = run_remote(
        tool_name,
        tool_args,
        host=host,
        registry_url=effective_registry,
        ssh_user=ssh_user,
        ssh_key=ssh_key,
        no_host_key_check=no_host_key_check,
        api_key=registry_key,
        cert=registry_cert,
    )
    sys.exit(rc)


def cmd_init(args: list[str]) -> None:
    """Scaffold a new runnable — config and code stub."""
    name_flag = _get_flag(args, "--name")
    lang_flag = _get_flag(args, "--lang") or "python"
    example = "--example" in args
    write_project, project_root_arg = _get_optional_flag(args, "--write-project", default="..")

    cwd = Path.cwd()
    pkg_name = _sanitize_name(cwd.name)
    runnable_name = name_flag or ("clean" if example else pkg_name)
    runspec_toml = cwd / "runspec.toml"

    _init_runspec_toml(runspec_toml, runnable_name, example=example)
    _init_code_stub(cwd, runnable_name, lang_flag, example=example)

    if write_project:
        project_root = (cwd / project_root_arg).resolve()
        _init_package_init(cwd)
        _init_pyproject(project_root, runnable_name, pkg_name)
        _print_next_steps(install_from=project_root_arg)
    else:
        _print_pyproject_snippet(runnable_name, pkg_name)
        _print_next_steps(install_from=None)


def _sanitize_name(raw: str) -> str:
    """Convert a directory name into a valid TOML key."""
    import re

    s = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return s or "myscript"


def _init_runspec_toml(path: Path, name: str, example: bool = False) -> None:
    if path.exists():
        print(f"✗  {path.name} already exists — already initialized")
        print(f"   Edit {path.name} directly to add more runnables.")
        sys.exit(1)

    content = (
        _build_example_toml(name)
        if example
        else (f'[{name}]\ndescription = "Describe what {name} does"\nautonomy    = "confirm"\n\n[{name}.args]\n# example = {{type = "str", description = "An example argument"}}\n')
    )
    _write_and_verify(path, content, None)
    print(f"  ✓  Created runspec.toml with [{name}] runnable")


def _build_example_toml(name: str) -> str:
    return (
        f"[{name}]\n"
        f'description = "Find and optionally delete stale temporary files in a directory"\n'
        f'autonomy    = "confirm"\n'
        f"\n"
        f"[{name}.args]\n"
        f'directory  = {{type = "path",   description = "Directory to scan",                            default = "."}}\n'
        f'pattern    = {{type = "str",    description = "Glob pattern to match",                        default = "*.tmp"}}\n'
        f'older_than = {{type = "int",    description = "Only match files older than N days",           default = 7}}\n'
        f'format     = {{type = "choice", description = "Output format", options = ["text", "json"],    default = "text"}}\n'
        f'delete     = {{type = "flag",   description = "Delete matched files (asks for confirmation)", default = false}}\n'
    )


_EXAMPLE_PYTHON_STUB = """\
import json
import time

from runspec import parse


def main():
    args = parse()

    cutoff = time.time() - args.older_than * 86400
    matches = [p for p in args.directory.glob(args.pattern) if p.is_file() and p.stat().st_mtime < cutoff]

    if not matches:
        print(f"No '{args.pattern}' files older than {args.older_than} days found in {args.directory}.")
        return

    if args.format == "json":
        data = [
            {"path": str(p), "size": p.stat().st_size, "days_old": int((time.time() - p.stat().st_mtime) / 86400)}
            for p in matches
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Found {len(matches)} file(s) matching '{args.pattern}' older than {args.older_than} days:")
        print()
        for p in matches:
            days = int((time.time() - p.stat().st_mtime) / 86400)
            print(f"  {p}  ({p.stat().st_size:,} bytes, {days}d old)")

    if args.delete:
        for p in matches:
            p.unlink()
        print()
        print(f"Deleted {len(matches)} file(s).")


if __name__ == "__main__":
    main()
"""

_CODE_STUB_TEMPLATES: dict[str, tuple[str, str]] = {
    "python": (
        ".py",
        'from runspec import parse\n\n\ndef main():\n    args = parse()\n    # your logic here\n\n\nif __name__ == "__main__":\n    main()\n',
    ),
    "typescript": (
        ".ts",
        "import { parse } from 'runspec';\n\nfunction main(): void {\n  const args = parse();\n  // your logic here\n}\n\nmain();\n",
    ),
    "javascript": (
        ".js",
        "const { parse } = require('runspec');\n\nfunction main() {\n  const args = parse();\n  // your logic here\n}\n\nmain();\n",
    ),
}


def _init_code_stub(directory: Path, name: str, lang: str, example: bool = False) -> None:
    if example and lang != "python":
        print(f"  ℹ  --example is only available for Python — using minimal stub for {lang}")
        example = False

    if lang not in _CODE_STUB_TEMPLATES:
        print(f"✗  Unknown --lang: {lang}")
        print("   Supported: python, typescript, javascript")
        sys.exit(1)

    if example:
        ext, content = ".py", _EXAMPLE_PYTHON_STUB
    else:
        ext, content = _CODE_STUB_TEMPLATES[lang]

    stub_path = directory / (name + ext)

    if stub_path.exists():
        print(f"  ℹ  {stub_path.name} already exists — skipped")
    else:
        stub_path.write_text(content, encoding="utf-8")
        print(f"  ✓  Created {stub_path.name}")


def _init_package_init(directory: Path) -> None:
    init_path = directory / "__init__.py"
    if init_path.exists():
        print("  ℹ  __init__.py already exists — skipped")
    else:
        init_path.write_text("", encoding="utf-8")
        print("  ✓  Created __init__.py")


def _init_pyproject(project_root: Path, runnable_name: str, pkg_name: str) -> None:
    pyproject = project_root / "pyproject.toml"
    entry_point = f"{pkg_name}.{runnable_name}:main"

    if pyproject.exists():
        print(f"  ℹ  {pyproject} already exists — add this entry manually:")
        print("       [project.scripts]")
        print(f'       {runnable_name} = "{entry_point}"')
    else:
        pyproject.write_text(_build_pyproject(runnable_name, pkg_name), encoding="utf-8")
        print(f"  ✓  Created {pyproject}")


def _build_pyproject(runnable_name: str, pkg_name: str) -> str:
    entry_point = f"{pkg_name}.{runnable_name}:main"
    return (
        f"[project]\n"
        f'name            = "{runnable_name}"\n'
        f'version         = "0.1.0"\n'
        f'description     = ""\n'
        f'requires-python = ">=3.10"\n'
        f'dependencies    = ["runspec"]\n'
        f"\n"
        f"[project.optional-dependencies]\n"
        f'dev = ["pytest", "ruff"]\n'
        f"\n"
        f"[project.scripts]\n"
        f'{runnable_name} = "{entry_point}"\n'
        f"\n"
        f"[build-system]\n"
        f'requires      = ["setuptools>=69.0.2", "wheel"]\n'
        f'build-backend = "setuptools.build_meta"\n'
    )


def _print_pyproject_snippet(runnable_name: str, pkg_name: str) -> None:
    entry_point = f"{pkg_name}.{runnable_name}:main"
    print()
    print("  To register this runnable, add to your pyproject.toml:")
    print()
    print("    [project.scripts]")
    print(f'    {runnable_name} = "{entry_point}"')


def _print_next_steps(install_from: str | None) -> None:
    print()
    print("  Next steps:")
    if install_from is None:
        print("    1. Move both files inside your package directory before publishing")
        print("    2. Install before running:")
        print("         pip install -e .")
        print("         uv sync              # uv")
        print("         poetry install       # poetry")
        print("    3. Run 'runspec local' to validate your setup")
    else:
        print("    1. Install before running:")
        print(f"         pip install -e {install_from}")
        print(f"         uv sync              # uv — run from {install_from}")
        print(f"         poetry install       # poetry — run from {install_from}")
        print("    2. Run 'runspec local' to validate your setup")


def _write_and_verify(path: Path, content: str, original: str | None) -> None:
    """Write content, verify it parses as valid TOML, restore on failure."""
    path.write_text(content, encoding="utf-8")
    try:
        _load_toml_file(path)
    except Exception as e:
        if original is not None:
            path.write_text(original, encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        print("✗  Generated invalid TOML — this is a bug, please report it")
        print(f"   {e}")
        sys.exit(1)


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Read a TOML file using the stdlib or tomli fallback."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as f:
        return tomllib.load(f)


# ── Schema builders ───────────────────────────────────────────────────────────


def _build_schema(name: str, script: dict[str, Any], fmt: str) -> dict[str, Any]:
    """Build a tool schema for a script in the requested format."""
    properties: dict[str, Any] = {}
    required_args: list[str] = []

    for arg_name, arg in script.get("args", {}).items():
        prop = _arg_to_json_schema(arg)
        properties[arg_name] = prop
        if arg.get("required"):
            required_args.append(arg_name)

    schema: dict[str, Any] = {
        "name": name,
        "description": script.get("description") or "",
        "x-autonomy": script.get("autonomy", "confirm"),
        "x-output": script.get("output", "text"),
        "inputSchema": {
            "type": "object",
            "properties": properties,
        },
    }

    if required_args:
        schema["inputSchema"]["required"] = required_args

    if script.get("autonomy_reason"):
        schema["x-autonomy-reason"] = script["autonomy_reason"]

    return schema


def _arg_to_json_schema(arg: dict[str, Any]) -> dict[str, Any]:
    """Convert a runspec arg spec to a JSON Schema property."""
    type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "flag": "boolean",
        "path": "string",
        "choice": "string",
    }

    prop: dict[str, Any] = {
        "type": type_map.get(arg.get("type", "str"), "string"),
    }

    if arg.get("description"):
        prop["description"] = arg["description"]

    if arg.get("default") is not None:
        prop["default"] = arg["default"]

    if arg.get("options"):
        prop["enum"] = arg["options"]

    if arg.get("range"):
        min_val, max_val = arg["range"]
        prop["minimum"] = min_val
        prop["maximum"] = max_val

    if arg.get("multiple"):
        prop = {"type": "array", "items": prop}

    return prop


# ── Discovery helpers ─────────────────────────────────────────────────────────


def _discover_installed() -> list[dict[str, Any]]:
    """Find runspec-aware packages in the current Python environment via importlib.metadata."""
    import importlib.metadata as meta

    discovered: list[dict[str, Any]] = []

    for dist in meta.distributions():
        if not _requires_runspec(dist):
            continue
        try:
            items = _check_dist_files(dist)
            if not items:
                items = _check_editable_source(dist)
            discovered.extend(items)
        except Exception:
            continue

    return discovered


def _requires_runspec(dist: Any) -> bool:
    """Return True if this distribution lists runspec as a dependency."""
    import re

    requires = dist.requires
    if not requires:
        return False
    for req in requires:
        name = re.split(r"[\s\[;>=<!]", req.strip())[0]
        if name.lower().replace("-", "_") == "runspec":
            return True
    return False


def _check_dist_files(dist: Any) -> list[dict[str, Any]]:
    """Strategy 1: look for runspec.toml shipped as package data."""
    from runspec.loader import load_raw

    if dist.files is None:
        return []

    for f in dist.files:
        if f.name == "runspec.toml":
            try:
                config_path = Path(str(f.locate())).resolve()
                raw = load_raw(config_path)
                if not raw["runnables"]:
                    return []
                return [{"source": str(config_path), "runnable": name, "spec": spec} for name, spec in raw["runnables"].items()]
            except Exception:
                pass

    return []


def _check_editable_source(dist: Any) -> list[dict[str, Any]]:
    """Strategy 2: editable install — find source via direct_url.json."""
    import json as _json
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    from runspec.loader import load_raw

    if dist.files is None:
        return []

    direct_url_file = next((f for f in dist.files if f.name == "direct_url.json"), None)
    if direct_url_file is None:
        return []

    try:
        data = _json.loads(direct_url_file.locate().read_text(encoding="utf-8"))
    except Exception:
        return []

    if not data.get("dir_info", {}).get("editable"):
        return []

    url = data.get("url", "")
    if not url.startswith("file://"):
        return []

    source_dir = Path(url2pathname(urlparse(url).path)).resolve()
    if not source_dir.is_dir():
        return []

    discovered: list[dict[str, Any]] = []
    try:
        for subdir in sorted(source_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            candidate = subdir / "runspec.toml"
            if not candidate.exists():
                continue
            try:
                raw = load_raw(candidate)
                for name, spec in raw["runnables"].items():
                    discovered.append({"source": str(candidate), "runnable": name, "spec": spec})
            except Exception:
                continue
    except PermissionError:
        pass

    return discovered


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate (resolved_source_path, runnable_name) pairs."""
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(Path(item["source"]).resolve()), item["runnable"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _emit_all(discovered: list[dict[str, Any]], fmt: str) -> dict[str, Any]:
    """Emit all discovered runnables as a unified schema."""
    tools = [_build_schema(item["runnable"], item["spec"], fmt) for item in discovered]
    if fmt == "mcp":
        return {"tools": tools}
    return {tool["name"]: tool for tool in tools}


def _print_local_text(discovered: list[dict[str, Any]]) -> None:
    """Print installed runnables with inline validation warnings."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for item in discovered:
        by_source.setdefault(item["source"], []).append(item)

    errors: list[str] = []
    warnings: list[str] = []

    print(f"Found {len(discovered)} installed runnable(s):\n")
    for source, items in by_source.items():
        print(f"  {source}")
        for item in items:
            name = item["runnable"]
            runnable = item["spec"]
            desc = runnable.get("description") or ""
            autonomy = runnable.get("autonomy") or "confirm"
            print(f"    {name:<24} {desc[:48]:<50}  [{autonomy}]")

            if not runnable.get("description"):
                warnings.append(f"'{name}' has no description — agents won't know what it does")
            if not runnable.get("autonomy"):
                warnings.append(f"'{name}' autonomy not declared — defaulting to 'confirm'")
            for arg_name, arg in runnable.get("args", {}).items():
                if not arg.get("description") and arg.get("required"):
                    warnings.append(f"'{name}.{arg_name}' is required but has no description")
            run_as = runnable.get("run_as")
            if isinstance(run_as, dict):
                from runspec.serve import _validate_run_as_patterns

                for err in _validate_run_as_patterns(run_as):
                    errors.append(f"'{name}' run_as: {err}")
        print()

    if warnings or errors:
        print("Issues:\n")
        for msg in warnings:
            print(f"  ℹ  {msg}")
        for msg in errors:
            print(f"  ✗  {msg}")
        print()

    print("Run 'runspec local --format mcp' to emit MCP tool schemas.")

    if errors:
        sys.exit(1)


# ── Arg parsing helpers ───────────────────────────────────────────────────────


def _get_flag(args: list[str], flag: str, default: str | None = None) -> str | None:
    """Extract a --flag value from args list."""
    try:
        idx = args.index(flag)
        return args[idx + 1]
    except (ValueError, IndexError):
        return default


def _get_optional_flag(args: list[str], flag: str, default: str | None = None) -> tuple[bool, str | None]:
    """Return (present, value) for a flag whose value argument is optional.

    If the token after the flag exists and does not start with '-', it is
    consumed as the value.  Otherwise the supplied default is used.
    """
    try:
        idx = args.index(flag)
    except ValueError:
        return False, None
    if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
        return True, args[idx + 1]
    return True, default


def _print_help() -> None:
    print("""runspec — interface specification for anything runnable

Usage:
  runspec <command> [options]

Commands:
  init        Scaffold a new runnable — config and code stub
  local       Inspect locally installed runnables
  serve       Start the MCP stdio server for this environment
  jump        List or run tools on a jump box via SSH

Options for local:
  --format    Output format: text (default), json, mcp, openai, anthropic
  --script    Runnable name to target (use with --format for single-runnable schemas)

Options for serve:
  --dev            Development mode: aggregate runnables under the nearest .git root
  --registry       Registry base URL (overrides [config] registry)
  --name           Instance name reported to registry (overrides [config] name)
  --registry-key   API key for registry write endpoints
  --registry-cert  CA certificate bundle path for HTTPS registry

Options for jump:
  <tool>               Tool name (omit to list available tools from registry)
  --host <host>        Jump box to run on
  --registry <url>     Registry base URL
  --registry-key <k>   API key for registry read endpoints
  --registry-cert <f>  CA certificate bundle for HTTPS registry
  --user <user>        SSH username
  --ssh-key <file>     Path to SSH private key
  --no-host-key-check  Skip SSH host key verification (insecure)
  --format             text (default) or json — listing mode only
  --                   Separator: everything after is passed to the tool

Options for init:
  --name           Runnable name (default: current directory name, or 'clean' with --example)
  --lang           Language for code stub: python (default), typescript, javascript
  --example        Generate a full working example (stale temp file cleaner)
  --write-project  Generate pyproject.toml, __init__.py, and print entry point wiring.
                   Writes one level up by default (you are inside your package directory).
                   Supply an explicit path to override: --write-project /path/to/project

Examples:
  runspec local                                  # list installed runnables + validate
  runspec local --format mcp                     # emit MCP tool schemas
  runspec local --format mcp --script deploy     # emit schema for one runnable
  runspec jump                                   # list tools from registry
  runspec jump --registry http://registry:8080   # list from explicit registry
  runspec jump deploy --host jumpbox-01 -- --env prod
  runspec jump deploy --host jumpbox-01 --user deploy --ssh-key ~/.ssh/id_deploy -- --env prod
  runspec init
  runspec init --example
  runspec init --example --write-project
  runspec init --name myapp --lang typescript
  runspec init --write-project /path/to/project
  runspec serve
  runspec serve --registry http://registry:8080
  runspec serve --dev
""")
