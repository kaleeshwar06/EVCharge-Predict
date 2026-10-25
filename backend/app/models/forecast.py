"""SQLAlchemy ORM models for Forecast and ForecastInterval entities."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.station import Station


class Forecast(Base, TimestampMixin):
    """Represents a generated multi-station, multi-interval forecast batch."""
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    forecast_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    forecast_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    horizon_intervals: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)  # completed, failed
    demand_type: Mapped[str] = mapped_column(String(32), default="baseline", nullable=False)

    # Provenance & model metadata
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    training_data_type: Mapped[str] = mapped_column(String(32), nullable=False)  # synthetic or real
    training_data_fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    intervals: Mapped[List[ForecastInterval]] = relationship(
        "ForecastInterval",
        back_populates="forecast",
        cascade="all, delete-orphan",
        order_by="ForecastInterval.interval_start",
    )

    __table_args__ = (
        Index("ix_forecasts_scenario_generated", "scenario_id", "generated_at"),
    )

    def __repr__(self) -> str:
        return f"<Forecast(id={self.id}, forecast_id='{self.forecast_id}', scenario='{self.scenario_id}', status='{self.status}')>"


class ForecastInterval(Base, TimestampMixin):
    """Station-specific hourly interval prediction within a forecast batch."""
    __tablename__ = "forecast_intervals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)

    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    predicted_arrivals: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_energy_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    # Relationships
    forecast: Mapped[Forecast] = relationship("Forecast", back_populates="intervals")
    station: Mapped[Station] = relationship("Station")

    __table_args__ = (
        CheckConstraint("predicted_arrivals >= 0", name="ck_forecast_arrivals_nonnegative"),
        CheckConstraint("predicted_energy_kwh >= 0", name="ck_forecast_energy_nonnegative"),
        CheckConstraint("interval_end > interval_start", name="ck_forecast_interval_order"),
        UniqueConstraint("forecast_id", "station_id", "interval_start", name="uq_forecast_station_interval"),
        Index("ix_forecast_station_start", "station_id", "interval_start"),
    )

    def __repr__(self) -> str:
        return f"<ForecastInterval(forecast_id={self.forecast_id}, station_id={self.station_id}, start={self.interval_start}, arr={self.predicted_arrivals}, kwh={self.predicted_energy_kwh})>"
