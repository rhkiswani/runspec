"""
finder.py — Locates the runspec configuration file.

Search order (per SPEC.md):
  1. pyproject.toml with [tool.runspec] section
  2. runspec.toml
  Walk up from the starting directory repeating 1 and 2.
"""

from __future__ import annotations

import sys
from pathlib import Path


def find_config(start: Path | None = None) -> tuple[Path, str]:
    """
    Find the runspec config file starting from `start` and walking up.

    Returns:
        (config_path, format) where format is "pyproject" or "runspec"

    Raises:
        FileNotFoundError: if no config file is found
    """
    search_dir = (start or _caller_directory()).resolve()

    for directory in [search_dir, *search_dir.parents]:
        # Check pyproject.toml first
        pyproject = directory / "pyproject.toml"
        if pyproject.exists() and _has_runspec_section(pyproject):
            return pyproject, "pyproject"

        # Then runspec.toml
        runspec_toml = directory / "runspec.toml"
        if runspec_toml.exists():
            return runspec_toml, "runspec"

    raise FileNotFoundError(
        "No runspec configuration found.\nExpected one of:\n  - pyproject.toml with [tool.runspec] section\n  - runspec.toml\n\nRun 'runspec check' to validate your project setup."
    )


def find_script_name(config_path: Path, format: str) -> str | None:
    """
    Infer the calling script's name from [project.scripts] or
    [tool.poetry.scripts] by matching the calling executable.

    Returns the script name if found, None if it cannot be determined.
    """
    import tomllib

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    # Get the name of the currently running script/executable
    caller = Path(sys.argv[0]).stem if sys.argv else None
    if not caller:
        return None

    # Check [project.scripts] first (PEP 517/518 standard)
    project_scripts = data.get("project", {}).get("scripts", {})
    if caller in project_scripts:
        return caller

    # Fall back to [tool.poetry.scripts] with a nudge logged
    poetry_scripts = data.get("tool", {}).get("poetry", {}).get("scripts", {})
    if caller in poetry_scripts:
        _nudge_poetry()
        return caller

    return caller  # return caller name even if not in scripts — let loader handle it


def _has_runspec_section(pyproject_path: Path) -> bool:
    """Return True if pyproject.toml contains a [tool.runspec] section."""
    import tomllib

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return "runspec" in data.get("tool", {})
    except Exception:
        return False


def _caller_directory() -> Path:
    """Return the directory of the script that called parse()."""
    # Walk up the call stack to find the first frame outside runspec
    import inspect

    for frame_info in inspect.stack():
        frame_path = Path(frame_info.filename).resolve()
        # Skip frames that are inside the runspec package itself
        if "runspec" not in frame_path.parts[-3:]:
            return frame_path.parent

    # Fallback to current working directory
    return Path.cwd()


def _nudge_poetry() -> None:
    """Print a one-time informational nudge about [project.scripts]."""
    import warnings

    warnings.warn(
        "\nrunspec: Using [tool.poetry.scripts] — consider migrating to [project.scripts]\n"
        "for better compatibility with modern Python packaging tools.\n"
        "See: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/\n",
        stacklevel=4,
    )
