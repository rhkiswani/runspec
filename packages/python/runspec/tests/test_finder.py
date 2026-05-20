"""
Tests for runspec.finder — config file location.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from runspec.finder import find_config


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
