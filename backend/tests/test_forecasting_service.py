"""Comprehensive automated tests for Phase 4: Model loading, Recursive forecasting, API endpoints, and Persistence."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.forecast import Forecast, ForecastInterval
from app.models.station import Station
from app.schemas.forecast import ForecastCreateRequest
from app.services.forecasting import (
    ForecastingEngine,
    InsufficientHistoryError,
    StationNotFoundError,
)
from app.services.model_loader import ModelArtifactError, ModelService

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
MODELS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "models"


# ─── Test Database & Fixture Setup ───────────────────────────────────────────
async def populate_test_database(session_factory):
    """Inserts 3 stations and 14 days of historical sessions for testing."""
    async with session_factory() as session:
        st1 = Station(station_id="ST-001", source_station_id="src-001", site_id="caltech")
        st2 = Station(station_id="ST-002", source_station_id="src-002", site_id="caltech")
        st3 = Station(station_id="ST-003", source_station_id="src-003", site_id="caltech")
        session.add_all([st1, st2, st3])
        await session.flush()

        # Seed 7 days (168 hours) of history up to 2026-10-25 00:00:00Z
        base_time = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
        sessions_to_add = []
        for h in range(168):
            t = base_time + timedelta(hours=h)
            for st in [st1, st2, st3]:
                # 1 session every 3 hours per station
                if h % 3 == 0:
                    sessions_to_add.append(
                        ChargingSession(
                            station_id=st.id,
                            connection_time=t + timedelta(minutes=15),
                            disconnect_time=t + timedelta(hours=2),
                            kwh_delivered=Decimal("22.50"),
                            source_dataset="synthetic-test",
                        )
                    )
        session.add_all(sessions_to_add)
        await session.commit()


# ─── 1. Model Loading & Compatibility Tests ──────────────────────────────────
def test_model_service_loads_valid_artifacts():
    service = ModelService(artifact_dir=MODELS_DIR)
    assert service.is_loaded is True
    assert service.load_error is None

    arr_m, ene_m, manifest = service.get_models()
    assert arr_m is not None
    assert ene_m is not None
    assert manifest["model_version"] == "1.0"
    assert manifest["is_synthetic"] is True
    assert len(manifest["feature_names"]) == 30


def test_model_service_missing_manifest_fails(tmp_path):
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()
    service = ModelService(artifact_dir=empty_dir)
    assert service.is_loaded is False
    assert "missing" in service.load_error.lower()
    with pytest.raises(ModelArtifactError):
        service.get_models()


def test_model_service_corrupt_manifest_fails(tmp_path):
    bad_dir = tmp_path / "bad_models"
    bad_dir.mkdir()
    with open(bad_dir / "manifest.json", "w") as f:
        f.write("{corrupt json")
    service = ModelService(artifact_dir=bad_dir)
    assert service.is_loaded is False
    assert "corrupted" in service.load_error.lower()


# ─── 2. Recursive Forecasting & Engine Unit Tests ────────────────────────────
def test_recursive_forecasting_generates_six_consecutive_intervals(tmp_path):
    async def run():
        db_file = tmp_path / "test_forecast_engine.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_database(sf)

        model_service = ModelService(artifact_dir=MODELS_DIR)

        async with sf() as session:
            forecasting_engine = ForecastingEngine(db=session, model_service=model_service)

            req = ForecastCreateRequest(
                scenario_id="scenario_test_01",
                station_ids=["ST-001", "ST-002"],
                forecast_start=datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc),
                interval_minutes=60,
                horizon_intervals=6,
            )
            resp = await forecasting_engine.generate_and_persist_forecast(req)

            assert resp.status == "completed"
            assert resp.demand_type == "baseline"
            assert resp.horizon_intervals == 6
            assert resp.forecast_id.startswith("fcst_")

            # Retrieve detail and verify 6 non-overlapping hourly intervals per station
            detail = await ForecastingEngine.get_forecast_by_id(session, resp.forecast_id)
            assert detail is not None
            assert len(detail.stations) == 2

            for st_entry in detail.stations:
                assert st_entry.station_id in ["ST-001", "ST-002"]
                assert len(st_entry.intervals) == 6

                for idx, interval in enumerate(st_entry.intervals):
                    expected_start = req.forecast_start + timedelta(hours=idx)
                    expected_end = expected_start + timedelta(hours=1)
                    assert interval.interval_start == expected_start
                    assert interval.interval_end == expected_end
                    assert interval.predicted_arrivals >= 0
                    assert interval.predicted_energy_kwh >= 0.0

        await engine.dispose()

    asyncio.run(run())


def test_forecast_rejects_unknown_station(tmp_path):
    async def run():
        db_file = tmp_path / "test_unknown_st.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_database(sf)

        async with sf() as session:
            forecasting_engine = ForecastingEngine(db=session)
            req = ForecastCreateRequest(
                scenario_id="scenario_bad_station",
                station_ids=["ST-999"],
                forecast_start=datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc),
            )
            with pytest.raises(StationNotFoundError):
                await forecasting_engine.generate_and_persist_forecast(req)

        await engine.dispose()

    asyncio.run(run())


def test_forecast_rejects_insufficient_history(tmp_path):
    async def run():
        db_file = tmp_path / "test_no_hist.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Add station but zero session history
        async with sf() as session:
            st = Station(station_id="ST-001", source_station_id="src-001")
            session.add(st)
            await session.commit()

        async with sf() as session:
            forecasting_engine = ForecastingEngine(db=session)
            # Forecast requested far in the future where no history window overlaps
            req = ForecastCreateRequest(
                scenario_id="scenario_no_hist",
                station_ids=["ST-001"],
                forecast_start=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
            )
            with pytest.raises(InsufficientHistoryError):
                await forecasting_engine.generate_and_persist_forecast(req)

        await engine.dispose()

    asyncio.run(run())


# ─── 3. Full API Endpoints & Contract Tests ──────────────────────────────────
def test_forecast_api_full_flow(tmp_path):
    async def run():
        db_file = tmp_path / "test_forecast_api.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_database(sf)

        async def override_get_db():
            async with sf() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health & Ready
            res_h = await client.get("/healthz")
            assert res_h.status_code == 200
            assert res_h.json()["service"] == "evcharge-predict"

            res_r = await client.get("/readyz")
            assert res_r.status_code == 200
            assert res_r.json()["status"] == "ready"

            # 2. POST /api/v1/forecasts
            post_payload = {
                "scenario_id": "scenario_demo_001",
                "station_ids": ["ST-001", "ST-002"],
                "forecast_start": "2026-10-25T00:00:00Z",
                "interval_minutes": 60,
                "horizon_intervals": 6,
            }
            res_post = await client.post("/api/v1/forecasts", json=post_payload)
            assert res_post.status_code == 201
            post_data = res_post.json()
            assert post_data["contract_version"] == "1.0"
            assert post_data["status"] == "completed"
            assert post_data["demand_type"] == "baseline"
            forecast_id = post_data["forecast_id"]
            forecast_url = post_data["forecast_url"]
            assert forecast_url == f"/api/v1/forecasts/{forecast_id}"

            # 3. GET /api/v1/forecasts/{forecast_id}
            res_get = await client.get(forecast_url)
            assert res_get.status_code == 200
            detail = res_get.json()
            assert detail["forecast_id"] == forecast_id
            assert detail["scenario_id"] == "scenario_demo_001"
            assert detail["horizon"]["interval_count"] == 6
            assert detail["model"]["training_data_type"] == "synthetic"
            assert len(detail["stations"]) == 2
            for st in detail["stations"]:
                assert len(st["intervals"]) == 6
                # Verify ISO UTC format with Z
                assert st["intervals"][0]["interval_start"].endswith("Z")
                assert st["intervals"][0]["interval_end"].endswith("Z")

            # 4. GET /api/v1/forecasts/latest?scenario_id=scenario_demo_001
            res_latest = await client.get("/api/v1/forecasts/latest?scenario_id=scenario_demo_001")
            assert res_latest.status_code == 200
            latest_data = res_latest.json()
            assert latest_data["forecast_id"] == forecast_id

            # 5. Non-existent forecast -> 404
            res_404 = await client.get("/api/v1/forecasts/fcst_nonexistent")
            assert res_404.status_code == 404

            # 6. Non-existent scenario latest -> 404
            res_no_scen = await client.get("/api/v1/forecasts/latest?scenario_id=no_such_scenario")
            assert res_no_scen.status_code == 404

            # 7. Unaligned forecast_start -> 422
            bad_start_payload = {
                "scenario_id": "bad_time",
                "station_ids": ["ST-001"],
                "forecast_start": "2026-10-25T00:15:00Z",  # Not hourly aligned
            }
            res_bad_time = await client.post("/api/v1/forecasts", json=bad_start_payload)
            assert res_bad_time.status_code == 422

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(run())


def test_recursive_forecasting_three_stations_simultaneously(tmp_path):
    """Regression test: verifies a single forecast request requesting all three supported stations (ST-001, ST-002, ST-003)."""
    async def run():
        db_file = tmp_path / "test_three_stations.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await populate_test_database(sf)

        model_service = ModelService(artifact_dir=MODELS_DIR)

        async with sf() as session:
            forecasting_engine = ForecastingEngine(db=session, model_service=model_service)

            target_station_ids = ["ST-001", "ST-002", "ST-003"]
            req = ForecastCreateRequest(
                scenario_id="scenario_three_stations_001",
                station_ids=target_station_ids,
                forecast_start=datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc),
                interval_minutes=60,
                horizon_intervals=6,
            )
            resp = await forecasting_engine.generate_and_persist_forecast(req)

            assert resp.status == "completed"
            assert resp.demand_type == "baseline"
            assert resp.horizon_intervals == 6
            assert resp.forecast_id.startswith("fcst_")

            # Retrieve detail and verify intervals for all 3 stations
            detail = await ForecastingEngine.get_forecast_by_id(session, resp.forecast_id)
            assert detail is not None
            assert len(detail.stations) == 3

            returned_station_ids = [st.station_id for st in detail.stations]
            assert sorted(returned_station_ids) == sorted(target_station_ids)

            for st_entry in detail.stations:
                assert st_entry.station_id in target_station_ids
                assert len(st_entry.intervals) == 6

                for idx, interval in enumerate(st_entry.intervals):
                    expected_start = req.forecast_start + timedelta(hours=idx)
                    expected_end = expected_start + timedelta(hours=1)
                    assert interval.interval_start == expected_start
                    assert interval.interval_end == expected_end
                    assert interval.predicted_arrivals >= 0
                    assert interval.predicted_energy_kwh >= 0.0

        await engine.dispose()

    asyncio.run(run())

