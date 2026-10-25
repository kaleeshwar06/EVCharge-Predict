"""Pydantic v2 schemas for EVCharge-Opt Allocation Feedback & Adjusted Demand."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


# ─── 1. Ingestion Request Schemas ────────────────────────────────────────────

class AllocationIntervalInput(BaseModel):
    """Interval-level allocation result reported by EVCharge-Opt."""
    interval_start: datetime = Field(..., description="UTC start of 60-min interval, must match forecast interval")
    interval_end: datetime = Field(..., description="UTC end of 60-min interval")
    allocated_energy_kwh: Optional[float] = Field(None, ge=0.0, description="Energy allocated by optimizer (kWh)")
    available_capacity_kw: Optional[float] = Field(None, ge=0.0, description="Available charger capacity (kW)")
    reported_unmet_demand_kwh: Optional[float] = Field(None, ge=0.0, description="Unmet demand explicitly reported by optimizer (kWh)")

    @field_validator("interval_start", "interval_end")
    @classmethod
    def validate_utc_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware UTC")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_interval_bounds(self) -> AllocationIntervalInput:
        if self.interval_end <= self.interval_start:
            raise ValueError(f"interval_end ({self.interval_end}) must be strictly after interval_start ({self.interval_start})")
        return self


class StationAllocationFeedbackInput(BaseModel):
    """Station-level allocation feedback with consecutive hourly intervals."""
    station_id: str = Field(..., description="Canonical station ID (e.g., 'ST-001')")
    intervals: List[AllocationIntervalInput] = Field(..., min_length=1, description="List of allocation intervals")

    @field_validator("station_id")
    @classmethod
    def validate_station_id(cls, v: str) -> str:
        clean = v.strip()
        if not clean.startswith("ST-"):
            raise ValueError(f"Invalid canonical station ID '{v}'. Must start with 'ST-'.")
        return clean

    @model_validator(mode="after")
    def validate_intervals_unique_ordered(self) -> StationAllocationFeedbackInput:
        seen = set()
        for it in self.intervals:
            start_iso = it.interval_start.isoformat()
            if start_iso in seen:
                raise ValueError(f"Duplicate interval_start '{start_iso}' for station '{self.station_id}'")
            seen.add(start_iso)
        return self


class FeedbackCreateRequest(BaseModel):
    """Payload submitted by EVCharge-Opt to report allocation feedback."""
    contract_version: str = Field("1.0", description="Integration contract version")
    allocation_run_id: str = Field(..., min_length=1, max_length=128, description="Unique optimizer execution identifier for idempotency")
    forecast_id: str = Field(..., min_length=1, max_length=64, description="Originating forecast identifier (e.g., 'fcst_...')")
    scenario_id: str = Field(..., min_length=1, max_length=128, description="Scenario identifier")
    submitted_at: datetime = Field(..., description="Timestamp when optimizer generated feedback")
    optimizer_version: Optional[str] = Field(None, max_length=64, description="Version of the EVCharge-Opt optimizer")
    stations: List[StationAllocationFeedbackInput] = Field(..., min_length=1, description="Per-station allocation results")

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware UTC")
        return v.astimezone(timezone.utc)

    @field_validator("stations")
    @classmethod
    def validate_stations_unique(cls, v: List[StationAllocationFeedbackInput]) -> List[StationAllocationFeedbackInput]:
        seen = set()
        for st in v:
            if st.station_id in seen:
                raise ValueError(f"Duplicate station_id '{st.station_id}' in feedback request")
            seen.add(st.station_id)
        return v


# ─── 2. Ingestion Response Schemas ───────────────────────────────────────────

class FeedbackCreateResponse(BaseModel):
    """Acknowledgement returned upon feedback submission (HTTP 201 or 200)."""
    contract_version: str = "1.0"
    feedback_id: str
    allocation_run_id: str
    forecast_id: str
    scenario_id: str
    status: str
    is_duplicate: bool
    received_at: datetime
    feedback_url: str

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("received_at", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── 3. Detail & Retrieval Schemas ───────────────────────────────────────────

class FeedbackDetailRead(BaseModel):
    """Stored feedback metadata and processing status."""
    contract_version: str
    feedback_id: str
    allocation_run_id: str
    forecast_id: str
    scenario_id: str
    status: str
    optimizer_version: Optional[str] = None
    submitted_at: datetime
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("submitted_at", "received_at", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AdjustedDemandIntervalRead(BaseModel):
    """Single interval comparing baseline predictions with feedback and derived operational demand."""
    interval_start: datetime
    interval_end: datetime

    # Preserved baseline
    baseline_arrivals: int = Field(..., ge=0, description="Preserved baseline predicted arrivals")
    baseline_energy_kwh: float = Field(..., ge=0.0, description="Preserved baseline predicted energy demand (kWh)")

    # Feedback inputs
    allocated_energy_kwh: Optional[float] = Field(None, ge=0.0, description="Optimizer allocated energy (kWh)")
    available_capacity_kw: Optional[float] = Field(None, ge=0.0, description="Optimizer available capacity (kW)")
    reported_unmet_demand_kwh: Optional[float] = Field(None, ge=0.0, description="Explicit unmet demand reported by optimizer (kWh)")

    # Derived operational result
    adjusted_operational_demand_kwh: float = Field(..., ge=0.0, description="Derived operational energy demand (kWh)")
    adjustment_status: str = Field(..., description="'adjusted', 'unchanged', or 'insufficient_data'")

    @field_serializer("interval_start", "interval_end", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StationAdjustedDemandRead(BaseModel):
    """Station container for adjusted demand intervals."""
    station_id: str
    intervals: List[AdjustedDemandIntervalRead]


class AdjustedDemandResponse(BaseModel):
    """Full feedback-adjusted operational demand payload."""
    contract_version: str = "1.0"
    forecast_id: str
    scenario_id: str
    feedback_id: str
    allocation_run_id: str
    demand_type: str = "feedback-adjusted-operational"
    adjustment_policy_version: str
    policy_description: str
    policy_limitations: str
    computed_at: datetime
    stations: List[StationAdjustedDemandRead]

    @field_serializer("computed_at", when_used="json")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
