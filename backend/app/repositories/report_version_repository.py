import uuid

from sqlalchemy import func, select

from app.models.report_version import ReportVersion


class ReportVersionRepository:
    def __init__(self, db):
        self.db = db

    def next_version_number(self, report_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(ReportVersion.version_number), 0)).where(ReportVersion.report_id == report_id)
        return self.db.execute(stmt).scalar_one() + 1

    def list_for_report(self, report_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[ReportVersion]:
        stmt = select(ReportVersion).where(ReportVersion.report_id == report_id).order_by(ReportVersion.version_number)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_report(self, report_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(ReportVersion).where(ReportVersion.report_id == report_id)
        return int(self.db.scalar(stmt) or 0)

    def add(self, version: ReportVersion) -> ReportVersion:
        self.db.add(version)
        self.db.flush()
        return version
