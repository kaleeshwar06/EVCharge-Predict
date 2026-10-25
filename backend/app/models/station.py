"""SQLAlchemy model for Charging Station."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.charging_session import ChargingSession


class Station(Base, TimestampMixin):
    """Charging station entity with persistent canonical ID mapping."""
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    source_station_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    site_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    sessions: Mapped[List[ChargingSession]] = relationship(
        "ChargingSession",
        back_populates="station",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Station(id={self.id}, station_id='{self.station_id}', source='{self.source_station_id}')>"
