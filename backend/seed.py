"""Development seed data.

Run with: PYTHONPATH=. python seed.py

Creates: Demo University org, all 4 roles, a Director, a Teacher, three
groups (BK2405/04/03), several students, one reusable template with a
published version, one internship in BK2405 published to its students,
and one submitted report — enough to exercise the full Phase 1 slice
(login as any seeded user, My Groups, group detail, create/publish
internship, student submit) without hand-creating data through the API.
"""
from copy import deepcopy

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.config import settings
from app.db.session import SessionLocal
from app.documents.defaults import build_default_document
from app.models.department import Department
from app.models.enums import InternshipStatus, RoleName
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

DEV_PASSWORD = "Practice123!"


def get_or_create_role(db: Session, name: RoleName) -> Role:
    role = db.query(Role).filter_by(name=name.value).one_or_none()
    if role is None:
        role = Role(name=name.value, description=f"{name.value} role")
        db.add(role)
        db.flush()
    return role


def make_user(db: Session, email: str, full_name: str) -> User:
    existing = db.query(User).filter_by(email=email).one_or_none()
    if existing:
        return existing
    user = User(email=email, hashed_password=hash_password(DEV_PASSWORD), full_name=full_name)
    db.add(user)
    db.flush()
    return user


def membership(db: Session, user: User, org: Organization, role: Role) -> OrganizationMembership:
    existing = db.query(OrganizationMembership).filter_by(user_id=user.id, organization_id=org.id).one_or_none()
    if existing:
        return existing
    m = OrganizationMembership(user_id=user.id, organization_id=org.id, role_id=role.id)
    db.add(m)
    db.flush()
    return m


def run() -> None:
    if settings.ENV.strip().lower() != "development":
        raise SystemExit("Development seed data is disabled unless ENV=development.")
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug="demo-university").one_or_none()
        if org is None:
            org = Organization(name="Demo University", slug="demo-university")
            db.add(org)
            db.flush()

        role_super_admin = get_or_create_role(db, RoleName.SUPER_ADMIN)
        role_director = get_or_create_role(db, RoleName.DIRECTOR)
        role_teacher = get_or_create_role(db, RoleName.TEACHER)
        role_student = get_or_create_role(db, RoleName.STUDENT)

        department = db.query(Department).filter_by(organization_id=org.id, name="Software Engineering").one_or_none()
        if department is None:
            department = Department(organization_id=org.id, name="Software Engineering")
            db.add(department)
            db.flush()

        specialty = db.query(Specialty).filter_by(organization_id=org.id, name="Software Engineering").one_or_none()
        if specialty is None:
            specialty = Specialty(organization_id=org.id, department_id=department.id, name="Software Engineering", code="SE")
            db.add(specialty)
            db.flush()

        # --- Users ---
        super_admin_user = make_user(db, "superadmin@demo.edu", "Асель Нурланова")
        membership(db, super_admin_user, org, role_super_admin)

        director_user = make_user(db, "director@demo.edu", "Марат Ахметов")
        membership(db, director_user, org, role_director)

        teacher_user = make_user(db, "teacher@demo.edu", "Гульнара Сатпаева")
        teacher_membership = membership(db, teacher_user, org, role_teacher)
        teacher = db.query(Teacher).filter_by(membership_id=teacher_membership.id).one_or_none()
        if teacher is None:
            teacher = Teacher(membership_id=teacher_membership.id, department_id=department.id)
            db.add(teacher)
            db.flush()

        # --- Groups ---
        group_names = ["BK2405", "BK2404", "BK2403"]
        groups = {}
        for name in group_names:
            group = db.query(Group).filter_by(organization_id=org.id, name=name).one_or_none()
            if group is None:
                group = Group(organization_id=org.id, specialty_id=specialty.id, name=name, academic_year="2024-2025")
                db.add(group)
                db.flush()
            groups[name] = group
            link = (
                db.query(TeacherGroup).filter_by(teacher_id=teacher.id, group_id=group.id).one_or_none()
            )
            if link is None:
                db.add(TeacherGroup(teacher_id=teacher.id, group_id=group.id))
                db.flush()

        # --- Students (5 in BK2405, 2 each in the others) ---
        student_first_names = ["Айгерим", "Дамир", "Жанна", "Ержан", "Сая", "Нурлан", "Динара"]
        all_students = []
        for i, first_name in enumerate(student_first_names):
            email = f"student{i+1}@demo.edu"
            user = make_user(db, email, f"{first_name} Студентова")
            mem = membership(db, user, org, role_student)
            student = db.query(Student).filter_by(membership_id=mem.id).one_or_none()
            if student is None:
                student = Student(membership_id=mem.id, specialty_id=specialty.id)
                db.add(student)
                db.flush()
            all_students.append(student)

        bk2405_students = all_students[:5]
        bk2404_students = all_students[5:7]
        for student in bk2405_students:
            if not db.query(GroupMember).filter_by(group_id=groups["BK2405"].id, student_id=student.id).one_or_none():
                db.add(GroupMember(group_id=groups["BK2405"].id, student_id=student.id))
        for student in bk2404_students:
            if not db.query(GroupMember).filter_by(group_id=groups["BK2404"].id, student_id=student.id).one_or_none():
                db.add(GroupMember(group_id=groups["BK2404"].id, student_id=student.id))
        db.flush()

        # --- Template + published version ---
        template = db.query(Template).filter_by(organization_id=org.id, name="Отчет по производственной практике").one_or_none()
        if template is None:
            template = Template(
                organization_id=org.id,
                created_by_teacher_id=teacher.id,
                name="Отчет по производственной практике",
                description="Стандартный шаблон отчета по практике (ГОСТ)",
            )
            db.add(template)
            db.flush()

        template_version = db.query(TemplateVersion).filter_by(template_id=template.id, version_number=1).one_or_none()
        if template_version is None:
            default_document = build_default_document()
            template_version = TemplateVersion(
                template_id=template.id,
                version_number=1,
                document_data=default_document.model_dump(mode="json"),
                schema_version=default_document.schema_version,
                is_published=True,
            )
            db.add(template_version)
            db.flush()

        # --- Internship in BK2405, published ---
        from datetime import date

        internship = db.query(Internship).filter_by(organization_id=org.id, group_id=groups["BK2405"].id).one_or_none()
        if internship is None:
            internship = Internship(
                organization_id=org.id,
                group_id=groups["BK2405"].id,
                template_version_id=template_version.id,
                created_by_teacher_id=teacher.id,
                title="Производственная практика 2025",
                description="Летняя производственная практика для группы BK2405",
                specialty_id=specialty.id,
                start_date=date(2025, 6, 1),
                end_date=date(2025, 7, 15),
                deadline=date(2025, 7, 20),
                status=InternshipStatus.PUBLISHED,
            )
            db.add(internship)
            db.flush()

            for student in bk2405_students:
                db.add(
                    Report(
                        organization_id=org.id,
                        internship_id=internship.id,
                        student_id=student.id,
                        document_data=deepcopy(template_version.document_data),
                        document_schema_version=template_version.schema_version,
                    )
                )
            db.flush()

        db.commit()

        print("Seed complete.")
        print(f"Organization slug: {org.slug}")
        print(f"Dev password for all users: {DEV_PASSWORD}")
        print("Users:")
        print("  superadmin@demo.edu  (SUPER_ADMIN)")
        print("  director@demo.edu    (DIRECTOR)")
        print("  teacher@demo.edu     (TEACHER, owns BK2405/BK2404/BK2403)")
        for i in range(len(student_first_names)):
            print(f"  student{i+1}@demo.edu    (STUDENT)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
