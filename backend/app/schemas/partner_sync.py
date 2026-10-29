"""Pydantic v2 schemas for EVCharge-Opt Partner Sync."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PartnerSyncRequest(BaseModel):
    """Payload to initiate an authenticated sync with EVCharge-Opt."""
    forecast_id: str = Field(..., description="Originating forecast identifier")
    scenario_id: Optional[str] = Field("SCN-001", description="Scenario identifier on EVCharge-Opt")
    forecast_start: Optional[str] = Field(None, description="Forecast start ISO timestamp (UTC)")
    station_ids: Optional[List[str]] = Field(
        None,
        description="Station IDs to optimize (defaults to active stations on partner)"
    )
    interval_start: Optional[str] = Field(None, description="Start of allocation interval (UTC)")
    interval_end: Optional[str] = Field(None, description="End of allocation interval (UTC)")
    deferred_fraction: Optional[float] = Field(0.7, ge=0.0, le=1.0, description="Optimizer deferred fraction")


class StationAllocationSummary(BaseModel):
    """Station allocation metrics returned by EVCharge-Opt."""
    station_id: str
    station_name: str
    predicted_arrivals: float
    predicted_energy_kwh: float
    estimated_served: float
    estimated_unserved: float
    allocated_power_kw: float
    estimated_wait_minutes: float
    charger_utilization_pct: float
    warnings: List[str] = []


class PartnerSyncResponse(BaseModel):
    """Complete, verified response from EVCharge-Opt end-to-end sync."""
    success: bool
    partner_service: str = "EVCharge-Opt"
    partner_base_url: str
    stage_reached: str
    opt_forecast_id: Optional[str] = None
    opt_scenario_id: Optional[str] = None
    opt_allocation_id: Optional[str] = None
    opt_feedback_id: Optional[str] = None
    allocation_status: Optional[str] = None
    feedback_status: Optional[str] = None
    total_stations: int = 0
    total_allocated_power_kw: float = 0.0
    total_served_vehicles: float = 0.0
    total_unserved_vehicles: float = 0.0
    average_wait_minutes: float = 0.0
    allocation_results: List[StationAllocationSummary] = []
    feedback_outcomes: List[Dict[str, Any]] = []
    roundtrip_duration_ms: float = 0.0
    error: Optional[str] = None
    correlation_id: Optional[str] = None
