"""Deterministic fixtures for the isolated browser E2E environment.

This script is deliberately separate from ``seed.py``.  It may run only with
``ENV=e2e`` and is started only by ``docker-compose.e2e.yml`` against its
ephemeral PostgreSQL database.  It must never be used for local development
or a deployed environment.
"""
from copy import deepcopy
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.documents.defaults import build_default_document
from app.models.department import Department
from app.models.enums import InternshipStatus, ReportStatus, RoleName
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.internship import Internship
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.report import Report
from app.models.role import Role
from app.models.specialty import Specialty
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.template import Template
from app.models.template_version import TemplateVersion
from app.models.user import User


E2E_PASSWORD = "Practice123!"
# This ID is intentionally stable so the browser suite can prove that a
# student from demo-university cannot retrieve a report that belongs to the
# second tenant.
OTHER_TENANT_REPORT_ID = UUID("d4ccf32d-6f2b-4f0e-9cbd-3bd1b2c3c502")


def _role(db: Session, name: RoleName) -> Role:
    role = db.query(Role).filter_by(name=name.value).one_or_none()
    if role is None:
        role = Role(name=name.value, description=f"{name.value} role")
        db.add(role)
        db.flush()
    return role


def _seed_tenant(
    db: Session,
    *,
    organization_name: str,
    organization_slug: str,
    teacher_email: str,
    student_email: str,
    director_email: str | None = None,
    report_id: UUID | None = None,
) -> Report:
    existing = db.query(Organization).filter_by(slug=organization_slug).one_or_none()
    if existing is not None:
        report = db.query(Report).filter_by(organization_id=existing.id).one()
        return report

    organization = Organization(name=organization_name, slug=organization_slug)
    db.add(organization)
    db.flush()

    department = Department(organization_id=organization.id, name="E2E Software Engineering")
    db.add(department)
    db.flush()

    specialty = Specialty(
        organization_id=organization.id,
        department_id=department.id,
        name="E2E Software Engineering",
        code="E2E-SE",
    )
    db.add(specialty)
    db.flush()

    teacher_user = User(
        email=teacher_email,
        hashed_password=hash_password(E2E_PASSWORD),
        full_name="E2E Teacher",
    )
    student_user = User(
        email=student_email,
        hashed_password=hash_password(E2E_PASSWORD),
        full_name="E2E Student",
    )
    director_user = User(
        email=director_email,
        hashed_password=hash_password(E2E_PASSWORD),
        full_name="E2E Director",
    ) if director_email else None
    db.add_all([teacher_user, student_user, *([director_user] if director_user else [])])
    db.flush()

    teacher_membership = OrganizationMembership(
        user_id=teacher_user.id,
        organization_id=organization.id,
        role_id=_role(db, RoleName.TEACHER).id,
    )
    student_membership = OrganizationMembership(
        user_id=student_user.id,
        organization_id=organization.id,
        role_id=_role(db, RoleName.STUDENT).id,
    )
    db.add_all([teacher_membership, student_membership])
    if director_user:
        db.add(OrganizationMembership(
            user_id=director_user.id,
            organization_id=organization.id,
            role_id=_role(db, RoleName.DIRECTOR).id,
        ))
    db.flush()

    teacher = Teacher(membership_id=teacher_membership.id, department_id=department.id)
    student = Student(membership_id=student_membership.id, specialty_id=specialty.id)
    db.add_all([teacher, student])
    db.flush()

    group = Group(
        organization_id=organization.id,
        specialty_id=specialty.id,
        name="E2E-Group",
        academic_year="2025-2026",
    )
    db.add(group)
    db.flush()
    db.add_all([TeacherGroup(teacher_id=teacher.id, group_id=group.id), GroupMember(group_id=group.id, student_id=student.id)])

    template = Template(
        organization_id=organization.id,
        created_by_teacher_id=teacher.id,
        name="E2E Report Template",
        description="Deterministic fixture template for browser tests.",
    )
    db.add(template)
    db.flush()
    document = build_default_document()
    template_version = TemplateVersion(
        template_id=template.id,
        version_number=1,
        document_data=document.model_dump(mode="json"),
        schema_version=document.schema_version,
        is_published=True,
    )
    db.add(template_version)
    db.flush()

    internship = Internship(
        organization_id=organization.id,
        group_id=group.id,
        template_version_id=template_version.id,
        created_by_teacher_id=teacher.id,
        title="E2E Practice",
        description="Fixture internship for browser tests.",
        specialty_id=specialty.id,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
        deadline=date(2025, 7, 1),
        status=InternshipStatus.PUBLISHED,
    )
    db.add(internship)
    db.flush()

    report = Report(
        **({"id": report_id} if report_id else {}),
        organization_id=organization.id,
        internship_id=internship.id,
        student_id=student.id,
        status=ReportStatus.REVISION_REQUIRED,
        document_data=deepcopy(template_version.document_data),
        document_schema_version=template_version.schema_version,
    )
    db.add(report)
    db.flush()
    return report


def run() -> None:
    if settings.ENV.strip().lower() != "e2e":
        raise SystemExit("E2E fixture data is disabled unless ENV=e2e.")

    db = SessionLocal()
    try:
        _seed_tenant(
            db,
            organization_name="E2E Demo University",
            organization_slug="demo-university",
            teacher_email="teacher@demo.edu",
            student_email="student1@demo.edu",
            director_email="director@demo.edu",
        )
        _seed_tenant(
            db,
            organization_name="E2E Other University",
            organization_slug="other-university",
            teacher_email="teacher@other.demo.edu",
            student_email="student@other.demo.edu",
            report_id=OTHER_TENANT_REPORT_ID,
        )
        db.commit()
        print("E2E fixture seed complete: two deterministic organizations created.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
