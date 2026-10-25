"""
seed_demo_sessions.py
---------------------
Inserts synthetic charging sessions for ST-001, ST-002, and ST-003
into the SQLite database so the forecast endpoint has enough history
(≥ 5 observations) to build the 30-feature input vector.

Run from the project root:
    py -3.14 scripts/seed_demo_sessions.py
"""
from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make sure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select, text
from app.db.session import get_engine, get_session_factory
from app.db.base import Base
from app.models.station import Station
from app.models.charging_session import ChargingSession

STATION_IDS = ["ST-001", "ST-002", "ST-003"]
SESSIONS_PER_STATION = 40       # well above the 5-observation minimum
SEED_DAYS_BACK = 14             # sessions spread across past 14 days

random.seed(42)


def _random_session(station_pk: int, idx: int, station_canonical: str, base_time: datetime) -> ChargingSession:
    """Generate one plausible synthetic session."""
    # Arrival spread across the day with a morning/evening peak bias
    hour_weights = [1,1,1,1,1,1,2,5,8,7,5,4,4,5,6,7,8,7,6,5,4,3,2,1]
    hour = random.choices(range(24), weights=hour_weights, k=1)[0]
    minute = random.randint(0, 59)
    arrival = base_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    duration_hrs = round(random.uniform(0.5, 4.0), 2)
    departure = arrival + timedelta(hours=duration_hrs)
    energy_kwh = round(duration_hrs * random.uniform(4.0, 9.5), 3)  # ~4-9.5 kW rate

    return ChargingSession(
        station_id=station_pk,
        source_session_id=f"seed-{station_canonical}-{idx:04d}",
        connection_time=arrival,
        disconnect_time=departure,
        kwh_delivered=energy_kwh,
        source_dataset="seed-synthetic",
    )


async def seed() -> None:
    engine = get_engine()
    session_factory = get_session_factory()

    # Ensure tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        # Upsert stations — get or create, track integer PKs
        station_pks: dict[str, int] = {}
        for st_id in STATION_IDS:
            result = await session.execute(
                select(Station).where(Station.station_id == st_id)
            )
            existing_station = result.scalars().first()
            if existing_station:
                station_pks[st_id] = existing_station.id
                print(f"  Station {st_id} already exists (pk={existing_station.id})")
            else:
                new_station = Station(
                    station_id=st_id,
                    source_station_id=f"demo-src-{st_id}",
                    site_id="demo-site",
                )
                session.add(new_station)
                await session.flush()  # get the auto-generated PK
                station_pks[st_id] = new_station.id
                print(f"  Created station {st_id} (pk={new_station.id})")

        # Insert sessions
        now = datetime.now(tz=timezone.utc)
        added = 0
        for st_id in STATION_IDS:
            pk = station_pks[st_id]
            for i in range(SESSIONS_PER_STATION):
                src_id = f"seed-{st_id}-{i:04d}"
                # Skip if already seeded
                dup = await session.execute(
                    text("SELECT 1 FROM charging_sessions WHERE source_session_id = :sid"),
                    {"sid": src_id},
                )
                if dup.fetchone() is not None:
                    continue

                days_back = random.randint(0, SEED_DAYS_BACK - 1)
                base = now - timedelta(days=days_back)
                sess_obj = _random_session(pk, i, st_id, base)
                session.add(sess_obj)
                added += 1

        await session.commit()
        print(f"\n[OK] Seeded {added} synthetic sessions across {STATION_IDS}.")
        print("     You can now POST /api/v1/forecasts with any of these station IDs.")


if __name__ == "__main__":
    asyncio.run(seed())
