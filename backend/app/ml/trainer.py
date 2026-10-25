"""End-to-end model training orchestrator."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import joblib
import pandas as pd
import sklearn

from app.ml.aggregator import DemandAggregator
from app.ml.data_loader import DataLoader, DataQualityError, DataQualityReport
from app.ml.features import FeatureEngineer
from app.ml.models import (
    HistoricalAverageBaseline,
    ModelEvaluationReport,
    RandomForestDemandModel,
    compute_metrics,
)
from app.ml.persistence import ArtifactManager, TrainingManifest
from app.ml.split import chronological_split


class TrainingPipeline:
    """Coordinates validation, feature engineering, chronological evaluation, and artifact saving."""

    def __init__(
        self,
        output_dir: Path,
        min_energy_coverage: float = 0.50,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
    ) -> None:
        self.output_dir = output_dir
        self.min_energy_coverage = min_energy_coverage
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.artifact_mgr = ArtifactManager(output_dir=self.output_dir)

    def run(
        self,
        sessions_df: pd.DataFrame,
        quality_report: DataQualityReport,
        dry_run: bool = False,
    ) -> Tuple[TrainingManifest, List[ModelEvaluationReport]]:
        """Executes full training and evaluation workflow."""
        if sessions_df.empty or quality_report.valid_records < 10:
            raise DataQualityError(
                f"Dataset contains insufficient usable records ({quality_report.valid_records}). Minimum 10 required."
            )

        if quality_report.time_span_hours < 48.0:
            raise DataQualityError(
                f"Dataset temporal coverage ({quality_report.time_span_hours:.1f}h) is too brief for a chronological split (minimum 48h required)."
            )

        # 1. Hourly Aggregation
        hourly_df = DemandAggregator.aggregate_hourly(sessions_df)

        # 2. Feature Engineering (Strictly Past-Only)
        feature_df, station_encoder = FeatureEngineer.create_features(hourly_df)
        feature_names = FeatureEngineer.get_feature_names()

        # 3. Chronological Split
        split = chronological_split(
            feature_df,
            train_ratio=self.train_ratio,
            val_ratio=self.val_ratio,
        )

        evaluation_reports: List[ModelEvaluationReport] = []
        limitations: List[str] = []

        if quality_report.is_synthetic:
            limitations.append("Model trained on synthetic fixtures. Metrics do not establish real-world predictive accuracy.")

        # 4. Target A: Hourly Session Arrivals
        arr_report, arr_model = self._train_and_evaluate_target(
            target_col="arrivals",
            target_unit="sessions/hour",
            split=split,
            feature_names=feature_names,
        )
        evaluation_reports.append(arr_report)

        # 5. Target B: Session-Start Energy Demand (kWh)
        ene_model: Optional[RandomForestDemandModel] = None
        if quality_report.energy_coverage_ratio >= self.min_energy_coverage:
            ene_report, ene_model = self._train_and_evaluate_target(
                target_col="session_start_energy_kwh",
                target_unit="kWh",
                split=split,
                feature_names=feature_names,
            )
            evaluation_reports.append(ene_report)
        else:
            limitations.append(
                f"Energy model skipped: energy measurement coverage was {quality_report.energy_coverage_ratio:.1%}, "
                f"below required threshold ({self.min_energy_coverage:.1%})."
            )

        # 6. Build Manifest
        manifest = TrainingManifest(
            model_version="1.0",
            created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            is_synthetic=quality_report.is_synthetic,
            data_source=quality_report.source_type,
            total_raw_records=quality_report.total_records,
            usable_session_records=quality_report.valid_records,
            station_count=quality_report.station_count,
            stations=quality_report.unique_stations,
            time_span_hours=quality_report.time_span_hours,
            energy_coverage_ratio=quality_report.energy_coverage_ratio,
            train_start=split.train_window.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            train_end=split.train_window.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            val_start=split.val_window.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            val_end=split.val_window.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            test_start=split.test_window.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            test_end=split.test_window.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            feature_names=feature_names,
            station_encoder=station_encoder,
            arrival_metrics=asdict(arr_report),
            energy_metrics=asdict(evaluation_reports[1]) if len(evaluation_reports) > 1 else None,
            scikit_learn_version=sklearn.__version__,
            joblib_version=joblib.__version__,
            limitations=limitations,
        )

        # 7. Persist Artifacts (unless dry run)
        if not dry_run:
            self.artifact_mgr.save_run(
                arrival_model=arr_model,
                energy_model=ene_model,
                manifest=manifest,
                evaluation_reports=evaluation_reports,
            )

        return manifest, evaluation_reports

    def _train_and_evaluate_target(
        self,
        target_col: str,
        target_unit: str,
        split: Any,
        feature_names: List[str],
    ) -> Tuple[ModelEvaluationReport, RandomForestDemandModel]:
        # Fit Baseline strictly on training set
        baseline = HistoricalAverageBaseline(target_col=target_col)
        baseline.fit(split.train_df)

        base_val_preds = baseline.predict(split.val_df)
        base_test_preds = baseline.predict(split.test_df)

        base_val_scores = compute_metrics(split.val_df[target_col].values, base_val_preds)
        base_test_scores = compute_metrics(split.test_df[target_col].values, base_test_preds)

        # Fit Random Forest strictly on training set
        rf = RandomForestDemandModel(target_col=target_col)
        rf.fit(split.train_df, feature_names)

        rf_val_preds = rf.predict(split.val_df)
        rf_test_preds = rf.predict(split.test_df)

        rf_val_scores = compute_metrics(split.val_df[target_col].values, rf_val_preds)
        rf_test_scores = compute_metrics(split.test_df[target_col].values, rf_test_preds)

        outperformed = rf_test_scores.mae < base_test_scores.mae

        # Per-station metrics on test set
        per_station: Dict[str, Dict[str, float]] = {}
        for st_id, st_group in split.test_df.groupby("station_id"):
            st_idx = st_group.index
            st_true = st_group[target_col].values
            st_b_pred = base_test_preds[split.test_df.index.isin(st_idx)]
            st_rf_pred = rf_test_preds[split.test_df.index.isin(st_idx)]
            if len(st_true) > 0:
                per_station[st_id] = {
                    "sample_count": len(st_true),
                    "baseline_mae": round(float(compute_metrics(st_true, st_b_pred).mae), 4),
                    "rf_mae": round(float(compute_metrics(st_true, st_rf_pred).mae), 4),
                }

        report = ModelEvaluationReport(
            target_name=target_col,
            target_unit=target_unit,
            baseline_val=base_val_scores,
            baseline_test=base_test_scores,
            rf_val=rf_val_scores,
            rf_test=rf_test_scores,
            rf_outperformed_baseline=outperformed,
            per_station_test=per_station,
        )
        return report, rf
