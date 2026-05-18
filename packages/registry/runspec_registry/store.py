"""
store.py — In-memory instance store with stale detection.

TTL = 3 × heartbeat_interval (per-instance, tracked from last seen time).
Stale instances are marked inactive, not deleted, so history is preserved.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class _Instance:
    __slots__ = ("instance_id", "name", "version", "host", "active", "last_seen", "heartbeat_interval", "tools")

    def __init__(self, instance_id: str, name: str, version: str, host: str, heartbeat_interval: int) -> None:
        self.instance_id = instance_id
        self.name = name
        self.version = version
        self.host = host
        self.active = True
        self.last_seen = time.time()
        self.heartbeat_interval = heartbeat_interval
        self.tools: list[dict[str, Any]] = []

    @property
    def ttl(self) -> float:
        return self.heartbeat_interval * 3.0

    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > self.ttl

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "version": self.version,
            "host": self.host,
            "active": self.active,
            "last_seen": self.last_seen,
            "tools": list(self.tools),
        }


class InstanceStore:
    """Thread-safe in-memory store for registered runspec instances."""

    def __init__(self, default_heartbeat_interval: int = 30) -> None:
        self._lock = threading.Lock()
        self._instances: dict[str, _Instance] = {}
        self._default_heartbeat_interval = default_heartbeat_interval

    # ── Write operations ──────────────────────────────────────────────────────

    def register(self, instance_id: str, name: str, version: str, host: str, heartbeat_interval: int | None = None) -> None:
        interval = heartbeat_interval if heartbeat_interval is not None else self._default_heartbeat_interval
        with self._lock:
            inst = _Instance(instance_id, name, version, host, interval)
            self._instances[instance_id] = inst

    def heartbeat(self, instance_id: str) -> str:
        """
        Record a heartbeat for the given instance.

        Returns "refresh" if the instance has no tools recorded (e.g. after a
        registry restart), so serve re-sends the full tool list.
        Returns "ack" otherwise.
        """
        with self._lock:
            inst = self._instances.get(instance_id)
            if inst is None:
                return "refresh"
            inst.last_seen = time.time()
            inst.active = True
            if not inst.tools:
                return "refresh"
            return "ack"

    def update_tools(self, instance_id: str, tools: list[dict[str, Any]]) -> None:
        with self._lock:
            inst = self._instances.get(instance_id)
            if inst is not None:
                inst.tools = list(tools)

    def deregister(self, instance_id: str) -> None:
        with self._lock:
            inst = self._instances.get(instance_id)
            if inst is not None:
                inst.active = False

    def purge_stale(self) -> int:
        """Mark stale instances inactive. Returns count of instances marked."""
        count = 0
        with self._lock:
            for inst in self._instances.values():
                if inst.active and inst.is_stale():
                    inst.active = False
                    count += 1
        return count

    # ── Read operations ───────────────────────────────────────────────────────

    def get_instance(self, instance_id: str) -> dict[str, Any] | None:
        with self._lock:
            inst = self._instances.get(instance_id)
            return inst.to_dict() if inst is not None else None

    def list_instances(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            instances = list(self._instances.values())
        if active_only:
            instances = [i for i in instances if i.active]
        return [i.to_dict() for i in instances]

    def list_tools(self, active_only: bool = True) -> list[dict[str, Any]]:
        """
        Return all tools across all instances, grouped by tool name.

        Each entry: {name, description, inputSchema, hosts: [...]}
        where hosts is a list of per-host dicts: {host, x-command, x-run-as,
        x-become-method, x-become-flags}. Execution metadata stays per-host
        because run_as resolution differs across instances.
        """
        _SHARED_KEYS = {"name", "description", "inputSchema"}
        _HOST_KEYS = {"x-command", "x-run-as", "x-become-method", "x-become-flags"}
        tool_map: dict[str, dict[str, Any]] = {}
        with self._lock:
            for inst in self._instances.values():
                if active_only and not inst.active:
                    continue
                for tool in inst.tools:
                    tname = tool.get("name", "")
                    host_entry: dict[str, Any] = {"host": inst.host}
                    for k in _HOST_KEYS:
                        if k in tool:
                            host_entry[k] = tool[k]
                    if tname not in tool_map:
                        entry = {k: tool[k] for k in _SHARED_KEYS if k in tool}
                        entry["hosts"] = [host_entry]
                        tool_map[tname] = entry
                    else:
                        tool_map[tname]["hosts"].append(host_entry)
        return list(tool_map.values())

    def get_tool(self, tool_name: str, active_only: bool = True) -> dict[str, Any] | None:
        for tool in self.list_tools(active_only=active_only):
            if tool.get("name") == tool_name:
                return tool
        return None

    def list_hosts(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Return one entry per (host, name) combination."""
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        with self._lock:
            for inst in self._instances.values():
                if active_only and not inst.active:
                    continue
                key = (inst.host, inst.name)
                if key not in seen:
                    seen[key] = {
                        "host": inst.host,
                        "name": inst.name,
                        "instance_id": inst.instance_id,
                        "version": inst.version,
                        "tool_count": len(inst.tools),
                    }
        return list(seen.values())
