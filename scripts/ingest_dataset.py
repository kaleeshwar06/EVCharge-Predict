"""CLI command for ingesting ACN-Data JSON files into EVCharge-Predict."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.services.ingestion import IngestionPipeline, IngestionReport
from app.services.station_mapping import StationMappingService


async def main_async(args: argparse.Namespace) -> int:
    file_path = Path(args.file).resolve()
    print("=" * 60)
    print("EVCharge-Predict — Dataset Ingestion Pipeline")
    print("=" * 60)
    print(f"Target File: {file_path}")
    print(f"Dataset Tag: {args.dataset}")
    print(f"Dry Run:     {args.dry_run}")
    print("-" * 60)

    # Initialize tables if using local SQLite database
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mapping_service = StationMappingService()
    session_factory = get_session_factory()

    async with session_factory() as session:
        pipeline = IngestionPipeline(session=session, mapping_service=mapping_service)
        report: IngestionReport = await pipeline.ingest_file(
            file_path=file_path,
            source_dataset=args.dataset,
            dry_run=args.dry_run,
        )

    print("Ingestion Results:")
    print(f"  Import ID:        {report.import_id}")
    print(f"  Status:           {report.status}")
    print(f"  Total Read:       {report.total_records_read}")
    print(f"  Inserted:         {report.records_inserted}")
    print(f"  Skipped (dupes):  {report.records_skipped}")
    print(f"  Rejected:         {report.records_rejected}")

    if report.rejection_reasons:
        print("\nRejection Breakdown:")
        for reason, count in report.rejection_reasons.items():
            print(f"  - {reason}: {count}")

    if report.errors:
        print("\nErrors:")
        for err in report.errors:
            print(f"  [ERROR] {err}")

    print("=" * 60)
    return 0 if report.status in ("completed", "dry_run_success") else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ACN-Data JSON dataset.")
    parser.add_argument("file", help="Path to ACN-Data JSON export file")
    parser.add_argument("--dataset", default="acn-data", help="Source dataset name (default: acn-data)")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing sessions to database")
    args = parser.parse_args()

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
