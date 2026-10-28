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


@pytest.mark.asyncio
async def test_readyz_healthy():
    """Validates /readyz and /api/v1/readyz return 200 when database and models are available."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_root = await client.get("/readyz")
        res_v1 = await client.get("/api/v1/readyz")

    assert res_root.status_code == 200
    data = res_root.json()
    assert data["status"] == "ready"
    assert data["database_ready"] is True
    assert data["models_loaded"] is True
    assert data["model_error"] is None

    assert res_v1.status_code == 200
    assert res_v1.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_readyz_database_failure(monkeypatch):
    """Validates /readyz returns 503 and reports not_ready when the database connection fails."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    # Simulate database connection failure
    mock_engine.connect.side_effect = ConnectionRefusedError("Database unreachable")
    monkeypatch.setattr("app.api.v1.routes.ready.get_engine", lambda: mock_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database_ready"] is False


@pytest.mark.asyncio
async def test_readyz_models_unavailable(monkeypatch):
    """Validates /readyz returns 503 and includes model_error when model artifacts are not loaded."""
    from unittest.mock import MagicMock

    mock_model_service = MagicMock()
    mock_model_service.is_loaded = False
    mock_model_service.load_error = "Model manifest missing at: /nonexistent/manifest.json"
    monkeypatch.setattr("app.api.v1.routes.ready.ModelService.get_instance", lambda: mock_model_service)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["models_loaded"] is False
    assert "Model manifest missing" in data["model_error"]


@pytest.mark.asyncio
async def test_readyz_schema_missing(monkeypatch):
    """Validates /readyz returns 503 when the stations table is missing (relation does not exist)."""
    from unittest.mock import AsyncMock, MagicMock

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception('relation "stations" does not exist')
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn
    mock_ctx.__aexit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_ctx
    monkeypatch.setattr("app.api.v1.routes.ready.get_engine", lambda: mock_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database_ready"] is False
