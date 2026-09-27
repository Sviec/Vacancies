"""Тесты /health и единого формата ошибок (раздел 6 ТЗ)."""

from fastapi import FastAPI
from httpx import AsyncClient

from app import __version__


async def test_health_ok(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == __version__
    assert set(payload["checks"]) == {"database", "redis"}
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"


async def test_health_degraded(app: FastAPI, degrade_redis: None, client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["redis"]["status"] == "error"
    assert payload["checks"]["database"]["status"] == "ok"


async def test_unknown_route_returns_error_envelope(client: AsyncClient):
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "NOT_FOUND"
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["details"] == {}
