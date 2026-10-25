"""Charging session query endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.charging_session import ChargingSession
from app.models.station import Station
from app.schemas.charging_session import ChargingSessionRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get(
    "",
    response_model=List[ChargingSessionRead],
    summary="List charging sessions",
    description="Returns charging sessions with pagination and optional station/time filters.",
)
async def list_sessions(
    station_id: Optional[str] = Query(None, description="Canonical station ID (e.g. ST-001)"),
    start_time: Optional[datetime] = Query(None, description="Filter connection_time >= start_time (UTC ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="Filter connection_time <= end_time (UTC ISO 8601)"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db_session),
) -> List[ChargingSessionRead]:
    query = (
        select(ChargingSession, Station.station_id)
        .join(Station, ChargingSession.station_id == Station.id)
        .order_by(ChargingSession.connection_time.asc())
        .limit(limit)
        .offset(offset)
    )
    if station_id:
        query = query.where(Station.station_id == station_id)
    if start_time:
        query = query.where(ChargingSession.connection_time >= start_time)
    if end_time:
        query = query.where(ChargingSession.connection_time <= end_time)

    result = await db.execute(query)
    rows = result.all()

    output = []
    for sess, st_canonical_id in rows:
        output.append(
            ChargingSessionRead(
                id=sess.id,
                source_session_id=sess.source_session_id,
                station_id=st_canonical_id,
                connection_time=sess.connection_time,
                disconnect_time=sess.disconnect_time,
                kwh_delivered=sess.kwh_delivered,
                source_site_id=sess.source_site_id,
                source_timezone=sess.source_timezone,
                source_dataset=sess.source_dataset,
            )
        )
    return output
