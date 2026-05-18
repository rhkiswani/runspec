"""
Tests for the FastAPI registry endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import SAMPLE_TOOLS, register_instance

# ── POST /instances ───────────────────────────────────────────────────────────


def test_register_returns_201(client: TestClient) -> None:
    resp = client.post("/instances", json={"instance_id": "id-1", "name": "agent", "version": "1", "host": "host-01"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"


def test_register_missing_fields_returns_422(client: TestClient) -> None:
    resp = client.post("/instances", json={"instance_id": "id-1"})
    assert resp.status_code == 422


# ── POST /instances/{id}/heartbeat ───────────────────────────────────────────


def test_heartbeat_ack(client: TestClient) -> None:
    register_instance(client)
    client.post("/instances/inst-1/tools", json={"tools": SAMPLE_TOOLS})
    resp = client.post("/instances/inst-1/heartbeat", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ack"


def test_heartbeat_refresh_when_no_tools(client: TestClient) -> None:
    register_instance(client)
    resp = client.post("/instances/inst-1/heartbeat", json={})
    assert resp.json()["status"] == "refresh"


def test_heartbeat_refresh_unknown_instance(client: TestClient) -> None:
    resp = client.post("/instances/ghost/heartbeat", json={})
    assert resp.json()["status"] == "refresh"


# ── POST /instances/{id}/tools ────────────────────────────────────────────────


def test_update_tools_ok(client: TestClient) -> None:
    register_instance(client)
    resp = client.post("/instances/inst-1/tools", json={"tools": SAMPLE_TOOLS})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_update_tools_unknown_instance_404(client: TestClient) -> None:
    resp = client.post("/instances/ghost/tools", json={"tools": SAMPLE_TOOLS})
    assert resp.status_code == 404


# ── DELETE /instances/{id} ────────────────────────────────────────────────────


def test_deregister_returns_200(client: TestClient) -> None:
    register_instance(client)
    resp = client.delete("/instances/inst-1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_deregister_unknown_noop(client: TestClient) -> None:
    resp = client.delete("/instances/ghost")
    assert resp.status_code == 200


# ── GET /instances ────────────────────────────────────────────────────────────


def test_list_instances_empty(client: TestClient) -> None:
    resp = client.get("/instances")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_instances_returns_registered(client: TestClient) -> None:
    register_instance(client)
    resp = client.get("/instances")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["instance_id"] == "inst-1"


def test_list_instances_active_filter(client: TestClient) -> None:
    register_instance(client, "id-1", host="h1")
    register_instance(client, "id-2", host="h2")
    client.delete("/instances/id-2")
    resp = client.get("/instances?active=true")
    assert len(resp.json()) == 1


# ── GET /instances/{id} ───────────────────────────────────────────────────────


def test_get_instance_found(client: TestClient) -> None:
    register_instance(client)
    resp = client.get("/instances/inst-1")
    assert resp.status_code == 200
    assert resp.json()["host"] == "server-01"


def test_get_instance_not_found(client: TestClient) -> None:
    resp = client.get("/instances/ghost")
    assert resp.status_code == 404


# ── GET /tools ────────────────────────────────────────────────────────────────


def test_list_tools_empty(client: TestClient) -> None:
    resp = client.get("/tools")
    assert resp.json() == []


def test_list_tools_after_register(client: TestClient) -> None:
    register_instance(client)
    client.post("/instances/inst-1/tools", json={"tools": SAMPLE_TOOLS})
    resp = client.get("/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) == 1
    assert tools[0]["name"] == "deploy"
    host_names = [h["host"] for h in tools[0].get("hosts", [])]
    assert "server-01" in host_names


def test_list_tools_grouped_across_instances(client: TestClient) -> None:
    register_instance(client, "id-1", host="host-01")
    register_instance(client, "id-2", host="host-02")
    client.post("/instances/id-1/tools", json={"tools": SAMPLE_TOOLS})
    client.post("/instances/id-2/tools", json={"tools": SAMPLE_TOOLS})
    tools = client.get("/tools").json()
    assert len(tools) == 1
    hosts = tools[0]["hosts"]
    assert len(hosts) == 2
    host_names = {h["host"] for h in hosts}
    assert host_names == {"host-01", "host-02"}


# ── GET /tools/{name} ─────────────────────────────────────────────────────────


def test_get_tool_found(client: TestClient) -> None:
    register_instance(client)
    client.post("/instances/inst-1/tools", json={"tools": SAMPLE_TOOLS})
    resp = client.get("/tools/deploy")
    assert resp.status_code == 200
    assert resp.json()["name"] == "deploy"


def test_get_tool_not_found(client: TestClient) -> None:
    resp = client.get("/tools/ghost")
    assert resp.status_code == 404


# ── GET /hosts ────────────────────────────────────────────────────────────────


def test_list_hosts_empty(client: TestClient) -> None:
    resp = client.get("/hosts")
    assert resp.json() == []


def test_list_hosts_returns_active(client: TestClient) -> None:
    register_instance(client, "id-1", host="host-01")
    register_instance(client, "id-2", host="host-02")
    client.delete("/instances/id-2")
    resp = client.get("/hosts")
    assert len(resp.json()) == 1
    assert resp.json()[0]["host"] == "host-01"


# ── GET /health ───────────────────────────────────────────────────────────────


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────────────


def test_write_requires_api_key(authed_client: TestClient) -> None:
    resp = authed_client.post("/instances", json={"instance_id": "x", "name": "y", "version": "1", "host": "h"})
    assert resp.status_code == 403


def test_write_with_correct_api_key(authed_client: TestClient) -> None:
    resp = authed_client.post("/instances", json={"instance_id": "x", "name": "y", "version": "1", "host": "h"}, headers={"X-API-Key": "secret"})
    assert resp.status_code == 201


def test_read_without_api_key(authed_client: TestClient) -> None:
    resp = authed_client.get("/instances")
    assert resp.status_code == 200
