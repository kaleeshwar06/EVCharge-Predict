"""Pydantic v2 schemas for the Forecast API matching the integration contract."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class ForecastCreateRequest(BaseModel):
    """Request payload to trigger a 6-interval hourly forecast generation."""
    scenario_id: str = Field(..., min_length=1, max_length=128, examples=["scenario_demo_001"])
    station_ids: List[str] = Field(..., min_length=1, examples=[["ST-001", "ST-002", "ST-003"]])
    forecast_start: datetime = Field(..., examples=["2026-10-25T09:00:00Z"])
    interval_minutes: int = Field(60, description="Forecast step size in minutes (must be 60 for v1.0)")
    horizon_intervals: int = Field(6, description="Number of intervals (must be 6 for v1.0)")

    @field_validator("station_ids")
    @classmethod
    def validate_station_ids(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("station_ids cannot be empty")
        seen = set()
        duplicates = []
        for st in v:
            clean = st.strip()
            if not clean.startswith("ST-"):
                raise ValueError(f"Invalid canonical station ID '{st}'. Must follow format 'ST-xxx'.")
            if clean in seen:
                duplicates.append(clean)
            seen.add(clean)
        if duplicates:
            raise ValueError(f"Duplicate station IDs provided: {sorted(set(duplicates))}")
        return [st.strip() for st in v]

    @field_validator("forecast_start")
    @classmethod
    def validate_forecast_start_alignment(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("forecast_start must be timezone-aware (e.g. UTC ISO 8601 with Z suffix)")
        v_utc = v.astimezone(timezone.utc)
        if v_utc.minute != 0 or v_utc.second != 0 or v_utc.microsecond != 0:
            raise ValueError(f"forecast_start must be aligned to a UTC hourly boundary (got {v_utc.strftime('%Y-%m-%dT%H:%M:%SZ')})")
        return v_utc

    @field_validator("interval_minutes")
    @classmethod
    def validate_interval_minutes(cls, v: int) -> int:
        if v != 60:
            raise ValueError("Contract version 1.0 supports exactly interval_minutes = 60")
        return v

    @field_validator("horizon_intervals")
    @classmethod
    def validate_horizon_intervals(cls, v: int) -> int:
        if v != 6:
            raise ValueError("Contract version 1.0 supports exactly horizon_intervals = 6")
        return v


class ForecastCreateResponse(BaseModel):
    """Initial lightweight confirmation returned upon forecast creation (HTTP 201)."""
    contract_version: str = Field("1.0")
    forecast_id: str
    scenario_id: str
    status: str
    demand_type: str = "baseline"
    generated_at: datetime
    interval_minutes: int = 60
    horizon_intervals: int = 6
    forecast_url: str

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("generated_at", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ForecastIntervalRead(BaseModel):
    """Forecast interval prediction."""
    interval_start: datetime
    interval_end: datetime
    predicted_arrivals: int = Field(..., ge=0)
    predicted_energy_kwh: float = Field(..., ge=0.0)

    @field_serializer("interval_start", "interval_end", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StationForecastRead(BaseModel):
    """Container for a single station's intervals."""
    station_id: str
    intervals: List[ForecastIntervalRead]


class HorizonMetadata(BaseModel):
    start: datetime
    end: datetime
    interval_minutes: int
    interval_count: int

    @field_serializer("start", "end", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ModelProvenanceMetadata(BaseModel):
    model_version: str
    training_data_type: str  # synthetic or real
    scikit_learn_version: Optional[str] = None
    training_data_fingerprint: Optional[str] = None


class ForecastSummaryRead(BaseModel):
    """Summary of a saved forecast for prediction history listings."""
    contract_version: str = Field("1.0")
    forecast_id: str
    scenario_id: str
    status: str
    demand_type: str = "baseline"
    generated_at: datetime
    forecast_start: datetime
    forecast_end: datetime
    interval_minutes: int = 60
    horizon_intervals: int = 6
    station_count: int
    station_ids: List[str]

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("generated_at", "forecast_start", "forecast_end", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ForecastDetailRead(BaseModel):
    """Full detail forecast response matching the contract."""
    contract_version: str = Field("1.0")
    forecast_id: str
    scenario_id: str
    generated_at: datetime
    horizon: HorizonMetadata
    demand_type: str = "baseline"
    stations: List[StationForecastRead]
    model: ModelProvenanceMetadata

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("generated_at", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

