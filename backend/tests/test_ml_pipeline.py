"""Automated tests for Phase 3: ML data loading, aggregation, features, split, training, and artifacts."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from app.ml.aggregator import DemandAggregator
from app.ml.data_loader import DataLoader, DataQualityError
from app.ml.features import FeatureEngineer
from app.ml.models import HistoricalAverageBaseline, RandomForestDemandModel, compute_metrics
from app.ml.persistence import ArtifactManager
from app.ml.split import chronological_split
from app.ml.trainer import TrainingPipeline
from app.services.station_mapping import StationMappingService

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── 1. Aggregation Tests ───────────────────────────────────────────────────
def test_hourly_aggregation_counts_and_boundaries():
    """Verify half-open interval [t, t+1h) and exact arrivals/energy calculation."""
    sessions = [
        # Hour 08:00
        {"session_id": "1", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 8, 0, 0, tzinfo=timezone.utc), "kwh_delivered": 10.0},
        {"session_id": "2", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 8, 59, 59, tzinfo=timezone.utc), "kwh_delivered": 15.0},
        # Hour 09:00 (exact boundary falls into 09:00, not 08:00)
        {"session_id": "3", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc), "kwh_delivered": 20.0},
        # Hour 11:00 (skipping 10:00 to test zero-fill within span)
        {"session_id": "4", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 11, 30, 0, tzinfo=timezone.utc), "kwh_delivered": 25.0},
    ]
    df = pd.DataFrame(sessions)
    agg = DemandAggregator.aggregate_hourly(df)

    assert len(agg) == 4  # Hours: 08, 09, 10, 11
    row_08 = agg[agg["interval_start"] == pd.Timestamp("2026-10-01 08:00:00+0000")].iloc[0]
    assert row_08["arrivals"] == 2
    assert row_08["session_start_energy_kwh"] == 25.0

    row_09 = agg[agg["interval_start"] == pd.Timestamp("2026-10-01 09:00:00+0000")].iloc[0]
    assert row_09["arrivals"] == 1
    assert row_09["session_start_energy_kwh"] == 20.0

    # Intermediate missing hour 10:00 must be zero-filled
    row_10 = agg[agg["interval_start"] == pd.Timestamp("2026-10-01 10:00:00+0000")].iloc[0]
    assert row_10["arrivals"] == 0
    assert row_10["session_start_energy_kwh"] == 0.0


def test_missing_energy_values_not_treated_as_measured_zero():
    """Missing energy must not distort measured energy count."""
    sessions = [
        {"session_id": "1", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 8, 10, tzinfo=timezone.utc), "kwh_delivered": 12.0},
        {"session_id": "2", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 8, 40, tzinfo=timezone.utc), "kwh_delivered": None},
    ]
    df = pd.DataFrame(sessions)
    agg = DemandAggregator.aggregate_hourly(df)
    row = agg.iloc[0]
    assert row["arrivals"] == 2
    assert row["session_start_energy_kwh"] == 12.0
    assert row["energy_measured_count"] == 1  # Only 1 had measured energy


# ─── 2. Feature Engineering Tests ───────────────────────────────────────────
def test_no_future_leakage_in_features():
    """Verify that lag and rolling window features for interval t never peek at target t or future."""
    # Synthetic sequence of arrivals: 1, 2, 3, 4, 5
    times = pd.date_range("2026-10-01 00:00", periods=5, freq="1h", tz="UTC")
    agg_df = pd.DataFrame({
        "station_id": "ST-001",
        "interval_start": times,
        "interval_end": times + pd.Timedelta(hours=1),
        "arrivals": [10, 20, 30, 40, 50],
        "session_start_energy_kwh": [100.0, 200.0, 300.0, 400.0, 500.0],
        "energy_measured_count": [1, 1, 1, 1, 1],
    })
    feat_df, _ = FeatureEngineer.create_features(agg_df, drop_na_lags=False)

    # For row index 2 (interval 02:00, arrival=30):
    # lag_arrivals_1h must be 20 (interval 01:00), never 30 or 40
    row_2 = feat_df.iloc[2]
    assert row_2["arrivals"] == 30
    assert row_2["lag_arrivals_1h"] == 20
    assert row_2["lag_arrivals_2h"] == 10

    # Rolling 6h mean for row 2 must be (10 + 20) / 2 = 15.0 (excluding 30)
    assert row_2["rolling_arrivals_6h_mean"] == 15.0


# ─── 3. Chronological Split Tests ───────────────────────────────────────────
def test_chronological_split_strict_ordering():
    """Verify train, validation, and test splits have strict chronological boundaries."""
    times = pd.date_range("2026-10-01 00:00", periods=100, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "station_id": "ST-001",
        "interval_start": times,
        "arrivals": np.random.randint(0, 5, 100),
        "session_start_energy_kwh": np.random.uniform(0, 50, 100),
    })
    split = chronological_split(df, train_ratio=0.70, val_ratio=0.15)

    assert split.train_window.end_time < split.val_window.start_time
    assert split.val_window.end_time < split.test_window.start_time
    assert len(split.train_df) + len(split.val_df) + len(split.test_df) == 100


# ─── 4. End-to-End Pipeline & Artifact Tests ─────────────────────────────────
def test_training_pipeline_end_to_end(tmp_path):
    """Test full training pipeline with 14-day synthetic fixture."""
    fixture_path = FIXTURES_DIR / "synthetic_14day_sessions.json"
    mapping_service = StationMappingService(mapping_file=tmp_path / "station_map.json")

    sessions_df, quality_report = DataLoader.load_from_processed_file(
        file_path=fixture_path,
        mapping_service=mapping_service,
    )
    assert quality_report.is_synthetic is True
    assert quality_report.valid_records > 200

    output_dir = tmp_path / "models"
    pipeline = TrainingPipeline(output_dir=output_dir)
    manifest, reports = pipeline.run(sessions_df, quality_report, dry_run=False)

    assert len(reports) == 2  # arrivals and energy
    arr_rep = reports[0]
    assert arr_rep.target_name == "arrivals"
    assert arr_rep.baseline_test.mae >= 0.0
    assert arr_rep.rf_test.mae >= 0.0

    # Verify persisted artifacts
    assert (output_dir / "arrival_model.joblib").exists()
    assert (output_dir / "energy_model.joblib").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "evaluation_report.md").exists()

    # Verify loading model back
    loaded_arr_model = joblib.load(output_dir / "arrival_model.joblib")
    assert isinstance(loaded_arr_model, RandomForestDemandModel)
    assert len(loaded_arr_model.feature_names_) > 0

    # Verify manifest content
    with open(output_dir / "manifest.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["is_synthetic"] is True
    assert "synthetic" in data["limitations"][0].lower()


def test_inadequate_data_fails_gracefully(tmp_path):
    """Verify that inadequate temporal coverage raises DataQualityError."""
    # Only 2 hours of data
    sessions = [
        {"session_id": "1", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc), "kwh_delivered": 10.0},
        {"session_id": "2", "station_id": "ST-001", "connection_time": datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc), "kwh_delivered": 15.0},
    ]
    df = pd.DataFrame(sessions)
    from app.ml.data_loader import DataQualityReport
    report = DataQualityReport(
        source_type="test", is_synthetic=True, total_records=2, valid_records=2, rejected_records=0,
        station_count=1, unique_stations=["ST-001"], min_connection_time=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
        max_connection_time=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc), time_span_hours=1.0,
        total_energy_kwh=25.0, energy_measured_records=2, energy_missing_records=0, energy_coverage_ratio=1.0,
    )
    pipeline = TrainingPipeline(output_dir=tmp_path / "models")
    with pytest.raises(DataQualityError):
        pipeline.run(df, report)
