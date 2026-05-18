"""
Tests for runspec serve — MCP stdio server.

Covers arg translation, protocol handlers, dispatch routing, and
script discovery. Subprocess execution is tested via mocking.
"""

from __future__ import annotations

from runspec.serve import (
    MCP_PROTOCOL_VERSION,
    _args_to_argv,
    _dispatch,
    _find_script,
    _handle_initialize,
    _handle_tools_call,
    _handle_tools_list,
    _server_name,
)

# ── _args_to_argv ─────────────────────────────────────────────────────────────


def test_argv_str_arg():
    assert _args_to_argv({"env": "prod"}, {"env": {"type": "str"}}) == ["--env", "prod"]


def test_argv_int_arg():
    assert _args_to_argv({"workers": 4}, {"workers": {"type": "int"}}) == ["--workers", "4"]


def test_argv_flag_true():
    assert _args_to_argv({"dry-run": True}, {"dry-run": {"type": "flag"}}) == ["--dry-run"]


def test_argv_flag_false_omitted():
    assert _args_to_argv({"dry-run": False}, {"dry-run": {"type": "flag"}}) == []


def test_argv_missing_arg_omitted():
    assert _args_to_argv({}, {"env": {"type": "str"}}) == []


def test_argv_multiple():
    result = _args_to_argv({"tag": ["a", "b", "c"]}, {"tag": {"type": "str", "multiple": True}})
    assert result == ["--tag", "a", "--tag", "b", "--tag", "c"]


def test_argv_hyphen_name():
    result = _args_to_argv({"api-key": "secret"}, {"api-key": {"type": "str"}})
    assert result == ["--api-key", "secret"]


def test_argv_underscore_form_accepted():
    # Caller passes underscore form, spec has hyphen form
    result = _args_to_argv({"dry_run": True}, {"dry-run": {"type": "flag"}})
    assert result == ["--dry-run"]


def test_argv_ordering_follows_spec():
    specs = {"env": {"type": "str"}, "workers": {"type": "int"}, "dry-run": {"type": "flag"}}
    result = _args_to_argv({"workers": 2, "env": "dev", "dry-run": True}, specs)
    assert result == ["--env", "dev", "--workers", "2", "--dry-run"]


def test_argv_choice_arg():
    result = _args_to_argv({"format": "json"}, {"format": {"type": "choice", "options": ["json", "csv"]}})
    assert result == ["--format", "json"]


# ── _handle_initialize ────────────────────────────────────────────────────────


def test_initialize_shape():
    resp = _handle_initialize(1, "analytics-pipeline")
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "analytics-pipeline"
    assert "tools" in result["capabilities"]


def test_initialize_version_string():
    resp = _handle_initialize(42, "my-env")
    assert resp["result"]["protocolVersion"] == "2024-11-05"


# ── _handle_tools_list ────────────────────────────────────────────────────────


def test_tools_list_empty():
    resp = _handle_tools_list(2, {})
    assert resp["result"]["tools"] == []


def test_tools_list_returns_tool_schemas():
    tools = {
        "deploy": {"name": "deploy", "description": "Deploy", "inputSchema": {"type": "object", "properties": {}}},
    }
    resp = _handle_tools_list(2, tools)
    assert len(resp["result"]["tools"]) == 1
    assert resp["result"]["tools"][0]["name"] == "deploy"


def test_tools_list_shape():
    resp = _handle_tools_list(99, {})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 99
    assert "tools" in resp["result"]


# ── _dispatch ─────────────────────────────────────────────────────────────────


DUMMY_TOOLS: dict = {"greet": {"name": "greet", "inputSchema": {"type": "object", "properties": {}}}}
DUMMY_SPECS: dict = {"greet": {}}
DUMMY_EXEC_SPECS: dict = {"greet": {"command": None}}


def test_dispatch_initialize():
    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    resp = _dispatch(req, DUMMY_TOOLS, DUMMY_SPECS, DUMMY_EXEC_SPECS, "test-env")
    assert resp is not None
    assert "protocolVersion" in resp["result"]


def test_dispatch_tools_list():
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = _dispatch(req, DUMMY_TOOLS, DUMMY_SPECS, DUMMY_EXEC_SPECS, "test-env")
    assert resp is not None
    assert "tools" in resp["result"]


def test_dispatch_notification_returns_none():
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = _dispatch(req, DUMMY_TOOLS, DUMMY_SPECS, DUMMY_EXEC_SPECS, "test-env")
    assert resp is None


def test_dispatch_unknown_method():
    req = {"jsonrpc": "2.0", "id": 5, "method": "unknown/method"}
    resp = _dispatch(req, DUMMY_TOOLS, DUMMY_SPECS, DUMMY_EXEC_SPECS, "test-env")
    assert resp is not None
    assert resp["error"]["code"] == -32601


