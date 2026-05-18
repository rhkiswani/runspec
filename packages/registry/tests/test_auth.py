"""
Tests for the make_write_auth dependency factory.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from runspec_registry.auth import make_write_auth


def _app_with_auth(api_key: str | None) -> TestClient:
    from fastapi import Depends

    app = FastAPI()
    auth = make_write_auth(api_key)

    @app.post("/protected", dependencies=[Depends(auth)])
    async def protected() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/open")
    async def open_route() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_no_key_required_when_none() -> None:
    client = _app_with_auth(None)
    resp = client.post("/protected")
    assert resp.status_code == 200


def test_correct_key_accepted() -> None:
    client = _app_with_auth("mykey")
    resp = client.post("/protected", headers={"X-API-Key": "mykey"})
    assert resp.status_code == 200


def test_wrong_key_rejected() -> None:
    client = _app_with_auth("mykey")
    resp = client.post("/protected", headers={"X-API-Key": "wrongkey"})
    assert resp.status_code == 403


def test_missing_key_rejected() -> None:
    client = _app_with_auth("mykey")
    resp = client.post("/protected")
    assert resp.status_code == 403


def test_open_endpoint_always_accessible() -> None:
    client = _app_with_auth("mykey")
    resp = client.get("/open")
    assert resp.status_code == 200
