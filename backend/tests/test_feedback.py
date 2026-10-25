"""Comprehensive automated tests for Phase 5: Feedback Ingestion, Idempotency, Policy v1 Adjustment, and Baseline Immutability."""
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
from app.models.feedback import AdjustedDemandInterval, AllocationFeedback
from app.models.forecast import Forecast, ForecastInterval
from app.models.station import Station
from app.schemas.feedback import FeedbackCreateRequest
from app.services.feedback_service import (
    FeedbackConflictError,
    FeedbackIntervalAlignmentError,
    FeedbackService,
    FeedbackStationError,
    ForecastNotFoundError,
    POLICY_VERSION,
    ScenarioMismatchError,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── Test Database & Fixtures Helper ─────────────────────────────────────────
async def setup_forecast_baseline(session_factory):
    """Creates stations, a completed baseline forecast, and 6 forecast intervals per station."""
    async with session_factory() as session:
        st1 = Station(station_id="ST-001", source_station_id="src-st-001", site_id="site-a")
        st2 = Station(station_id="ST-002", source_station_id="src-st-002", site_id="site-a")
        session.add_all([st1, st2])
        await session.flush()

        fcst_start = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)
        fcst_end = fcst_start + timedelta(hours=6)
        now_utc = datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)

        forecast = Forecast(
            forecast_id="fcst_test_p5_001",
            scenario_id="scenario_p5_base",
            generated_at=now_utc,
            forecast_start=fcst_start,
            forecast_end=fcst_end,
            interval_minutes=60,
            horizon_intervals=6,
            status="completed",
            demand_type="baseline",
            model_version="1.0",
            training_data_type="synthetic",
        )
        session.add(forecast)
        await session.flush()

        # Add 6 intervals for ST-001 and ST-002
        intervals = []
        for idx in range(6):
            s_time = fcst_start + timedelta(hours=idx)
            e_time = s_time + timedelta(hours=1)

            # ST-001 baseline: arrivals=2, energy=20.000 + idx*5
            intervals.append(
                ForecastInterval(
                    forecast_id=forecast.id,
                    station_id=st1.id,
                    interval_start=s_time,
                    interval_end=e_time,
                    predicted_arrivals=2,
                    predicted_energy_kwh=Decimal(f"{20.0 + idx * 5:.3f}"),
                )
            )
            # ST-002 baseline: arrivals=1, energy=15.000
            intervals.append(
                ForecastInterval(
                    forecast_id=forecast.id,
                    station_id=st2.id,
                    interval_start=s_time,
                    interval_end=e_time,
                    predicted_arrivals=1,
                    predicted_energy_kwh=Decimal("15.000"),
                )
            )
        session.add_all(intervals)
        await session.commit()

        return forecast.forecast_id, "scenario_p5_base", fcst_start


# ─── 1. Unit & Policy Calculation Tests ──────────────────────────────────────
def test_feedback_service_valid_submission_and_policy_calculation(tmp_path):
    async def run():
        db_file = tmp_path / "test_feedback_policy.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        fcst_id, scenario_id, fcst_start = await setup_forecast_baseline(sf)

        async with sf() as session:
            service = FeedbackService(db=session)

            # Construct feedback where ST-001 interval 0 allocates 35 kWh (> baseline 20 kWh -> adjusted)
            # and ST-001 interval 1 allocates 10 kWh (< baseline 25 kWh -> unchanged)
            intervals_st1 = []
            for h in range(6):
                s_t = fcst_start + timedelta(hours=h)
                e_t = s_t + timedelta(hours=1)
                alloc = 35.0 if h == 0 else 10.0
                intervals_st1.append({
                    "interval_start": s_t,
                    "interval_end": e_t,
                    "allocated_energy_kwh": alloc,
                    "available_capacity_kw": 50.0,
                    "reported_unmet_demand_kwh": 5.0 if h == 0 else 0.0,
                })

            payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_opt_001",
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=datetime.now(timezone.utc),
                optimizer_version="evcharge-opt-v2.1",
                stations=[{"station_id": "ST-001", "intervals": intervals_st1}],
            )

            resp, code = await service.submit_feedback(payload)
            assert code == 201
            assert resp.status == "accepted"
            assert resp.is_duplicate is False
            assert resp.feedback_id.startswith("fbk_")

            # Verify persisted derived adjusted demand
            adj_resp = await service.get_adjusted_demand(forecast_id=fcst_id, feedback_id=resp.feedback_id)
            assert adj_resp is not None
            assert adj_resp.adjustment_policy_version == POLICY_VERSION
            assert len(adj_resp.stations) == 1
            st1_res = adj_resp.stations[0]
            assert st1_res.station_id == "ST-001"

            # Interval 0: alloc=35 > base=20 -> adj=35, status="adjusted", arrivals preserved=2
            int0 = st1_res.intervals[0]
            assert int0.baseline_arrivals == 2
            assert int0.baseline_energy_kwh == 20.0
            assert int0.allocated_energy_kwh == 35.0
            assert int0.adjusted_operational_demand_kwh == 35.0
            assert int0.adjustment_status == "adjusted"
            assert int0.reported_unmet_demand_kwh == 5.0

            # Interval 1: alloc=10 < base=25 -> adj=25, status="unchanged", arrivals preserved=2
            int1 = st1_res.intervals[1]
            assert int1.baseline_arrivals == 2
            assert int1.baseline_energy_kwh == 25.0
            assert int1.allocated_energy_kwh == 10.0
            assert int1.adjusted_operational_demand_kwh == 25.0
            assert int1.adjustment_status == "unchanged"

        await engine.dispose()

    asyncio.run(run())


