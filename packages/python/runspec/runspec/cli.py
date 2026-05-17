"""
cli.py — The runspec command-line interface.

Commands:
    runspec discover [--format mcp|openai|anthropic|json]
    runspec check
    runspec emit --script <name> [--format mcp|openai|anthropic]
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
        "discover": cmd_discover,
        "check": cmd_check,
        "emit": cmd_emit,
        "serve": cmd_serve,
    }

    if command not in commands:
        print(f"✗  Unknown command: {command}")
        print(f"   Available commands: {', '.join(commands)}")
        sys.exit(1)

    commands[command](rest)


def cmd_discover(args: list[str]) -> None:
    """
    Discover all runspec-aware runnables in the current environment.
    Checks installed packages and the current directory.
    """
    fmt = _get_flag(args, "--format", default="text")

    discovered = _deduplicate(_discover_local() + _discover_installed())

    if not discovered:
        print("No runspec-aware runnables found in this environment.")
        print("Add a [tool.runspec.yourname] section to pyproject.toml or create runspec.toml")
        return

    if fmt == "text":
        _print_discover_text(discovered)
    elif fmt == "json":
        print(json.dumps(discovered, indent=2, default=str))
    elif fmt in ("mcp", "openai", "anthropic"):
        schema = _emit_all(discovered, fmt)
        print(json.dumps(schema, indent=2, default=str))
    else:
        print(f"✗  Unknown format: {fmt}")
        print("   Available formats: text, json, mcp, openai, anthropic")
        sys.exit(1)


def cmd_check(args: list[str]) -> None:
    """
    Validate the current project's runspec setup.
    """
    from runspec.finder import find_config
    from runspec.loader import load_raw

    try:
        config_path, fmt = find_config(Path.cwd())
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)

    raw = load_raw(config_path, fmt)
    errors: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    # Check config file found
    ok.append(f"Config found: {config_path}")

    # Check entry points if pyproject.toml
    if fmt == "pyproject":
        entry_points = raw.get("entry_points", {})
        if entry_points:
            ok.append(f"[project.scripts] found — {len(entry_points)} entry point(s)")
        else:
            warnings.append("No [project.scripts] found — agents may not discover runnables automatically\n  Add entry points to pyproject.toml or use runspec.toml")

    # Check for reserved name
    if "config" in raw["runnables"]:
        errors.append("'config' is a reserved name — rename your runnable to something else")

    # Check each runnable
    for runnable_name, runnable in raw["runnables"].items():
        if not runnable.get("description"):
            warnings.append(f"'{runnable_name}' has no description — agents won't know what it does")
        else:
            ok.append(f"'{runnable_name}' — description present")

        if not runnable.get("autonomy"):
            warnings.append(f"'{runnable_name}' autonomy not declared — will default to '{raw['config']['autonomy_default']}'")
        else:
            ok.append(f"'{runnable_name}' — autonomy: {runnable['autonomy']}")

        for arg_name, arg in runnable.get("args", {}).items():
            if not arg.get("description") and arg.get("required"):
                warnings.append(f"'{runnable_name}.{arg_name}' is required but has no description")

    # Print results
    for msg in ok:
        print(f"  ✓  {msg}")
    for msg in warnings:
        print(f"  ℹ  {msg}")
    for msg in errors:
        print(f"  ✗  {msg}")

    if errors:
        sys.exit(1)
    elif not warnings:
        print("\n  All checks passed.")


def cmd_serve(args: list[str]) -> None:
    """Start the MCP stdio server for this environment."""
    from runspec.serve import serve

    serve()


def cmd_init(args: list[str]) -> None:
    """Create or update pyproject.toml or runspec.toml with a runspec scaffold."""
    name_flag = _get_flag(args, "--name")
    file_flag = _get_flag(args, "--file")

    cwd = Path.cwd()
    runnable_name = name_flag or _sanitize_name(cwd.name)

    pyproject = cwd / "pyproject.toml"
    runspec_toml = cwd / "runspec.toml"

    if file_flag == "runspec":
        _init_runspec_toml(runspec_toml, runnable_name)
    elif file_flag == "pyproject" or pyproject.exists():
        _init_pyproject(pyproject, runnable_name)
    else:
        _init_runspec_toml(runspec_toml, runnable_name)


def _sanitize_name(raw: str) -> str:
    """Convert a directory name into a valid TOML key."""
    import re

    s = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return s or "myscript"


def _init_pyproject(path: Path, name: str) -> None:
    """Add a runspec scaffold to pyproject.toml (create if absent)."""
    if path.exists():
        original = path.read_text(encoding="utf-8")
        try:
            data = _load_toml_file(path)
        except Exception as e:
            print(f"✗  Could not read {path.name}: {e}")
            sys.exit(1)

        if "runspec" in data.get("tool", {}):
            existing = [k for k, v in data["tool"]["runspec"].items() if k != "config" and isinstance(v, dict)]
            print(f"✗  {path.name} already has [tool.runspec] — already initialized")
            if existing:
                print(f"   Existing runnables: {', '.join(existing)}")
            sys.exit(1)

        content = original.rstrip("\n") + "\n\n" + _pyproject_block(name)
    else:
        original = None
        content = _pyproject_block(name)

    _write_and_verify(path, content, original)
    action = "Updated" if original is not None else "Created"
    print(f"  ✓  {action} {path.name} with [{name}] runnable")
    print("     Run 'runspec check' to validate.")


def _init_runspec_toml(path: Path, name: str) -> None:
    """Create runspec.toml with a runspec scaffold."""
    if path.exists():
        print(f"✗  {path.name} already exists — already initialized")
        print(f"   Edit {path.name} directly to add more runnables.")
        sys.exit(1)

    content = _runspec_toml_block(name)
    _write_and_verify(path, content, None)
    print(f"  ✓  Created {path.name} with [{name}] runnable")
    print("     Run 'runspec check' to validate.")


def _pyproject_block(name: str) -> str:
    return (
        f'[tool.runspec.{name}]\ndescription = "Describe what {name} does"\nautonomy    = "confirm"\n\n[tool.runspec.{name}.args]\n# example = {{type = "str", description = "An example argument"}}\n'
    )


def _runspec_toml_block(name: str) -> str:
    return f'[{name}]\ndescription = "Describe what {name} does"\nautonomy    = "confirm"\n\n[{name}.args]\n# example = {{type = "str", description = "An example argument"}}\n'


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


def cmd_emit(args: list[str]) -> None:
    """
    Emit a tool schema for one or all runnables.
    """
    script_name = _get_flag(args, "--script")
    fmt = _get_flag(args, "--format", default="mcp")

    from runspec.finder import find_config
    from runspec.inference import infer_script
    from runspec.loader import load_raw

    try:
        config_path, file_fmt = find_config(Path.cwd())
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)

    raw = load_raw(config_path, file_fmt)
    config = raw["config"]

    if script_name:
        if script_name not in raw["runnables"]:
            print(f"✗  Runnable '{script_name}' not found")
            sys.exit(1)
        runnables = {script_name: raw["runnables"][script_name]}
    else:
        runnables = raw["runnables"]

    schema = {}
    for name, runnable in runnables.items():
        inferred = infer_script(runnable, config["autonomy_default"])
        schema[name] = _build_schema(name, inferred, fmt or "mcp")

    output = {"tools": list(schema.values())} if fmt == "mcp" else schema

    print(json.dumps(output, indent=2, default=str))


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


def _discover_local() -> list[dict[str, Any]]:
    """Look for runspec config in the current directory."""
    from runspec.finder import find_config
    from runspec.loader import load_raw

    try:
        config_path, fmt = find_config(Path.cwd())
        raw = load_raw(config_path, fmt)
        return [{"source": str(config_path), "runnable": name, "spec": spec} for name, spec in raw["runnables"].items()]
    except FileNotFoundError:
        return []


def _discover_installed() -> list[dict[str, Any]]:
    """
    Find runspec-aware packages in the current Python environment
    using importlib.metadata.
    """
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
    """
    Strategy 1: look for runspec.toml shipped as package data.
    Returns discovered items or [] if not found.
    """
    from runspec.loader import load_raw

    if dist.files is None:
        return []

    for f in dist.files:
        if f.name == "runspec.toml":
            try:
                config_path = Path(str(f.locate())).resolve()
                raw = load_raw(config_path, "runspec")
                if not raw["runnables"]:
                    return []
                return [{"source": str(config_path), "runnable": name, "spec": spec} for name, spec in raw["runnables"].items()]
            except Exception:
                pass

    return []


def _check_editable_source(dist: Any) -> list[dict[str, Any]]:
    """
    Strategy 2: editable install — read direct_url.json to find the source
    directory, then look for pyproject.toml with [tool.runspec] or runspec.toml.
    Returns discovered items or [] if not applicable.
    """
    import json as _json
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    from runspec.finder import find_config
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

    try:
        config_path, fmt = find_config(source_dir)
        raw = load_raw(config_path, fmt)
        if not raw["runnables"]:
            return []
        return [{"source": str(config_path), "runnable": name, "spec": spec} for name, spec in raw["runnables"].items()]
    except FileNotFoundError:
        return []


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


def _print_discover_text(discovered: list[dict[str, Any]]) -> None:
    """Pretty-print discovered runnables."""
    by_source: dict[str, list[str]] = {}
    for item in discovered:
        src = item["source"]
        by_source.setdefault(src, []).append(item["runnable"])

    print(f"Found {len(discovered)} runspec-aware runnable(s):\n")
    for source, runnables in by_source.items():
        print(f"  {source}")
        for r in runnables:
            print(f"    • {r}")
    print()
    print("Run 'runspec discover --format mcp' to emit MCP tool schemas.")


# ── Arg parsing helpers ───────────────────────────────────────────────────────


def _get_flag(args: list[str], flag: str, default: str | None = None) -> str | None:
    """Extract a --flag value from args list."""
    try:
        idx = args.index(flag)
        return args[idx + 1]
    except (ValueError, IndexError):
        return default


def _print_help() -> None:
    print("""runspec — interface specification for anything runnable

Usage:
  runspec <command> [options]

Commands:
  init        Create or update pyproject.toml or runspec.toml with a scaffold
  discover    Find all runspec-aware runnables in this environment
  check       Validate this project's runspec setup
  emit        Emit tool schemas for agent frameworks
  serve       Start the MCP stdio server for this environment

Options for init:
  --name      Runnable name (default: current directory name)
  --file      Target file: pyproject or runspec (auto-detected if omitted)

Options for discover:
  --format    Output format: text (default), json, mcp, openai, anthropic

Options for emit:
  --script    Runnable name to emit (all runnables if omitted)
  --format    Output format: mcp (default), openai, anthropic

Examples:
  runspec init
  runspec init --name myapp
  runspec init --file runspec
  runspec discover
  runspec discover --format mcp
  runspec check
  runspec emit --name compress --format mcp
  runspec emit --format openai
""")
