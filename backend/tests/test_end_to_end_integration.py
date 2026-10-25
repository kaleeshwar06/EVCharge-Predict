"""End-to-End Integration, Security, and Consumer-Contract Test Suite for Phase 6.

Validates:
1. Production Fail-Closed Security Configuration.
2. Service-to-service Bearer token enforcement (401 Missing, 403 Invalid, 200/201 Authorized).
3. Public probe exemption (/healthz and /readyz).
4. Safe request correlation ID headers & regex sanitization.
5. Full End-to-End pipeline: Forecast generation -> Verification -> Feedback ingestion -> Adjusted demand.
6. Consumer-contract verification with JSON fixtures.
7. Database rollback atomicity on feedback write failures.
8. Baseline forecast strict immutability.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.feedback import AdjustedDemandInterval, AllocationFeedback
from app.models.forecast import Forecast, ForecastInterval
from app.models.station import Station
from app.schemas.feedback import FeedbackCreateRequest
from app.schemas.forecast import ForecastCreateRequest
from app.services.feedback_service import FeedbackService

CONTRACT_EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "integration-contract" / "examples"
MODELS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "models"
TEST_SECRET_TOKEN = "test-secure-bearer-token-12345"


# ─── Helper Setup ─────────────────────────────────────────────────────────────
async def populate_test_e2e_db(session_factory):
    """Inserts ST-001, ST-002 and 7 days of historical sessions for forecasting."""
    async with session_factory() as session:
        st1 = Station(station_id="ST-001", source_station_id="src-e2e-001", site_id="site-e2e")
        st2 = Station(station_id="ST-002", source_station_id="src-e2e-002", site_id="site-e2e")
        session.add_all([st1, st2])
        await session.flush()

        base_time = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
        from app.models.charging_session import ChargingSession
        sessions_to_add = []
        for h in range(168):
            t = base_time + timedelta(hours=h)
            if h % 3 == 0:
                for st in [st1, st2]:
                    sessions_to_add.append(
                        ChargingSession(
                            station_id=st.id,
                            connection_time=t + timedelta(minutes=10),
                            disconnect_time=t + timedelta(hours=2),
                            kwh_delivered=Decimal("25.00"),
                            source_dataset="e2e-synthetic",
                        )
                    )
        session.add_all(sessions_to_add)
        await session.commit()


# ─── 1. Security & Configuration Tests ────────────────────────────────────────
def test_production_fails_closed_when_token_missing():
    """Verify that Settings validation fails closed on startup if APP_ENV=production without token."""
    with pytest.raises(ValueError, match="Production configuration violation"):
        Settings(app_env="production", api_auth_token=None)

    with pytest.raises(ValueError, match="Production configuration violation"):
        Settings(app_env="production", api_auth_token="")

    with pytest.raises(ValueError, match="Production configuration violation"):
        Settings(app_env="production", api_auth_token="replace-with-service-token")

    # Valid production settings pass
    valid_prod = Settings(app_env="production", api_auth_token="strong-production-token-secret")
    assert valid_prod.api_auth_token == "strong-production-token-secret"


def test_service_to_service_auth_enforcement_and_public_probes(tmp_path):
    """Verifies that protected routes require Bearer token, while probes remain public."""
    async def run():
        db_file = tmp_path / "test_auth_enforce.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_e2e_db(sf)

        async def override_get_db():
            async with sf() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_db

        # Configure mock settings with an active API_AUTH_TOKEN
        mock_settings = Settings(
            app_env="production",
            api_auth_token=TEST_SECRET_TOKEN,
            enable_docs=False,
        )

        with patch("app.core.security.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Public probes: /healthz and /readyz succeed without auth
                res_h = await client.get("/healthz")
                assert res_h.status_code == 200
                assert res_h.json()["status"] == "ok"

                res_r = await client.get("/readyz")
                assert res_r.status_code == 200
                assert res_r.json()["status"] == "ready"

                res_h_v1 = await client.get("/api/v1/healthz")
                assert res_h_v1.status_code == 200

                # 2. Protected business route without token -> HTTP 401
                res_unauth = await client.get("/api/v1/stations")
                assert res_unauth.status_code == 401
                assert "WWW-Authenticate" in res_unauth.headers

                # 3. Protected route with invalid token -> HTTP 403
                res_bad = await client.get("/api/v1/stations", headers={"Authorization": "Bearer wrong-token"})
                assert res_bad.status_code == 403

                # 4. Protected route with valid token -> HTTP 200
                res_ok = await client.get(
                    "/api/v1/stations",
                    headers={"Authorization": f"Bearer {TEST_SECRET_TOKEN}"},
                )
                assert res_ok.status_code == 200
                assert len(res_ok.json()) == 2

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(run())


# ─── 2. Request Correlation & Observability Tests ─────────────────────────────
def test_correlation_id_handling_and_header_reflection(tmp_path):
    """Verifies format validation of X-Request-ID, sanitization, and response header generation."""
    async def run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Valid client-supplied correlation ID reflected
            client_id = "req-client-trace-12345"
            res = await client.get("/healthz", headers={"X-Request-ID": client_id})
            assert res.status_code == 200
            assert res.headers.get("X-Request-ID") == client_id

            # 2. Missing ID -> Middleware generates a UUID
            res_auto = await client.get("/healthz")
            assert res_auto.status_code == 200
            gen_id = res_auto.headers.get("X-Request-ID")
            assert gen_id is not None
            assert len(gen_id) >= 16

            # 3. Malformed / injection-like ID (multiline or spaces) -> Replaced with safe UUID
            malicious_id = "req_123\nINJECT_LOG\rMALICIOUS: true"
            res_inj = await client.get("/healthz", headers={"X-Request-ID": malicious_id})
            assert res_inj.status_code == 200
            sanitized_id = res_inj.headers.get("X-Request-ID")
            assert sanitized_id != malicious_id
            assert "\n" not in sanitized_id
            assert "\r" not in sanitized_id

    asyncio.run(run())


# ─── 3. Full End-to-End Workflow with Contract Fixtures ───────────────────────
def test_e2e_forecast_and_feedback_lifecycle(tmp_path):
    """Executes the full closed loop: Forecast -> Verification -> Feedback -> Adjusted Demand -> Baseline Immutability."""
    async def run():
        db_file = tmp_path / "test_e2e_lifecycle.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_e2e_db(sf)

        async def override_get_db():
            async with sf() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_db

        mock_settings = Settings(
            app_env="production",
            api_auth_token=TEST_SECRET_TOKEN,
        )

        with patch("app.core.security.get_settings", return_value=mock_settings):
            auth_headers = {
                "Authorization": f"Bearer {TEST_SECRET_TOKEN}",
                "X-Request-ID": "e2e-session-trace-001",
            }
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Step 1: POST /api/v1/forecasts
                fcst_start = "2026-10-25T00:00:00Z"
                req_payload = {
                    "scenario_id": "scenario_e2e_001",
                    "station_ids": ["ST-001", "ST-002"],
                    "forecast_start": fcst_start,
                    "interval_minutes": 60,
                    "horizon_intervals": 6,
                }
                res_create = await client.post("/api/v1/forecasts", json=req_payload, headers=auth_headers)
                assert res_create.status_code == 201
                create_data = res_create.json()
                forecast_id = create_data["forecast_id"]

                # Step 2: GET /api/v1/forecasts/{forecast_id}
                res_detail = await client.get(f"/api/v1/forecasts/{forecast_id}", headers=auth_headers)
                assert res_detail.status_code == 200
                fcst_data = res_detail.json()
                assert len(fcst_data["stations"]) == 2
                for st in fcst_data["stations"]:
                    assert len(st["intervals"]) == 6
                    for it in st["intervals"]:
                        assert it["predicted_arrivals"] >= 0
                        assert it["predicted_energy_kwh"] >= 0.0

                # Snapshot baseline ST-001 interval 0
                st1_int0_base_kwh = fcst_data["stations"][0]["intervals"][0]["predicted_energy_kwh"]
                st1_int0_base_arr = fcst_data["stations"][0]["intervals"][0]["predicted_arrivals"]

                # Step 3: POST /api/v1/feedback (EVCharge-Opt reports allocation)
                alloc_kwh = float(st1_int0_base_kwh) + 25.0  # Force an increase
                fbk_payload = {
                    "contract_version": "1.0",
                    "allocation_run_id": "opt-run-e2e-001",
                    "forecast_id": forecast_id,
                    "scenario_id": "scenario_e2e_001",
                    "submitted_at": "2026-10-25T00:15:00Z",
                    "optimizer_version": "evcharge-opt-e2e",
                    "stations": [
                        {
                            "station_id": "ST-001",
                            "intervals": [
                                {
                                    "interval_start": fcst_start,
                                    "interval_end": "2026-10-25T01:00:00Z",
                                    "allocated_energy_kwh": alloc_kwh,
                                    "available_capacity_kw": 50.0,
                                    "reported_unmet_demand_kwh": 3.0,
                                }
                            ],
                        }
                    ],
                }
                res_fbk = await client.post("/api/v1/feedback", json=fbk_payload, headers=auth_headers)
                assert res_fbk.status_code == 201
                fbk_id = res_fbk.json()["feedback_id"]

                # Step 4: GET /api/v1/forecasts/{id}/adjusted-demand?feedback_id=...
                res_adj = await client.get(
                    f"/api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id={fbk_id}",
                    headers=auth_headers,
                )
                assert res_adj.status_code == 200
                adj_data = res_adj.json()
                st1_adj_int0 = adj_data["stations"][0]["intervals"][0]
                assert st1_adj_int0["baseline_energy_kwh"] == st1_int0_base_kwh
                assert st1_adj_int0["allocated_energy_kwh"] == alloc_kwh
                assert st1_adj_int0["adjusted_operational_demand_kwh"] == alloc_kwh
                assert st1_adj_int0["adjustment_status"] == "adjusted"
                # Arrivals preserved strictly without fabrication
                assert st1_adj_int0["baseline_arrivals"] == st1_int0_base_arr
                assert st1_adj_int0["reported_unmet_demand_kwh"] == 3.0

                # Step 5: Verify original baseline forecast endpoint returns unaltered data
                res_base_verify = await client.get(f"/api/v1/forecasts/{forecast_id}", headers=auth_headers)
                assert res_base_verify.status_code == 200
                assert res_base_verify.json()["stations"][0]["intervals"][0]["predicted_energy_kwh"] == st1_int0_base_kwh

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(run())


# ─── 4. Consumer-Contract Fixtures Schema Validation ──────────────────────────
def test_consumer_contract_fixtures_are_valid():
    """Validates that all contract example files under integration-contract/examples match Pydantic schemas."""
    # 1. forecast_request.json
    with open(CONTRACT_EXAMPLES_DIR / "forecast_request.json") as f:
        fcst_req_data = json.load(f)
    req_model = ForecastCreateRequest.model_validate(fcst_req_data)
    assert req_model.horizon_intervals == 6
    assert req_model.interval_minutes == 60

    # 2. feedback_request.json
    with open(CONTRACT_EXAMPLES_DIR / "feedback_request.json") as f:
        fbk_req_data = json.load(f)
    fbk_model = FeedbackCreateRequest.model_validate(fbk_req_data)
    assert fbk_model.contract_version == "1.0"
    assert len(fbk_model.stations) >= 1
    assert fbk_model.stations[0].intervals[0].allocated_energy_kwh is not None


# ─── 5. Database Rollback Atomicity on Failure ────────────────────────────────
def test_feedback_transaction_rollback_on_write_failure(tmp_path):
    """Induces a database failure during feedback persistence and ensures zero partial records exist."""
    async def run():
        db_file = tmp_path / "test_rollback.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_e2e_db(sf)

        async with sf() as session:
            # Create a baseline forecast and baseline interval for ST-001
            st_res = await session.execute(select(Station).where(Station.station_id == "ST-001"))
            st1 = st_res.scalar_one()

            forecast = Forecast(
                forecast_id="fcst_rollback_01",
                scenario_id="scen_rb",
                generated_at=datetime.now(timezone.utc),
                forecast_start=datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc),
                forecast_end=datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc),
                interval_minutes=60,
                horizon_intervals=6,
                status="completed",
                demand_type="baseline",
                model_version="1.0",
                training_data_type="synthetic",
            )
            session.add(forecast)
            await session.flush()

            fi = ForecastInterval(
                forecast_id=forecast.id,
                station_id=st1.id,
                interval_start=datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc),
                interval_end=datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc),
                predicted_arrivals=2,
                predicted_energy_kwh=Decimal("20.000"),
            )
            session.add(fi)
            await session.commit()

        async with sf() as session:
            service = FeedbackService(db=session)

            payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_fail_induced",
                forecast_id="fcst_rollback_01",
                scenario_id="scen_rb",
                submitted_at=datetime.now(timezone.utc),
                stations=[{
                    "station_id": "ST-001",
                    "intervals": [{
                        "interval_start": datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc),
                        "interval_end": datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc),
                        "allocated_energy_kwh": 30.0,
                    }],
                }],
            )

            # Intentionally simulate commit failure
            with patch.object(session, "commit", side_effect=RuntimeError("Simulated Disk/DB Failure")):
                with pytest.raises(RuntimeError, match="Simulated Disk/DB Failure"):
                    await service.submit_feedback(payload)

        # Confirm rollback: No allocation_feedbacks or adjusted_demand_intervals written
        async with sf() as session:
            q1 = await session.execute(select(AllocationFeedback).where(AllocationFeedback.allocation_run_id == "run_fail_induced"))
            assert q1.scalar_one_or_none() is None

            q2 = await session.execute(select(AdjustedDemandInterval))
            assert len(q2.scalars().all()) == 0

        await engine.dispose()

    asyncio.run(run())
