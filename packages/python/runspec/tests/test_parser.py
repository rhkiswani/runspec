"""
Tests for parser._parse_argv — raw argv → dict conversion.
Tests for parse() — clean error handling (no tracebacks to user).
"""

from __future__ import annotations

import textwrap

import pytest

import runspec
from runspec.parser import _parse_argv

# ── parse() error handling ────────────────────────────────────────────────────


@pytest.fixture()
def spec_dir(tmp_path, monkeypatch):
    (tmp_path / "runspec.toml").write_text(
        textwrap.dedent("""\
            [clean]
            [clean.args.directory]
            type = "path"
            default = "."
            [clean.args.count]
            type = "int"
            default = 10
            [clean.args.format]
            type = "choice"
            options = ["text", "json"]
            default = "text"
            [clean.args.name]
            type = "str"
            required = true
        """),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestParseCleanErrors:
    def test_missing_required_arg_exits_cleanly(self, spec_dir, capsys):
        with pytest.raises(SystemExit) as exc:
            runspec.parse(script_name="clean", argv=[])
        assert exc.value.code == 1
        assert "Missing required argument" in capsys.readouterr().out

    def test_invalid_type_exits_cleanly(self, spec_dir, capsys):
        with pytest.raises(SystemExit) as exc:
            runspec.parse(script_name="clean", argv=["--name", "x", "--count", "abc"])
        assert exc.value.code == 1
        assert "--count" in capsys.readouterr().out

    def test_invalid_choice_exits_cleanly(self, spec_dir, capsys):
        with pytest.raises(SystemExit) as exc:
            runspec.parse(script_name="clean", argv=["--name", "x", "--format", "xml"])
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "--format" in out
        assert "text" in out

    def test_no_config_exits_cleanly(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            runspec.parse(script_name="clean", argv=[])
        assert exc.value.code == 1
        assert "runspec.toml" in capsys.readouterr().out

    def test_valid_args_return_runspec(self, spec_dir):
        result = runspec.parse(script_name="clean", argv=["--name", "hello"])
        assert result.name == "hello"


class TestParseArgvHappyPath:
    def test_string_arg(self):
        result = _parse_argv(["--env", "prod"], {"env": {"type": "str"}})
        assert result == {"env": "prod"}

    def test_int_arg(self):
        result = _parse_argv(["--count", "5"], {"count": {"type": "int"}})
        assert result == {"count": "5"}

    def test_float_arg(self):
        result = _parse_argv(["--threshold", "0.9"], {"threshold": {"type": "float"}})
        assert result == {"threshold": "0.9"}

    def test_path_arg(self):
        result = _parse_argv(["--directory", "/tmp"], {"directory": {"type": "path"}})
        assert result == {"directory": "/tmp"}

    def test_choice_arg(self):
        result = _parse_argv(["--format", "json"], {"format": {"type": "choice", "options": ["text", "json"]}})
        assert result == {"format": "json"}

    def test_flag_no_value(self):
        result = _parse_argv(["--dry-run"], {"dry-run": {"type": "flag"}})
        assert result == {"dry_run": True}

    def test_key_equals_value(self):
        result = _parse_argv(["--env=prod"], {"env": {"type": "str"}})
        assert result == {"env": "prod"}

    def test_hyphenated_name_normalised(self):
        result = _parse_argv(["--dry-run"], {"dry-run": {"type": "flag"}})
        assert "dry_run" in result

    def test_short_flag(self):
        result = _parse_argv(["-n", "42"], {"count": {"type": "int", "short": "-n"}})
        assert result == {"count": "42"}

    def test_short_flag_boolean(self):
        result = _parse_argv(["-v"], {"verbose": {"type": "flag", "short": "-v"}})
        assert result == {"verbose": True}

    def test_unknown_token_skipped(self):
        result = _parse_argv(["positional", "--env", "prod"], {"env": {"type": "str"}})
        assert result == {"env": "prod"}

    def test_absent_arg_is_none(self):
        result = _parse_argv([], {"env": {"type": "str"}})
        assert result == {"env": None}

    def test_multiple_values_accumulated(self):
        result = _parse_argv(["--file", "a.txt", "--file", "b.txt"], {"file": {"type": "str", "multiple": True}})
        assert result == {"file": ["a.txt", "b.txt"]}


class TestParseArgvMissingValue:
    def test_str_arg_missing_value(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--env"], {"env": {"type": "str"}})
        assert exc.value.code == 1
        assert "--env requires a value" in capsys.readouterr().out

    def test_int_arg_missing_value(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--count"], {"count": {"type": "int"}})
        assert exc.value.code == 1
        assert "--count requires a value" in capsys.readouterr().out

    def test_float_arg_missing_value(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--threshold"], {"threshold": {"type": "float"}})
        assert exc.value.code == 1
        assert "--threshold requires a value" in capsys.readouterr().out

    def test_path_arg_missing_value(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--directory"], {"directory": {"type": "path"}})
        assert exc.value.code == 1
        assert "--directory requires a value" in capsys.readouterr().out

    def test_choice_arg_missing_value_shows_options(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--format"], {"format": {"type": "choice", "options": ["text", "json"]}})
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "--format requires a value" in out
        assert "text" in out
        assert "json" in out

    def test_missing_value_when_followed_by_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(
                ["--format", "--delete"],
                {"format": {"type": "choice", "options": ["text", "json"]}, "delete": {"type": "flag"}},
            )
        assert exc.value.code == 1
        assert "--format requires a value" in capsys.readouterr().out

    def test_flag_type_is_exempt(self):
        # flag args never need a value — this must NOT raise
        result = _parse_argv(["--verbose"], {"verbose": {"type": "flag"}})
        assert result == {"verbose": True}
