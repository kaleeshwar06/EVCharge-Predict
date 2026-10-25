"""Service implementing feedback ingestion, validation, idempotency, and policy-driven operational demand adjustment."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.feedback import AdjustedDemandInterval, AllocationFeedback
from app.models.forecast import Forecast, ForecastInterval
from app.models.station import Station
from app.schemas.feedback import (
    AdjustedDemandIntervalRead,
    AdjustedDemandResponse,
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    FeedbackDetailRead,
    StationAdjustedDemandRead,
)

POLICY_VERSION = "v1-heuristic-operational-envelope"
POLICY_DESCRIPTION = (
    "Operational demand envelope taking max(baseline_predicted_energy_kwh, allocated_energy_kwh). "
    "Arrivals strictly preserved from baseline without fabrication."
)
POLICY_LIMITATIONS = (
    "Allocated energy reflects optimizer decisions under physical and grid constraints, not unconstrained physical demand. "
    "This envelope does not represent verified ground-truth physical driver demand."
)


class FeedbackError(Exception):
    """Base exception for feedback service."""
    pass


class ForecastNotFoundError(FeedbackError):
    """Originating forecast does not exist."""
    pass


class ScenarioMismatchError(FeedbackError):
    """Originating scenario ID does not match forecast scenario ID."""
    pass


class FeedbackStationError(FeedbackError):
    """Station ID not found or not part of originating forecast."""
    pass


class FeedbackIntervalAlignmentError(FeedbackError):
    """Feedback intervals do not match originating forecast intervals."""
    pass


class FeedbackConflictError(FeedbackError):
    """Same allocation_run_id submitted with conflicting payload."""
    pass


def compute_payload_hash(request: FeedbackCreateRequest) -> str:
    """Computes a deterministic SHA-256 hash of the normalized request payload."""
    raw_dict = request.model_dump(mode="json")
    canonical_json = json.dumps(raw_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class FeedbackService:
    """Handles feedback processing, idempotency, storage, and derived demand calculation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def submit_feedback(self, request: FeedbackCreateRequest) -> Tuple[FeedbackCreateResponse, int]:
        """Validates and persists allocation feedback atomically with derived adjusted demand.

        Returns:
            Tuple of (FeedbackCreateResponse, status_code) where status_code is 201 or 200.
        """
        payload_hash = compute_payload_hash(request)

        # 1. Check for existing allocation_run_id (Idempotency check)
        existing_q = await self.db.execute(
            select(AllocationFeedback).where(AllocationFeedback.allocation_run_id == request.allocation_run_id)
        )
        existing_fbk = existing_q.scalar_one_or_none()

        if existing_fbk:
            if existing_fbk.payload_hash == payload_hash:
                # Idempotent retry: return existing record
                resp = FeedbackCreateResponse(
                    contract_version=existing_fbk.contract_version,
                    feedback_id=existing_fbk.feedback_id,
                    allocation_run_id=existing_fbk.allocation_run_id,
                    forecast_id=request.forecast_id,
                    scenario_id=existing_fbk.scenario_id,
                    status=existing_fbk.status,
                    is_duplicate=True,
                    received_at=existing_fbk.received_at,
                    feedback_url=f"/api/v1/feedback/{existing_fbk.feedback_id}",
                )
                return resp, 200
            else:
                # Same allocation_run_id but payload differs: 409 Conflict
                raise FeedbackConflictError(
                    f"Allocation run '{request.allocation_run_id}' was already submitted with different content. "
                    "Reusing the same run identifier with modified data is prohibited."
                )

        # 2. Validate Originating Forecast
        fcst_q = await self.db.execute(
            select(Forecast)
            .where(Forecast.forecast_id == request.forecast_id)
            .options(selectinload(Forecast.intervals))
        )
        forecast = fcst_q.scalar_one_or_none()
        if not forecast:
            raise ForecastNotFoundError(f"Originating forecast '{request.forecast_id}' does not exist.")

        if forecast.scenario_id != request.scenario_id:
            raise ScenarioMismatchError(
                f"Submitted scenario_id '{request.scenario_id}' does not match forecast scenario '{forecast.scenario_id}'."
            )

        # 3. Resolve Stations
        submitted_station_ids = [s.station_id for s in request.stations]
        st_q = await self.db.execute(select(Station).where(Station.station_id.in_(submitted_station_ids)))
        stations_map = {s.station_id: s for s in st_q.scalars().all()}

        missing_stations = [sid for sid in submitted_station_ids if sid not in stations_map]
        if missing_stations:
            raise FeedbackStationError(f"Stations not found in system: {missing_stations}")

        # Index baseline forecast intervals by (station_id_pk, interval_start_utc)
        baseline_intervals: Dict[Tuple[int, datetime], ForecastInterval] = {}
        for fi in forecast.intervals:
            start_utc = fi.interval_start if fi.interval_start.tzinfo else fi.interval_start.replace(tzinfo=timezone.utc)
            baseline_intervals[(fi.station_id, start_utc)] = fi

        # 4. Validate intervals align with forecast
        for st_input in request.stations:
            st_pk = stations_map[st_input.station_id].id
            for int_in in st_input.intervals:
                key = (st_pk, int_in.interval_start)
                if key not in baseline_intervals:
                    raise FeedbackIntervalAlignmentError(
                        f"Station '{st_input.station_id}' interval starting {int_in.interval_start.isoformat()} "
                        f"does not correspond to any baseline interval in forecast '{request.forecast_id}'."
                    )

        # 5. Atomic Persistence of Feedback + Derived Adjusted Demand
        now_utc = datetime.now(timezone.utc)
        feedback_id = f"fbk_{uuid4().hex[:12]}"

        feedback_record = AllocationFeedback(
            feedback_id=feedback_id,
            allocation_run_id=request.allocation_run_id,
            forecast_id=forecast.id,  # Integer FK to forecasts.id
            scenario_id=request.scenario_id,
            contract_version=request.contract_version,
            submitted_at=request.submitted_at,
            received_at=now_utc,
            status="accepted",
            optimizer_version=request.optimizer_version,
            payload_hash=payload_hash,
            raw_payload=json.dumps(request.model_dump(mode="json")),
        )
        self.db.add(feedback_record)
        await self.db.flush()  # Generates feedback_record.id

        # Derive adjusted demand per station and interval using Policy v1
        for st_input in request.stations:
            st_pk = stations_map[st_input.station_id].id
            for int_in in st_input.intervals:
                fi = baseline_intervals[(st_pk, int_in.interval_start)]
                base_arr = fi.predicted_arrivals
                base_kwh = float(fi.predicted_energy_kwh)

                # Policy v1: Heuristic Operational Envelope
                alloc_kwh = int_in.allocated_energy_kwh
                avail_kw = int_in.available_capacity_kw
                unmet_kwh = int_in.reported_unmet_demand_kwh

                if alloc_kwh is not None and alloc_kwh >= 0:
                    adj_kwh = round(max(base_kwh, alloc_kwh), 3)
                    status = "adjusted" if alloc_kwh > base_kwh else "unchanged"
                else:
                    adj_kwh = base_kwh
                    status = "insufficient_data"

                adj_record = AdjustedDemandInterval(
                    feedback_id=feedback_record.id,
                    forecast_interval_id=fi.id,
                    station_id=st_pk,
                    interval_start=int_in.interval_start,
                    interval_end=int_in.interval_end,
                    baseline_arrivals=base_arr,
                    baseline_energy_kwh=Decimal(f"{base_kwh:.3f}"),
                    allocated_energy_kwh=Decimal(f"{alloc_kwh:.3f}") if alloc_kwh is not None else None,
                    available_capacity_kw=Decimal(f"{avail_kw:.3f}") if avail_kw is not None else None,
                    reported_unmet_demand_kwh=Decimal(f"{unmet_kwh:.3f}") if unmet_kwh is not None else None,
                    adjusted_operational_demand_kwh=Decimal(f"{adj_kwh:.3f}"),
                    adjustment_status=status,
                    adjustment_policy_version=POLICY_VERSION,
                    computed_at=now_utc,
                )
                self.db.add(adj_record)

        await self.db.commit()

        resp = FeedbackCreateResponse(
            contract_version="1.0",
            feedback_id=feedback_id,
            allocation_run_id=request.allocation_run_id,
            forecast_id=request.forecast_id,
            scenario_id=request.scenario_id,
            status="accepted",
            is_duplicate=False,
            received_at=now_utc,
            feedback_url=f"/api/v1/feedback/{feedback_id}",
        )
        return resp, 201

    async def get_feedback_by_id(self, feedback_id: str) -> Optional[FeedbackDetailRead]:
        """Loads a stored feedback record by its feedback_id."""
        q = (
            select(AllocationFeedback, Forecast.forecast_id)
            .join(Forecast, AllocationFeedback.forecast_id == Forecast.id)
            .where(AllocationFeedback.feedback_id == feedback_id)
        )
        res = await self.db.execute(q)
        row = res.first()
        if not row:
            return None

        fbk, ext_fcst_id = row
        sub_at = fbk.submitted_at if fbk.submitted_at.tzinfo else fbk.submitted_at.replace(tzinfo=timezone.utc)
        rec_at = fbk.received_at if fbk.received_at.tzinfo else fbk.received_at.replace(tzinfo=timezone.utc)

        return FeedbackDetailRead(
            contract_version=fbk.contract_version,
            feedback_id=fbk.feedback_id,
            allocation_run_id=fbk.allocation_run_id,
            forecast_id=ext_fcst_id,
            scenario_id=fbk.scenario_id,
            status=fbk.status,
            optimizer_version=fbk.optimizer_version,
            submitted_at=sub_at,
            received_at=rec_at,
        )

    async def list_feedback(
        self,
        forecast_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> List[FeedbackDetailRead]:
        """Lists feedback records filtered by forecast_id and/or scenario_id."""
        q = (
            select(AllocationFeedback, Forecast.forecast_id)
            .join(Forecast, AllocationFeedback.forecast_id == Forecast.id)
            .order_by(AllocationFeedback.received_at.desc())
        )
        if forecast_id:
            q = q.where(Forecast.forecast_id == forecast_id)
        if scenario_id:
            q = q.where(AllocationFeedback.scenario_id == scenario_id)

        res = await self.db.execute(q)
        rows = res.all()

        results = []
        for fbk, ext_fcst_id in rows:
            sub_at = fbk.submitted_at if fbk.submitted_at.tzinfo else fbk.submitted_at.replace(tzinfo=timezone.utc)
            rec_at = fbk.received_at if fbk.received_at.tzinfo else fbk.received_at.replace(tzinfo=timezone.utc)
            results.append(
                FeedbackDetailRead(
                    contract_version=fbk.contract_version,
                    feedback_id=fbk.feedback_id,
                    allocation_run_id=fbk.allocation_run_id,
                    forecast_id=ext_fcst_id,
                    scenario_id=fbk.scenario_id,
                    status=fbk.status,
                    optimizer_version=fbk.optimizer_version,
                    submitted_at=sub_at,
                    received_at=rec_at,
                )
            )
        return results

    async def get_adjusted_demand(
        self,
        forecast_id: str,
        feedback_id: str,
    ) -> Optional[AdjustedDemandResponse]:
        """Retrieves derived adjusted demand for a specific forecast and feedback submission."""
        # Find feedback and check forecast association
        q_fbk = (
            select(AllocationFeedback, Forecast.forecast_id)
            .join(Forecast, AllocationFeedback.forecast_id == Forecast.id)
            .where(AllocationFeedback.feedback_id == feedback_id)
            .where(Forecast.forecast_id == forecast_id)
        )
        res_fbk = await self.db.execute(q_fbk)
        row_fbk = res_fbk.first()
        if not row_fbk:
            return None

        fbk, ext_fcst_id = row_fbk

        # Fetch adjusted intervals with joined station
        q_ints = (
            select(AdjustedDemandInterval, Station.station_id)
            .join(Station, AdjustedDemandInterval.station_id == Station.id)
            .where(AdjustedDemandInterval.feedback_id == fbk.id)
            .order_by(Station.station_id, AdjustedDemandInterval.interval_start)
        )
        res_ints = await self.db.execute(q_ints)
        rows = res_ints.all()

        if not rows:
            return None

        stations_map: Dict[str, List[AdjustedDemandIntervalRead]] = {}
        computed_at_ref = rows[0][0].computed_at

        for interval, st_canonical_id in rows:
            if st_canonical_id not in stations_map:
                stations_map[st_canonical_id] = []

            s_dt = interval.interval_start if interval.interval_start.tzinfo else interval.interval_start.replace(tzinfo=timezone.utc)
            e_dt = interval.interval_end if interval.interval_end.tzinfo else interval.interval_end.replace(tzinfo=timezone.utc)

            stations_map[st_canonical_id].append(
                AdjustedDemandIntervalRead(
                    interval_start=s_dt,
                    interval_end=e_dt,
                    baseline_arrivals=interval.baseline_arrivals,
                    baseline_energy_kwh=float(interval.baseline_energy_kwh),
                    allocated_energy_kwh=float(interval.allocated_energy_kwh) if interval.allocated_energy_kwh is not None else None,
                    available_capacity_kw=float(interval.available_capacity_kw) if interval.available_capacity_kw is not None else None,
                    reported_unmet_demand_kwh=float(interval.reported_unmet_demand_kwh) if interval.reported_unmet_demand_kwh is not None else None,
                    adjusted_operational_demand_kwh=float(interval.adjusted_operational_demand_kwh),
                    adjustment_status=interval.adjustment_status,
                )
            )

        comp_dt = computed_at_ref if computed_at_ref.tzinfo else computed_at_ref.replace(tzinfo=timezone.utc)

        return AdjustedDemandResponse(
            contract_version="1.0",
            forecast_id=ext_fcst_id,
            scenario_id=fbk.scenario_id,
            feedback_id=fbk.feedback_id,
            allocation_run_id=fbk.allocation_run_id,
            demand_type="feedback-adjusted-operational",
            adjustment_policy_version=POLICY_VERSION,
            policy_description=POLICY_DESCRIPTION,
            policy_limitations=POLICY_LIMITATIONS,
            computed_at=comp_dt,
            stations=[
                StationAdjustedDemandRead(station_id=st_id, intervals=ints)
                for st_id, ints in sorted(stations_map.items())
            ],
        )
