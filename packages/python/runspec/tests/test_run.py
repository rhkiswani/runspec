"""
Tests for runspec.run — command building, registry fetch, local/remote dispatch.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from runspec.run import (
    _arg_name_to_env_key,
    _args_to_runspec_env,
    _build_remote_command,
    _http_get,
    _parse_argv_to_dict,
    _resolve_local_command,
    list_registry_tools,
    run_local,
)

# ── _arg_name_to_env_key ─────────────────────────────────────────────────────


def test_env_key_simple() -> None:
    assert _arg_name_to_env_key("env") == "RUNSPEC_ENV"


def test_env_key_hyphen() -> None:
    assert _arg_name_to_env_key("dry-run") == "RUNSPEC_DRY_RUN"


def test_env_key_underscore() -> None:
    assert _arg_name_to_env_key("input_file") == "RUNSPEC_INPUT_FILE"


# ── _args_to_runspec_env ──────────────────────────────────────────────────────


def test_env_str_value() -> None:
    specs = {"env": {"type": "str"}}
    result = _args_to_runspec_env({"env": "prod"}, specs)
    assert result == {"RUNSPEC_ENV": "prod"}


def test_env_int_value() -> None:
    specs = {"days": {"type": "int"}}
    result = _args_to_runspec_env({"days": 7}, specs)
    assert result == {"RUNSPEC_DAYS": "7"}


def test_env_flag_true() -> None:
    specs = {"dry-run": {"type": "flag"}}
    result = _args_to_runspec_env({"dry-run": True}, specs)
    assert result == {"RUNSPEC_DRY_RUN": "1"}


def test_env_flag_false() -> None:
    specs = {"dry-run": {"type": "flag"}}
    result = _args_to_runspec_env({"dry-run": False}, specs)
    assert result == {"RUNSPEC_DRY_RUN": "0"}


def test_env_bool_true() -> None:
    specs = {"verbose": {"type": "bool"}}
    result = _args_to_runspec_env({"verbose": True}, specs)
    assert result == {"RUNSPEC_VERBOSE": "1"}


def test_env_bool_false() -> None:
    specs = {"verbose": {"type": "bool"}}
    result = _args_to_runspec_env({"verbose": False}, specs)
    assert result == {"RUNSPEC_VERBOSE": "0"}


def test_env_uses_default_when_absent() -> None:
    specs = {"days": {"type": "int", "default": 7}}
    result = _args_to_runspec_env({}, specs)
    assert result == {"RUNSPEC_DAYS": "7"}


def test_env_skips_arg_with_no_value_and_no_default() -> None:
    specs = {"env": {"type": "str"}}
    result = _args_to_runspec_env({}, specs)
    assert "RUNSPEC_ENV" not in result


def test_env_multiple_values() -> None:
    specs = {"files": {"type": "str", "multiple": True}}
    result = _args_to_runspec_env({"files": ["a.txt", "b.txt"]}, specs)
    assert result == {"RUNSPEC_FILES": "a.txt\nb.txt"}


def test_env_accepts_underscore_key_from_caller() -> None:
    specs = {"dry-run": {"type": "flag"}}
    result = _args_to_runspec_env({"dry_run": True}, specs)
    assert result == {"RUNSPEC_DRY_RUN": "1"}


# ── _parse_argv_to_dict ───────────────────────────────────────────────────────


def test_parse_argv_string_arg() -> None:
    specs = {"env": {"type": "str"}}
    result = _parse_argv_to_dict(["--env", "prod"], specs)
    assert result == {"env": "prod"}


def test_parse_argv_flag_no_value() -> None:
    specs = {"dry-run": {"type": "flag"}}
    result = _parse_argv_to_dict(["--dry-run"], specs)
    assert result == {"dry-run": True}


def test_parse_argv_multiple_values() -> None:
    specs = {"file": {"type": "str", "multiple": True}}
    result = _parse_argv_to_dict(["--file", "a.txt", "--file", "b.txt"], specs)
    assert result == {"file": ["a.txt", "b.txt"]}


def test_parse_argv_skips_non_flag_tokens() -> None:
    specs = {"env": {"type": "str"}}
    result = _parse_argv_to_dict(["positional", "--env", "prod"], specs)
    assert result == {"env": "prod"}


# ── _build_remote_command ─────────────────────────────────────────────────────


def test_no_run_as_returns_plain_command() -> None:
    result = _build_remote_command("/bin/deploy", [], None, "sudo", None)
    assert result == "/bin/deploy"


def test_no_run_as_with_args() -> None:
    result = _build_remote_command("/bin/deploy", ["--env", "prod"], None, "sudo", None)
    assert result == "/bin/deploy --env prod"


def test_sudo_run_as() -> None:
    result = _build_remote_command("/bin/deploy", ["--env", "prod"], "oracle", "sudo", None)
    assert result == "sudo -u oracle /bin/deploy --env prod"


def test_sudo_with_flags() -> None:
    result = _build_remote_command("/bin/deploy", [], "oracle", "sudo", "-H")
    assert result == "sudo -H -u oracle /bin/deploy"


def test_pbrun_run_as() -> None:
    result = _build_remote_command("/bin/deploy", [], "oracle", "pbrun", None)
    assert result == "pbrun -u oracle /bin/deploy"


def test_dzdo_run_as() -> None:
    result = _build_remote_command("/bin/deploy", [], "oracle", "dzdo", None)
    assert result == "dzdo -u oracle /bin/deploy"


def test_su_run_as() -> None:
    result = _build_remote_command("/bin/deploy", [], "oracle", "su", None)
    assert result == "su -c /bin/deploy oracle"


def test_su_with_args() -> None:
    result = _build_remote_command("/bin/deploy", ["--env", "prod"], "oracle", "su", None)
    assert result == "su -c '/bin/deploy --env prod' oracle"


def test_su_with_flags() -> None:
    result = _build_remote_command("/bin/deploy", [], "oracle", "su", "-l")
    assert result == "su -l -c /bin/deploy oracle"


def test_args_are_shell_quoted() -> None:
    result = _build_remote_command("/bin/deploy", ["--msg", "hello world"], "oracle", "sudo", None)
    assert "'hello world'" in result


def test_command_with_spaces_is_quoted() -> None:
    result = _build_remote_command("/path with spaces/deploy", [], "oracle", "sudo", None)
    assert "'/path with spaces/deploy'" in result


# ── _http_get / list_registry_tools (with mock HTTP server) ──────────────────


def _make_server(response_body: Any, status: int = 200) -> HTTPServer:
    body_bytes = json.dumps(response_body).encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body_bytes)

        def log_message(self, *args: Any) -> None:
            pass

    return HTTPServer(("127.0.0.1", 0), _Handler)


def _server_url(srv: HTTPServer) -> str:
    port = srv.server_address[1]
    return f"http://127.0.0.1:{port}"


def test_http_get_returns_parsed_json() -> None:
    payload = [{"name": "deploy", "hosts": []}]
    srv = _make_server(payload)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    result = _http_get(_server_url(srv) + "/tools", None, None)
    t.join()
    srv.server_close()
    assert result == payload


def test_list_registry_tools_shapes_output() -> None:
    payload = [
        {
            "name": "deploy",
            "description": "Deploy the app",
            "hosts": [{"host": "server-01", "x-command": "/bin/d"}],
        }
    ]
    srv = _make_server(payload)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    tools = list_registry_tools(_server_url(srv))
    t.join()
    srv.server_close()
    assert len(tools) == 1
    assert tools[0]["name"] == "deploy"
    assert tools[0]["hosts"] == ["server-01"]


def test_http_get_exits_on_404(capsys: pytest.CaptureFixture[str]) -> None:
    srv = _make_server({"detail": "not found"}, status=404)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    with pytest.raises(SystemExit) as exc:
        _http_get(_server_url(srv) + "/tools/ghost", None, None)
    t.join()
    srv.server_close()
    assert exc.value.code == 1


# ── _resolve_local_command ────────────────────────────────────────────────────


def test_resolve_local_command_finds_in_scripts_dir(tmp_path) -> None:
    script = tmp_path / "greet"
    script.touch()
    result = _resolve_local_command("greet", tmp_path)
    assert result == [str(script)]


def test_resolve_local_command_finds_exe(tmp_path) -> None:
    script = tmp_path / "greet.exe"
    script.touch()
    result = _resolve_local_command("greet", tmp_path)
    assert result == [str(script)]


def test_resolve_local_command_toml_dir_fallback(tmp_path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    toml_dir = tmp_path / "mypkg"
    toml_dir.mkdir()
    script = toml_dir / "greet"
    script.touch()
    result = _resolve_local_command("greet", scripts_dir, toml_dir)
    assert result == [str(script)]


def test_resolve_local_command_toml_dir_py_fallback(tmp_path) -> None:
    import sys
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    toml_dir = tmp_path / "mypkg"
    toml_dir.mkdir()
    py_script = toml_dir / "greet.py"
    py_script.touch()
    result = _resolve_local_command("greet", scripts_dir, toml_dir)
    assert result == [sys.executable, str(py_script)]


def test_resolve_local_command_toml_dir_sh_fallback(tmp_path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    toml_dir = tmp_path / "mypkg"
    toml_dir.mkdir()
    sh_script = toml_dir / "greet.sh"
    sh_script.touch()
    result = _resolve_local_command("greet", scripts_dir, toml_dir)
    assert result == [str(sh_script)]


def test_resolve_local_command_venv_beats_toml_dir(tmp_path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    venv_script = scripts_dir / "greet"
    venv_script.touch()
    toml_dir = tmp_path / "mypkg"
    toml_dir.mkdir()
    (toml_dir / "greet").touch()
    result = _resolve_local_command("greet", scripts_dir, toml_dir)
    assert result == [str(venv_script)]


def test_resolve_local_command_exits_when_missing(tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _resolve_local_command("missing", tmp_path)
    assert exc.value.code == 1
    assert "missing" in capsys.readouterr().err


# ── run_local (dev=True) ──────────────────────────────────────────────────────


def test_run_local_dev_exits_when_no_configs(tmp_path, capsys) -> None:
    from unittest.mock import patch

    with patch("runspec.finder.find_configs_dev", return_value=[]):
        with pytest.raises(SystemExit) as exc:
            run_local("greet", [], dev=True)

    assert exc.value.code == 1
    assert "No runspec.toml" in capsys.readouterr().err


def test_run_local_dev_exits_when_tool_not_found(tmp_path, capsys) -> None:
    from unittest.mock import patch

    toml = tmp_path / "mypkg" / "runspec.toml"
    toml.parent.mkdir()
    toml.write_text("[other]\ndescription = 'Other'\n", encoding="utf-8")

    with patch("runspec.finder.find_configs_dev", return_value=[toml]):
        with pytest.raises(SystemExit) as exc:
            run_local("missing", [], dev=True)

    assert exc.value.code == 1
    assert "missing" in capsys.readouterr().err


def test_run_local_dev_runs_script_from_toml_dir(tmp_path) -> None:
    import subprocess as sp
    from unittest.mock import patch

    toml = tmp_path / "mypkg" / "runspec.toml"
    toml.parent.mkdir()
    toml.write_text("[greet]\ndescription = 'Greet'\n", encoding="utf-8")

    # Script lives alongside runspec.toml (toml_dir fallback)
    script = tmp_path / "mypkg" / "greet"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    fake_scripts_dir = tmp_path / "empty_scripts"
    fake_scripts_dir.mkdir()

    with (
        patch("runspec.finder.find_configs_dev", return_value=[toml]),
        patch("sysconfig.get_path", return_value=str(fake_scripts_dir)),
        patch("subprocess.run", return_value=sp.CompletedProcess([], 0)) as mock_run,
    ):
        result = run_local("greet", [], dev=True)

    assert result == 0
    # Command must reference the script in the package directory
    called_cmd = mock_run.call_args[0][0]
    assert str(script) == called_cmd[0]
