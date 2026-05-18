"""
Tests for runspec init — creates runspec.toml with a scaffold.
"""

from __future__ import annotations

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


# ── idempotency — refuse if already initialized ──────────────────────────────


def test_refuses_if_runspec_toml_exists(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runspec.toml").write_text('[greeter]\ndescription = "hi"\n', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cmd_init(["--name", "greeter"])
    assert exc.value.code == 1
    assert "already exists" in capsys.readouterr().out


# ── generated files are valid TOML and parseable by runspec ──────────────────


def test_runspec_toml_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "myscript"])

    from runspec.loader import load_raw

    raw = load_raw(tmp_path / "runspec.toml")
    assert "myscript" in raw["runnables"]


# ── codegen — default Python stub ────────────────────────────────────────────


def test_creates_python_stub_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greet"])

    stub = tmp_path / "greet.py"
    assert stub.exists()
    content = stub.read_text()
    assert "from runspec import parse" in content
    assert "def main():" in content
    assert 'if __name__ == "__main__"' in content


def test_python_stub_is_executable_as_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greet"])
    # compile-check: no syntax errors
    import ast
    ast.parse((tmp_path / "greet.py").read_text())


# ── codegen — --lang overrides ────────────────────────────────────────────────


def test_lang_typescript_generates_ts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greet", "--lang", "typescript"])

    stub = tmp_path / "greet.ts"
    assert stub.exists()
    content = stub.read_text()
    assert "import { parse } from 'runspec'" in content
    assert "function main()" in content
    assert "main();" in content


def test_lang_javascript_generates_js(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd_init(["--name", "greet", "--lang", "javascript"])

    stub = tmp_path / "greet.js"
    assert stub.exists()
    content = stub.read_text()
    assert "require('runspec')" in content
    assert "main();" in content


def test_unknown_lang_exits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cmd_init(["--name", "greet", "--lang", "ruby"])
    assert exc.value.code == 1


# ── codegen — no-overwrite behaviour ─────────────────────────────────────────


def test_does_not_overwrite_existing_stub(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "greet.py"
    existing.write_text("# existing\n", encoding="utf-8")

    cmd_init(["--name", "greet"])

    assert existing.read_text() == "# existing\n"
    assert "already exists" in capsys.readouterr().out
