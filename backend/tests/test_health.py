"""Tests for the /healthz endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_healthz_root():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "evcharge-predict"
    assert data["api_version"] == "1.0"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_healthz_v1():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "evcharge-predict"
    assert data["api_version"] == "1.0"
    assert data["status"] == "ok"
