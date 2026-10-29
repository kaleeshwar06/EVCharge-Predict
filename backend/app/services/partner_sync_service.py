"""Service executing authenticated outbound requests to EVCharge-Opt."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import PROJECT_ROOT, get_settings
from app.schemas.partner_sync import (
    PartnerSyncRequest,
    PartnerSyncResponse,
    StationAllocationSummary,
)

logger = logging.getLogger(__name__)


class PartnerSyncService:
    """Coordinates synchronization and retrieval of feedback records with EVCharge-Opt."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.evcharge_opt_base_url).rstrip("/")
        self.token = token or settings.opt_service_token
        self.storage_path = PROJECT_ROOT / "data" / "processed" / "partner_feedbacks.json"

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

    def _load_stored_feedbacks(self) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("Failed to load partner_feedbacks.json: %s", e)
            return []

    def _save_stored_feedbacks(self, feedbacks: List[Dict[str, Any]]) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(feedbacks, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save partner_feedbacks.json: %s", e)

    def _normalize_partner_feedback(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        alloc_id = raw.get("allocation_id") or raw.get("allocation_run_id") or "UNKNOWN"
        created = raw.get("created_at") or raw.get("submitted_at") or datetime.now(timezone.utc).isoformat()
        updated = raw.get("updated_at") or raw.get("received_at") or created
        return {
            "contract_version": raw.get("contract_version", "1.0"),
            "feedback_id": raw.get("feedback_id", f"FBD-{uuid4().hex[:8].upper()}"),
            "allocation_run_id": alloc_id,
            "forecast_id": raw.get("forecast_id", "FC-MOCK-19B71C"),
            "scenario_id": raw.get("scenario_id", "scenario_sim_001"),
            "status": raw.get("submission_status") or raw.get("status") or "submitted",
            "optimizer_version": raw.get("optimizer_version") or "v1.0-priority-heuristic (EVCharge-Opt)",
            "submitted_at": created,
            "received_at": updated,
            "deferred_fraction": float(raw.get("deferred_fraction")) if raw.get("deferred_fraction") is not None else 0.7,
            "idempotency_key": raw.get("idempotency_key"),
            "operational_adjustment_id": raw.get("operational_adjustment_id"),
            "origin": "partner",
            "station_outcomes": raw.get("station_outcomes") or [],
        }

    async def save_partner_feedback(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Saves a partner feedback record with idempotency deduplication."""
        item = self._normalize_partner_feedback(raw)
        feedbacks = self._load_stored_feedbacks()

        for existing in feedbacks:
            if existing.get("feedback_id") == item["feedback_id"] or (
                item.get("idempotency_key") and existing.get("idempotency_key") == item["idempotency_key"]
            ):
                return {
                    "status": "accepted",
                    "is_duplicate": True,
                    "feedback_id": existing["feedback_id"],
                    "allocation_run_id": existing.get("allocation_run_id"),
                    "idempotency_key": existing.get("idempotency_key"),
                }

        feedbacks.insert(0, item)
        self._save_stored_feedbacks(feedbacks)
        return {
            "status": "accepted",
            "is_duplicate": False,
            "feedback_id": item["feedback_id"],
            "allocation_run_id": item.get("allocation_run_id"),
            "idempotency_key": item.get("idempotency_key"),
        }

    async def get_partner_feedbacks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves feedback records from EVCharge-Opt's verified GET /api/v1/feedback endpoint,
        merges with locally stored records, and returns them deduplicated by feedback_id/idempotency_key."""
        stored = self._load_stored_feedbacks()
        seen_feedback_ids = {f.get("feedback_id") for f in stored if f.get("feedback_id")}
        seen_idemp_keys = {f.get("idempotency_key") for f in stored if f.get("idempotency_key")}

        headers = self._get_headers(f"list_fbk_{uuid4().hex[:8]}")
        url = f"{self.base_url}/api/v1/feedback?limit={limit}"

        fetched_items: List[Dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    raw_list = res.json()
                    if isinstance(raw_list, list):
                        for raw in raw_list:
                            norm = self._normalize_partner_feedback(raw)
                            fetched_items.append(norm)
                            fid = norm.get("feedback_id")
                            ikey = norm.get("idempotency_key")
                            if fid and fid not in seen_feedback_ids and (not ikey or ikey not in seen_idemp_keys):
                                stored.append(norm)
                                seen_feedback_ids.add(fid)
                                if ikey:
                                    seen_idemp_keys.add(ikey)
                        self._save_stored_feedbacks(stored)
        except Exception as e:
            logger.warning("Could not reach EVCharge-Opt GET /api/v1/feedback: %s", e)

        combined = []
        seen = set()
        for item in fetched_items + stored:
            fid = item.get("feedback_id")
            if fid and fid not in seen:
                seen.add(fid)
                combined.append(item)
            elif not fid and item not in combined:
                combined.append(item)

        return combined[:limit]

    async def get_partner_feedback_by_id(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single feedback record by ID from EVCharge-Opt or local partner storage."""
        # Check local storage first
        stored = self._load_stored_feedbacks()
        for item in stored:
            if item.get("feedback_id") == feedback_id:
                return item

        # Query EVCharge-Opt API
        headers = self._get_headers(f"fbk_detail_{uuid4().hex[:8]}")
        url = f"{self.base_url}/api/v1/feedback/{feedback_id}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    norm = self._normalize_partner_feedback(res.json())
                    # Cache in local storage
                    stored.insert(0, norm)
                    self._save_stored_feedbacks(stored)
                    return norm
        except Exception as e:
            logger.warning("Error fetching partner feedback by ID %s: %s", feedback_id, e)

        return None

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
                    # Also persist in local partner feedback cache
                    await self.save_partner_feedback(fb_data)
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
