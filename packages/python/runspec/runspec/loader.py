"""
loader.py — Reads and normalises runspec.toml into a raw spec dict.

Runnables are top-level sections:
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


def load_raw(config_path: Path) -> dict[str, Any]:
    """
    Read runspec.toml and return the normalised spec dict.

    Args:
        config_path: Path to runspec.toml

    Returns:
        Normalised dict with keys: config, runnables

    Raises:
        ValueError: if the runspec section is malformed
        FileNotFoundError: if config_path does not exist
    """
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    runnables_raw = {key: value for key, value in data.items() if key != "config" and isinstance(value, dict)}

    return {
        "config": _normalise_config(data.get("config", {})),
        "runnables": _normalise_runnables(runnables_raw),
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
    """Normalise runnables — everything at the top level except [config]."""
    return {name: _normalise_script(name, script_data) for name, script_data in raw.items()}


def _normalise_script(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single script definition."""
    return {
        "name": name,
        "description": raw.get("description"),
        "autonomy": raw.get("autonomy"),
        "autonomy_reason": raw.get("autonomy-reason"),
        "output": raw.get("output", "text"),
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
            normalised[name] = _normalise_arg(name, value)
        else:
            normalised[name] = _normalise_arg(name, {"default": value})

    return normalised


def _normalise_arg(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single argument definition dict."""
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
