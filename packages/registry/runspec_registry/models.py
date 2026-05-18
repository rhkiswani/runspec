"""
models.py — Pydantic models for registry request/response bodies.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    instance_id: str
    name: str
    version: str
    host: str


class HeartbeatRequest(BaseModel):
    system: dict[str, Any] | None = None


class ToolsRequest(BaseModel):
    tools: list[dict[str, Any]]


class StatusResponse(BaseModel):
    status: str


class HeartbeatResponse(BaseModel):
    status: str = Field(default="ack")


class ToolEntry(BaseModel):
    """A single tool as stored in the registry (MCP schema + x- fields)."""

    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    # Execution metadata (x- extension fields)
    x_command: str = Field(default="", alias="x-command")
    x_run_as: str = Field(default="", alias="x-run-as")
    x_become_method: str = Field(default="sudo", alias="x-become-method")
    x_become_flags: str | None = Field(default=None, alias="x-become-flags")

    model_config = {"populate_by_name": True}


class InstanceInfo(BaseModel):
    """Full instance record returned by the API."""

    instance_id: str
    name: str
    version: str
    host: str
    active: bool
    last_seen: float
    tools: list[dict[str, Any]] = Field(default_factory=list)
