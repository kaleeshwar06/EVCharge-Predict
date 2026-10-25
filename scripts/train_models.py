"""CLI entry point for EVCharge-Predict Demand Model Training."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.session import get_session_factory
from app.ml.data_loader import DataLoader, DataQualityError
from app.ml.trainer import TrainingPipeline
from app.services.station_mapping import StationMappingService


async def run_training(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    print("=" * 65)
    print("EVCharge-Predict — Model Training Pipeline (Phase 3)")
    print("=" * 65)
    print(f"Data Source:     {args.source}")
    print(f"Output Dir:      {output_dir}")
    print(f"Train/Val Split: {args.train_fraction:.0%} / {args.val_fraction:.0%}")
    print(f"Dry Run:         {args.dry_run}")
    print("-" * 65)

    try:
        if args.source == "database":
            session_factory = get_session_factory()
            async with session_factory() as session:
                sessions_df, quality_report = await DataLoader.load_from_db(session)
        else:
            file_path = Path(args.source).resolve()
            mapping_service = StationMappingService()
            sessions_df, quality_report = DataLoader.load_from_processed_file(
                file_path=file_path,
                mapping_service=mapping_service,
            )
    except DataQualityError as err:
        print(f"[FATAL DATA QUALITY ERROR] {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"[DATA LOAD ERROR] {err}", file=sys.stderr)
        return 1

    # Print Data Quality Summary
    print("Data Quality Assessment:")
    print(f"  Type:            {'SYNTHETIC FIXTURE' if quality_report.is_synthetic else 'REAL ACN-DATA'}")
    print(f"  Total Records:   {quality_report.total_records}")
    print(f"  Valid Sessions:  {quality_report.valid_records}")
    print(f"  Rejected:        {quality_report.rejected_records}")
    print(f"  Unique Stations: {quality_report.station_count} ({', '.join(quality_report.unique_stations)})")
    print(f"  Time Span:       {quality_report.time_span_hours:.1f} hours")
    print(f"  Energy Coverage: {quality_report.energy_coverage_ratio:.1%}")
    if quality_report.rejection_reasons:
        print("  Rejection Reasons:")
        for reason, count in quality_report.rejection_reasons.items():
            print(f"    - {reason}: {count}")
    print("-" * 65)

    pipeline = TrainingPipeline(
        output_dir=output_dir,
        min_energy_coverage=args.min_energy_coverage,
        train_ratio=args.train_fraction,
        val_ratio=args.val_fraction,
    )

    try:
        manifest, reports = pipeline.run(
            sessions_df=sessions_df,
            quality_report=quality_report,
            dry_run=args.dry_run,
        )
    except DataQualityError as err:
        print(f"[TRAINING ABORTED] {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"[UNEXPECTED PIPELINE ERROR] {err}", file=sys.stderr)
        return 1

    print("Model Evaluation Results:")
    for rep in reports:
        better = "YES" if rep.rf_outperformed_baseline else "NO"
        print(f"\nTarget: {rep.target_name} ({rep.target_unit})")
        print(f"  Baseline (Test) -> MAE: {rep.baseline_test.mae:.3f}, RMSE: {rep.baseline_test.rmse:.3f}")
        print(f"  Random Forest   -> MAE: {rep.rf_test.mae:.3f}, RMSE: {rep.rf_test.rmse:.3f}")
        print(f"  Random Forest Outperformed Baseline? {better}")

    print("\nArtifact Generation:")
    if args.dry_run:
        print("  [Dry Run Mode] Model validation succeeded. No artifacts persisted.")
    else:
        print(f"  Arrival Model:   {output_dir / 'arrival_model.joblib'}")
        if manifest.energy_metrics:
            print(f"  Energy Model:    {output_dir / 'energy_model.joblib'}")
        print(f"  Manifest JSON:   {output_dir / 'manifest.json'}")
        print(f"  Report Markdown: {output_dir / 'evaluation_report.md'}")

    print("=" * 65)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Train demand prediction models for EVCharge-Predict.")
    parser.add_argument("--source", default="database", help="Data source: 'database' or path to JSON file")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "artifacts" / "models"), help="Artifact destination directory")
    parser.add_argument("--train-fraction", type=float, default=0.70, help="Train ratio (default: 0.70)")
    parser.add_argument("--val-fraction", type=float, default=0.15, help="Validation ratio (default: 0.15)")
    parser.add_argument("--min-energy-coverage", type=float, default=0.50, help="Minimum valid energy ratio to train energy model (default: 0.50)")
    parser.add_argument("--dry-run", action="store_true", help="Run validation without persisting artifacts")

    args = parser.parse_args()
    exit_code = asyncio.run(run_training(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
