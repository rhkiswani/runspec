"""
finder.py — Locates runspec configuration files.

Search strategies:
  find_config(start)      — walk up from start, return first runspec.toml found
  find_configs_dev(start) — walk up to .git, then recurse down collecting all runspec.toml files
"""

from __future__ import annotations

from pathlib import Path

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".tox", "dist", "build", ".eggs", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "htmlcov",
})


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

    raise FileNotFoundError(
        "No runspec.toml found.\nRun 'runspec init' to create one, then move it inside your package directory."
    )


def find_configs_dev(start: Path | None = None) -> list[Path]:
    """
    Walk up from start until .git is found (project root), then recurse down
    collecting all runspec.toml files, skipping heavy/non-package directories.

    If no .git is found, uses start (or cwd) as the project root.

    Returns:
        List of Path objects for all runspec.toml files found (sorted for determinism)
    """
    search_dir = (start or Path.cwd()).resolve()

    project_root = search_dir
    for directory in [search_dir, *search_dir.parents]:
        if (directory / ".git").exists():
            project_root = directory
            break

    configs: list[Path] = []

    root_candidate = project_root / "runspec.toml"
    if root_candidate.exists():
        configs.append(root_candidate)

    def _walk(directory: Path) -> None:
        try:
            for entry in sorted(directory.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                candidate = entry / "runspec.toml"
                if candidate.exists():
                    configs.append(candidate)
                _walk(entry)
        except PermissionError:
            pass

    _walk(project_root)
    return configs
