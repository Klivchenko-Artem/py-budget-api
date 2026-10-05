"""Служебные ручки."""

from __future__ import annotations

from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_checks_dependencies(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"postgres": "ok", "redis": "ok", "status": "ready"}


async def test_openapi_is_published(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    assert "/api/reports/monthly" in schema["paths"]
