"""
auth.py — API key authentication for write endpoints.

Write endpoints (POST, DELETE) require X-API-Key when the server is
started with --api-key. Read endpoints (GET) are always open.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_AuthDep = Callable[..., Coroutine[Any, Any, None]]


def make_write_auth(api_key: str | None) -> _AuthDep:
    """
    Return a FastAPI dependency that enforces the given API key on write endpoints.

    If api_key is None, the returned dependency is a no-op (open access).
    """
    if api_key is None:

        async def _no_auth(key: str | None = Security(_API_KEY_HEADER)) -> None:
            pass

        return _no_auth

    async def _check_key(key: str | None = Security(_API_KEY_HEADER)) -> None:
        if key != api_key:
            raise HTTPException(status_code=403, detail="Invalid or missing API key")

    return _check_key
