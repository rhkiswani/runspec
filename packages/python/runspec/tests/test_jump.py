"""Tests for runspec.jump — pure helper functions (no SSH required)."""

from __future__ import annotations

import pytest

from runspec.jump import parse_tool_argv, ssh_cmd
from runspec.loader import _normalise_jump_hosts
from runspec.parser import _parse_argv


def test_normalise_jump_hosts_basic() -> None:
    raw = {"myserver": {"bin": "/usr/local/bin/runspec", "user": "deploy"}}
    result = _normalise_jump_hosts(raw)
    assert result["myserver"]["host"] == "myserver"  # alias = hostname by default
    assert result["myserver"]["bin"] == "/usr/local/bin/runspec"
    assert result["myserver"]["user"] == "deploy"
    assert result["myserver"]["port"] == 22


def test_normalise_jump_hosts_explicit_host() -> None:
    raw = {"prod": {"host": "prod.example.com", "bin": "runspec"}}
    result = _normalise_jump_hosts(raw)
    assert result["prod"]["host"] == "prod.example.com"


def test_normalise_jump_hosts_ssh_key() -> None:
    raw = {"box": {"ssh-key": "~/.ssh/id_deploy"}}
    result = _normalise_jump_hosts(raw)
    assert result["box"]["ssh_key"] == "~/.ssh/id_deploy"


def test_normalise_jump_hosts_custom_port() -> None:
    raw = {"box": {"port": 2222}}
    result = _normalise_jump_hosts(raw)
    assert result["box"]["port"] == 2222


def test_normalise_jump_hosts_empty() -> None:
    assert _normalise_jump_hosts({}) == {}


def test_normalise_jump_hosts_skips_non_dict() -> None:
    raw = {"box": "not-a-dict"}  # type: ignore[dict-item]
    assert _normalise_jump_hosts(raw) == {}


# ── ssh_cmd ───────────────────────────────────────────────────────────────────


def test_ssh_cmd_minimal() -> None:
    cfg = {"host": "myserver", "bin": "runspec", "user": None, "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert cmd == ["ssh", "-o", "BatchMode=yes", "myserver", "runspec", "serve"]


def test_ssh_cmd_with_user() -> None:
    cfg = {"host": "myserver", "bin": "runspec", "user": "deploy", "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "deploy@myserver" in cmd


def test_ssh_cmd_custom_port() -> None:
    cfg = {"host": "myserver", "bin": "runspec", "user": None, "port": 2222, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "-p" in cmd
    assert "2222" in cmd


def test_ssh_cmd_default_port_not_included() -> None:
    cfg = {"host": "myserver", "bin": "runspec", "user": None, "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "-p" not in cmd


def test_ssh_cmd_with_key() -> None:
    cfg = {"host": "myserver", "bin": "/usr/local/bin/runspec", "user": None, "port": 22, "ssh_key": "~/.ssh/id_rsa"}
    cmd = ssh_cmd(cfg)
    assert "-i" in cmd
    assert "~/.ssh/id_rsa" in cmd


def test_ssh_cmd_ends_with_serve() -> None:
    cfg = {"host": "h", "bin": "runspec", "user": None, "port": 22, "ssh_key": None}
    assert ssh_cmd(cfg)[-1] == "serve"


# ── _parse_argv against the jump command's spec ───────────────────────────────

_JUMP_SPEC = {
    "list-jump-hosts": {"name": "list-jump-hosts", "type": "flag", "default": False},
    "format": {"name": "format", "type": "choice", "options": ["text", "json"], "default": "text"},
    "jump-host": {"name": "jump-host", "type": "str", "position": 1, "required": False},
    "tool": {"name": "tool", "type": "str", "position": 2, "required": False},
    "tool-args": {"name": "tool-args", "type": "rest", "default": []},
}


def test_jump_argv_no_flags() -> None:
    result = _parse_argv(["myserver", "deploy"], _JUMP_SPEC)
    assert result["jump_host"] == "myserver"
    assert result["tool"] == "deploy"


def test_jump_argv_bool_flag_then_positional() -> None:
    result = _parse_argv(["--list-jump-hosts", "myserver"], _JUMP_SPEC)
    assert result["list_jump_hosts"] is True
    assert result["jump_host"] == "myserver"


def test_jump_argv_value_flag_then_positional() -> None:
    result = _parse_argv(["myserver", "--format", "json"], _JUMP_SPEC)
    assert result["jump_host"] == "myserver"
    assert result["format"] == "json"


def test_jump_argv_just_flags() -> None:
    result = _parse_argv(["--list-jump-hosts", "--format", "json"], _JUMP_SPEC)
    assert result["list_jump_hosts"] is True
    assert result["jump_host"] is None
    assert result["tool"] is None


def test_jump_argv_host_and_tool_with_format() -> None:
    result = _parse_argv(["myserver", "deploy", "--format", "json"], _JUMP_SPEC)
    assert result["jump_host"] == "myserver"
    assert result["tool"] == "deploy"
    assert result["format"] == "json"


def test_jump_argv_rest_after_separator() -> None:
    result = _parse_argv(["myserver", "deploy", "--", "--env", "prod"], _JUMP_SPEC)
    assert result["jump_host"] == "myserver"
    assert result["tool"] == "deploy"
    assert result["tool_args"] == ["--env", "prod"]


def test_jump_argv_no_rest_args_when_no_separator() -> None:
    result = _parse_argv(["myserver"], _JUMP_SPEC)
    assert result["tool_args"] is None  # _apply_defaults fills in [] later


# ── parse_tool_argv ───────────────────────────────────────────────────────────


_SCHEMA = {
    "inputSchema": {
        "properties": {
            "env": {"type": "string", "description": "Environment"},
            "delete": {"type": "boolean", "description": "Delete flag"},
            "count": {"type": "integer", "description": "Count"},
        }
    }
}


def test_parse_tool_argv_string_arg() -> None:
    result = parse_tool_argv(["--env", "prod"], _SCHEMA)
    assert result == {"env": "prod"}


def test_parse_tool_argv_bool_flag() -> None:
    result = parse_tool_argv(["--delete"], _SCHEMA)
    assert result == {"delete": True}


def test_parse_tool_argv_mixed() -> None:
    result = parse_tool_argv(["--env", "prod", "--delete", "--count", "5"], _SCHEMA)
    assert result["env"] == "prod"
    assert result["delete"] is True
    assert result["count"] == "5"


def test_parse_tool_argv_unknown_arg_treated_as_value() -> None:
    result = parse_tool_argv(["--unknown", "val"], _SCHEMA)
    assert result == {"unknown": "val"}


def test_parse_tool_argv_empty() -> None:
    assert parse_tool_argv([], _SCHEMA) == {}


def test_parse_tool_argv_non_flag_tokens_ignored() -> None:
    result = parse_tool_argv(["positional", "--env", "prod"], _SCHEMA)
    assert result == {"env": "prod"}


def test_parse_tool_argv_missing_value_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        parse_tool_argv(["--env"], _SCHEMA)
