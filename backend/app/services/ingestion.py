"""Pipeline for ingesting ACN-Data charging session exports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.charging_session import ChargingSession
from app.models.dataset_import import DatasetImport
from app.models.station import Station
from app.services.station_mapping import StationMappingService


class IngestionError(Exception):
    """Custom exception raised for unrecoverable dataset ingestion errors."""
    pass


@dataclass
class IngestionReport:
    import_id: str
    source_filename: str
    source_dataset: str
    status: str
    total_records_read: int = 0
    records_inserted: int = 0
    records_skipped: int = 0
    records_rejected: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False


class IngestionPipeline:
    """Validates, parses, normalizes, and commits ACN-Data charging records."""

    def __init__(
        self,
        session: AsyncSession,
        mapping_service: Optional[StationMappingService] = None,
    ) -> None:
        self.db = session
        self.mapping_service = mapping_service or StationMappingService()

    @staticmethod
    def compute_checksum(file_path: Path) -> str:
        """Compute SHA256 checksum of a file to detect duplicate runs."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def parse_iso_or_rfc(ts_str: Any) -> Optional[datetime]:
        """Parse various date formats found in ACN-Data into UTC timezone-aware datetimes."""
        if not ts_str or not isinstance(ts_str, str):
            return None
        clean_str = ts_str.strip()
        if not clean_str:
            return None
        try:
            dt = date_parser.parse(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, TypeError, OverflowError):
            return None

    def read_dataset_file(self, file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Read and validate the JSON structure, extracting items under _items."""
        if not file_path.exists():
            raise IngestionError(f"Dataset file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except json.JSONDecodeError as err:
            raise IngestionError(f"Malformed or truncated JSON file: {err}")
        except Exception as err:
            raise IngestionError(f"Failed to read file: {err}")

        if not isinstance(data, dict):
            raise IngestionError("Invalid JSON structure: top-level element must be a JSON object")

        if "_items" not in data:
            raise IngestionError("Invalid ACN-Data format: missing '_items' list key")

        items = data["_items"]
        if not isinstance(items, list):
            raise IngestionError("Invalid ACN-Data format: '_items' must be a list")

        meta = data.get("_meta", {})
        return items, meta if isinstance(meta, dict) else {}

    async def ingest_file(
        self,
        file_path: Path,
        source_dataset: str = "acn-data",
        dry_run: bool = False,
    ) -> IngestionReport:
        """Execute full ingestion workflow with audit tracking and database transactions."""
        import_id = f"imp-{uuid4().hex[:12]}"
        checksum = self.compute_checksum(file_path) if file_path.exists() else None

        report = IngestionReport(
            import_id=import_id,
            source_filename=file_path.name,
            source_dataset=source_dataset,
            status="dry_run" if dry_run else "in_progress",
            dry_run=dry_run,
        )

        # Parse JSON
        try:
            items, meta = self.read_dataset_file(file_path)
        except IngestionError as err:
            report.status = "failed"
            report.errors.append(str(err))
            if not dry_run:
                db_import = DatasetImport(
                    import_id=import_id,
                    source_dataset=source_dataset,
                    source_filename=file_path.name,
                    file_checksum=checksum,
                    status="failed",
                    total_records_read=0,
                    error_summary=str(err),
                )
                self.db.add(db_import)
                await self.db.commit()
            return report

        report.total_records_read = len(items)

        # Cache existing stations from database
        stations_query = await self.db.execute(select(Station))
        stations_by_source: Dict[str, Station] = {
            s.source_station_id: s for s in stations_query.scalars().all()
        }

        # Cache existing session identifiers to prevent duplicates
        # 1. By source_session_id
        session_ids_query = await self.db.execute(
            select(ChargingSession.source_session_id).where(ChargingSession.source_session_id.is_not(None))
        )
        existing_session_ids = set(session_ids_query.scalars().all())

        # 2. Composite key for fallback deduplication: (canonical_station_id, UTC iso timestamp)
        # Handles dialect-independent comparison across PostgreSQL and SQLite
        existing_composite_keys: Set[Tuple[str, str]] = set()
        existing_composites_query = await self.db.execute(
            select(Station.station_id, ChargingSession.connection_time)
            .join(Station, ChargingSession.station_id == Station.id)
        )
        for st_canonical_id, conn_t in existing_composites_query.all():
            if conn_t.tzinfo is None:
                conn_t = conn_t.replace(tzinfo=timezone.utc)
            else:
                conn_t = conn_t.astimezone(timezone.utc)
            existing_composite_keys.add((st_canonical_id, conn_t.strftime("%Y-%m-%dT%H:%M:%SZ")))

        new_sessions: List[ChargingSession] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                report.records_rejected += 1
                report.rejection_reasons["record_not_dict"] = report.rejection_reasons.get("record_not_dict", 0) + 1
                continue

            # Extract fields with fallback variants
            source_sess_id = item.get("sessionID") or item.get("_id") or item.get("id")
            source_station_id = item.get("stationID") or item.get("spaceID")
            site_id = item.get("siteID") or meta.get("site")
            conn_raw = item.get("connectionTime")
            disc_raw = item.get("disconnectTime")
            kwh_raw = item.get("kWhDelivered")
            source_tz = item.get("timezone")

            # 1. Validate station identifier
            if not source_station_id or not str(source_station_id).strip():
                report.records_rejected += 1
                report.rejection_reasons["missing_station_id"] = report.rejection_reasons.get("missing_station_id", 0) + 1
                continue
            clean_source_station = str(source_station_id).strip()

            # 2. Check duplicate session ID if present
            if source_sess_id and str(source_sess_id).strip() in existing_session_ids:
                report.records_skipped += 1
                continue

            # 3. Parse connectionTime
            conn_time = self.parse_iso_or_rfc(conn_raw)
            if conn_time is None:
                report.records_rejected += 1
                report.rejection_reasons["invalid_connection_time"] = report.rejection_reasons.get("invalid_connection_time", 0) + 1
                continue

            # 4. Resolve Station
            station = stations_by_source.get(clean_source_station)
            if station is None:
                canonical_st_id = self.mapping_service.get_or_create(clean_source_station)
                station = Station(
                    station_id=canonical_st_id,
                    source_station_id=clean_source_station,
                    site_id=str(site_id).strip() if site_id else None,
                )
                if not dry_run:
                    self.db.add(station)
                    await self.db.flush()
                stations_by_source[clean_source_station] = station

            # 5. Fallback deduplication: check composite key (canonical_station_id, UTC iso timestamp)
            conn_time_iso = conn_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            composite_key = (station.station_id, conn_time_iso)
            if not source_sess_id and composite_key in existing_composite_keys:
                report.records_skipped += 1
                continue

            # 6. Parse disconnectTime
            disc_time = None
            if disc_raw:
                disc_time = self.parse_iso_or_rfc(disc_raw)
                if disc_time is None:
                    report.records_rejected += 1
                    report.rejection_reasons["invalid_disconnect_time"] = report.rejection_reasons.get("invalid_disconnect_time", 0) + 1
                    continue
                if disc_time < conn_time:
                    report.records_rejected += 1
                    report.rejection_reasons["disconnect_before_connection"] = report.rejection_reasons.get("disconnect_before_connection", 0) + 1
                    continue

            # 7. Parse kWhDelivered
            kwh_decimal = None
            if kwh_raw is not None:
                try:
                    kwh_decimal = Decimal(str(kwh_raw))
                    if kwh_decimal < 0:
                        report.records_rejected += 1
                        report.rejection_reasons["negative_kwh"] = report.rejection_reasons.get("negative_kwh", 0) + 1
                        continue
                except (InvalidOperation, ValueError, TypeError):
                    report.records_rejected += 1
                    report.rejection_reasons["invalid_kwh"] = report.rejection_reasons.get("invalid_kwh", 0) + 1
                    continue

            # 8. Construct ChargingSession
            clean_sess_id = str(source_sess_id).strip() if source_sess_id else None
            session_model = ChargingSession(
                source_session_id=clean_sess_id,
                station_id=station.id if not dry_run else 0,
                connection_time=conn_time,
                disconnect_time=disc_time,
                kwh_delivered=kwh_decimal,
                source_site_id=str(site_id).strip() if site_id else None,
                source_timezone=str(source_tz).strip() if source_tz else None,
                source_dataset=source_dataset,
            )
            new_sessions.append(session_model)
            if clean_sess_id:
                existing_session_ids.add(clean_sess_id)
            existing_composite_keys.add(composite_key)
            report.records_inserted += 1

        # Commit or rollback
        if not dry_run:
            for s in new_sessions:
                if s.station_id == 0:
                    st_obj = stations_by_source.get(s.station.source_station_id) if hasattr(s, "station") else None
                    if st_obj:
                        s.station_id = st_obj.id
                self.db.add(s)

            db_import = DatasetImport(
                import_id=import_id,
                source_dataset=source_dataset,
                source_filename=file_path.name,
                file_checksum=checksum,
                status="completed",
                completed_at=datetime.now(timezone.utc),
                total_records_read=report.total_records_read,
                records_inserted=report.records_inserted,
                records_skipped=report.records_skipped,
                records_rejected=report.records_rejected,
                error_summary=json.dumps(report.rejection_reasons) if report.rejection_reasons else None,
            )
            self.db.add(db_import)
            await self.db.commit()
            report.status = "completed"
        else:
            report.status = "dry_run_success"

        return report
