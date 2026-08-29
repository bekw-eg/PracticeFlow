import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganizationMembership
from app.models.teacher import Teacher


class TeacherRepository:
    """Teacher profiles are scoped through their membership's organization_id
    (Teacher has no direct organization_id column)."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, org_id: uuid.UUID, teacher_id: uuid.UUID) -> Teacher | None:
        stmt = (
            select(Teacher)
            .join(OrganizationMembership, Teacher.membership_id == OrganizationMembership.id)
            .where(Teacher.id == teacher_id, OrganizationMembership.organization_id == org_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_membership_id(self, membership_id: uuid.UUID) -> Teacher | None:
        stmt = select(Teacher).where(Teacher.membership_id == membership_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def add(self, teacher: Teacher) -> Teacher:
        self.db.add(teacher)
        self.db.flush()
        return teacher
