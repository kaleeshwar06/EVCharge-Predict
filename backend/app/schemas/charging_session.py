"""Pydantic schemas for ChargingSession entity."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class SessionIngestItem(BaseModel):
    """Schema representing an incoming raw parsed session record."""
    source_session_id: Optional[str] = None
    source_station_id: str = Field(..., min_length=1)
    connection_time: datetime
    disconnect_time: Optional[datetime] = None
    kwh_delivered: Optional[Decimal] = Field(None, ge=0)
    source_site_id: Optional[str] = None
    source_timezone: Optional[str] = None
    source_dataset: str = "acn-data"

    @model_validator(mode="after")
    def validate_timestamps_and_order(self) -> "SessionIngestItem":
        # Ensure connection_time is timezone-aware
        if self.connection_time.tzinfo is None:
            self.connection_time = self.connection_time.replace(tzinfo=timezone.utc)
        else:
            self.connection_time = self.connection_time.astimezone(timezone.utc)

        if self.disconnect_time is not None:
            if self.disconnect_time.tzinfo is None:
                self.disconnect_time = self.disconnect_time.replace(tzinfo=timezone.utc)
            else:
                self.disconnect_time = self.disconnect_time.astimezone(timezone.utc)

            if self.disconnect_time < self.connection_time:
                raise ValueError("disconnect_time cannot be earlier than connection_time")

        return self


class ChargingSessionRead(BaseModel):
    """Public API response schema for a charging session."""
    id: int
    source_session_id: Optional[str] = None
    station_id: str = Field(..., description="Canonical station ID", examples=["ST-001"])
    connection_time: datetime
    disconnect_time: Optional[datetime] = None
    kwh_delivered: Optional[Decimal] = None
    source_site_id: Optional[str] = None
    source_timezone: Optional[str] = None
    source_dataset: str

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("connection_time", "disconnect_time", when_used="json")
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        if dt is None:
            return None
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
