"""Tests for runspec.jump — pure helper functions (no SSH required)."""

from __future__ import annotations

from typing import Any

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
    # New fields default cleanly
    assert result["myserver"]["use_ssh_config"] is True
    assert result["myserver"]["ssh_options"] == []


def test_normalise_jump_hosts_bin_unset_returns_none() -> None:
    """Loader returns None for bin when unset; jump.ssh_cmd applies the cascade."""
    raw = {"box": {}}
    result = _normalise_jump_hosts(raw)
    assert result["box"]["bin"] is None


def test_normalise_jump_hosts_use_ssh_config_false() -> None:
    raw = {"box": {"use-ssh-config": False}}
    result = _normalise_jump_hosts(raw)
    assert result["box"]["use_ssh_config"] is False


def test_normalise_jump_hosts_ssh_options_list() -> None:
    raw = {"box": {"ssh-options": ["ConnectTimeout=10", "StrictHostKeyChecking=no"]}}
    result = _normalise_jump_hosts(raw)
    assert result["box"]["ssh_options"] == ["ConnectTimeout=10", "StrictHostKeyChecking=no"]


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


def test_ssh_cmd_use_ssh_config_false_adds_dash_F_null() -> None:
    cfg = {"host": "h", "bin": "runspec", "user": None, "port": 22, "ssh_key": None, "use_ssh_config": False}
    cmd = ssh_cmd(cfg)
    assert "-F" in cmd
    assert "/dev/null" in cmd


def test_ssh_cmd_use_ssh_config_true_omits_dash_F() -> None:
    cfg = {"host": "h", "bin": "runspec", "user": None, "port": 22, "ssh_key": None, "use_ssh_config": True}
    cmd = ssh_cmd(cfg)
    assert "-F" not in cmd


def test_ssh_cmd_ssh_options_each_becomes_dash_o() -> None:
    cfg = {
        "host": "h",
        "bin": "runspec",
        "user": None,
        "port": 22,
        "ssh_key": None,
        "ssh_options": ["ConnectTimeout=10", "Compression=yes"],
    }
    cmd = ssh_cmd(cfg)
    # Each option gets its own -o flag
    assert cmd.count("-o") == 3  # BatchMode + two user options
    assert "ConnectTimeout=10" in cmd
    assert "Compression=yes" in cmd


def test_ssh_cmd_argv_order_explicit_before_ssh_options() -> None:
    """ssh-options are placed after explicit -p/-i so explicit fields win on conflict."""
    cfg = {
        "host": "h",
        "bin": "runspec",
        "user": None,
        "port": 2222,
        "ssh_key": "/tmp/key",
        "ssh_options": ["Port=99"],  # would lose to -p 2222 via OpenSSH first-wins
    }
    cmd = ssh_cmd(cfg)
    port_idx = cmd.index("-p")
    user_opt_idx = cmd.index("Port=99")
    assert port_idx < user_opt_idx


