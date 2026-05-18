"""
Tests for runspec serve registry integration.

Uses a mock HTTP server (stdlib http.server) as the test fixture.
The registry client functions are tested against it directly.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from runspec.serve import (
    _registry_deregister,
    _registry_heartbeat,
    _registry_register,
    _registry_request,
    _registry_tools,
    _resolve_run_as,
    _validate_run_as_patterns,
)

# ── Mock registry fixture ──────────────────────────────────────────────────────


class _RegistryState:
    """Shared mutable state between test and mock server."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.heartbeat_response: str = "ack"


def _make_handler(state: _RegistryState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                return json.loads(self.rfile.read(length))
            return {}

        def _send_json(self, data: dict[str, Any]) -> None:
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            body = self._read_body()
            state.requests.append({"method": "POST", "path": self.path, "body": body, "headers": dict(self.headers)})
            if self.path.endswith("/heartbeat"):
                self._send_json({"status": state.heartbeat_response})
            else:
                self._send_json({"status": "ok"})

        def do_DELETE(self) -> None:
            state.requests.append({"method": "DELETE", "path": self.path, "body": {}, "headers": dict(self.headers)})
            self._send_json({"status": "ok"})

        def log_message(self, *args: Any) -> None:
            pass

    return Handler


@pytest.fixture()
def mock_registry():
    """Start a mock registry server; yield (base_url, state); shut down after test."""
    state = _RegistryState()
    server = HTTPServer(("127.0.0.1", 0), _make_handler(state))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url, state
    server.shutdown()
    server.server_close()


# ── _registry_register ────────────────────────────────────────────────────────


def test_register_sends_correct_body(mock_registry):
    url, state = mock_registry
    _registry_register(url, "agent-123", "my-pipeline", "1", "myhost.corp")
    assert len(state.requests) == 1
    req = state.requests[0]
    assert req["path"] == "/instances"
    assert req["body"]["instance_id"] == "agent-123"
    assert req["body"]["name"] == "my-pipeline"
    assert req["body"]["version"] == "1"
    assert req["body"]["host"] == "myhost.corp"


def test_register_does_not_raise_on_ok(mock_registry):
    url, _ = mock_registry
    _registry_register(url, "x", "y", "1", "host")  # should not raise


def test_register_sends_api_key_header(mock_registry):
    url, state = mock_registry
    _registry_register(url, "x", "y", "1", "host", api_key="secret-key")
    assert state.requests[0]["headers"].get("X-Api-Key") == "secret-key"


# ── _registry_heartbeat ───────────────────────────────────────────────────────


def test_heartbeat_path_contains_instance_id(mock_registry):
    url, state = mock_registry
    _registry_heartbeat(url, "agent-abc", [], time.time())
    assert state.requests[0]["path"] == "/instances/agent-abc/heartbeat"


def test_heartbeat_sends_empty_body_when_no_data_fields(mock_registry):
    url, state = mock_registry
    _registry_heartbeat(url, "agent-abc", [], time.time())
    assert state.requests[0]["body"] == {}


def test_heartbeat_includes_system_data(mock_registry):
    url, state = mock_registry
    start = time.time() - 60
    _registry_heartbeat(url, "agent-abc", ["system"], start)
    body = state.requests[0]["body"]
    assert "system" in body
    assert isinstance(body["system"]["pid"], int)
    assert body["system"]["uptime"] >= 60


def test_heartbeat_returns_ack(mock_registry):
    url, state = mock_registry
    state.heartbeat_response = "ack"
    assert _registry_heartbeat(url, "agent-abc", [], time.time()) == "ack"


def test_heartbeat_returns_refresh(mock_registry):
    url, state = mock_registry
    state.heartbeat_response = "refresh"
    assert _registry_heartbeat(url, "agent-abc", [], time.time()) == "refresh"


# ── _registry_tools ───────────────────────────────────────────────────────────


def test_tools_path_contains_instance_id(mock_registry):
    url, state = mock_registry
    _registry_tools(url, "agent-abc", [])
    assert state.requests[0]["path"] == "/instances/agent-abc/tools"


def test_tools_sends_tool_list(mock_registry):
    url, state = mock_registry
    tools = [{"name": "deploy", "description": "Deploy", "inputSchema": {"type": "object"}}]
    _registry_tools(url, "agent-abc", tools)
    body = state.requests[0]["body"]
    assert len(body["tools"]) == 1
    assert body["tools"][0]["name"] == "deploy"


def test_tools_sends_empty_list(mock_registry):
    url, state = mock_registry
    _registry_tools(url, "agent-abc", [])
    assert state.requests[0]["body"]["tools"] == []


# ── _registry_deregister ──────────────────────────────────────────────────────


def test_deregister_uses_delete_method(mock_registry):
    url, state = mock_registry
    _registry_deregister(url, "agent-xyz")
    assert state.requests[0]["method"] == "DELETE"


def test_deregister_path_contains_instance_id(mock_registry):
    url, state = mock_registry
    _registry_deregister(url, "agent-xyz")
    assert state.requests[0]["path"] == "/instances/agent-xyz"


# ── _registry_request error handling ──────────────────────────────────────────


def test_request_raises_on_connection_refused():
    with pytest.raises(RuntimeError, match="failed"):
        _registry_request("http://127.0.0.1:1", "/instances", {})


def test_request_raises_on_http_error(mock_registry):
    class ErrorHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            body = b'{"error": "boom"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    err_server = HTTPServer(("127.0.0.1", 0), ErrorHandler)
    err_port = err_server.server_address[1]
    threading.Thread(target=err_server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(RuntimeError, match="HTTP 500"):
            _registry_request(f"http://127.0.0.1:{err_port}", "/instances", {})
    finally:
        err_server.shutdown()
        err_server.server_close()


# ── _resolve_run_as ───────────────────────────────────────────────────────────


def test_resolve_run_as_none():
    assert _resolve_run_as(None, "myhost") == ""


def test_resolve_run_as_simple_string():
    assert _resolve_run_as("oracle", "myhost") == "oracle"


def test_resolve_run_as_env_var(monkeypatch):
    monkeypatch.setenv("ORACLE_USER", "dba")
    assert _resolve_run_as("$ORACLE_USER", "myhost") == "dba"


def test_resolve_run_as_env_var_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert _resolve_run_as("$MISSING_VAR", "myhost") == ""


def test_resolve_run_as_exact_host_match():
    spec = {"default": "oracle", "hosts": {"special-box": "dba"}}
    assert _resolve_run_as(spec, "special-box") == "dba"


def test_resolve_run_as_exact_host_empty_string_means_no_sudo():
    spec = {"default": "oracle", "hosts": {"no-sudo-box": ""}}
    assert _resolve_run_as(spec, "no-sudo-box") == ""


def test_resolve_run_as_exact_host_takes_priority_over_pattern():
    spec = {
        "default": "oracle",
        "hosts": {"lpexp001": "hostuser"},
        "patterns": {"lpexp[0-9]*": "patternuser"},
    }
    assert _resolve_run_as(spec, "lpexp001") == "hostuser"


def test_resolve_run_as_pattern_match():
    spec = {"default": "oracle", "patterns": {"[lg]pexp[0-9]*": "orasvc"}}
    assert _resolve_run_as(spec, "lpexp042") == "orasvc"
    assert _resolve_run_as(spec, "gpexp001") == "orasvc"


def test_resolve_run_as_pattern_no_match_falls_back_to_default():
    spec = {"default": "oracle", "patterns": {"prod[0-9]*": "produser"}}
    assert _resolve_run_as(spec, "dev001") == "oracle"


def test_resolve_run_as_pattern_first_match_wins():
    spec = {"patterns": {"[lg]pexp[0-9]*": "first", "gpexp[0-9]*": "second"}}
    assert _resolve_run_as(spec, "gpexp001") == "first"


def test_resolve_run_as_no_match_no_default():
    spec = {"patterns": {"prod[0-9]*": "produser"}}
    assert _resolve_run_as(spec, "dev001") == ""


def test_resolve_run_as_pattern_fullmatch_not_search():
    # Pattern should not match a hostname that contains the pattern as a substring
    spec = {"patterns": {"pexp[0-9]*": "orasvc"}}
    assert _resolve_run_as(spec, "hostname-pexp001") == ""


# ── _validate_run_as_patterns ─────────────────────────────────────────────────


def test_validate_run_as_patterns_valid():
    spec = {"patterns": {"[lg]pexp[0-9]*": "oracle", "prod[0-9]+": "produser"}}
    assert _validate_run_as_patterns(spec) == []


def test_validate_run_as_patterns_invalid():
    spec = {"patterns": {"[invalid(": "oracle"}}
    errors = _validate_run_as_patterns(spec)
    assert len(errors) == 1
    assert "[invalid(" in errors[0]


def test_validate_run_as_patterns_non_dict():
    assert _validate_run_as_patterns("oracle") == []
    assert _validate_run_as_patterns(None) == []


def test_validate_run_as_patterns_no_patterns_key():
    assert _validate_run_as_patterns({"default": "oracle", "hosts": {}}) == []


# ── loader config normalisation ───────────────────────────────────────────────


def test_loader_normalises_registry_fields(tmp_path):
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text(
        '[config]\nname = "my-agent"\nregistry = "https://reg.example.com"\nheartbeat = 60\nheartbeat_data = ["system"]\n\n[greet]\ndescription = "hi"\n',
        encoding="utf-8",
    )
    raw = load_raw(toml, "runspec")
    cfg = raw["config"]
    assert cfg["name"] == "my-agent"
    assert cfg["registry"] == "https://reg.example.com"
    assert cfg["heartbeat"] == 60
    assert cfg["heartbeat_data"] == ["system"]


def test_loader_registry_defaults(tmp_path):
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text('[greet]\ndescription = "hi"\n', encoding="utf-8")
    raw = load_raw(toml, "runspec")
    cfg = raw["config"]
    assert cfg["registry"] is None
    assert cfg["heartbeat"] == 30
    assert cfg["heartbeat_data"] == []
    assert cfg["name"] is None


def test_loader_normalises_hosts_and_run_as(tmp_path):
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text(
        '[greet]\ndescription = "hi"\nhosts = ["server-01", "server-02"]\nrun_as = "oracle"\nbecome_method = "sudo"\nbecome_flags = "-H"\n',
        encoding="utf-8",
    )
    raw = load_raw(toml, "runspec")
    r = raw["runnables"]["greet"]
    assert r["hosts"] == ["server-01", "server-02"]
    assert r["run_as"] == "oracle"
    assert r["become_method"] == "sudo"
    assert r["become_flags"] == "-H"


def test_loader_run_as_table_form(tmp_path):
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text(
        '[greet]\ndescription = "hi"\n\n[greet.run_as]\ndefault = "oracle"\n\n[greet.run_as.hosts]\n"special-box" = "dba"\n',
        encoding="utf-8",
    )
    raw = load_raw(toml, "runspec")
    run_as = raw["runnables"]["greet"]["run_as"]
    assert run_as["default"] == "oracle"
    assert run_as["hosts"]["special-box"] == "dba"


def test_loader_become_method_default(tmp_path):
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text('[greet]\ndescription = "hi"\n', encoding="utf-8")
    raw = load_raw(toml, "runspec")
    assert raw["runnables"]["greet"]["become_method"] == "sudo"
    assert raw["runnables"]["greet"]["become_flags"] is None
