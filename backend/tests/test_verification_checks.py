"""Verification tests for persistent station mapping and duplicate session handling."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.charging_session import ChargingSession
from app.models.station import Station
from app.services.ingestion import IngestionPipeline
from app.services.station_mapping import StationMappingService

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_station_mapping_concurrent_safety(tmp_path):
    """Test 1: Verify persistent station mapping under concurrent threads.

    Confirms that multiple concurrent mapping calls never assign duplicate canonical IDs,
    atomically save to disk, and always map identical source station IDs to the exact same canonical ID.
    """
    map_file = tmp_path / "station_mapping.json"
    mapping_service = StationMappingService(mapping_file=map_file)

    source_stations = [f"SRC_STATION_{i % 10}" for i in range(100)]

    def allocate(src: str):
        # Create a fresh service instance to simulate separate workers reading from disk
        srv = StationMappingService(mapping_file=map_file)
        return src, srv.get_or_create(src)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(allocate, source_stations))

    # All allocations for the same source ID must yield the exact same canonical ID
    mapping_by_src = {}
    for src, canonical_id in results:
        if src in mapping_by_src:
            assert mapping_by_src[src] == canonical_id
        else:
            mapping_by_src[src] = canonical_id

    # Must have exactly 10 distinct canonical IDs for the 10 distinct source stations
    assert len(mapping_by_src) == 10
    canonical_set = set(mapping_by_src.values())
    assert len(canonical_set) == 10
    expected_ids = {f"ST-{i:03d}" for i in range(1, 11)}
    assert canonical_set == expected_ids


def test_missing_session_id_deduplication(tmp_path):
    """Test 2: Verify fallback deduplication when source_session_id is missing/NULL.

    Demonstrates that repeated ingestion of records lacking session IDs correctly detects
    the composite (station_id, connection_time) duplicate and avoids inserting duplicates.
    """
    async def run():
        db_file = tmp_path / "test_dedup.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        mapping_service = StationMappingService(mapping_file=tmp_path / "map.json")

        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
            # Run 1: Should insert 2 sessions with NULL source_session_id
            rep1 = await pipeline.ingest_file(FIXTURES_DIR / "missing_session_ids.json")
            assert rep1.status == "completed"
            assert rep1.total_records_read == 2
            assert rep1.records_inserted == 2
            assert rep1.records_skipped == 0

            # Run 2: Same file ingested again — fallback composite deduplication must skip both
            rep2 = await pipeline.ingest_file(FIXTURES_DIR / "missing_session_ids.json")
            assert rep2.status == "completed"
            assert rep2.total_records_read == 2
            assert rep2.records_inserted == 0
            assert rep2.records_skipped == 2

            # Confirm database has exactly 2 records
            sessions = (await session.execute(select(ChargingSession))).scalars().all()
            assert len(sessions) == 2
            assert all(s.source_session_id is None for s in sessions)

        await engine.dispose()

    asyncio.run(run())
