"""
Tests for runspec serve — MCP stdio server.

Covers arg translation, protocol handlers, dispatch routing, and
script discovery. Subprocess execution is tested via mocking.
"""

from __future__ import annotations

import pytest

from runspec.serve import (
    MCP_PROTOCOL_VERSION,
    _args_to_argv,
    _dispatch,
    _expand_tools,
    _find_script,
    _handle_initialize,
    _handle_tools_call,
    _handle_tools_list,
    _server_name,
    serve,
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
    exec_specs = {"greet": {"command": [str(script)]}}

    resp = _handle_tools_call(3, {"name": "greet", "arguments": {}}, tools, {}, exec_specs)
    assert resp["result"]["isError"] is False
    assert "hello" in resp["result"]["content"][0]["text"]


def test_tools_call_failure(tmp_path):
    script = tmp_path / "deploy"
    script.write_text("#!/bin/sh\necho 'bad things' >&2\nexit 1", encoding="utf-8")
    script.chmod(0o755)

    tools = {"deploy": {"name": "deploy", "inputSchema": {"type": "object", "properties": {}}}}
    exec_specs = {"deploy": {"command": [str(script)]}}

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
    exec_specs = {"check_env": {"command": [str(script)]}}

    resp = _handle_tools_call(5, {"name": "check_env", "arguments": {}}, tools, {}, exec_specs)
    assert "1" in resp["result"]["content"][0]["text"]


# ── _find_script ──────────────────────────────────────────────────────────────


def test_find_script_in_scripts_dir(tmp_path):
    script = tmp_path / "deploy"
    script.touch()
    assert _find_script("deploy", tmp_path) == [str(script)]


def test_find_script_exe_in_scripts_dir(tmp_path):
    script = tmp_path / "deploy.exe"
    script.touch()
    assert _find_script("deploy", tmp_path) == [str(script)]



def test_find_script_missing(tmp_path):
    assert _find_script("missing", tmp_path) is None


# ── _expand_tools ─────────────────────────────────────────────────────────────

_LEAF_INFERRED = {
    "description": "Do a thing",
    "autonomy": "confirm",
    "output": "text",
    "args": {"env": {"type": "str", "required": True}},
    "commands": {},
}


def test_expand_tools_no_commands():
    entries = _expand_tools("greet", _LEAF_INFERRED, ["/bin/greet"], None, "sudo", None)
    assert len(entries) == 1
    flat_name, schema, arg_spec, exec_spec = entries[0]
    assert flat_name == "greet"
    assert schema["name"] == "greet"
    assert exec_spec["command"] == ["/bin/greet"]


def test_expand_tools_one_level():
    inferred = {
        "description": "Pipeline tool",
        "autonomy": "confirm",
        "output": "text",
        "args": {},
        "commands": {
            "run": _LEAF_INFERRED,
            "validate": {**_LEAF_INFERRED, "description": "Validate"},
        },
    }
    entries = _expand_tools("pipeline", inferred, ["/bin/pipeline"], None, "sudo", None)
    names = [e[0] for e in entries]
    assert names == ["pipeline_run", "pipeline_validate"]
    _, _, _, exec_spec_run = entries[0]
    assert exec_spec_run["command"] == ["/bin/pipeline", "run"]
    _, _, _, exec_spec_val = entries[1]
    assert exec_spec_val["command"] == ["/bin/pipeline", "validate"]


def test_expand_tools_two_levels():
    get_list = {**_LEAF_INFERRED, "description": "List orders", "args": {"limit": {"type": "int"}}}
    post_sale = {**_LEAF_INFERRED, "description": "Post a sale", "args": {"amount": {"type": "int", "required": True}}}
    orders_endpoint = {
        "description": "Orders endpoint",
        "autonomy": "confirm",
        "output": "text",
        "args": {},
        "commands": {"get_list": get_list, "post_sale": post_sale},
    }
    portal_api = {
        "description": "Portal API",
        "autonomy": "confirm",
        "output": "text",
        "args": {},
        "commands": {"orders_endpoint": orders_endpoint},
    }
    entries = _expand_tools("portal_api", portal_api, ["/bin/portal_api"], None, "sudo", None)
    names = [e[0] for e in entries]
    assert "portal_api_orders_endpoint_get_list" in names
    assert "portal_api_orders_endpoint_post_sale" in names
    # Command prefix includes both subcommand levels
    by_name = {e[0]: e for e in entries}
    _, _, _, exec_get = by_name["portal_api_orders_endpoint_get_list"]
    assert exec_get["command"] == ["/bin/portal_api", "orders_endpoint", "get_list"]
    _, _, arg_spec_post, exec_post = by_name["portal_api_orders_endpoint_post_sale"]
    assert exec_post["command"] == ["/bin/portal_api", "orders_endpoint", "post_sale"]
    assert "amount" in arg_spec_post


def test_expand_tools_none_command_propagated():
    entries = _expand_tools("greet", _LEAF_INFERRED, None, None, "sudo", None)
    _, _, _, exec_spec = entries[0]
    assert exec_spec["command"] is None


def test_expand_tools_run_as_propagated_to_leaves():
    inferred = {
        "description": "root",
        "autonomy": "confirm",
        "output": "text",
        "args": {},
        "commands": {"sub": _LEAF_INFERRED},
    }
    entries = _expand_tools("tool", inferred, ["/bin/tool"], "oracle", "sudo", "-H")
    _, _, _, exec_spec = entries[0]
    assert exec_spec["run_as"] == "oracle"
    assert exec_spec["become_flags"] == "-H"


def test_expand_tools_leaf_schema_has_args():
    entries = _expand_tools("greet", _LEAF_INFERRED, ["/bin/greet"], None, "sudo", None)
    _, schema, arg_spec, _ = entries[0]
    assert "env" in schema["inputSchema"]["properties"]
    assert "env" in arg_spec


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


# ── serve(dev=True) ───────────────────────────────────────────────────────────


def test_serve_dev_exits_when_no_configs_found(capsys):
    from unittest.mock import patch

    with patch("runspec.finder.find_configs_dev", return_value=[]):
        with pytest.raises(SystemExit) as exc:
            serve(dev=True)

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "No runspec.toml" in captured.err


def test_serve_dev_warns_on_duplicate_runnable_name(tmp_path, capsys):
    from unittest.mock import patch

    toml1 = tmp_path / "pkg1" / "runspec.toml"
    toml1.parent.mkdir()
    toml1.write_text("[greet]\ndescription = 'From pkg1'\n", encoding="utf-8")

    toml2 = tmp_path / "pkg2" / "runspec.toml"
    toml2.parent.mkdir()
    toml2.write_text("[greet]\ndescription = 'From pkg2'\n", encoding="utf-8")

    captured_tools: dict = {}

    def fake_mcp_loop(tools, arg_specs, exec_specs, name):
        captured_tools.update(tools)

    with (
        patch("runspec.finder.find_configs_dev", return_value=[toml1, toml2]),
        patch("runspec.serve._mcp_loop", fake_mcp_loop),
        patch("runspec.serve._find_script", return_value=None),
    ):
        serve(dev=True)

    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "greet" in captured.err
    # First definition wins
    assert "greet" in captured_tools


def test_serve_dev_aggregates_runnables_from_multiple_tomls(tmp_path):
    from unittest.mock import patch

    toml1 = tmp_path / "pkg1" / "runspec.toml"
    toml1.parent.mkdir()
    toml1.write_text("[greet]\ndescription = 'Greet'\n", encoding="utf-8")

    toml2 = tmp_path / "pkg2" / "runspec.toml"
    toml2.parent.mkdir()
    toml2.write_text("[deploy]\ndescription = 'Deploy'\n", encoding="utf-8")

    captured_tools: dict = {}

    def fake_mcp_loop(tools, arg_specs, exec_specs, name):
        captured_tools.update(tools)

    with (
        patch("runspec.finder.find_configs_dev", return_value=[toml1, toml2]),
        patch("runspec.serve._mcp_loop", fake_mcp_loop),
        patch("runspec.serve._find_script", return_value=None),
    ):
        serve(dev=True)

    assert "greet" in captured_tools
    assert "deploy" in captured_tools
