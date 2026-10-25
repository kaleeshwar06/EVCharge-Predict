"""Pydantic schemas for DatasetImport entity."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_serializer


class DatasetImportRead(BaseModel):
    """Public API representation of an import job."""
    import_id: str
    source_dataset: str
    source_filename: str
    file_checksum: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_records_read: int
    records_inserted: int
    records_skipped: int
    records_rejected: int
    error_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("started_at", "completed_at", when_used="json")
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        if dt is None:
            return None
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
