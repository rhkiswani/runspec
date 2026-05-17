"""
Tests for runspec init — creates or updates pyproject.toml / runspec.toml.
"""

from __future__ import annotations

import sys

import pytest

from runspec.cli import _sanitize_name, cmd_init

# ── _sanitize_name ────────────────────────────────────────────────────────────


def test_sanitize_name_simple():
    assert _sanitize_name("myapp") == "myapp"


def test_sanitize_name_hyphens():
    assert _sanitize_name("my-app") == "my_app"


def test_sanitize_name_spaces():
    assert _sanitize_name("My App") == "my_app"


def test_sanitize_name_leading_trailing_specials():
    assert _sanitize_name("--myapp--") == "myapp"


def test_sanitize_name_empty_falls_back():
    assert _sanitize_name("---") == "myscript"


def test_sanitize_name_mixed():
    assert _sanitize_name("Analytics-Pipeline_v2") == "analytics_pipeline_v2"


# ── creates runspec.toml when no file exists ──────────────────────────────────


def test_creates_runspec_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greeter"])

    toml = tmp_path / "runspec.toml"
    assert toml.exists()
    content = toml.read_text()
    assert "[greeter]" in content
    assert 'autonomy    = "confirm"' in content
    assert "[greeter.args]" in content


def test_creates_runspec_toml_default_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init([])

    toml = tmp_path / "runspec.toml"
    assert toml.exists()
    name = _sanitize_name(tmp_path.name)
    assert f"[{name}]" in toml.read_text()


# ── appends to existing pyproject.toml ───────────────────────────────────────


def test_appends_to_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "myproject"\n', encoding="utf-8")

    cmd_init(["--name", "deploy"])

    content = pyproject.read_text()
    assert "[tool.runspec.deploy]" in content
    assert '[project]\nname = "myproject"' in content  # original preserved


def test_appends_preserves_existing_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    original = '[project]\nname = "myproject"\nversion = "1.0"\n'
    pyproject.write_text(original, encoding="utf-8")

    cmd_init(["--name", "deploy"])

    content = pyproject.read_text()
    assert 'name = "myproject"' in content
    assert 'version = "1.0"' in content
    assert "[tool.runspec.deploy]" in content


def test_creates_pyproject_when_absent_with_file_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greeter", "--file", "pyproject"])

    pyproject = tmp_path / "pyproject.toml"
    assert pyproject.exists()
    assert "[tool.runspec.greeter]" in pyproject.read_text()


# ── --file flag overrides auto-detection ─────────────────────────────────────


def test_file_flag_runspec_when_pyproject_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")

    cmd_init(["--name", "myscript", "--file", "runspec"])

    assert (tmp_path / "runspec.toml").exists()
    assert "[tool.runspec" not in pyproject.read_text()


def test_file_flag_pyproject_when_runspec_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    cmd_init(["--name", "myscript", "--file", "pyproject"])

    assert "[tool.runspec.myscript]" in (tmp_path / "pyproject.toml").read_text()
    assert not (tmp_path / "runspec.toml").exists()


# ── idempotency — refuse if already initialized ──────────────────────────────


def test_refuses_if_runspec_toml_exists(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runspec.toml").write_text('[greeter]\ndescription = "hi"\n', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cmd_init(["--name", "greeter"])
    assert exc.value.code == 1
    assert "already exists" in capsys.readouterr().out


def test_refuses_if_pyproject_has_runspec(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\n\n[tool.runspec.greeter]\ndescription = "hi"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        cmd_init(["--name", "deploy"])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "already initialized" in out
    assert "greeter" in out


# ── generated files are valid TOML and parseable by runspec ──────────────────


def test_runspec_toml_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "myscript"])

    from runspec.loader import load_raw

    raw = load_raw(tmp_path / "runspec.toml", "runspec")
    assert "myscript" in raw["runnables"]


def test_pyproject_block_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    cmd_init(["--name", "deploy"])

    from runspec.loader import load_raw

    raw = load_raw(tmp_path / "pyproject.toml", "pyproject")
    assert "deploy" in raw["runnables"]


def test_pyproject_after_append_is_valid_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "myproject"\nversion = "1.0"\n\n[project.dependencies]\n',
        encoding="utf-8",
    )
    cmd_init(["--name", "run"])

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert "runspec" in data.get("tool", {})
    assert "run" in data["tool"]["runspec"]
