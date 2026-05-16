"""
parser.py — Main entry point. Builds a RunSpec from sys.argv.

Orchestrates: find → load → infer → parse argv → validate → coerce → build RunSpec
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from runspec import errors
from runspec.finder import find_config, find_script_name
from runspec.inference import effective_autonomy, infer_script
from runspec.loader import load_raw
from runspec.models import Arg, Group, RunSpec
from runspec.types import coerce
from runspec.validator import raise_if_errors, validate_args, validate_groups


def parse(script_name: str | None = None, argv: list[str] | None = None) -> RunSpec:
    """
    Parse arguments for the calling runnable.

    Args:
        script_name: Override runnable name. Inferred from [project.scripts] if None.
        argv:        Override sys.argv. Uses sys.argv[1:] if None. Useful for testing.

    Returns:
        RunSpec — the fully parsed, validated, coerced argument namespace.

    Raises:
        RunSpecError:      if required args are missing or validation fails
        FileNotFoundError: if no runspec config is found
    """
    # 1. Find config
    config_path, fmt = find_config()

    # 2. Load and normalise TOML
    raw = load_raw(config_path, fmt)
    config = raw["config"]

    # 3. Resolve runnable name
    name = script_name or find_script_name(config_path, fmt) or _infer_from_argv()

    # Guard reserved name
    if name == "config":
        raise errors.RunSpecError("✗  'config' is a reserved name in runspec.\n   Rename your runnable to something else.")

    if name not in raw["runnables"]:
        available = ", ".join(raw["runnables"].keys()) or "(none)"
        raise errors.RunSpecError(f"✗  Runnable '{name}' not found in runspec config.\n   Available runnables: {available}\n   Config: {config_path}")

    # 4. Infer defaults for the script
    raw_script = infer_script(raw["runnables"][name], config["autonomy_default"])

    # 5. Resolve subcommand if any
    argv_list = argv if argv is not None else sys.argv[1:]
    raw_script, active_command, argv_list = _resolve_subcommand(raw_script, argv_list)

    # 6. Handle --help / -h before any validation
    if "--help" in argv_list or "-h" in argv_list:
        _print_help(name, raw_script, active_command)
        sys.exit(0)

    # 7. Parse argv into raw values
    parsed_values = _parse_argv(argv_list, raw_script["args"])

    # 8. Apply env var fallbacks
    parsed_values = _apply_env(parsed_values, raw_script["args"])

    # 9. Apply defaults
    parsed_values = _apply_defaults(parsed_values, raw_script["args"])

    # 10. Pass 1 — validate individual args
    arg_errors = validate_args(parsed_values, raw_script["args"])
    raise_if_errors(arg_errors)

    # 11. Pass 2 — validate groups
    group_errors = validate_groups(parsed_values, raw_script["groups"])
    raise_if_errors(group_errors)

    # 12. Coerce values to native Python types
    coerced_values = _coerce_values(parsed_values, raw_script["args"])

    # 13. Calculate effective autonomy
    autonomy = effective_autonomy(
        raw_script["autonomy"],
        parsed_values,
        raw_script["args"],
    )

    # 14. Build and return RunSpec
    return _build_runspec(
        name=name,
        config_path=config_path,
        command=active_command,
        autonomy=autonomy,
        coerced_values=coerced_values,
        arg_specs=raw_script["args"],
        group_specs=raw_script["groups"],
        raw_script=raw_script,
    )


def load_spec(script_name: str | None = None) -> RunSpec:
    """
    Load the spec without parsing argv. Useful for introspection,
    emit, and scaffold operations.

    Returns a RunSpec with default values only — no CLI args applied.
    """
    return parse(script_name=script_name, argv=[])


# ── Internal helpers ──────────────────────────────────────────────────────────


def _print_help(name: str, script: dict[str, Any], command: str | None) -> None:
    """Print a human-readable help message for a runnable and exit."""
    full_name = f"{name} {command}" if command else name
    description = script.get("description") or ""
    args = script.get("args", {})

    # Build usage line
    usage_parts = [full_name]
    for arg_name, spec in args.items():
        flag = f"--{arg_name}"
        if spec.get("type") == "flag":
            usage_parts.append(f"[{flag}]")
        elif spec.get("required"):
            usage_parts.append(f"{flag} <{spec.get('type', 'str')}>")
        else:
            usage_parts.append(f"[{flag} <{spec.get('type', 'str')}>]")

    print(f"Usage: {' '.join(usage_parts)}")
    if description:
        print(f"\n{description}")

    if args:
        print("\nArguments:")
        for arg_name, spec in args.items():
            flag = f"  --{arg_name}"
            arg_type = spec.get("type", "str")
            parts = []
            if arg_type == "flag":
                parts.append("flag")
            else:
                parts.append(arg_type)
            if spec.get("required"):
                parts.append("required")
            elif spec.get("default") is not None:
                parts.append(f"default: {spec['default']}")
            if spec.get("options"):
                parts.append(f"one of: {', '.join(str(o) for o in spec['options'])}")
            if spec.get("description"):
                print(f"{flag:<24} {spec['description']}  ({', '.join(parts)})")
            else:
                print(f"{flag:<24} ({', '.join(parts)})")

    autonomy = script.get("autonomy")
    if autonomy:
        print(f"\nAutonomy: {autonomy}")
        if script.get("autonomy_reason"):
            print(f"  {script['autonomy_reason']}")

    print("\n  -h, --help    Show this message and exit")


def _infer_from_argv() -> str:
    """Infer script name from sys.argv[0]."""
    return Path(sys.argv[0]).stem if sys.argv else "unknown"


def _resolve_subcommand(
    raw_script: dict[str, Any],
    argv: list[str],
) -> tuple[dict[str, Any], str | None, list[str]]:
    """
    If the script has subcommands and argv[0] matches one, return the
    subcommand spec and remaining argv. Otherwise return the script unchanged.
    """
    commands = raw_script.get("commands", {})
    if not commands or not argv:
        return raw_script, None, argv

    candidate = argv[0]
    if candidate in commands:
        return commands[candidate], candidate, argv[1:]

    return raw_script, None, argv


def _parse_argv(
    argv: list[str],
    arg_specs: dict[str, Any],
) -> dict[str, Any]:
    """
    Parse argv into a raw dict of {arg_name: value | None}.
    Handles --flag, --key value, --key=value, -short, and multiple values.
    """
    # Build lookup maps
    name_map: dict[str, str] = {}  # --flag-name → normalised_name
    short_map: dict[str, str] = {}  # -v → normalised_name
    for name, spec in arg_specs.items():
        normalised = name.replace("-", "_")
        name_map[f"--{name}"] = normalised
        name_map[f"--{normalised}"] = normalised
        if spec.get("short"):
            short_map[spec["short"]] = normalised

    result: dict[str, Any] = {name.replace("-", "_"): None for name in arg_specs}

    i = 0
    while i < len(argv):
        token = argv[i]

        # --key=value form
        if "=" in token and token.startswith("--"):
            key, value = token.split("=", 1)
            norm = name_map.get(key)
            if norm:
                result[norm] = _append_or_set(result.get(norm), value, arg_specs.get(norm.replace("_", "-"), arg_specs.get(norm, {})))
            i += 1
            continue

        # --flag or -short
        norm = name_map.get(token) or short_map.get(token)
        if norm:
            spec = arg_specs.get(norm.replace("_", "-"), arg_specs.get(norm, {}))
            arg_type = spec.get("type", "str")

            if arg_type == "flag":
                result[norm] = True
                i += 1
            elif i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                raw_str = argv[i + 1]
                delimiter = spec.get("delimiter")
                parsed: str | list[str] = raw_str.split(delimiter) if delimiter else raw_str
                result[norm] = _append_or_set(result.get(norm), parsed, spec)
                i += 2
            else:
                # Flag-style bool
                result[norm] = True
                i += 1
            continue

        i += 1

    return result


def _append_or_set(current: Any, value: Any, spec: dict[str, Any]) -> Any:
    """For multiple=true args, accumulate values. Otherwise set."""
    if spec.get("multiple"):
        if isinstance(value, list):
            return (current or []) + value
        return (current or []) + [value]
    return value


def _apply_env(
    parsed: dict[str, Any],
    arg_specs: dict[str, Any],
) -> dict[str, Any]:
    """Apply environment variable fallbacks where values are still None."""
    result = dict(parsed)
    for name, spec in arg_specs.items():
        norm = name.replace("-", "_")
        if result.get(norm) is None and spec.get("env"):
            env_val = os.environ.get(spec["env"])
            if env_val is not None:
                result[norm] = env_val
    return result


def _apply_defaults(
    parsed: dict[str, Any],
    arg_specs: dict[str, Any],
) -> dict[str, Any]:
    """Apply spec defaults where values are still None."""
    result = dict(parsed)
    for name, spec in arg_specs.items():
        norm = name.replace("-", "_")
        if result.get(norm) is None and spec.get("default") is not None:
            result[norm] = spec["default"]
    return result


def _coerce_values(
    parsed: dict[str, Any],
    arg_specs: dict[str, Any],
) -> dict[str, Any]:
    """Coerce all resolved values to native Python types."""
    result: dict[str, Any] = {}
    for name, spec in arg_specs.items():
        norm = name.replace("-", "_")
        value = parsed.get(norm)
        if value is None:
            result[norm] = (None, "default")
            continue
        source = _determine_source(norm, parsed)
        coerced = coerce(value, spec)
        result[norm] = (coerced, source)
    return result


def _determine_source(name: str, parsed: dict[str, Any]) -> str:
    """Determine where a value came from: cli, env, config, or default."""
    # Simplified — a full implementation would track this through the pipeline
    # For now: if value is non-None it came from cli or env
    return "cli" if parsed.get(name) is not None else "default"


def _build_runspec(
    name: str,
    config_path: Path,
    command: str | None,
    autonomy: str,
    coerced_values: dict[str, Any],
    arg_specs: dict[str, Any],
    group_specs: dict[str, Any],
    raw_script: dict[str, Any],
) -> RunSpec:
    """Assemble the final RunSpec object."""
    groups = [
        Group(
            name=gname,
            args=gspec.get("args", []),
            exclusive=gspec.get("exclusive", False),
            inclusive=gspec.get("inclusive", False),
            at_least_one=gspec.get("at_least_one", False),
            exactly_one=gspec.get("exactly_one", False),
            condition=gspec.get("condition"),
        )
        for gname, gspec in group_specs.items()
    ]

    runspec = RunSpec(
        __script__=name,
        __source__=config_path,
        __command__=command,
        __autonomy__=autonomy,
        __spec__=raw_script,
        __groups__=groups,
    )

    for arg_name, spec in arg_specs.items():
        norm = arg_name.replace("-", "_")
        value, source = coerced_values.get(norm, (None, "default"))

        arg = Arg(
            value=value,
            name=arg_name,
            type=spec.get("type", "str"),
            required=spec.get("required", False),
            default=spec.get("default"),
            description=spec.get("description"),
            options=spec.get("options"),
            range=spec.get("range"),
            multiple=spec.get("multiple", False),
            delimiter=spec.get("delimiter"),
            short=spec.get("short"),
            env=spec.get("env"),
            deprecated=spec.get("deprecated"),
            autonomy=spec.get("autonomy"),
            ui=spec.get("ui"),
            source=source,
        )
        runspec._set_arg(arg_name, arg)

    return runspec
