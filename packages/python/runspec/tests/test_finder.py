"""
Tests for runspec.finder — config file location.

Covers find_config (walk-up) and find_configs_dev (recursive dev-mode scan).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from runspec.finder import find_config, find_configs_dev


# ── find_config ───────────────────────────────────────────────────────────────


def test_find_config_finds_in_cwd(tmp_path, monkeypatch):
    (tmp_path / "runspec.toml").touch()
    monkeypatch.chdir(tmp_path)
    assert find_config() == tmp_path / "runspec.toml"


def test_find_config_walks_up(tmp_path, monkeypatch):
    toml = tmp_path / "runspec.toml"
    toml.touch()
    subdir = tmp_path / "a" / "b"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    assert find_config() == toml


def test_find_config_with_explicit_start(tmp_path):
    toml = tmp_path / "runspec.toml"
    toml.touch()
    assert find_config(tmp_path) == toml


def test_find_config_raises_when_not_found(tmp_path, monkeypatch):
    # Patch Path.exists so stale runspec.toml files in ancestor dirs don't interfere
    original = Path.exists

    def _exists(self: Path) -> bool:
        if self.name == "runspec.toml" and not self.is_relative_to(tmp_path):
            return False
        return original(self)

    monkeypatch.setattr(Path, "exists", _exists)
    with pytest.raises(FileNotFoundError, match="runspec.toml"):
        find_config(tmp_path)


# ── find_configs_dev ──────────────────────────────────────────────────────────


def test_find_configs_dev_one_level(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    toml = pkg / "runspec.toml"
    toml.touch()
    result = find_configs_dev(tmp_path)
    assert result == [toml]


def test_find_configs_dev_recursive(tmp_path):
    """Config nested two levels deep is found (monorepo layout)."""
    git = tmp_path / ".git"
    git.mkdir()
    nested = tmp_path / "packages" / "python" / "mypkg"
    nested.mkdir(parents=True)
    toml = nested / "runspec.toml"
    toml.touch()
    result = find_configs_dev(tmp_path)
    assert toml in result


def test_find_configs_dev_multiple_configs(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    for name in ("pkga", "pkgb"):
        d = tmp_path / name
        d.mkdir()
        (d / "runspec.toml").touch()
    result = find_configs_dev(tmp_path)
    assert len(result) == 2


def test_find_configs_dev_sorted(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    for name in ("z_pkg", "a_pkg"):
        d = tmp_path / name
        d.mkdir()
        (d / "runspec.toml").touch()
    result = find_configs_dev(tmp_path)
    assert result == sorted(result)


def test_find_configs_dev_skips_venv(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "runspec.toml").touch()  # would be found without pruning
    result = find_configs_dev(tmp_path)
    assert result == []


def test_find_configs_dev_skips_pycache(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "runspec.toml").touch()
    result = find_configs_dev(tmp_path)
    assert result == []


def test_find_configs_dev_skips_hidden_dirs(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "runspec.toml").touch()
    result = find_configs_dev(tmp_path)
    assert result == []


def test_find_configs_dev_skips_node_modules(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "runspec.toml").touch()
    result = find_configs_dev(tmp_path)
    assert result == []


def test_find_configs_dev_walks_up_to_git(tmp_path):
    """When started from a subdir, the .git boundary is found by walking up."""
    git = tmp_path / ".git"
    git.mkdir()
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    toml = pkg / "runspec.toml"
    toml.touch()

    # Start from a nested subdirectory
    nested_start = tmp_path / "deeply" / "nested"
    nested_start.mkdir(parents=True)
    result = find_configs_dev(nested_start)
    assert toml in result


def test_find_configs_dev_finds_toml_at_project_root(tmp_path):
    """runspec.toml directly in the project root (e.g. single-package dev) is found."""
    git = tmp_path / ".git"
    git.mkdir()
    toml = tmp_path / "runspec.toml"
    toml.touch()
    result = find_configs_dev(tmp_path)
    assert toml in result


def test_find_configs_dev_empty_when_no_tomls(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (tmp_path / "emptypkg").mkdir()
    result = find_configs_dev(tmp_path)
    assert result == []


def test_find_configs_dev_uses_cwd_as_root_without_git(tmp_path, monkeypatch):
    """Without a .git root, falls back to the start directory."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    toml = pkg / "runspec.toml"
    toml.touch()
    monkeypatch.chdir(tmp_path)
    result = find_configs_dev(tmp_path)
    assert toml in result
