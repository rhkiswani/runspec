"""
conftest.py — Shared fixtures for registry tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runspec_registry.app import _make_app
from runspec_registry.auth import make_write_auth
from runspec_registry.store import InstanceStore


@pytest.fixture()
def store() -> InstanceStore:
    return InstanceStore(default_heartbeat_interval=30)


@pytest.fixture()
def client(store: InstanceStore) -> TestClient:
    """Open registry with no API key (write access open)."""
    app = _make_app(store, make_write_auth(None), purge_interval=9999)
    return TestClient(app)


@pytest.fixture()
def authed_client(store: InstanceStore) -> TestClient:
    """Open registry with API key = 'secret'."""
    app = _make_app(store, make_write_auth("secret"), purge_interval=9999)
    return TestClient(app)


# Helpers shared across test modules
def register_instance(client: TestClient, instance_id: str = "inst-1", name: str = "my-agent", host: str = "server-01") -> None:
    resp = client.post("/instances", json={"instance_id": instance_id, "name": name, "version": "1", "host": host})
    assert resp.status_code == 201


SAMPLE_TOOLS = [
    {
        "name": "deploy",
        "description": "Deploy the app",
        "inputSchema": {"type": "object", "properties": {}},
        "x-command": "/usr/local/bin/deploy",
        "x-run-as": "oracle",
        "x-become-method": "sudo",
    }
]
