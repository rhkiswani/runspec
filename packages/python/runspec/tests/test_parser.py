"""
Tests for parser._parse_argv — raw argv → dict conversion.
"""

from __future__ import annotations

import pytest

from runspec.parser import _parse_argv


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
