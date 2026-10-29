"""Service executing authenticated outbound requests to EVCharge-Opt."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.schemas.partner_sync import (
    PartnerSyncRequest,
    PartnerSyncResponse,
    StationAllocationSummary,
)

logger = logging.getLogger(__name__)


class PartnerSyncService:
    """Coordinates the 4-stage synchronization workflow with EVCharge-Opt."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.evcharge_opt_base_url).rstrip("/")
        self.token = token or settings.opt_service_token

    def _get_headers(self, correlation_id: str) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Correlation-ID": correlation_id,
            "User-Agent": "EVCharge-Predict-PartnerClient/1.0",
        }
        if self.token and self.token.strip() and self.token != "replace-with-service-token":
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    async def execute_sync(self, req: PartnerSyncRequest) -> PartnerSyncResponse:
        correlation_id = f"sync_{uuid4().hex[:12]}"
        t0 = time.perf_counter()

        # Sensible defaults for timestamps if not specified
        now = datetime.now(timezone.utc)
        default_start_iso = now.strftime("%Y-%m-%dT%H:00:00Z")
        forecast_start = req.forecast_start or default_start_iso
        interval_start = req.interval_start or forecast_start
        # Default interval_end is 1 hour after interval_start
        try:
            start_dt = datetime.fromisoformat(interval_start.replace("Z", "+00:00"))
            end_dt = datetime.fromtimestamp(start_dt.timestamp() + 3600, tz=timezone.utc)
            default_end_iso = end_dt.strftime("%Y-%m-%dT%H:00:00Z")
        except Exception:
            default_end_iso = interval_start

        interval_end = req.interval_end or default_end_iso
        scenario_id = req.scenario_id or "SCN-001"
        station_ids = req.station_ids or ["STN-01", "STN-02", "STN-03", "STN-04", "STN-05"]

        headers = self._get_headers(correlation_id)

        timeout = httpx.Timeout(45.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # ─────────────────────────────────────────────────────────────────
            # Stage 1: Send forecast to EVCharge-Opt POST /api/v1/forecasts
            # ─────────────────────────────────────────────────────────────────
            fc_payload = {
                "scenario_id": scenario_id,
                "station_ids": station_ids,
                "forecast_start": forecast_start,
                "interval_minutes": 60,
                "horizon_intervals": 6,
            }
            try:
                fc_url = f"{self.base_url}/api/v1/forecasts"
                fc_res = await client.post(fc_url, json=fc_payload, headers=headers)
                if fc_res.status_code not in (200, 201):
                    duration_ms = (time.perf_counter() - t0) * 1000
                    return PartnerSyncResponse(
                        success=False,
                        partner_base_url=self.base_url,
                        stage_reached="forecast_dispatch_failed",
                        error=f"EVCharge-Opt POST /api/v1/forecasts returned HTTP {fc_res.status_code}: {fc_res.text[:200]}",
                        roundtrip_duration_ms=round(duration_ms, 2),
                        correlation_id=correlation_id,
                    )
                fc_data = fc_res.json()
                opt_forecast_id = fc_data.get("forecast_id") or "UNKNOWN"
            except httpx.RequestError as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                return PartnerSyncResponse(
                    success=False,
                    partner_base_url=self.base_url,
                    stage_reached="connection_failed",
                    error=f"Network error contacting EVCharge-Opt at {self.base_url}: {str(exc)}",
                    roundtrip_duration_ms=round(duration_ms, 2),
                    correlation_id=correlation_id,
                )

            # ─────────────────────────────────────────────────────────────────
            # Stage 2: Ensure scenario linkage on EVCharge-Opt POST /api/v1/scenarios
            # ─────────────────────────────────────────────────────────────────
            if scenario_id != "SCN-001":
                try:
                    scen_url = f"{self.base_url}/api/v1/scenarios"
                    scen_payload = {
                        "scenario_id": scenario_id,
                        "name": f"Predict Sync Run for {req.forecast_id}",
                        "selected_forecast_id": opt_forecast_id,
                        "planning_horizon_intervals": 6,
                        "provider_mode": "mock",
                    }
                    await client.post(scen_url, json=scen_payload, headers=headers)
                except Exception as e:
                    logger.warning("Optional scenario link returned: %s", e)

            # ─────────────────────────────────────────────────────────────────
            # Stage 3: Trigger optimization run POST /api/v1/allocations/run
            # ─────────────────────────────────────────────────────────────────
            alloc_payload = {
                "scenario_id": scenario_id,
                "forecast_id": opt_forecast_id,
                "interval_start": interval_start,
                "interval_end": interval_end,
                "operational_adjustment_id": None,
            }
            try:
                alloc_url = f"{self.base_url}/api/v1/allocations/run"
                alloc_res = await client.post(alloc_url, json=alloc_payload, headers=headers)
                if alloc_res.status_code not in (200, 201):
                    duration_ms = (time.perf_counter() - t0) * 1000
                    return PartnerSyncResponse(
                        success=False,
                        partner_base_url=self.base_url,
                        stage_reached="allocation_failed",
                        opt_forecast_id=opt_forecast_id,
                        opt_scenario_id=scenario_id,
                        error=f"EVCharge-Opt POST /api/v1/allocations/run returned HTTP {alloc_res.status_code}: {alloc_res.text[:200]}",
                        roundtrip_duration_ms=round(duration_ms, 2),
                        correlation_id=correlation_id,
                    )
                alloc_data = alloc_res.json()
                opt_allocation_id = alloc_data.get("allocation_id") or "UNKNOWN"
                alloc_status = alloc_data.get("status") or "completed"
            except httpx.RequestError as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                return PartnerSyncResponse(
                    success=False,
                    partner_base_url=self.base_url,
                    stage_reached="allocation_request_error",
                    opt_forecast_id=opt_forecast_id,
                    opt_scenario_id=scenario_id,
                    error=f"Network error during allocation on EVCharge-Opt: {str(exc)}",
                    roundtrip_duration_ms=round(duration_ms, 2),
                    correlation_id=correlation_id,
                )

            # Parse allocation results
            raw_results = alloc_data.get("results") or []
            allocation_results: List[StationAllocationSummary] = []
            total_power = 0.0
            total_served = 0.0
            total_unserved = 0.0
            wait_times: List[float] = []

            for r in raw_results:
                power = float(r.get("allocated_power_kw") or 0.0)
                served = float(r.get("estimated_served") or 0.0)
                unserved = float(r.get("estimated_unserved") or 0.0)
                wait = float(r.get("estimated_wait_minutes") or 0.0)
                total_power += power
                total_served += served
                total_unserved += unserved
                wait_times.append(wait)

                allocation_results.append(
                    StationAllocationSummary(
                        station_id=r.get("station_id") or "UNKNOWN",
                        station_name=r.get("station_name") or r.get("station_id") or "Station",
                        predicted_arrivals=float(r.get("predicted_arrivals") or 0.0),
                        predicted_energy_kwh=float(r.get("predicted_energy_kwh") or 0.0),
                        estimated_served=served,
                        estimated_unserved=unserved,
                        allocated_power_kw=round(power, 2),
                        estimated_wait_minutes=round(wait, 1),
                        charger_utilization_pct=float(r.get("charger_utilization_pct") or 0.0),
                        warnings=r.get("warnings") or [],
                    )
                )

            avg_wait = round(sum(wait_times) / len(wait_times), 1) if wait_times else 0.0

            # ─────────────────────────────────────────────────────────────────
            # Stage 4: Submit feedback POST /api/v1/allocations/{id}/feedback
            # ─────────────────────────────────────────────────────────────────
            opt_feedback_id = None
            feedback_status = None
            feedback_outcomes = []
            feedback_error = None

            try:
                fb_url = f"{self.base_url}/api/v1/allocations/{opt_allocation_id}/feedback"
                fb_payload = {
                    "deferred_fraction": req.deferred_fraction or 0.7,
                    "idempotency_key": f"sync_{opt_allocation_id}_{uuid4().hex[:6]}",
                }
                fb_res = await client.post(fb_url, json=fb_payload, headers=headers)
                if fb_res.status_code in (200, 201):
                    fb_data = fb_res.json()
                    opt_feedback_id = fb_data.get("feedback_id")
                    feedback_status = fb_data.get("submission_status") or "accepted"
                    feedback_outcomes = fb_data.get("station_outcomes") or []
                else:
                    feedback_error = f"Feedback HTTP {fb_res.status_code}: {fb_res.text[:150]}"
            except Exception as e:
                feedback_error = f"Feedback error: {str(e)}"

            duration_ms = (time.perf_counter() - t0) * 1000

            return PartnerSyncResponse(
                success=True,
                partner_service="EVCharge-Opt",
                partner_base_url=self.base_url,
                stage_reached="completed",
                opt_forecast_id=opt_forecast_id,
                opt_scenario_id=scenario_id,
                opt_allocation_id=opt_allocation_id,
                opt_feedback_id=opt_feedback_id,
                allocation_status=alloc_status,
                feedback_status=feedback_status or ("pending_submission" if feedback_error else "completed"),
                total_stations=len(allocation_results),
                total_allocated_power_kw=round(total_power, 2),
                total_served_vehicles=round(total_served, 1),
                total_unserved_vehicles=round(total_unserved, 1),
                average_wait_minutes=avg_wait,
                allocation_results=allocation_results,
                feedback_outcomes=feedback_outcomes,
                roundtrip_duration_ms=round(duration_ms, 2),
                error=feedback_error,
                correlation_id=correlation_id,
            )
