"""Automated tests for Phase 2: models, schemas, ingestion, station mapping, and API endpoints."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.charging_session import ChargingSession
from app.models.dataset_import import DatasetImport
from app.models.station import Station
from app.schemas.charging_session import SessionIngestItem
from app.schemas.station import StationCreate
from app.services.ingestion import IngestionPipeline, IngestionReport
from app.services.station_mapping import StationMappingService

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── 1. Schema Validation Tests ──────────────────────────────────────────────
def test_schema_valid_session():
    item = SessionIngestItem(
        source_session_id="s1",
        source_station_id="st-src-1",
        connection_time=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
        disconnect_time=datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc),
        kwh_delivered=Decimal("15.5"),
    )
    assert item.kwh_delivered == Decimal("15.5")
    assert item.connection_time.tzinfo is not None


def test_schema_negative_kwh_rejected():
    with pytest.raises(ValidationError):
        SessionIngestItem(
            source_station_id="st-1",
            connection_time=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            kwh_delivered=Decimal("-5.0"),
        )


def test_schema_disconnect_before_connection_rejected():
    with pytest.raises(ValidationError):
        SessionIngestItem(
            source_station_id="st-1",
            connection_time=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            disconnect_time=datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc),
            kwh_delivered=Decimal("10.0"),
        )


def test_schema_station_canonical_pattern():
    with pytest.raises(ValidationError):
        StationCreate(station_id="INVALID_ID", source_station_id="src-1")


# ─── 2. Station Mapping Tests ────────────────────────────────────────────────
def test_station_mapping_stability(tmp_path):
    map_file = tmp_path / "station_mapping.json"
    mapping_service = StationMappingService(mapping_file=map_file)
    id1 = mapping_service.get_or_create("ACN-101")
    id2 = mapping_service.get_or_create("ACN-102")
    assert id1 == "ST-001"
    assert id2 == "ST-002"

    # Reload from disk to verify persistence
    reloaded_service = StationMappingService(mapping_file=map_file)
    assert reloaded_service.get_or_create("ACN-101") == "ST-001"
    assert reloaded_service.get_or_create("ACN-102") == "ST-002"
    # New one gets ST-003
    assert reloaded_service.get_or_create("ACN-103") == "ST-003"


# ─── 3. Ingestion Pipeline Tests ─────────────────────────────────────────────
def test_ingest_valid_dataset(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            report = await pipeline.ingest_file(
                file_path=FIXTURES_DIR / "valid_sessions.json",
                dry_run=False,
            )
            assert report.status == "completed"
            assert report.total_records_read == 3
            assert report.records_inserted == 3
            assert report.records_skipped == 0
            assert report.records_rejected == 0

            # Verify stations in DB
            stations = (await session.execute(select(Station))).scalars().all()
            assert len(stations) == 2
            canonical_ids = {s.station_id for s in stations}
            assert canonical_ids == {"ST-001", "ST-002"}

            # Verify sessions in DB
            sessions = (await session.execute(select(ChargingSession))).scalars().all()
            assert len(sessions) == 3

        await engine.dispose()

    asyncio.run(run())


def test_ingest_duplicate_sessions_skipped(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            # Run 1
            await pipeline.ingest_file(file_path=FIXTURES_DIR / "valid_sessions.json")
            # Run 2
            report2 = await pipeline.ingest_file(file_path=FIXTURES_DIR / "valid_sessions.json")
            assert report2.status == "completed"
            assert report2.total_records_read == 3
            assert report2.records_inserted == 0
            assert report2.records_skipped == 3

        await engine.dispose()

    asyncio.run(run())


def test_ingest_dry_run_no_database_changes(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            report = await pipeline.ingest_file(
                file_path=FIXTURES_DIR / "valid_sessions.json",
                dry_run=True,
            )
            assert report.status == "dry_run_success"
            assert report.records_inserted == 3

            sessions = (await session.execute(select(ChargingSession))).scalars().all()
            assert len(sessions) == 0

        await engine.dispose()

    asyncio.run(run())


def test_ingest_invalid_records_handling(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            report = await pipeline.ingest_file(
                file_path=FIXTURES_DIR / "invalid_records.json"
            )
            assert report.status == "completed"
            assert report.total_records_read == 4
            assert report.records_inserted == 0
            assert report.records_rejected == 4
            assert "negative_kwh" in report.rejection_reasons
            assert "disconnect_before_connection" in report.rejection_reasons
            assert "missing_station_id" in report.rejection_reasons
            assert "invalid_connection_time" in report.rejection_reasons

        await engine.dispose()

    asyncio.run(run())


def test_ingest_malformed_json_failure(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            report = await pipeline.ingest_file(
                file_path=FIXTURES_DIR / "malformed_truncated.json"
            )
            assert report.status == "failed"
            assert len(report.errors) > 0
            assert "JSON" in report.errors[0]

        await engine.dispose()

    asyncio.run(run())


def test_ingest_missing_items_key_failure(tmp_path):
    async def run():
        db_file = tmp_path / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            report = await pipeline.ingest_file(
                file_path=FIXTURES_DIR / "missing_items_key.json"
            )
            assert report.status == "failed"
            assert "missing '_items'" in report.errors[0]

        await engine.dispose()

    asyncio.run(run())


# ─── 4. API Endpoints Tests ──────────────────────────────────────────────────
def test_api_stations_and_sessions(tmp_path):
    async def run():
        db_file = tmp_path / "test_api.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        # Ingest data first
        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            await pipeline.ingest_file(file_path=FIXTURES_DIR / "valid_sessions.json")

        async def override_get_db():
            async with session_factory() as s:
                yield s

        app.dependency_overrides[get_db_session] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # GET /api/v1/stations
            st_res = await client.get("/api/v1/stations")
            assert st_res.status_code == 200
            st_data = st_res.json()
            assert len(st_data) == 2
            assert st_data[0]["station_id"].startswith("ST-")

            # GET /api/v1/sessions
            sess_res = await client.get("/api/v1/sessions?limit=2")
            assert sess_res.status_code == 200
            sess_data = sess_res.json()
            assert len(sess_data) == 2
            assert sess_data[0]["connection_time"].endswith("Z")

            # GET /api/v1/sessions with station filter
            filter_res = await client.get("/api/v1/sessions?station_id=ST-001")
            assert filter_res.status_code == 200
            filter_data = filter_res.json()
            assert all(s["station_id"] == "ST-001" for s in filter_data)

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(run())