def test_feedback_idempotent_retry_and_conflict_detection(tmp_path):
    async def run():
        db_file = tmp_path / "test_feedback_idempotency.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        fcst_id, scenario_id, fcst_start = await setup_forecast_baseline(sf)

        async with sf() as session:
            service = FeedbackService(db=session)

            fixed_time = datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc)
            intervals_st1 = [{
                "interval_start": fcst_start,
                "interval_end": fcst_start + timedelta(hours=1),
                "allocated_energy_kwh": 30.0,
            }]
            payload1 = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_opt_unique_123",
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=fixed_time,
                stations=[{"station_id": "ST-001", "intervals": intervals_st1}],
            )

            # 1. Initial submission -> 201
            resp1, code1 = await service.submit_feedback(payload1)
            assert code1 == 201
            assert resp1.is_duplicate is False
            fbk_id = resp1.feedback_id

            # 2. Identical submission -> 200 with is_duplicate=True
            resp2, code2 = await service.submit_feedback(payload1)
            assert code2 == 200
            assert resp2.is_duplicate is True
            assert resp2.feedback_id == fbk_id

            # 3. Differing payload with SAME allocation_run_id -> 409 Conflict
            conflicting_payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_opt_unique_123",  # Same run id
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=fixed_time,
                stations=[{"station_id": "ST-001", "intervals": [{
                    "interval_start": fcst_start,
                    "interval_end": fcst_start + timedelta(hours=1),
                    "allocated_energy_kwh": 99.0,  # Changed allocated energy
                }]}],
            )
            with pytest.raises(FeedbackConflictError):
                await service.submit_feedback(conflicting_payload)

        await engine.dispose()

    asyncio.run(run())


def test_baseline_forecast_strictly_immutable_after_feedback(tmp_path):
    async def run():
        db_file = tmp_path / "test_baseline_immutability.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        fcst_id, scenario_id, fcst_start = await setup_forecast_baseline(sf)

        # Snapshot baseline intervals before feedback
        async with sf() as session:
            q = (
                select(ForecastInterval)
                .join(Forecast, ForecastInterval.forecast_id == Forecast.id)
                .where(Forecast.forecast_id == fcst_id)
            )
            res = await session.execute(q)
            before_snapshot = [(fi.id, fi.predicted_arrivals, fi.predicted_energy_kwh) for fi in res.scalars().all()]

        # Submit feedback with massive allocation
        async with sf() as session:
            service = FeedbackService(db=session)
            payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_massive_alloc",
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=datetime.now(timezone.utc),
                stations=[{
                    "station_id": "ST-001",
                    "intervals": [{
                        "interval_start": fcst_start,
                        "interval_end": fcst_start + timedelta(hours=1),
                        "allocated_energy_kwh": 500.0,
                    }],
                }],
            )
            await service.submit_feedback(payload)

        # Verify baseline intervals in database are 100% unchanged
        async with sf() as session:
            q = (
                select(ForecastInterval)
                .join(Forecast, ForecastInterval.forecast_id == Forecast.id)
                .where(Forecast.forecast_id == fcst_id)
            )
            res = await session.execute(q)
            after_snapshot = [(fi.id, fi.predicted_arrivals, fi.predicted_energy_kwh) for fi in res.scalars().all()]

            assert before_snapshot == after_snapshot

        await engine.dispose()

    asyncio.run(run())


