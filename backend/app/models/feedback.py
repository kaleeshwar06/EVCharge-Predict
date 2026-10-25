"""SQLAlchemy ORM models for AllocationFeedback and AdjustedDemandInterval."""
from __future__ import annotations

from datetime import datetime, timezone
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
    from app.models.forecast import Forecast, ForecastInterval
    from app.models.station import Station


class AllocationFeedback(Base, TimestampMixin):
    """Immutable record of allocation feedback submitted by EVCharge-Opt."""
    __tablename__ = "allocation_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feedback_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    allocation_run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    forecast_id: Mapped[int] = mapped_column(ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    contract_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False)  # accepted, rejected
    optimizer_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    forecast: Mapped[Forecast] = relationship("Forecast")
    adjusted_intervals: Mapped[List[AdjustedDemandInterval]] = relationship(
        "AdjustedDemandInterval",
        back_populates="feedback",
        cascade="all, delete-orphan",
        order_by="AdjustedDemandInterval.interval_start",
    )

    __table_args__ = (
        Index("ix_feedback_scenario_forecast", "scenario_id", "forecast_id"),
    )

    def __repr__(self) -> str:
        return f"<AllocationFeedback(id={self.id}, feedback_id='{self.feedback_id}', run_id='{self.allocation_run_id}')>"


class AdjustedDemandInterval(Base, TimestampMixin):
    """Station-interval feedback-adjusted operational demand derived from allocation feedback."""
    __tablename__ = "adjusted_demand_intervals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("allocation_feedbacks.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_interval_id: Mapped[int] = mapped_column(ForeignKey("forecast_intervals.id", ondelete="CASCADE"), nullable=False, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)

    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Baseline preservation
    baseline_arrivals: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_energy_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    # Feedback inputs
    allocated_energy_kwh: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    available_capacity_kw: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    reported_unmet_demand_kwh: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    # Derived operational result
    adjusted_operational_demand_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    adjustment_status: Mapped[str] = mapped_column(String(32), nullable=False)  # adjusted, unchanged, insufficient_data
    adjustment_policy_version: Mapped[str] = mapped_column(String(64), default="v1-heuristic-operational-envelope", nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    feedback: Mapped[AllocationFeedback] = relationship("AllocationFeedback", back_populates="adjusted_intervals")
    forecast_interval: Mapped[ForecastInterval] = relationship("ForecastInterval")
    station: Mapped[Station] = relationship("Station")

    __table_args__ = (
        CheckConstraint("baseline_arrivals >= 0", name="ck_adj_baseline_arrivals_nonneg"),
        CheckConstraint("baseline_energy_kwh >= 0", name="ck_adj_baseline_energy_nonneg"),
        CheckConstraint("allocated_energy_kwh IS NULL OR allocated_energy_kwh >= 0", name="ck_adj_alloc_energy_nonneg"),
        CheckConstraint("available_capacity_kw IS NULL OR available_capacity_kw >= 0", name="ck_adj_avail_capacity_nonneg"),
        CheckConstraint("reported_unmet_demand_kwh IS NULL OR reported_unmet_demand_kwh >= 0", name="ck_adj_unmet_demand_nonneg"),
        CheckConstraint("adjusted_operational_demand_kwh >= 0", name="ck_adj_operational_demand_nonneg"),
        CheckConstraint("interval_end > interval_start", name="ck_adj_interval_order"),
        UniqueConstraint("feedback_id", "station_id", "interval_start", name="uq_adj_feedback_station_interval"),
        Index("ix_adj_station_start", "station_id", "interval_start"),
    )

    def __repr__(self) -> str:
        return (
            f"<AdjustedDemandInterval(feedback_id={self.feedback_id}, station_id={self.station_id}, "
            f"start={self.interval_start}, base_kwh={self.baseline_energy_kwh}, adj_kwh={self.adjusted_operational_demand_kwh})>"
        )
