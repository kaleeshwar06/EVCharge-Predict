"""Pydantic schemas for Station entity."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class StationBase(BaseModel):
    station_id: str = Field(..., pattern=r"^ST-\d+$", examples=["ST-001"])
    source_station_id: str = Field(..., min_length=1, examples=["1-39-139-650"])
    site_id: Optional[str] = Field(None, examples=["caltech"])


class StationCreate(StationBase):
    pass


class StationRead(StationBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
