import os
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.documents.defaults import build_default_document
from app.main import app
from app.models.enums import RoleName
from app.models.group import Group
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.role import Role
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.template import Template
from app.models.template_version import TemplateVersion
from app.models.user import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is required. Start docker-compose.test.yml and point it to a dedicated *_test database."
    )

test_database_name = urlparse(TEST_DATABASE_URL.replace("postgresql+psycopg", "postgresql", 1)).path.lstrip("/")
configured_database_url = os.getenv("DATABASE_URL")
if not test_database_name.lower().endswith("_test"):
    raise RuntimeError("Refusing to run tests: TEST_DATABASE_URL database name must end with '_test'.")
if configured_database_url and TEST_DATABASE_URL == configured_database_url:
    raise RuntimeError("Refusing to run tests: TEST_DATABASE_URL must differ from DATABASE_URL.")

engine = create_engine(TEST_DATABASE_URL, future=True)
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

DEV_PASSWORD = "Practice123!"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    # Collection search uses PostgreSQL trigram indexes.  Keep the direct
    # metadata test schema equivalent to the Alembic migration schema.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table before each test so tests are independent, without
    the complexity of SAVEPOINT-based rollback (services call db.commit()
    internally, which would release a savepoint-based transaction anyway)."""
    def truncate() -> None:
        with engine.connect() as conn:
            table_names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
            conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
            conn.commit()

    truncate()
    try:
        yield
    finally:
        # Several services commit internally.  Cleaning again guarantees that
        # the following test never inherits such data, including after errors.
        truncate()


@pytest.fixture
def db() -> Session:
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _get_or_create_role(db: Session, name: RoleName) -> Role:
    role = db.query(Role).filter_by(name=name.value).one_or_none()
    if role is None:
        role = Role(name=name.value)
        db.add(role)
        db.flush()
    return role


class OrgFixture:
    """Small builder for a fully-wired organization used across tests:
    one teacher owning one group, with a student inside it."""

    def __init__(self, db: Session, slug: str):
        self.db = db
        self.org = Organization(name=slug, slug=slug)
        db.add(self.org)
        db.flush()

        self.role_teacher = _get_or_create_role(db, RoleName.TEACHER)
        self.role_student = _get_or_create_role(db, RoleName.STUDENT)

        self.teacher_user = User(email=f"teacher@{slug}.edu", hashed_password=hash_password(DEV_PASSWORD), full_name="Test Teacher")
        db.add(self.teacher_user)
        db.flush()
        teacher_membership = OrganizationMembership(user_id=self.teacher_user.id, organization_id=self.org.id, role_id=self.role_teacher.id)
        db.add(teacher_membership)
        db.flush()
        self.teacher = Teacher(membership_id=teacher_membership.id)
        db.add(self.teacher)
        db.flush()

        self.student_user = User(email=f"student@{slug}.edu", hashed_password=hash_password(DEV_PASSWORD), full_name="Test Student")
        db.add(self.student_user)
        db.flush()
        student_membership = OrganizationMembership(user_id=self.student_user.id, organization_id=self.org.id, role_id=self.role_student.id)
        db.add(student_membership)
        db.flush()
        self.student = Student(membership_id=student_membership.id)
        db.add(self.student)
        db.flush()

        self.group = Group(organization_id=self.org.id, name=f"{slug.upper()}-G1")
        db.add(self.group)
        db.flush()
        db.add(TeacherGroup(teacher_id=self.teacher.id, group_id=self.group.id))

        self.template = Template(organization_id=self.org.id, created_by_teacher_id=self.teacher.id, name="Test Template")
        db.add(self.template)
        db.flush()
        default_document = build_default_document()
        self.template_version = TemplateVersion(
            template_id=self.template.id,
            version_number=1,
            document_data=default_document.model_dump(mode="json"),
            is_published=True,
        )
        db.add(self.template_version)
        db.commit()

    def login(self, client: TestClient, email: str) -> str:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": DEV_PASSWORD, "organization_slug": self.org.slug},
        )
        # Test helpers deliberately complete the same MFA flow as a browser
        # when a fixture creates a privileged user.  This keeps authorization
        # tests focused on their policy while MFA behavior has dedicated tests.
        if resp.status_code == 202 and resp.json().get("status") == "MFA_ENROLLMENT_REQUIRED":
            challenge_id = resp.json()["challenge_id"]
            enrollment = client.post("/api/v1/auth/mfa/enrollment/start", json={"challenge_id": challenge_id})
            assert enrollment.status_code == 200, enrollment.text
            from app.services.mfa_service import MfaService

            code = MfaService._totp(enrollment.json()["manual_key"], MfaService._totp_counter())
            resp = client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": code})
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    def teacher_token(self, client: TestClient) -> str:
        return self.login(client, self.teacher_user.email)

    def student_token(self, client: TestClient) -> str:
        return self.login(client, self.student_user.email)


@pytest.fixture
def org_a(db: Session) -> OrgFixture:
    return OrgFixture(db, "org-a")


@pytest.fixture
def org_b(db: Session) -> OrgFixture:
    return OrgFixture(db, "org-b")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
