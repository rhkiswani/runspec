"""
Tests for InstanceStore.
"""

from __future__ import annotations

import time

import pytest

from runspec_registry.store import InstanceStore


@pytest.fixture()
def s() -> InstanceStore:
    return InstanceStore(default_heartbeat_interval=30)


def test_register_and_get(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    inst = s.get_instance("id-1")
    assert inst is not None
    assert inst["instance_id"] == "id-1"
    assert inst["name"] == "agent"
    assert inst["host"] == "host-01"
    assert inst["active"] is True


def test_register_overwrites_existing(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    s.register("id-1", "agent-v2", "2", "host-01")
    inst = s.get_instance("id-1")
    assert inst is not None
    assert inst["name"] == "agent-v2"
    assert inst["version"] == "2"


def test_heartbeat_returns_ack_when_tools_present(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    s.update_tools("id-1", [{"name": "deploy"}])
    result = s.heartbeat("id-1")
    assert result == "ack"


def test_heartbeat_returns_refresh_when_no_tools(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    result = s.heartbeat("id-1")
    assert result == "refresh"


def test_heartbeat_returns_refresh_for_unknown_instance(s: InstanceStore) -> None:
    result = s.heartbeat("ghost-id")
    assert result == "refresh"


def test_heartbeat_marks_instance_active(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    s.deregister("id-1")
    inst = s.get_instance("id-1")
    assert inst is not None and inst["active"] is False
    s.heartbeat("id-1")
    inst = s.get_instance("id-1")
    assert inst is not None and inst["active"] is True


def test_update_tools_stores_list(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    tools = [{"name": "deploy", "description": "Deploy"}]
    s.update_tools("id-1", tools)
    inst = s.get_instance("id-1")
    assert inst is not None
    assert len(inst["tools"]) == 1
    assert inst["tools"][0]["name"] == "deploy"


def test_update_tools_noop_for_unknown(s: InstanceStore) -> None:
    s.update_tools("ghost", [{"name": "x"}])  # must not raise


def test_deregister_marks_inactive(s: InstanceStore) -> None:
    s.register("id-1", "agent", "1", "host-01")
    s.deregister("id-1")
    inst = s.get_instance("id-1")
    assert inst is not None and inst["active"] is False


def test_deregister_unknown_noop(s: InstanceStore) -> None:
    s.deregister("ghost")  # must not raise


def test_list_instances_all(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "h1")
    s.register("id-2", "b", "1", "h2")
    s.deregister("id-2")
    result = s.list_instances(active_only=False)
    assert len(result) == 2


def test_list_instances_active_only(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "h1")
    s.register("id-2", "b", "1", "h2")
    s.deregister("id-2")
    result = s.list_instances(active_only=True)
    assert len(result) == 1
    assert result[0]["instance_id"] == "id-1"


def test_list_tools_groups_by_name(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.register("id-2", "b", "1", "host-02")
    tool = {"name": "deploy", "description": "Deploy", "x-command": "/bin/deploy", "x-run-as": "oracle"}
    s.update_tools("id-1", [tool])
    s.update_tools("id-2", [tool])
    tools = s.list_tools()
    assert len(tools) == 1
    hosts = tools[0]["hosts"]
    assert len(hosts) == 2
    host_names = {h["host"] for h in hosts}
    assert host_names == {"host-01", "host-02"}
    for h in hosts:
        assert h["x-command"] == "/bin/deploy"
        assert h["x-run-as"] == "oracle"


def test_list_tools_excludes_inactive(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.update_tools("id-1", [{"name": "deploy"}])
    s.deregister("id-1")
    tools = s.list_tools(active_only=True)
    assert tools == []


def test_list_tools_includes_inactive_when_asked(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.update_tools("id-1", [{"name": "deploy"}])
    s.deregister("id-1")
    tools = s.list_tools(active_only=False)
    assert len(tools) == 1


def test_list_tools_per_host_exec_fields_preserved(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.register("id-2", "b", "1", "host-02")
    s.update_tools("id-1", [{"name": "deploy", "x-command": "/bin/d", "x-run-as": "orasvc", "x-become-method": "sudo"}])
    s.update_tools("id-2", [{"name": "deploy", "x-command": "/bin/d", "x-run-as": "produser", "x-become-method": "sudo"}])
    tools = s.list_tools()
    assert len(tools) == 1
    by_host = {h["host"]: h for h in tools[0]["hosts"]}
    assert by_host["host-01"]["x-run-as"] == "orasvc"
    assert by_host["host-02"]["x-run-as"] == "produser"
    assert "x-run-as" not in tools[0]


def test_get_tool_found(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.update_tools("id-1", [{"name": "deploy"}])
    tool = s.get_tool("deploy")
    assert tool is not None
    assert tool["name"] == "deploy"


def test_get_tool_not_found(s: InstanceStore) -> None:
    assert s.get_tool("ghost") is None


def test_list_hosts(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    s.register("id-2", "b", "1", "host-02")
    hosts = s.list_hosts()
    assert len(hosts) == 2
    host_names = {h["host"] for h in hosts}
    assert host_names == {"host-01", "host-02"}


def test_purge_stale_marks_inactive(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01", heartbeat_interval=1)
    inst = s.get_instance("id-1")
    assert inst is not None
    # Manually backdate last_seen
    with s._lock:
        s._instances["id-1"].last_seen = time.time() - 10  # 10s ago, TTL is 3s
    count = s.purge_stale()
    assert count == 1
    inst = s.get_instance("id-1")
    assert inst is not None and inst["active"] is False


def test_purge_stale_leaves_fresh_instance(s: InstanceStore) -> None:
    s.register("id-1", "a", "1", "host-01")
    count = s.purge_stale()
    assert count == 0
    inst = s.get_instance("id-1")
    assert inst is not None and inst["active"] is True
