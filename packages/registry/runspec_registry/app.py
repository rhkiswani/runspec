"""
app.py — FastAPI application for runspec-registry.

Endpoints:
  POST   /instances                      — register a new instance
  POST   /instances/{id}/heartbeat       — heartbeat
  POST   /instances/{id}/tools           — update tool list
  DELETE /instances/{id}                 — deregister

  GET    /instances                      — list instances
  GET    /instances/{id}                 — get single instance
  GET    /tools                          — list all tools (grouped by name)
  GET    /tools/{name}                   — get single tool
  GET    /hosts                          — list active hosts
  GET    /export/superputty              — SuperPuTTY XML export
  GET    /export/mobaxterm               — MobaXterm sessions export
  GET    /health                         — liveness check
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .export import generate_mobaxterm, generate_superputty
from .models import HeartbeatRequest, HeartbeatResponse, RegisterRequest, StatusResponse, ToolsRequest
from .store import InstanceStore


def _make_app(store: InstanceStore, write_auth: Any, purge_interval: int = 60) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        async def _purge_loop() -> None:
            while True:
                await asyncio.sleep(purge_interval)
                store.purge_stale()

        task = asyncio.create_task(_purge_loop())
        try:
            yield
        finally:
            task.cancel()

    limiter = Limiter(key_func=get_remote_address)

    app = FastAPI(
        title="runspec-registry",
        description="Read-only HTTP catalog for runspec tool instances",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # ── Write endpoints ───────────────────────────────────────────────────────

    @app.post("/instances", response_model=StatusResponse, status_code=201, dependencies=[Depends(write_auth)])
    @limiter.limit("60/minute")
    async def register_instance(request: Request, body: RegisterRequest) -> dict[str, str]:
        store.register(body.instance_id, body.name, body.version, body.host)
        return {"status": "ok"}

    @app.post("/instances/{instance_id}/heartbeat", response_model=HeartbeatResponse, dependencies=[Depends(write_auth)])
    @limiter.limit("120/minute")
    async def heartbeat(request: Request, instance_id: str, body: HeartbeatRequest) -> dict[str, str]:
        status = store.heartbeat(instance_id)
        return {"status": status}

    @app.post("/instances/{instance_id}/tools", response_model=StatusResponse, dependencies=[Depends(write_auth)])
    @limiter.limit("60/minute")
    async def update_tools(request: Request, instance_id: str, body: ToolsRequest) -> dict[str, str]:
        if store.get_instance(instance_id) is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        store.update_tools(instance_id, body.tools)
        return {"status": "ok"}

    @app.delete("/instances/{instance_id}", response_model=StatusResponse, dependencies=[Depends(write_auth)])
    @limiter.limit("60/minute")
    async def deregister_instance(request: Request, instance_id: str) -> dict[str, str]:
        store.deregister(instance_id)
        return {"status": "ok"}

    # ── Read endpoints ────────────────────────────────────────────────────────

    @app.get("/instances", response_model=list[dict[str, Any]])
    async def list_instances(active: bool = False) -> list[dict[str, Any]]:
        return store.list_instances(active_only=active)

    @app.get("/instances/{instance_id}", response_model=dict[str, Any])
    async def get_instance(instance_id: str) -> dict[str, Any]:
        inst = store.get_instance(instance_id)
        if inst is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        return inst

    @app.get("/tools", response_model=list[dict[str, Any]])
    async def list_tools(active: bool = True) -> list[dict[str, Any]]:
        return store.list_tools(active_only=active)

    @app.get("/tools/{tool_name}", response_model=dict[str, Any])
    async def get_tool(tool_name: str, active: bool = True) -> dict[str, Any]:
        tool = store.get_tool(tool_name, active_only=active)
        if tool is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        return tool

    @app.get("/hosts", response_model=list[dict[str, Any]])
    async def list_hosts(active: bool = True) -> list[dict[str, Any]]:
        return store.list_hosts(active_only=active)

    @app.get("/export/superputty", response_class=PlainTextResponse)
    async def export_superputty(user: str = "") -> Response:
        hosts = store.list_hosts(active_only=True)
        xml = generate_superputty(hosts, default_user=user)
        return Response(content=xml, media_type="application/xml", headers={"Content-Disposition": "attachment; filename=runspec-sessions.xml"})

    @app.get("/export/mobaxterm", response_class=PlainTextResponse)
    async def export_mobaxterm(user: str = "") -> Response:
        hosts = store.list_hosts(active_only=True)
        content = generate_mobaxterm(hosts, default_user=user)
        return Response(content=content, media_type="text/plain", headers={"Content-Disposition": "attachment; filename=runspec.mxtsessions"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_app(api_key: str | None = None, purge_interval: int = 60) -> FastAPI:
    """Create a registry app with its own InstanceStore. For production use."""
    from .auth import make_write_auth

    store = InstanceStore()
    write_auth = make_write_auth(api_key)
    return _make_app(store, write_auth, purge_interval=purge_interval)


def _reload_app() -> FastAPI:
    """App factory used by uvicorn --reload mode (reads config from env vars)."""
    import os

    api_key = os.environ.get("RUNSPEC_REGISTRY_API_KEY") or None
    purge_interval = int(os.environ.get("RUNSPEC_REGISTRY_PURGE_INTERVAL", "60"))
    return create_app(api_key=api_key, purge_interval=purge_interval)
