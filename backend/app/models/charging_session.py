"""SQLAlchemy model for Charging Session."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.station import Station


class ChargingSession(Base, TimestampMixin):
    """Individual EV charging session record."""
    __tablename__ = "charging_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)

    connection_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    disconnect_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    kwh_delivered: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    source_site_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_dataset: Mapped[str] = mapped_column(String(64), default="acn-data", nullable=False)

    # Relationship
    station: Mapped[Station] = relationship("Station", back_populates="sessions")

    __table_args__ = (
        # Non-negative energy constraint
        CheckConstraint("kwh_delivered IS NULL OR kwh_delivered >= 0", name="ck_sessions_kwh_nonnegative"),
        # Disconnect time must not precede connection time
        CheckConstraint("disconnect_time IS NULL OR disconnect_time >= connection_time", name="ck_sessions_time_order"),
        # Prevent duplicate imports when a stable source_session_id exists
        UniqueConstraint("source_session_id", name="uq_sessions_source_session_id"),
        # Composite index for time-series forecasting queries per station
        Index("ix_station_connection_time", "station_id", "connection_time"),
    )

    def __repr__(self) -> str:
        return f"<ChargingSession(id={self.id}, station_id={self.station_id}, conn={self.connection_time}, kwh={self.kwh_delivered})>"
