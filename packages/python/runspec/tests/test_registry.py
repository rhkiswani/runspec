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
    _registry_post,
    _registry_register,
    _registry_tools,
)


# ── Mock registry fixture ──────────────────────────────────────────────────────


class _RegistryState:
    """Shared mutable state between test and mock server."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.heartbeat_response: str = "ack"  # "ack" or "refresh"


def _make_handler(state: _RegistryState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            state.requests.append({"path": self.path, "body": body})

            if self.path == "/heartbeat":
                resp = {"status": state.heartbeat_response}
            else:
                resp = {"status": "ok"}

            data = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            pass  # suppress noisy test output

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
    _registry_register(url, "agent-123", "my-pipeline", "1")
    assert len(state.requests) == 1
    req = state.requests[0]
    assert req["path"] == "/register"
    assert req["body"]["agent_id"] == "agent-123"
    assert req["body"]["name"] == "my-pipeline"
    assert req["body"]["version"] == "1"
    assert req["body"]["tools_seq"] == 1


def test_register_does_not_raise_on_ok(mock_registry):
    url, _ = mock_registry
    _registry_register(url, "x", "y", "1")  # should not raise


# ── _registry_heartbeat ───────────────────────────────────────────────────────


def test_heartbeat_sends_minimal_body(mock_registry):
    url, state = mock_registry
    _registry_heartbeat(url, "agent-abc", [], time.time())
    req = state.requests[0]
    assert req["path"] == "/heartbeat"
    assert req["body"]["agent_id"] == "agent-abc"
    assert req["body"]["tools_seq"] == 1
    assert "system" not in req["body"]


def test_heartbeat_includes_system_data(mock_registry):
    url, state = mock_registry
    start = time.time() - 60
    _registry_heartbeat(url, "agent-abc", ["system"], start)
    req = state.requests[0]
    assert "system" in req["body"]
    assert isinstance(req["body"]["system"]["pid"], int)
    assert req["body"]["system"]["uptime"] >= 60


def test_heartbeat_returns_ack(mock_registry):
    url, state = mock_registry
    state.heartbeat_response = "ack"
    result = _registry_heartbeat(url, "agent-abc", [], time.time())
    assert result == "ack"


def test_heartbeat_returns_refresh(mock_registry):
    url, state = mock_registry
    state.heartbeat_response = "refresh"
    result = _registry_heartbeat(url, "agent-abc", [], time.time())
    assert result == "refresh"


# ── _registry_tools ───────────────────────────────────────────────────────────


def test_tools_sends_tool_list(mock_registry):
    url, state = mock_registry
    tools = [
        {
            "name": "deploy",
            "description": "Deploy to production",
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]
    _registry_tools(url, "agent-abc", tools)
    req = state.requests[0]
    assert req["path"] == "/tools"
    assert req["body"]["agent_id"] == "agent-abc"
    assert req["body"]["tools_seq"] == 1
    assert len(req["body"]["tools"]) == 1
    assert req["body"]["tools"][0]["name"] == "deploy"


def test_tools_sends_empty_list(mock_registry):
    url, state = mock_registry
    _registry_tools(url, "agent-abc", [])
    assert state.requests[0]["body"]["tools"] == []


# ── _registry_deregister ──────────────────────────────────────────────────────


def test_deregister_sends_agent_id(mock_registry):
    url, state = mock_registry
    _registry_deregister(url, "agent-xyz")
    req = state.requests[0]
    assert req["path"] == "/deregister"
    assert req["body"]["agent_id"] == "agent-xyz"


def test_deregister_body_has_only_agent_id(mock_registry):
    url, state = mock_registry
    _registry_deregister(url, "agent-xyz")
    assert list(state.requests[0]["body"].keys()) == ["agent_id"]


# ── _registry_post error handling ─────────────────────────────────────────────


def test_post_raises_on_connection_refused():
    with pytest.raises(RuntimeError, match="failed"):
        _registry_post("http://127.0.0.1:1", "/register", {})


def test_post_raises_on_http_error(mock_registry):
    url, state = mock_registry

    # Temporarily replace handler to return 500
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

    # We can't swap the handler mid-fixture, so test against a second server
    err_server = HTTPServer(("127.0.0.1", 0), ErrorHandler)
    err_port = err_server.server_address[1]
    t = threading.Thread(target=err_server.serve_forever, daemon=True)
    t.start()
    try:
        with pytest.raises(RuntimeError, match="HTTP 500"):
            _registry_post(f"http://127.0.0.1:{err_port}", "/register", {})
    finally:
        err_server.shutdown()
        err_server.server_close()


# ── loader config normalisation ───────────────────────────────────────────────


def test_loader_normalises_registry_fields(tmp_path):
    """_normalise_config picks up registry, heartbeat, heartbeat_data, name."""
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
    """When registry fields are absent, sensible defaults are used."""
    from runspec.loader import load_raw

    toml = tmp_path / "runspec.toml"
    toml.write_text("[greet]\ndescription = \"hi\"\n", encoding="utf-8")
    raw = load_raw(toml, "runspec")
    cfg = raw["config"]
    assert cfg["registry"] is None
    assert cfg["heartbeat"] == 30
    assert cfg["heartbeat_data"] == []
    assert cfg["name"] is None
