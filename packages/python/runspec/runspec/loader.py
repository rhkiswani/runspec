"""
loader.py — Reads and normalises TOML into a raw spec dict.

Handles both pyproject.toml ([tool.runspec]) and runspec.toml
transparently. Returns the same normalised structure regardless of source.

In pyproject.toml, runnables live directly under [tool.runspec]:
    [tool.runspec.greeter]
    [tool.runspec.greeter.args]

In runspec.toml, runnables are top-level sections:
    [greeter]
    [greeter.args]

The reserved name 'config' is used for project-wide settings.
Everything else at the top level is treated as a runnable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


def load_raw(config_path: Path, fmt: str) -> dict[str, Any]:
    """
    Read the config file and return the normalised runspec section.

    Args:
        config_path: Path to pyproject.toml or runspec.toml
        fmt: "pyproject" or "runspec"

    Returns:
        Normalised dict with keys: config, runnables, entry_points

    Raises:
        ValueError: if the runspec section is malformed
        FileNotFoundError: if config_path does not exist
    """
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    if fmt == "pyproject":
        raw = data.get("tool", {}).get("runspec", {})
        entry_points = _read_entry_points(data)
    else:
        raw = data
        entry_points = {}

    # Runnables are everything at the top level except [config]
    # In pyproject.toml: [tool.runspec.greeter] → key "greeter"
    # In runspec.toml:   [greeter]              → key "greeter"
    runnables_raw = {key: value for key, value in raw.items() if key != "config" and isinstance(value, dict)}

    return {
        "config": _normalise_config(raw.get("config", {})),
        "runnables": _normalise_runnables(runnables_raw),
        "entry_points": entry_points,
    }


def _normalise_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise the [config] section, applying defaults."""
    return {
        "autonomy_default": raw.get("autonomy-default", "confirm"),
        "lang": raw.get("lang"),
        "name": raw.get("name"),
        "version": str(raw.get("version", "1")),
        "registry": raw.get("registry"),
        "heartbeat": int(raw.get("heartbeat", 30)),
        "heartbeat_data": list(raw.get("heartbeat_data", [])),
    }


def _normalise_runnables(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise runnables — everything under [tool.runspec] except [config].
    In pyproject.toml: [tool.runspec.greeter]
    In runspec.toml:   [greeter]
    Each runnable's args are expanded from shorthand to full form.
    Reserved name 'config' is excluded by the caller.
    """
    return {name: _normalise_script(name, script_data) for name, script_data in raw.items()}


def _normalise_script(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single script definition."""
    return {
        "name": name,
        "description": raw.get("description"),
        "autonomy": raw.get("autonomy"),
        "autonomy_reason": raw.get("autonomy-reason"),
        "hosts": raw.get("hosts"),
        "run_as": raw.get("run_as"),
        "become_method": raw.get("become_method", "sudo"),
        "become_flags": raw.get("become_flags"),
        "args": _normalise_args(raw.get("args", {})),
        "groups": _normalise_groups(raw.get("groups", {})),
        "commands": {cmd_name: _normalise_script(cmd_name, cmd_data) for cmd_name, cmd_data in raw.get("commands", {}).items()},
    }


def _normalise_args(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Expand all arg shorthand forms into full dicts.

    Handles:
      bare value:   verbose = false
      inline table: quality = {default = 85, range = [1, 100]}
      full block:   already a dict, pass through
    """
    normalised: dict[str, Any] = {}

    for name, value in raw.items():
        if isinstance(value, dict):
            # Inline table or full block — normalise fields
            normalised[name] = _normalise_arg(name, value)
        else:
            # Bare value shorthand — wrap in a dict
            normalised[name] = _normalise_arg(name, {"default": value})

    return normalised


def _normalise_arg(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single argument definition dict."""
    # Normalise hyphenated field names to underscore
    return {
        "name": name,
        "type": raw.get("type"),
        "default": raw.get("default"),
        "required": raw.get("required"),
        "description": raw.get("description"),
        "options": raw.get("options"),
        "range": tuple(raw["range"]) if "range" in raw else None,
        "multiple": raw.get("multiple", False),
        "delimiter": raw.get("delimiter"),
        "short": raw.get("short"),
        "env": raw.get("env"),
        "deprecated": raw.get("deprecated"),
        "autonomy": raw.get("autonomy"),
        "ui": raw.get("ui"),
        "meta": raw.get("meta"),
    }


def _normalise_groups(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise the groups section of a script."""
    normalised: dict[str, Any] = {}

    for name, group_data in raw.items():
        normalised[name] = {
            "name": name,
            "args": group_data.get("args", []),
            "exclusive": group_data.get("exclusive", False),
            "inclusive": group_data.get("inclusive", False),
            "at_least_one": group_data.get("at-least-one", False),
            "exactly_one": group_data.get("exactly-one", False),
            "condition": group_data.get("if"),
            "requires": group_data.get("requires", []),
        }

    return normalised


def _read_entry_points(pyproject_data: dict[str, Any]) -> dict[str, str]:
    """
    Read [project.scripts] from pyproject.toml.
    Falls back to [tool.poetry.scripts] if not found.
    Returns a dict of {script_name: "module:function"}.
    """
    # Prefer [project.scripts] — PEP 517/518 standard
    project_scripts = pyproject_data.get("project", {}).get("scripts", {})
    if project_scripts:
        return dict(project_scripts)

    # Fall back to [tool.poetry.scripts]
    return dict(pyproject_data.get("tool", {}).get("poetry", {}).get("scripts", {}))
