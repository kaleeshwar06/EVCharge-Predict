"""Recursive 6-hour forecasting engine matching the shared integration contract."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.charging_session import ChargingSession
from app.models.forecast import Forecast, ForecastInterval
from app.models.station import Station
from app.schemas.forecast import (
    ForecastCreateRequest,
    ForecastCreateResponse,
    ForecastDetailRead,
    ForecastIntervalRead,
    HorizonMetadata,
    ModelProvenanceMetadata,
    StationForecastRead,
)
from app.services.model_loader import ModelArtifactError, ModelService


class ForecastingError(Exception):
    """Base error for forecasting failures."""
    pass


class InsufficientHistoryError(ForecastingError):
    """Raised when station history is inadequate to construct required lag features."""
    pass


class StationNotFoundError(ForecastingError):
    """Raised when a requested canonical station ID does not exist in the database."""
    pass


class ForecastingEngine:
    """Orchestrates historical data retrieval, recursive 6-hour prediction, and database persistence."""

    def __init__(self, db: AsyncSession, model_service: Optional[ModelService] = None) -> None:
        self.db = db
        self.model_service = model_service or ModelService.get_instance()

    async def generate_and_persist_forecast(
        self,
        request: ForecastCreateRequest,
    ) -> ForecastCreateResponse:
        """Executes full multi-station 6-interval recursive forecast workflow in a single transaction."""
        arr_model, ene_model, manifest = self.model_service.get_models()

        feature_names: List[str] = manifest["feature_names"]
        station_encoder: Dict[str, int] = manifest.get("station_encoder", {})
        forecast_start_utc = request.forecast_start.astimezone(timezone.utc)
        forecast_end_utc = forecast_start_utc + timedelta(hours=request.horizon_intervals)
        now_utc = datetime.now(timezone.utc)
        forecast_id = f"fcst_{uuid4().hex[:12]}"

        # 1. Resolve Stations
        requested_ids = request.station_ids
        st_query = await self.db.execute(select(Station).where(Station.station_id.in_(requested_ids)))
        stations = {s.station_id: s for s in st_query.scalars().all()}

        missing_stations = [sid for sid in requested_ids if sid not in stations]
        if missing_stations:
            raise StationNotFoundError(f"Requested stations do not exist in database: {missing_stations}")

        # 2. Generate Predictions for Each Station Recursively
        station_predictions: Dict[int, List[Tuple[datetime, datetime, int, float]]] = {}

        for st_id in requested_ids:
            station_obj = stations[st_id]
            st_code = station_encoder.get(st_id, -1)

            # Retrieve past sessions strictly prior to forecast_start
            history_start_utc = forecast_start_utc - timedelta(days=21)
            sess_query = await self.db.execute(
                select(ChargingSession.connection_time, ChargingSession.kwh_delivered)
                .where(ChargingSession.station_id == station_obj.id)
                .where(ChargingSession.connection_time >= history_start_utc)
                .where(ChargingSession.connection_time < forecast_start_utc)
                .order_by(ChargingSession.connection_time.asc())
            )
            raw_sessions = sess_query.all()

            # Reject if station has zero or negligible actual observed historical sessions
            if len(raw_sessions) < 5:
                raise InsufficientHistoryError(
                    f"Station '{st_id}' has insufficient historical session observations ({len(raw_sessions)} found, minimum 5 required)."
                )

            # Build in-memory station hourly history
            station_history = self._build_station_hourly_history(
                raw_sessions=raw_sessions,
                history_start=history_start_utc,
                forecast_start=forecast_start_utc,
            )

            # Run 6-step recursive forecast
            intervals = self._recursive_forecast_station(
                station_history=station_history,
                station_code=st_code,
                forecast_start=forecast_start_utc,
                horizon_intervals=request.horizon_intervals,
                arr_model=arr_model,
                ene_model=ene_model,
                feature_names=feature_names,
            )
            station_predictions[station_obj.id] = intervals

        # 3. Persist Forecast and All Intervals in Database Transaction
        forecast_record = Forecast(
            forecast_id=forecast_id,
            scenario_id=request.scenario_id,
            generated_at=now_utc,
            forecast_start=forecast_start_utc,
            forecast_end=forecast_end_utc,
            interval_minutes=request.interval_minutes,
            horizon_intervals=request.horizon_intervals,
            status="completed",
            demand_type="baseline",
            model_version=manifest.get("model_version", "1.0"),
            training_data_type="synthetic" if manifest.get("is_synthetic", True) else "real",
            training_data_fingerprint=manifest.get("data_source"),
        )
        self.db.add(forecast_record)
        await self.db.flush()

        for st_obj_id, intervals in station_predictions.items():
            for int_start, int_end, arr, ene in intervals:
                interval_record = ForecastInterval(
                    forecast_id=forecast_record.id,
                    station_id=st_obj_id,
                    interval_start=int_start,
                    interval_end=int_end,
                    predicted_arrivals=arr,
                    predicted_energy_kwh=Decimal(f"{ene:.3f}"),
                )
                self.db.add(interval_record)

        await self.db.commit()

        return ForecastCreateResponse(
            contract_version="1.0",
            forecast_id=forecast_id,
            scenario_id=request.scenario_id,
            status="completed",
            demand_type="baseline",
            generated_at=now_utc,
            interval_minutes=request.interval_minutes,
            horizon_intervals=request.horizon_intervals,
            forecast_url=f"/api/v1/forecasts/{forecast_id}",
        )

    @staticmethod
    def _build_station_hourly_history(
        raw_sessions: List[Tuple[datetime, Optional[Decimal]]],
        history_start: datetime,
        forecast_start: datetime,
    ) -> pd.DataFrame:
        """Converts raw session tuples into continuous hourly series [history_start, forecast_start)."""
        idx = pd.date_range(start=history_start, end=forecast_start, freq="1h", inclusive="left", tz=timezone.utc, name="interval_start")
        base_df = pd.DataFrame(index=idx, data={"arrivals": 0, "session_start_energy_kwh": 0.0})

        if not raw_sessions:
            return base_df.reset_index()

        records = []
        for conn_time, kwh in raw_sessions:
            if conn_time.tzinfo is None:
                conn_time = conn_time.replace(tzinfo=timezone.utc)
            else:
                conn_time = conn_time.astimezone(timezone.utc)
            kwh_val = float(kwh) if kwh is not None and kwh >= 0 else 0.0
            records.append({
                "interval_start": conn_time.replace(minute=0, second=0, microsecond=0),
                "arrivals": 1,
                "session_start_energy_kwh": kwh_val,
            })

        sess_df = pd.DataFrame(records)
        agg_df = sess_df.groupby("interval_start").agg({
            "arrivals": "sum",
            "session_start_energy_kwh": "sum",
        })

        merged = base_df.combine_first(agg_df).reset_index()
        merged["arrivals"] = merged["arrivals"].fillna(0).astype(int)
        merged["session_start_energy_kwh"] = merged["session_start_energy_kwh"].fillna(0.0).astype(float)
        return merged.sort_values(by="interval_start").reset_index(drop=True)

    @staticmethod
    def _recursive_forecast_station(
        station_history: pd.DataFrame,
        station_code: int,
        forecast_start: datetime,
        horizon_intervals: int,
        arr_model: Any,
        ene_model: Any,
        feature_names: List[str],
    ) -> List[Tuple[datetime, datetime, int, float]]:
        """Performs sequential 6-step recursive autoregressive prediction."""
        working_history = station_history.copy()
        output_intervals: List[Tuple[datetime, datetime, int, float]] = []

        lag_steps = [1, 2, 3, 6, 12, 24, 48, 168]
        rolling_windows = [6, 24, 168]

        for step in range(horizon_intervals):
            current_target_time = forecast_start + timedelta(hours=step)
            next_target_time = current_target_time + timedelta(hours=1)

            # Build single-row feature dict
            hr = current_target_time.hour
            dow = current_target_time.weekday()
            is_wknd = 1 if dow >= 5 else 0

            row_feats: Dict[str, float] = {
                "hour": float(hr),
                "dayofweek": float(dow),
                "is_weekend": float(is_wknd),
                "sin_hour": float(np.sin(2 * np.pi * hr / 24.0)),
                "cos_hour": float(np.cos(2 * np.pi * hr / 24.0)),
                "sin_dayofweek": float(np.sin(2 * np.pi * dow / 7.0)),
                "cos_dayofweek": float(np.cos(2 * np.pi * dow / 7.0)),
                "station_code": float(station_code),
            }

            # Lags strictly prior to current_target_time
            n_hist = len(working_history)
            for lag in lag_steps:
                target_idx = n_hist - lag
                if target_idx >= 0:
                    arr_val = float(working_history.iloc[target_idx]["arrivals"])
                    ene_val = float(working_history.iloc[target_idx]["session_start_energy_kwh"])
                else:
                    arr_val = float(working_history.iloc[0]["arrivals"])
                    ene_val = float(working_history.iloc[0]["session_start_energy_kwh"])
                row_feats[f"lag_arrivals_{lag}h"] = arr_val
                row_feats[f"lag_energy_{lag}h"] = ene_val

            # Rolling averages strictly prior to current_target_time
            for window in rolling_windows:
                sub_slice = working_history.iloc[max(0, n_hist - window):n_hist]
                row_feats[f"rolling_arrivals_{window}h_mean"] = float(sub_slice["arrivals"].mean()) if not sub_slice.empty else 0.0
                row_feats[f"rolling_energy_{window}h_mean"] = float(sub_slice["session_start_energy_kwh"].mean()) if not sub_slice.empty else 0.0

            # Convert to DataFrame with strict feature order
            feature_row = pd.DataFrame([[row_feats[feat] for feat in feature_names]], columns=feature_names)

            # Predict
            raw_arr = arr_model.predict(feature_row)[0]
            raw_ene = ene_model.predict(feature_row)[0]

            # Output Policy:
            pred_arr = int(np.round(max(0.0, float(raw_arr))))
            pred_ene = round(max(0.0, float(raw_ene)), 3)

            output_intervals.append((current_target_time, next_target_time, pred_arr, pred_ene))

            # Recursive step: Append newly predicted interval to working_history
            new_hist_row = pd.DataFrame([{
                "interval_start": current_target_time,
                "arrivals": pred_arr,
                "session_start_energy_kwh": pred_ene,
            }])
            working_history = pd.concat([working_history, new_hist_row], ignore_index=True)

        return output_intervals

    @staticmethod
    async def get_forecast_by_id(db: AsyncSession, forecast_id: str) -> Optional[ForecastDetailRead]:
        """Loads and formats a complete stored forecast."""
        query = (
            select(Forecast)
            .where(Forecast.forecast_id == forecast_id)
        )
        res = await db.execute(query)
        forecast_obj = res.scalar_one_or_none()
        if not forecast_obj:
            return None

        # Fetch intervals joined with station
        int_query = (
            select(ForecastInterval, Station.station_id)
            .join(Station, ForecastInterval.station_id == Station.id)
            .where(ForecastInterval.forecast_id == forecast_obj.id)
            .order_by(Station.station_id, ForecastInterval.interval_start)
        )
        int_res = await db.execute(int_query)
        rows = int_res.all()

        stations_map: Dict[str, List[ForecastIntervalRead]] = {}
        for interval, st_canonical_id in rows:
            if st_canonical_id not in stations_map:
                stations_map[st_canonical_id] = []

            # Ensure UTC timezone awareness on retrieved datetime
            start_dt = interval.interval_start
            end_dt = interval.interval_end
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            stations_map[st_canonical_id].append(
                ForecastIntervalRead(
                    interval_start=start_dt,
                    interval_end=end_dt,
                    predicted_arrivals=interval.predicted_arrivals,
                    predicted_energy_kwh=float(interval.predicted_energy_kwh),
                )
            )

        station_forecasts = [
            StationForecastRead(station_id=st_id, intervals=ints)
            for st_id, ints in sorted(stations_map.items())
        ]

        f_start = forecast_obj.forecast_start
        f_end = forecast_obj.forecast_end
        f_gen = forecast_obj.generated_at
        if f_start.tzinfo is None:
            f_start = f_start.replace(tzinfo=timezone.utc)
        if f_end.tzinfo is None:
            f_end = f_end.replace(tzinfo=timezone.utc)
        if f_gen.tzinfo is None:
            f_gen = f_gen.replace(tzinfo=timezone.utc)

        return ForecastDetailRead(
            contract_version="1.0",
            forecast_id=forecast_obj.forecast_id,
            scenario_id=forecast_obj.scenario_id,
            generated_at=f_gen,
            horizon=HorizonMetadata(
                start=f_start,
                end=f_end,
                interval_minutes=forecast_obj.interval_minutes,
                interval_count=forecast_obj.horizon_intervals,
            ),
            demand_type=forecast_obj.demand_type,
            stations=station_forecasts,
            model=ModelProvenanceMetadata(
                model_version=forecast_obj.model_version,
                training_data_type=forecast_obj.training_data_type,
                training_data_fingerprint=forecast_obj.training_data_fingerprint,
            ),
        )

    @staticmethod
    async def get_latest_baseline_forecast(db: AsyncSession, scenario_id: str) -> Optional[ForecastDetailRead]:
        """Finds the latest completed baseline forecast for scenario_id."""
        query = (
            select(Forecast.forecast_id)
            .where(Forecast.scenario_id == scenario_id)
            .where(Forecast.status == "completed")
            .where(Forecast.demand_type == "baseline")
            .order_by(Forecast.generated_at.desc(), Forecast.id.desc())
            .limit(1)
        )
        res = await db.execute(query)
        latest_fcst_id = res.scalar_one_or_none()
        if not latest_fcst_id:
            return None
        return await ForecastingEngine.get_forecast_by_id(db, latest_fcst_id)
