"""SQLAlchemy model for Dataset Import tracking."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DatasetImport(Base, TimestampMixin):
    """Tracks dataset ingestion batches, audit counts, and error summaries."""
    __tablename__ = "dataset_imports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False) # in_progress, completed, failed, dry_run

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    total_records_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DatasetImport(import_id='{self.import_id}', status='{self.status}', inserted={self.records_inserted})>"
