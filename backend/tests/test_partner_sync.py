"""Tests for EVCharge-Opt Partner Sync service and routes."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.schemas.partner_sync import PartnerSyncRequest, PartnerSyncResponse
from app.services.partner_sync_service import PartnerSyncService


@pytest.mark.asyncio
async def test_partner_sync_schema_validation():
    """Verify PartnerSyncRequest validates correctly with defaults."""
    req = PartnerSyncRequest(
        forecast_id="fc_test_001",
        scenario_id="SCN-001",
    )
    assert req.forecast_id == "fc_test_001"
    assert req.scenario_id == "SCN-001"
    assert req.deferred_fraction == 0.7


@pytest.mark.asyncio
async def test_partner_sync_custom_scenario_workflow():
    """Verify full 4-stage partner sync with custom scenario creates scenario and allocation."""
    service = PartnerSyncService(base_url="https://mock-opt.example.com")

    mock_fc_resp = {
        "contract_version": "1.0",
        "forecast_id": "FC-MOCK-ABC123",
        "scenario_id": "SCN-CUSTOM-01",
        "status": "generated",
        "demand_type": "baseline",
        "generated_at": "2026-10-29T10:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
        "forecast_url": "/api/v1/forecasts/FC-MOCK-ABC123",
    }

    mock_scen_resp = {
        "scenario_id": "SCN-CUSTOM-01",
        "selected_forecast_id": "FC-MOCK-ABC123",
    }

    mock_alloc_resp = {
        "allocation_id": "ALC-MOCK-789XYZ",
        "scenario_id": "SCN-CUSTOM-01",
        "forecast_id": "FC-MOCK-ABC123",
        "status": "success",
        "outcome_kind": "simulation",
        "algorithm_version": "v1.0-priority-heuristic",
        "results": [
            {
                "station_id": "STN-01",
                "station_name": "Downtown Hub",
                "predicted_arrivals": 12.0,
                "predicted_energy_kwh": 250.0,
                "estimated_served": 10.0,
                "estimated_unserved": 2.0,
                "allocated_power_kw": 220.0,
                "estimated_wait_minutes": 15.0,
                "charger_utilization_pct": 95.0,
                "warnings": [],
            }
        ],
    }

    mock_fb_resp = {
        "feedback_id": "FBD-MOCK-456DEF",
        "submission_status": "submitted",
        "station_outcomes": [],
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        resp1 = AsyncMock()
        resp1.status_code = 201
        resp1.json = lambda: mock_fc_resp

        resp2 = AsyncMock()
        resp2.status_code = 201
        resp2.json = lambda: mock_scen_resp

        resp3 = AsyncMock()
        resp3.status_code = 201
        resp3.json = lambda: mock_alloc_resp

        resp4 = AsyncMock()
        resp4.status_code = 201
        resp4.json = lambda: mock_fb_resp

        mock_post.side_effect = [resp1, resp2, resp3, resp4]

        req = PartnerSyncRequest(
            forecast_id="fc_test_001",
            scenario_id="SCN-CUSTOM-01",
            interval_start="2026-10-29T10:00:00Z",
            interval_end="2026-10-29T11:00:00Z",
        )

        res = await service.execute_sync(req)

        assert res.success is True
        assert res.opt_forecast_id == "FC-MOCK-ABC123"
        assert res.opt_allocation_id == "ALC-MOCK-789XYZ"
        assert res.opt_feedback_id == "FBD-MOCK-456DEF"
        assert res.total_allocated_power_kw == 220.0
        assert res.total_served_vehicles == 10.0
        assert res.total_unserved_vehicles == 2.0
        assert len(res.allocation_results) == 1
        assert res.allocation_results[0].station_id == "STN-01"


@pytest.mark.asyncio
async def test_partner_sync_existing_scenario_workflow():
    """Verify partner sync with existing SCN-001 scenario invokes forecast, allocation, feedback."""
    service = PartnerSyncService(base_url="https://mock-opt.example.com")

    mock_fc_resp = {
        "contract_version": "1.0",
        "forecast_id": "FC-MOCK-ABC123",
        "scenario_id": "SCN-001",
        "status": "generated",
        "demand_type": "baseline",
        "generated_at": "2026-10-29T10:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
        "forecast_url": "/api/v1/forecasts/FC-MOCK-ABC123",
    }

    mock_alloc_resp = {
        "allocation_id": "ALC-MOCK-789XYZ",
        "scenario_id": "SCN-001",
        "forecast_id": "FC-MOCK-ABC123",
        "status": "success",
        "outcome_kind": "simulation",
        "algorithm_version": "v1.0-priority-heuristic",
        "results": [],
    }

    mock_fb_resp = {
        "feedback_id": "FBD-MOCK-456DEF",
        "submission_status": "submitted",
        "station_outcomes": [],
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        resp1 = AsyncMock()
        resp1.status_code = 201
        resp1.json = lambda: mock_fc_resp

        resp3 = AsyncMock()
        resp3.status_code = 201
        resp3.json = lambda: mock_alloc_resp

        resp4 = AsyncMock()
        resp4.status_code = 201
        resp4.json = lambda: mock_fb_resp

        mock_post.side_effect = [resp1, resp3, resp4]

        req = PartnerSyncRequest(
            forecast_id="fc_test_001",
            scenario_id="SCN-001",
        )

        res = await service.execute_sync(req)

        assert res.success is True
        assert res.opt_forecast_id == "FC-MOCK-ABC123"
        assert res.opt_allocation_id == "ALC-MOCK-789XYZ"
        assert res.opt_feedback_id == "FBD-MOCK-456DEF"


@pytest.mark.asyncio
async def test_partner_sync_network_failure_handling():
    """Verify network error produces clean failure without crashing or fabricating results."""
    service = PartnerSyncService(base_url="https://unreachable.invalid")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        req = PartnerSyncRequest(forecast_id="fc_test_err")
        res = await service.execute_sync(req)

        assert res.success is False
        assert res.stage_reached == "connection_failed"
        assert "Network error contacting EVCharge-Opt" in (res.error or "")
        assert res.opt_allocation_id is None


def test_api_partner_status_route():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"status": "healthy", "service_version": "0.1.0"}
        mock_get.return_value = mock_resp

        client = TestClient(app)
        res = client.get("/api/v1/partner/status")
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is True
        assert data["partner_details"]["status"] == "healthy"


def test_api_partner_sync_route():
    from fastapi.testclient import TestClient
    from app.main import app

    mock_sync_resp = PartnerSyncResponse(
        success=True,
        partner_service="EVCharge-Opt",
        partner_base_url="https://evcharge-opt-api.onrender.com",
        stage_reached="completed",
        opt_forecast_id="FC-MOCK-TEST",
        opt_allocation_id="ALC-TEST-123",
        opt_feedback_id="FBD-TEST-456",
        total_allocated_power_kw=100.0,
    )

    with patch("app.services.partner_sync_service.PartnerSyncService.execute_sync", return_value=mock_sync_resp):
        client = TestClient(app)
        res = client.post("/api/v1/partner/sync", json={"forecast_id": "fc_test"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["opt_allocation_id"] == "ALC-TEST-123"