def test_feedback_validation_rejections(tmp_path):
    async def run():
        db_file = tmp_path / "test_feedback_rejections.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        fcst_id, scenario_id, fcst_start = await setup_forecast_baseline(sf)

        async with sf() as session:
            service = FeedbackService(db=session)

            # 1. Non-existent forecast
            bad_fcst_payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_bad_fcst",
                forecast_id="fcst_nonexistent",
                scenario_id=scenario_id,
                submitted_at=datetime.now(timezone.utc),
                stations=[{"station_id": "ST-001", "intervals": [{
                    "interval_start": fcst_start,
                    "interval_end": fcst_start + timedelta(hours=1),
                    "allocated_energy_kwh": 10.0,
                }]}],
            )
            with pytest.raises(ForecastNotFoundError):
                await service.submit_feedback(bad_fcst_payload)

            # 2. Scenario mismatch
            bad_scen_payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_bad_scen",
                forecast_id=fcst_id,
                scenario_id="wrong_scenario_id",
                submitted_at=datetime.now(timezone.utc),
                stations=[{"station_id": "ST-001", "intervals": [{
                    "interval_start": fcst_start,
                    "interval_end": fcst_start + timedelta(hours=1),
                    "allocated_energy_kwh": 10.0,
                }]}],
            )
            with pytest.raises(ScenarioMismatchError):
                await service.submit_feedback(bad_scen_payload)

            # 3. Unknown station
            bad_station_payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_bad_station",
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=datetime.now(timezone.utc),
                stations=[{"station_id": "ST-999", "intervals": [{
                    "interval_start": fcst_start,
                    "interval_end": fcst_start + timedelta(hours=1),
                    "allocated_energy_kwh": 10.0,
                }]}],
            )
            with pytest.raises(FeedbackStationError):
                await service.submit_feedback(bad_station_payload)

            # 4. Unaligned interval
            bad_interval_payload = FeedbackCreateRequest(
                contract_version="1.0",
                allocation_run_id="run_bad_int",
                forecast_id=fcst_id,
                scenario_id=scenario_id,
                submitted_at=datetime.now(timezone.utc),
                stations=[{"station_id": "ST-001", "intervals": [{
                    "interval_start": fcst_start + timedelta(days=5),  # Outside forecast horizon
                    "interval_end": fcst_start + timedelta(days=5, hours=1),
                    "allocated_energy_kwh": 10.0,
                }]}],
            )
            with pytest.raises(FeedbackIntervalAlignmentError):
                await service.submit_feedback(bad_interval_payload)

        await engine.dispose()

    asyncio.run(run())


# ─── 2. Full HTTP API Endpoint Integration Tests ─────────────────────────────
def test_feedback_api_full_http_lifecycle(tmp_path):
    async def run():
        db_file = tmp_path / "test_feedback_http.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        fcst_id, scenario_id, fcst_start = await setup_forecast_baseline(sf)

        async def override_get_db():
            async with sf() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Submit POST /api/v1/feedback
            post_payload = {
                "contract_version": "1.0",
                "allocation_run_id": "run_http_test_001",
                "forecast_id": fcst_id,
                "scenario_id": scenario_id,
                "submitted_at": "2026-10-25T23:30:00Z",
                "optimizer_version": "evcharge-opt-test",
                "stations": [
                    {
                        "station_id": "ST-001",
                        "intervals": [
                            {
                                "interval_start": fcst_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "interval_end": (fcst_start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "allocated_energy_kwh": 45.5,
                                "available_capacity_kw": 60.0,
                                "reported_unmet_demand_kwh": 2.5,
                            }
                        ],
                    }
                ],
            }

            res_post = await client.post("/api/v1/feedback", json=post_payload)
            assert res_post.status_code == 201
            post_data = res_post.json()
            feedback_id = post_data["feedback_id"]
            assert post_data["is_duplicate"] is False
            assert post_data["status"] == "accepted"

            # 2. Idempotent Retry -> HTTP 200
            res_retry = await client.post("/api/v1/feedback", json=post_payload)
            assert res_retry.status_code == 200
            assert res_retry.json()["is_duplicate"] is True
            assert res_retry.json()["feedback_id"] == feedback_id

            # 3. GET /api/v1/feedback/{feedback_id}
            res_get = await client.get(f"/api/v1/feedback/{feedback_id}")
            assert res_get.status_code == 200
            get_data = res_get.json()
            assert get_data["feedback_id"] == feedback_id
            assert get_data["allocation_run_id"] == "run_http_test_001"
            assert get_data["forecast_id"] == fcst_id

            # 4. GET /api/v1/feedback (List with filters)
            res_list = await client.get(f"/api/v1/feedback?forecast_id={fcst_id}")
            assert res_list.status_code == 200
            assert len(res_list.json()) == 1

            # 5. GET /api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id=...
            res_adj = await client.get(f"/api/v1/forecasts/{fcst_id}/adjusted-demand?feedback_id={feedback_id}")
            assert res_adj.status_code == 200
            adj_data = res_adj.json()
            assert adj_data["forecast_id"] == fcst_id
            assert adj_data["feedback_id"] == feedback_id
            assert adj_data["demand_type"] == "feedback-adjusted-operational"
            assert adj_data["adjustment_policy_version"] == POLICY_VERSION
            assert len(adj_data["stations"]) == 1
            st_res = adj_data["stations"][0]
            assert st_res["station_id"] == "ST-001"
            int_res = st_res["intervals"][0]
            # Baseline was 20.0, allocated 45.5 -> adjusted is 45.5, status="adjusted"
            assert int_res["baseline_energy_kwh"] == 20.0
            assert int_res["allocated_energy_kwh"] == 45.5
            assert int_res["adjusted_operational_demand_kwh"] == 45.5
            assert int_res["adjustment_status"] == "adjusted"
            assert int_res["baseline_arrivals"] == 2

            # 6. Non-existent feedback detail -> 404
            res_404 = await client.get("/api/v1/feedback/fbk_nonexistent")
            assert res_404.status_code == 404

            # 7. Non-existent adjusted demand -> 404
            res_adj_404 = await client.get(f"/api/v1/forecasts/{fcst_id}/adjusted-demand?feedback_id=fbk_nonexistent")
            assert res_adj_404.status_code == 404

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(run())
