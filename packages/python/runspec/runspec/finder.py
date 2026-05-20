"""
finder.py — Locates runspec configuration files.

Search strategy:
  find_config(start) — walk up from start, return first runspec.toml found.
                       Used by `runspec jump` to locate the nearest
                       [config.jump-hosts] table. `runspec local` and
                       `runspec serve` use importlib.metadata instead.
"""

from __future__ import annotations

from pathlib import Path


def find_config(start: Path | None = None) -> Path:
    """
    Walk up from start looking for runspec.toml.

    Returns:
        Path to the first runspec.toml found

    Raises:
        FileNotFoundError: if no runspec.toml is found
    """
    search_dir = (start or Path.cwd()).resolve()

    for directory in [search_dir, *search_dir.parents]:
        candidate = directory / "runspec.toml"
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No runspec.toml found.\nRun 'runspec init' to create one, then move it inside your package directory.")