def test_ssh_cmd_bin_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When TOML has no bin, RUNSPEC_JUMP_BIN env var supplies the default."""
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/opt/runspec/bin/runspec")
    cfg = {"host": "h", "bin": None, "user": None, "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "/opt/runspec/bin/runspec" in cmd


def test_ssh_cmd_bin_toml_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/env/runspec")
    cfg = {"host": "h", "bin": "/toml/runspec", "user": None, "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "/toml/runspec" in cmd
    assert "/env/runspec" not in cmd


def test_ssh_cmd_bin_default_when_no_toml_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNSPEC_JUMP_BIN", raising=False)
    cfg = {"host": "h", "bin": None, "user": None, "port": 22, "ssh_key": None}
    cmd = ssh_cmd(cfg)
    assert "runspec" in cmd


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


# ── _report_remote_failure — friendly errors when SSH dies early ─────────────


class _FakeProc:
    """Minimal stand-in for subprocess.Popen used by _report_remote_failure tests."""

    def __init__(self, exit_code: int | None):
        self._exit_code = exit_code

    def wait(self, timeout: float | None = None) -> int:
        if self._exit_code is None:
            import subprocess as _sp

            raise _sp.TimeoutExpired(cmd="ssh", timeout=timeout or 1)
        return self._exit_code


def test_report_remote_failure_bare_name_blames_path(capsys: pytest.CaptureFixture[str]) -> None:
    """exit 127 with bare-name `bin` → 'not on remote PATH' message."""
    from runspec.jump import _report_remote_failure

    with pytest.raises(SystemExit) as exc:
        _report_remote_failure(_FakeProc(exit_code=127), bin_path="runspec")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "exit 127" in err
    assert "PATH" in err
    assert "RUNSPEC_JUMP_BIN" in err


def test_report_remote_failure_absolute_path_blames_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    """exit 127 with explicit `/path/to/runspec` → path hint in message."""
    from runspec.jump import _report_remote_failure

    with pytest.raises(SystemExit) as exc:
        _report_remote_failure(_FakeProc(exit_code=127), bin_path="/nonexistent/.venv/bin/runspec")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "exit 127" in err
    assert "/nonexistent/.venv/bin/runspec" in err
    assert "verify the path exists" in err
    # PATH-specific hint should NOT be in the absolute-path branch
    assert "remote shell's PATH" not in err


def test_report_remote_failure_no_bin_path_falls_back_to_path_branch(capsys: pytest.CaptureFixture[str]) -> None:
    """When bin_path isn't threaded through, default to the PATH-branch wording."""
    from runspec.jump import _report_remote_failure

    with pytest.raises(SystemExit) as exc:
        _report_remote_failure(_FakeProc(exit_code=127))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "exit 127" in err
    assert "PATH" in err


def test_report_remote_failure_ssh_connection(capsys: pytest.CaptureFixture[str]) -> None:
    """exit 255 is OpenSSH's connection-failure exit code."""
    from runspec.jump import _report_remote_failure

    with pytest.raises(SystemExit) as exc:
        _report_remote_failure(_FakeProc(exit_code=255))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "SSH connection failed" in err


def test_report_remote_failure_stdout_closed_but_process_alive(capsys: pytest.CaptureFixture[str]) -> None:
    """Unusual case: stdout EOF but process still running — fall back to generic message."""
    from runspec.jump import _report_remote_failure

    with pytest.raises(SystemExit) as exc:
        _report_remote_failure(_FakeProc(exit_code=None))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "closed stdout unexpectedly" in err


# ── _validate_bin_path — lock `bin` to the runspec executable ────────────────


def _cfg(**overrides: Any) -> dict[str, Any]:
    base = {"host": "h", "user": None, "port": 22, "ssh_key": None}
    base.update(overrides)
    return base


def test_bin_path_default_runspec_accepted() -> None:
    # Sanity: default "runspec" with no path qualifies
    ssh_cmd(_cfg(bin="runspec"))


def test_bin_path_full_path_to_runspec_accepted() -> None:
    ssh_cmd(_cfg(bin="/opt/svc-a/.venv/bin/runspec"))


def test_bin_path_runspec_exe_accepted() -> None:
    ssh_cmd(_cfg(bin="C:/Users/dev/.venv/Scripts/runspec.exe"))


def test_bin_path_redirection_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        ssh_cmd(_cfg(bin="/usr/bin/cat"))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "runspec" in err
    assert "/usr/bin/cat" in err
    assert "cat" in err  # basename mentioned


def test_bin_path_rejected_message_explains_lock(capsys: pytest.CaptureFixture[str]) -> None:
    """Error message tells the developer the field is intentionally locked."""
    with pytest.raises(SystemExit):
        ssh_cmd(_cfg(bin="/some/other/tool"))
    err = capsys.readouterr().err
    assert "locked" in err.lower() or "cannot be redirected" in err.lower()


