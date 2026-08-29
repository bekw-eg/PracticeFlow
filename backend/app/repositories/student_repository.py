import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganizationMembership
from app.models.student import Student


class StudentRepository:
    """Student profiles are scoped through their membership's organization_id
    (Student has no direct organization_id column)."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, org_id: uuid.UUID, student_id: uuid.UUID) -> Student | None:
        stmt = (
            select(Student)
            .join(OrganizationMembership, Student.membership_id == OrganizationMembership.id)
            .where(Student.id == student_id, OrganizationMembership.organization_id == org_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_membership_id(self, membership_id: uuid.UUID) -> Student | None:
        stmt = select(Student).where(Student.membership_id == membership_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def add(self, student: Student) -> Student:
        self.db.add(student)
        self.db.flush()
        return student
