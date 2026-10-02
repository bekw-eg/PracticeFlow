"""Copy DB-referenced LocalStorage files into the configured private S3 bucket.

The command is intentionally copy-only. It verifies a SHA-256 checksum and
size before reporting an object as transferred, skips already-matching keys,
and refuses to overwrite a mismatched destination object.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import ExportJobStatus
from app.models.export_job import ExportJob
from app.models.file import File
from app.models.group_review_report import GroupReviewReport
from app.services.group_review_report_service import PPTX_MIME
from app.services.storage_migration import LocalToS3Migrator, StorageMigrationCandidate
from app.storage.s3 import S3StorageService
from app.storage.local import LocalStorageService


def candidates_from_database(db: Session) -> list[StorageMigrationCandidate]:
    candidates = [
        StorageMigrationCandidate(
            key=file_row.storage_key,
            content_type=file_row.content_type,
            expected_size_bytes=file_row.size_bytes,
            source="file",
        )
        for file_row in db.scalars(select(File).order_by(File.created_at, File.id))
    ]
    candidates.extend(
        StorageMigrationCandidate(
            key=job.storage_key,
            content_type=job.content_type,
            expected_size_bytes=job.size_bytes,
            source="export_job",
        )
        for job in db.scalars(
            select(ExportJob)
            .where(
                ExportJob.status == ExportJobStatus.SUCCEEDED,
                ExportJob.storage_key.is_not(None),
                ExportJob.content_type.is_not(None),
            )
            .order_by(ExportJob.created_at, ExportJob.id)
        )
        if job.storage_key is not None and job.content_type is not None
    )
    candidates.extend(
        StorageMigrationCandidate(key=report.storage_key, content_type=PPTX_MIME,
                                  expected_size_bytes=None, source="group_review_report")
        for report in db.scalars(select(GroupReviewReport).where(
            GroupReviewReport.generated_at.is_not(None), GroupReviewReport.storage_key.is_not(None),
        ).order_by(GroupReviewReport.created_at, GroupReviewReport.id))
        if report.storage_key is not None
    )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely copy LocalStorage objects into configured private S3 storage.")
    parser.add_argument("--local-root", required=True, help="Existing LocalStorage root (for example the mounted backend_storage volume).")
    parser.add_argument("--dry-run", action="store_true", help="Verify sources and report intended copies without writing S3.")
    parser.add_argument("--report", type=Path, default=Path("storage-migration-report.json"), help="Path for the JSON report.")
    args = parser.parse_args()

    if settings.STORAGE_BACKEND != "s3":
        raise SystemExit("Set STORAGE_BACKEND=s3 plus complete S3_* configuration before running this copy tool.")

    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    try:
        with Session(engine) as db:
            report = LocalToS3Migrator(LocalStorageService(args.local_root), S3StorageService()).migrate(
                candidates_from_database(db), dry_run=args.dry_run
            )
    finally:
        engine.dispose()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.report), "transferred": len(report.transferred), "skipped": len(report.skipped), "errors": len(report.errors)}))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