def test_bin_path_env_var_also_validated(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """RUNSPEC_JUMP_BIN goes through the same check."""
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/etc/passwd")
    with pytest.raises(SystemExit) as exc:
        ssh_cmd(_cfg(bin=None))  # falls back to env var
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "/etc/passwd" in err


# ── jump --list-jump-hosts shows effective bin (cascaded) in BOTH formats ─────


def _make_toml(tmp_path: Any, content: str) -> Any:
    """Write a runspec.toml in tmp_path and return its path."""
    p = tmp_path / "runspec.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_list_jump_hosts_text_shows_effective_bin_from_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from runspec.cli import _cmd_list_jump_hosts

    _make_toml(tmp_path, '[config.jump-hosts.localhost]\nhost = "localhost"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/opt/svc/.venv/bin/runspec")

    _cmd_list_jump_hosts("text")
    out = capsys.readouterr().out
    assert "/opt/svc/.venv/bin/runspec" in out
    assert "bin=None" not in out


def test_list_jump_hosts_json_shows_effective_bin_from_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Both text and JSON output must show the effective bin — not raw null."""
    import json as _json

    from runspec.cli import _cmd_list_jump_hosts

    _make_toml(tmp_path, '[config.jump-hosts.localhost]\nhost = "localhost"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/opt/svc/.venv/bin/runspec")

    _cmd_list_jump_hosts("json")
    parsed = _json.loads(capsys.readouterr().out)
    assert parsed[0]["bin"] == "/opt/svc/.venv/bin/runspec"
    # No null bin — that was the bug
    assert parsed[0]["bin"] is not None


def test_list_jump_hosts_json_shows_default_runspec_when_unset(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """No TOML bin and no env var → 'runspec' default, not null."""
    import json as _json

    from runspec.cli import _cmd_list_jump_hosts

    _make_toml(tmp_path, '[config.jump-hosts.localhost]\nhost = "localhost"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RUNSPEC_JUMP_BIN", raising=False)

    _cmd_list_jump_hosts("json")
    parsed = _json.loads(capsys.readouterr().out)
    assert parsed[0]["bin"] == "runspec"


def test_list_jump_hosts_json_toml_bin_overrides_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """TOML bin takes precedence over RUNSPEC_JUMP_BIN in the listing too."""
    import json as _json

    from runspec.cli import _cmd_list_jump_hosts

    _make_toml(tmp_path, '[config.jump-hosts.localhost]\nhost = "localhost"\nbin = "/toml/runspec"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNSPEC_JUMP_BIN", "/env/runspec")

    _cmd_list_jump_hosts("json")
    parsed = _json.loads(capsys.readouterr().out)
    assert parsed[0]["bin"] == "/toml/runspec"


# ── call_tool propagates isError to its own exit code ────────────────────────


def test_call_tool_exits_nonzero_when_isError(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """When the remote tool reports isError=true, runspec jump exits 1."""
    from runspec import jump as jump_mod

    host_cfg = {"host": "h", "bin": "runspec", "user": None, "port": 22, "ssh_key": None}

    # Three MCP responses come back in order: tools/list, then tools/call
    responses = iter(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "broken", "inputSchema": {"type": "object", "properties": {}}}]},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": "exit_code: 1\nstderr: it failed"}],
                    "isError": True,
                },
            },
        ]
    )

    monkeypatch.setattr(jump_mod, "_open_session", lambda cfg: _FakeProc(exit_code=None))
    monkeypatch.setattr(jump_mod, "_send", lambda proc, msg: None)
    monkeypatch.setattr(jump_mod, "_recv", lambda proc, bin_path=None: next(responses))
    monkeypatch.setattr(jump_mod, "_close", lambda proc: None)

    with pytest.raises(SystemExit) as exc:
        jump_mod.call_tool(host_cfg, "broken", [])
    assert exc.value.code == 1
    # The structured exit_code block still appears in stdout for the user / MCP client
    assert "exit_code: 1" in capsys.readouterr().out


def test_call_tool_exits_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful tool call → no isError → jump exits 0."""
    from runspec import jump as jump_mod

    host_cfg = {"host": "h", "bin": "runspec", "user": None, "port": 22, "ssh_key": None}

    responses = iter(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "ok", "inputSchema": {"type": "object", "properties": {}}}]},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": "all good"}],
                    "isError": False,
                },
            },
        ]
    )

    monkeypatch.setattr(jump_mod, "_open_session", lambda cfg: _FakeProc(exit_code=None))
    monkeypatch.setattr(jump_mod, "_send", lambda proc, msg: None)
    monkeypatch.setattr(jump_mod, "_recv", lambda proc, bin_path=None: next(responses))
    monkeypatch.setattr(jump_mod, "_close", lambda proc: None)

    # Should not raise SystemExit
    jump_mod.call_tool(host_cfg, "ok", [])