# ── _handle_tools_call ────────────────────────────────────────────────────────


def test_tools_call_unknown_tool():
    resp = _handle_tools_call(3, {"name": "missing", "arguments": {}}, DUMMY_TOOLS, DUMMY_SPECS, DUMMY_EXEC_SPECS)
    assert resp["error"]["code"] == -32602
    assert "missing" in resp["error"]["message"]


def test_tools_call_script_not_found():
    tools = {"greet": {"name": "greet", "inputSchema": {"type": "object", "properties": {}}}}
    exec_specs = {"greet": {"command": None}}
    resp = _handle_tools_call(3, {"name": "greet", "arguments": {}}, tools, {}, exec_specs)
    assert resp["result"]["isError"] is True
    assert "greet" in resp["result"]["content"][0]["text"]


def test_tools_call_success(tmp_path):
    script = tmp_path / "greet"
    script.write_text("#!/bin/sh\necho hello", encoding="utf-8")
    script.chmod(0o755)

    tools = {"greet": {"name": "greet", "inputSchema": {"type": "object", "properties": {}}}}
    exec_specs = {"greet": {"command": script}}

    resp = _handle_tools_call(3, {"name": "greet", "arguments": {}}, tools, {}, exec_specs)
    assert resp["result"]["isError"] is False
    assert "hello" in resp["result"]["content"][0]["text"]


def test_tools_call_failure(tmp_path):
    script = tmp_path / "deploy"
    script.write_text("#!/bin/sh\necho 'bad things' >&2\nexit 1", encoding="utf-8")
    script.chmod(0o755)

    tools = {"deploy": {"name": "deploy", "inputSchema": {"type": "object", "properties": {}}}}
    exec_specs = {"deploy": {"command": script}}

    resp = _handle_tools_call(4, {"name": "deploy", "arguments": {}}, tools, {}, exec_specs)
    assert resp["result"]["isError"] is True
    text = resp["result"]["content"][0]["text"]
    assert "exit_code: 1" in text
    assert "bad things" in text


def test_tools_call_sets_runspec_agent_env(tmp_path):
    script = tmp_path / "check_env"
    script.write_text("#!/bin/sh\necho $RUNSPEC_AGENT", encoding="utf-8")
    script.chmod(0o755)

    tools = {"check_env": {"name": "check_env", "inputSchema": {"type": "object", "properties": {}}}}
    exec_specs = {"check_env": {"command": script}}

    resp = _handle_tools_call(5, {"name": "check_env", "arguments": {}}, tools, {}, exec_specs)
    assert "1" in resp["result"]["content"][0]["text"]


# ── _find_script ──────────────────────────────────────────────────────────────


def test_find_script_in_scripts_dir(tmp_path):
    (tmp_path / "deploy").touch()
    assert _find_script("deploy", tmp_path) == tmp_path / "deploy"


def test_find_script_exe_in_scripts_dir(tmp_path):
    (tmp_path / "deploy.exe").touch()
    assert _find_script("deploy", tmp_path) == tmp_path / "deploy.exe"


def test_find_script_sh_in_scripts_dir(tmp_path):
    (tmp_path / "backup.sh").touch()
    assert _find_script("backup", tmp_path) == tmp_path / "backup.sh"


def test_find_script_ksh_in_scripts_dir(tmp_path):
    (tmp_path / "validate.ksh").touch()
    assert _find_script("validate", tmp_path) == tmp_path / "validate.ksh"


def test_find_script_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "backup-logs"
    script.touch()
    assert _find_script("backup-logs", tmp_path / "nonexistent-scripts") == script


def test_find_script_sh_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "backup-logs.sh"
    script.touch()
    assert _find_script("backup-logs", tmp_path / "nonexistent-scripts") == script


def test_find_script_in_cwd_bin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backup-logs"
    script.touch()
    assert _find_script("backup-logs", tmp_path / "nonexistent-scripts") == script


def test_find_script_scripts_dir_takes_priority_over_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scripts_dir = tmp_path / "venv_scripts"
    scripts_dir.mkdir()
    venv_script = scripts_dir / "deploy"
    venv_script.touch()
    cwd_script = tmp_path / "deploy"
    cwd_script.touch()
    assert _find_script("deploy", scripts_dir) == venv_script


def test_find_script_missing(tmp_path):
    assert _find_script("missing", tmp_path) is None


# ── _server_name ──────────────────────────────────────────────────────────────


def test_server_name_from_config():
    assert _server_name({"name": "analytics-pipeline"}) == "analytics-pipeline"


def test_server_name_falls_back_to_venv():
    name = _server_name({})
    assert isinstance(name, str)
    assert len(name) > 0


def test_server_name_ignores_non_string():
    name = _server_name({"name": 42})
    assert isinstance(name, str)
