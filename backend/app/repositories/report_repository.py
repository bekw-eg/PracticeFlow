import uuid

from sqlalchemy import func, select

from app.models.report import Report
from app.repositories.base import TenantScopedRepository


class ReportRepository(TenantScopedRepository[Report]):
    model = Report

    def list_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Report]:
        """Reports for every internship inside a given group — this is what
        backs the group's 'Reports' tab."""
        from app.models.internship import Internship

        stmt = (
            select(Report)
            .join(Internship, Report.internship_id == Internship.id)
            .where(Report.organization_id == org_id, Internship.group_id == group_id)
            .order_by(Report.created_at.desc(), Report.id.desc())
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID) -> int:
        from app.models.internship import Internship

        stmt = (
            select(func.count())
            .select_from(Report)
            .join(Internship, Report.internship_id == Internship.id)
            .where(Report.organization_id == org_id, Internship.group_id == group_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def list_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Report]:
        stmt = (
            select(Report)
            .where(Report.organization_id == org_id, Report.student_id == student_id)
            .order_by(Report.created_at.desc(), Report.id.desc())
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Report).where(
            Report.organization_id == org_id, Report.student_id == student_id
        )
        return int(self.db.scalar(stmt) or 0)

    def get_for_internship_and_student(self, org_id: uuid.UUID, internship_id: uuid.UUID, student_id: uuid.UUID) -> Report | None:
        stmt = select(Report).where(
            Report.organization_id == org_id,
            Report.internship_id == internship_id,
            Report.student_id == student_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()
