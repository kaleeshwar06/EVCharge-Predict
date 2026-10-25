"""Data extraction and quality validation module for model training."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.charging_session import ChargingSession
from app.models.station import Station
from app.services.station_mapping import StationMappingService


class DataQualityError(Exception):
    """Raised when dataset is missing, corrupted, or insufficient for training."""
    pass


@dataclass
class DataQualityReport:
    """Diagnostic report on loaded charging sessions."""
    source_type: str
    is_synthetic: bool
    total_records: int
    valid_records: int
    rejected_records: int
    station_count: int
    unique_stations: List[str]
    min_connection_time: Optional[datetime]
    max_connection_time: Optional[datetime]
    time_span_hours: float
    total_energy_kwh: float
    energy_measured_records: int
    energy_missing_records: int
    energy_coverage_ratio: float
    rejection_reasons: Dict[str, int] = field(default_factory=dict)

    def is_sufficient_for_training(self, min_hours: float = 72.0, min_records: int = 10) -> bool:
        """Determines if chronological time series has minimal baseline coverage."""
        return self.valid_records >= min_records and self.time_span_hours >= min_hours


class DataLoader:
    """Loads session records from database or JSON export with strict quality checks."""

    @staticmethod
    async def load_from_db(session: AsyncSession) -> Tuple[pd.DataFrame, DataQualityReport]:
        """Extract validated sessions joined with canonical Station IDs from PostgreSQL/SQLite."""
        query = (
            select(
                ChargingSession.id,
                ChargingSession.source_session_id,
                Station.station_id,
                ChargingSession.connection_time,
                ChargingSession.disconnect_time,
                ChargingSession.kwh_delivered,
                ChargingSession.source_dataset,
            )
            .join(Station, ChargingSession.station_id == Station.id)
            .order_by(ChargingSession.connection_time.asc())
        )
        result = await session.execute(query)
        rows = result.all()

        records = []
        rejected = 0
        reasons: Dict[str, int] = {}
        energy_measured = 0
        energy_missing = 0
        total_energy = Decimal("0.0")

        for row in rows:
            conn_time = row.connection_time
            if conn_time.tzinfo is None:
                conn_time = conn_time.replace(tzinfo=timezone.utc)
            else:
                conn_time = conn_time.astimezone(timezone.utc)

            kwh = row.kwh_delivered
            if kwh is not None:
                if kwh < 0:
                    rejected += 1
                    reasons["negative_kwh"] = reasons.get("negative_kwh", 0) + 1
                    continue
                energy_measured += 1
                total_energy += Decimal(str(kwh))
                kwh_float = float(kwh)
            else:
                energy_missing += 1
                kwh_float = None

            records.append({
                "session_id": row.id,
                "source_session_id": row.source_session_id,
                "station_id": row.station_id,
                "connection_time": conn_time,
                "disconnect_time": row.disconnect_time,
                "kwh_delivered": kwh_float,
                "source_dataset": row.source_dataset,
            })

        df = pd.DataFrame(records)
        is_synthetic = any("synthetic" in str(r.get("source_dataset", "")) for r in records) or len(records) < 100

        valid_count = len(df)
        total_count = valid_count + rejected
        unique_stations = sorted(df["station_id"].unique().tolist()) if not df.empty else []
        min_time = df["connection_time"].min() if not df.empty else None
        max_time = df["connection_time"].max() if not df.empty else None
        time_span = (max_time - min_time).total_seconds() / 3600.0 if (min_time and max_time) else 0.0
        coverage = (energy_measured / valid_count) if valid_count > 0 else 0.0

        report = DataQualityReport(
            source_type="database",
            is_synthetic=is_synthetic,
            total_records=total_count,
            valid_records=valid_count,
            rejected_records=rejected,
            station_count=len(unique_stations),
            unique_stations=unique_stations,
            min_connection_time=min_time,
            max_connection_time=max_time,
            time_span_hours=time_span,
            total_energy_kwh=float(total_energy),
            energy_measured_records=energy_measured,
            energy_missing_records=energy_missing,
            energy_coverage_ratio=coverage,
            rejection_reasons=reasons,
        )
        return df, report

    @staticmethod
    def load_from_processed_file(
        file_path: Path,
        mapping_service: Optional[StationMappingService] = None,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """Load session records from a validated ACN-Data JSON or CSV file."""
        if not file_path.exists():
            raise DataQualityError(f"Dataset file does not exist: {file_path}")

        mapping = mapping_service or StationMappingService()
        records = []
        rejected = 0
        reasons: Dict[str, int] = {}
        energy_measured = 0
        energy_missing = 0
        total_energy = Decimal("0.0")

        if file_path.suffix.lower() == ".json":
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
            except Exception as e:
                raise DataQualityError(f"Invalid JSON file: {e}")

            if not isinstance(data, dict) or "_items" not in data:
                raise DataQualityError("File is missing top-level '_items' array")
            raw_items = data["_items"]
            if not isinstance(raw_items, list):
                raise DataQualityError("'_items' must be a list of records")
        else:
            raise DataQualityError(f"Unsupported file format: {file_path.suffix}")

        for item in raw_items:
            if not isinstance(item, dict):
                rejected += 1
                reasons["record_not_dict"] = reasons.get("record_not_dict", 0) + 1
                continue

            src_st = item.get("stationID") or item.get("spaceID")
            if not src_st or not str(src_st).strip():
                rejected += 1
                reasons["missing_station_id"] = reasons.get("missing_station_id", 0) + 1
                continue

            canonical_st = mapping.get_or_create(str(src_st).strip())

            conn_raw = item.get("connectionTime")
            if not conn_raw:
                rejected += 1
                reasons["missing_connection_time"] = reasons.get("missing_connection_time", 0) + 1
                continue

            try:
                dt = pd.to_datetime(conn_raw, utc=True).to_pydatetime()
            except Exception:
                rejected += 1
                reasons["invalid_connection_time"] = reasons.get("invalid_connection_time", 0) + 1
                continue

            kwh_raw = item.get("kWhDelivered")
            kwh_val = None
            if kwh_raw is not None:
                try:
                    dec = Decimal(str(kwh_raw))
                    if dec < 0:
                        rejected += 1
                        reasons["negative_kwh"] = reasons.get("negative_kwh", 0) + 1
                        continue
                    kwh_val = float(dec)
                    energy_measured += 1
                    total_energy += dec
                except Exception:
                    rejected += 1
                    reasons["invalid_kwh"] = reasons.get("invalid_kwh", 0) + 1
                    continue
            else:
                energy_missing += 1

            records.append({
                "session_id": item.get("sessionID") or item.get("_id"),
                "station_id": canonical_st,
                "connection_time": dt,
                "kwh_delivered": kwh_val,
                "source_dataset": "acn-data",
            })

        df = pd.DataFrame(records)
        is_synthetic = "synthetic" in file_path.name.lower() or len(records) < 100
        valid_count = len(df)
        total_count = valid_count + rejected
        unique_stations = sorted(df["station_id"].unique().tolist()) if not df.empty else []
        min_time = df["connection_time"].min() if not df.empty else None
        max_time = df["connection_time"].max() if not df.empty else None
        time_span = (max_time - min_time).total_seconds() / 3600.0 if (min_time and max_time) else 0.0
        coverage = (energy_measured / valid_count) if valid_count > 0 else 0.0

        report = DataQualityReport(
            source_type=f"file:{file_path.name}",
            is_synthetic=is_synthetic,
            total_records=total_count,
            valid_records=valid_count,
            rejected_records=rejected,
            station_count=len(unique_stations),
            unique_stations=unique_stations,
            min_connection_time=min_time,
            max_connection_time=max_time,
            time_span_hours=time_span,
            total_energy_kwh=float(total_energy),
            energy_measured_records=energy_measured,
            energy_missing_records=energy_missing,
            energy_coverage_ratio=coverage,
            rejection_reasons=reasons,
        )
        return df, report
