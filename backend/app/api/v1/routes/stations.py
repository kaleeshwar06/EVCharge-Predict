"""Station query endpoints."""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.station import Station
from app.schemas.station import StationRead

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get(
    "",
    response_model=List[StationRead],
    summary="List charging stations",
    description="Returns all registered charging stations with canonical ST-xxx identifiers.",
)
async def list_stations(
    site_id: Optional[str] = Query(None, description="Filter by site ID (e.g. caltech)"),
    db: AsyncSession = Depends(get_db_session),
) -> List[StationRead]:
    query = select(Station).order_by(Station.station_id)
    if site_id:
        query = query.where(Station.site_id == site_id)
    result = await db.execute(query)
    stations = result.scalars().all()
    return [StationRead.model_validate(s) for s in stations]
