"""Atomic model artifact persistence and manifest generation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import sklearn

from app.ml.models import ModelEvaluationReport, RandomForestDemandModel


@dataclass
class TrainingManifest:
    model_version: str
    created_at_utc: str
    is_synthetic: bool
    data_source: str
    total_raw_records: int
    usable_session_records: int
    station_count: int
    stations: List[str]
    time_span_hours: float
    energy_coverage_ratio: float
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    test_start: str
    test_end: str
    feature_names: List[str]
    station_encoder: Dict[str, int]
    arrival_metrics: Dict[str, Any]
    energy_metrics: Optional[Dict[str, Any]]
    scikit_learn_version: str
    joblib_version: str
    limitations: List[str]


class ArtifactManager:
    """Safely saves and loads models, encoders, and evaluation metadata atomically."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_run(
        self,
        arrival_model: RandomForestDemandModel,
        energy_model: Optional[RandomForestDemandModel],
        manifest: TrainingManifest,
        evaluation_reports: List[ModelEvaluationReport],
    ) -> Dict[str, Path]:
        """Saves models, manifest, and evaluation reports atomically."""
        saved_paths: Dict[str, Path] = {}

        # 1. Save Arrival Model
        arr_path = self.output_dir / "arrival_model.joblib"
        tmp_arr = arr_path.with_suffix(".tmp")
        joblib.dump(arrival_model, tmp_arr)
        tmp_arr.replace(arr_path)
        saved_paths["arrival_model"] = arr_path

        # 2. Save Energy Model (if trained)
        if energy_model is not None:
            ene_path = self.output_dir / "energy_model.joblib"
            tmp_ene = ene_path.with_suffix(".tmp")
            joblib.dump(energy_model, tmp_ene)
            tmp_ene.replace(ene_path)
            saved_paths["energy_model"] = ene_path

        # 3. Save Manifest JSON
        manifest_path = self.output_dir / "manifest.json"
        tmp_man = manifest_path.with_suffix(".tmp")
        with open(tmp_man, "w", encoding="utf-8") as f:
            json.dump(asdict(manifest), f, indent=2)
        tmp_man.replace(manifest_path)
        saved_paths["manifest"] = manifest_path

        # 4. Save Human-readable Evaluation Report Markdown
        report_path = self.output_dir / "evaluation_report.md"
        tmp_rep = report_path.with_suffix(".tmp")
        md_content = self._generate_markdown_report(manifest, evaluation_reports)
        with open(tmp_rep, "w", encoding="utf-8") as f:
            f.write(md_content)
        tmp_rep.replace(report_path)
        saved_paths["evaluation_report"] = report_path

        return saved_paths

    @staticmethod
    def _generate_markdown_report(manifest: TrainingManifest, reports: List[ModelEvaluationReport]) -> str:
        lines = [
            "# EVCharge-Predict — Model Training & Evaluation Report",
            f"\n- **Generated At (UTC):** {manifest.created_at_utc}",
            f"- **Dataset Source:** {manifest.data_source}",
            f"- **Data Type:** {'SYNTHETIC FIXTURE' if manifest.is_synthetic else 'REAL ACN-DATA'}",
            f"- **Total Raw Records:** {manifest.total_raw_records}",
            f"- **Valid Sessions:** {manifest.usable_session_records}",
            f"- **Stations:** {manifest.station_count} ({', '.join(manifest.stations)})",
            f"- **Energy Coverage Ratio:** {manifest.energy_coverage_ratio:.1%}",
            f"- **Time Span:** {manifest.time_span_hours:.1f} hours",
            "\n## Chronological Split Boundaries",
            f"- **Train:** {manifest.train_start} to {manifest.train_end}",
            f"- **Validation:** {manifest.val_start} to {manifest.val_end}",
            f"- **Test:** {manifest.test_start} to {manifest.test_end}",
            "\n## Model Performance Summary\n",
            "| Target | Baseline Test MAE | Baseline Test RMSE | RF Test MAE | RF Test RMSE | RF Outperformed? |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for rep in reports:
            b_mae = rep.baseline_test.mae
            b_rmse = rep.baseline_test.rmse
            rf_mae = rep.rf_test.mae
            rf_rmse = rep.rf_test.rmse
            better = "YES" if rep.rf_outperformed_baseline else "NO"
            lines.append(f"| {rep.target_name} ({rep.target_unit}) | {b_mae:.3f} | {b_rmse:.3f} | {rf_mae:.3f} | {rf_rmse:.3f} | {better} |")

        if manifest.limitations:
            lines.append("\n## Limitations & Data Warnings")
            for lim in manifest.limitations:
                lines.append(f"- ⚠️ {lim}")

        return "\n".join(lines) + "\n"
