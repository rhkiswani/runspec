"""
Tests for parser._parse_argv — raw argv → dict conversion.
"""

from __future__ import annotations

import pytest

from runspec.parser import _parse_argv


class TestParseArgv:
    def test_string_arg(self):
        result = _parse_argv(["--env", "prod"], {"env": {"type": "str"}})
        assert result == {"env": "prod"}

    def test_flag_no_value(self):
        result = _parse_argv(["--dry-run"], {"dry-run": {"type": "flag"}})
        assert result == {"dry_run": True}

    def test_key_equals_value(self):
        result = _parse_argv(["--env=prod"], {"env": {"type": "str"}})
        assert result == {"env": "prod"}

    def test_missing_value_for_str_arg_exits(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--env"], {"env": {"type": "str"}})
        assert exc.value.code == 1
        assert "--env requires a value" in capsys.readouterr().out

    def test_missing_value_for_choice_arg_shows_options(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--format"], {"format": {"type": "choice", "options": ["text", "json"]}})
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "--format requires a value" in out
        assert "text" in out
        assert "json" in out

    def test_missing_value_when_followed_by_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_argv(["--format", "--delete"], {"format": {"type": "choice", "options": ["text", "json"]}, "delete": {"type": "flag"}})
        assert exc.value.code == 1
        assert "--format requires a value" in capsys.readouterr().out
