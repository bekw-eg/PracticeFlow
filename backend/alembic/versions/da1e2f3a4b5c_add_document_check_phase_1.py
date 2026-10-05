"""add document-check profiles, rules, and assignments

Revision ID: da1e2f3a4b5c
Revises: c9d0e1f2a3b4
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "da1e2f3a4b5c"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


profile_version_status = postgresql.ENUM(
    "DRAFT", "PUBLISHED", "RETIRED", name="check_profile_version_status", create_type=False
)
check_rule_type = postgresql.ENUM(
    "PAGE_FORMAT_MARGINS",
    "FONTS_SIZES",
    "PARAGRAPH_SPACING_INDENTS",
    "HEADINGS",
    "TABLES",
    "FIGURE_CAPTIONS",
    "REFERENCES",
    "REQUIRED_SECTIONS",
    "SPELLING_LANGUAGES",
    name="check_rule_type",
    create_type=False,
)
check_rule_severity = postgresql.ENUM(
    "INFO", "WARNING", "ERROR", name="check_rule_severity", create_type=False
)
assignment_status = postgresql.ENUM(
    "DRAFT", "PUBLISHED", "CLOSED", name="document_check_assignment_status", create_type=False
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    profile_version_status.create(bind, checkfirst=True)
    check_rule_type.create(bind, checkfirst=True)
    check_rule_severity.create(bind, checkfirst=True)
    assignment_status.create(bind, checkfirst=True)

    for value in (
        "CHECK_PROFILE_CREATED",
        "CHECK_PROFILE_VERSION_CREATED",
        "CHECK_PROFILE_VERSION_PUBLISHED",
        "CHECK_PROFILE_VERSION_RETIRED",
        "DOCUMENT_CHECK_ASSIGNMENT_CREATED",
        "DOCUMENT_CHECK_ASSIGNMENT_PUBLISHED",
        "DOCUMENT_CHECK_ASSIGNMENT_CLOSED",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    # This redundant unique key changes no legacy group behavior; it is the
    # referenced key that lets assignments prove group tenant ownership in a FK.
    op.create_unique_constraint("uq_groups_org_id", "groups", ["organization_id", "id"])

    op.create_table(
        "check_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_teacher_id"], ["teachers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_check_profiles_org_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_check_profiles_org_name"),
    )
    op.create_index(
        "ix_check_profiles_org_created_id", "check_profiles", ["organization_id", "created_at", "id"]
    )

    op.create_table(
        "check_profile_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state", profile_version_status, server_default="DRAFT", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("version_number > 0", name="ck_check_profile_versions_number_positive"),
        sa.CheckConstraint(
            "(state = 'DRAFT' AND published_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'PUBLISHED' AND published_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND published_at IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_check_profile_versions_state_timestamps",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["check_profiles.organization_id", "check_profiles.id"],
            name="fk_check_profile_versions_profile_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_check_profile_versions_org_id"),
        sa.UniqueConstraint(
            "organization_id", "profile_id", "version_number", name="uq_check_profile_versions_number"
        ),
    )
    op.create_index(
        "ix_check_profile_versions_org_profile",
        "check_profile_versions",
        ["organization_id", "profile_id", "version_number"],
    )

    op.create_table(
        "check_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_type", check_rule_type, nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("severity", check_rule_severity, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("config_schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("sort_order >= 0", name="ck_check_rules_sort_nonnegative"),
        sa.CheckConstraint("config_schema_version = 1", name="ck_check_rules_schema_version"),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_check_rules_config_object"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_version_id"],
            ["check_profile_versions.organization_id", "check_profile_versions.id"],
            name="fk_check_rules_version_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_check_rules_org_id"),
        sa.UniqueConstraint(
            "organization_id", "profile_version_id", "sort_order", name="uq_check_rules_version_sort"
        ),
    )
    op.create_index(
        "ix_check_rules_org_version_sort",
        "check_rules",
        ["organization_id", "profile_version_id", "sort_order"],
    )

    op.create_table(
        "document_check_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("state", assignment_status, server_default="DRAFT", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assignment_timezone", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(state = 'DRAFT' AND published_at IS NULL AND closed_at IS NULL) OR "
            "(state = 'PUBLISHED' AND published_at IS NOT NULL AND closed_at IS NULL) OR "
            "(state = 'CLOSED' AND published_at IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_document_check_assignments_state_timestamps",
        ),
        sa.CheckConstraint("length(assignment_timezone) > 0", name="ck_document_check_assignments_timezone"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_teacher_id"], ["teachers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "group_id"],
            ["groups.organization_id", "groups.id"],
            name="fk_document_check_assignments_group_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_version_id"],
            ["check_profile_versions.organization_id", "check_profile_versions.id"],
            name="fk_document_check_assignments_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_check_assignments_org_id"),
    )
    op.create_index(
        "ix_document_check_assignments_org_group_created",
        "document_check_assignments",
        ["organization_id", "group_id", "created_at", "id"],
    )

    op.create_table(
        "assignment_students",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["document_check_assignments.organization_id", "document_check_assignments.id"],
            name="fk_assignment_students_assignment_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_assignment_students_org_id"),
        sa.UniqueConstraint(
            "organization_id", "assignment_id", "student_id", name="uq_assignment_students_roster"
        ),
    )
    op.create_index(
        "ix_assignment_students_org_assignment",
        "assignment_students",
        ["organization_id", "assignment_id", "id"],
    )

    op.execute(
        """
        CREATE FUNCTION pf_check_profile_teacher_tenant() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM teachers t
            JOIN organization_memberships m ON m.id = t.membership_id
            WHERE t.id = NEW.created_by_teacher_id AND m.organization_id = NEW.organization_id
          ) THEN
            RAISE EXCEPTION 'teacher and check profile must belong to the same organization'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_check_profile_teacher_tenant
          BEFORE INSERT OR UPDATE OF organization_id, created_by_teacher_id ON check_profiles
          FOR EACH ROW EXECUTE FUNCTION pf_check_profile_teacher_tenant();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pf_protect_check_profile_version() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.state <> 'DRAFT' THEN
              RAISE EXCEPTION 'published and retired profile versions are immutable' USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.state = 'PUBLISHED' THEN
            IF NEW.state <> 'RETIRED'
               OR (to_jsonb(NEW) - ARRAY['state','retired_at','updated_at'])
                  IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state','retired_at','updated_at']) THEN
              RAISE EXCEPTION 'published profile versions are immutable' USING ERRCODE = '23514';
            END IF;
          ELSIF OLD.state = 'RETIRED' THEN
            RAISE EXCEPTION 'retired profile versions are immutable' USING ERRCODE = '23514';
          ELSIF NEW.state NOT IN ('DRAFT', 'PUBLISHED') THEN
            RAISE EXCEPTION 'invalid profile version state transition' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_protect_check_profile_version
          BEFORE UPDATE OR DELETE ON check_profile_versions
          FOR EACH ROW EXECUTE FUNCTION pf_protect_check_profile_version();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pf_require_draft_check_rule() RETURNS trigger AS $$
        DECLARE parent_state check_profile_version_status;
        BEGIN
          SELECT state INTO parent_state FROM check_profile_versions
          WHERE id = COALESCE(NEW.profile_version_id, OLD.profile_version_id)
            AND organization_id = COALESCE(NEW.organization_id, OLD.organization_id);
          IF TG_OP = 'DELETE' AND parent_state IS NULL THEN
            RETURN OLD;
          ELSIF parent_state IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'rules of a published profile version are immutable' USING ERRCODE = '23514';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_require_draft_check_rule
          BEFORE INSERT OR UPDATE OR DELETE ON check_rules
          FOR EACH ROW EXECUTE FUNCTION pf_require_draft_check_rule();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pf_validate_document_check_assignment() RETURNS trigger AS $$
        DECLARE version_state check_profile_version_status;
        BEGIN
          IF TG_OP = 'INSERT'
             OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
             OR NEW.group_id IS DISTINCT FROM OLD.group_id
             OR NEW.created_by_teacher_id IS DISTINCT FROM OLD.created_by_teacher_id THEN
            IF NOT EXISTS (
              SELECT 1 FROM teachers t
              JOIN organization_memberships m ON m.id = t.membership_id
              JOIN teacher_groups tg ON tg.teacher_id = t.id AND tg.group_id = NEW.group_id
              WHERE t.id = NEW.created_by_teacher_id AND m.organization_id = NEW.organization_id
            ) THEN
              RAISE EXCEPTION 'assignment group must be owned by its creating teacher'
                USING ERRCODE = '23514';
            END IF;
          END IF;
          IF TG_OP = 'INSERT' OR OLD.state = 'DRAFT' THEN
            SELECT state INTO version_state FROM check_profile_versions
            WHERE id = NEW.profile_version_id AND organization_id = NEW.organization_id;
            IF version_state IS DISTINCT FROM 'PUBLISHED' THEN
              RAISE EXCEPTION 'assignment must pin a published profile version' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.state = 'PUBLISHED' THEN
              IF NEW.state <> 'CLOSED'
                 OR (to_jsonb(NEW) - ARRAY['state','closed_at','updated_at'])
                    IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state','closed_at','updated_at']) THEN
                RAISE EXCEPTION 'published assignments are immutable' USING ERRCODE = '23514';
              END IF;
            ELSIF OLD.state = 'CLOSED' THEN
              RAISE EXCEPTION 'closed assignments are immutable' USING ERRCODE = '23514';
            ELSIF NEW.state NOT IN ('DRAFT', 'PUBLISHED') THEN
              RAISE EXCEPTION 'invalid assignment state transition' USING ERRCODE = '23514';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_validate_document_check_assignment
          BEFORE INSERT OR UPDATE ON document_check_assignments
          FOR EACH ROW EXECUTE FUNCTION pf_validate_document_check_assignment();
        CREATE FUNCTION pf_protect_document_check_assignment_delete() RETURNS trigger AS $$
        BEGIN
          IF OLD.state <> 'DRAFT' THEN
            RAISE EXCEPTION 'published assignments are immutable' USING ERRCODE = '23514';
          END IF;
          RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_protect_document_check_assignment_delete
          BEFORE DELETE ON document_check_assignments
          FOR EACH ROW EXECUTE FUNCTION pf_protect_document_check_assignment_delete();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pf_validate_assignment_student() RETURNS trigger AS $$
        DECLARE assignment_state document_check_assignment_status;
        DECLARE target_org uuid;
        DECLARE target_student uuid;
        BEGIN
          target_org := COALESCE(NEW.organization_id, OLD.organization_id);
          target_student := COALESCE(NEW.student_id, OLD.student_id);
          IF NOT EXISTS (
            SELECT 1 FROM students s
            JOIN organization_memberships m ON m.id = s.membership_id
            WHERE s.id = target_student AND m.organization_id = target_org
          ) THEN
            RAISE EXCEPTION 'student and assignment must belong to the same organization'
              USING ERRCODE = '23514';
          END IF;
          SELECT state INTO assignment_state FROM document_check_assignments
          WHERE id = COALESCE(NEW.assignment_id, OLD.assignment_id)
            AND organization_id = target_org;
          IF assignment_state IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'published assignment rosters are immutable' USING ERRCODE = '23514';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_validate_assignment_student
          BEFORE INSERT OR UPDATE OR DELETE ON assignment_students
          FOR EACH ROW EXECUTE FUNCTION pf_validate_assignment_student();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_validate_assignment_student ON assignment_students")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_assignment_student()")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_document_check_assignment_delete ON document_check_assignments")
    op.execute("DROP FUNCTION IF EXISTS pf_protect_document_check_assignment_delete()")
    op.execute("DROP TRIGGER IF EXISTS trg_validate_document_check_assignment ON document_check_assignments")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_document_check_assignment()")
    op.execute("DROP TRIGGER IF EXISTS trg_require_draft_check_rule ON check_rules")
    op.execute("DROP FUNCTION IF EXISTS pf_require_draft_check_rule()")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_check_profile_version ON check_profile_versions")
    op.execute("DROP FUNCTION IF EXISTS pf_protect_check_profile_version()")
    op.execute("DROP TRIGGER IF EXISTS trg_check_profile_teacher_tenant ON check_profiles")
    op.execute("DROP FUNCTION IF EXISTS pf_check_profile_teacher_tenant()")
    op.drop_index("ix_assignment_students_org_assignment", table_name="assignment_students")
    op.drop_table("assignment_students")
    op.drop_index("ix_document_check_assignments_org_group_created", table_name="document_check_assignments")
    op.drop_table("document_check_assignments")
    op.drop_index("ix_check_rules_org_version_sort", table_name="check_rules")
    op.drop_table("check_rules")
    op.drop_index("ix_check_profile_versions_org_profile", table_name="check_profile_versions")
    op.drop_table("check_profile_versions")
    op.drop_index("ix_check_profiles_org_created_id", table_name="check_profiles")
    op.drop_table("check_profiles")
    op.drop_constraint("uq_groups_org_id", "groups", type_="unique")
    assignment_status.drop(op.get_bind(), checkfirst=True)
    check_rule_severity.drop(op.get_bind(), checkfirst=True)
    check_rule_type.drop(op.get_bind(), checkfirst=True)
    profile_version_status.drop(op.get_bind(), checkfirst=True)
    # Audit enum values remain because PostgreSQL cannot remove individual
    # values without destructively rebuilding the type and its history.
