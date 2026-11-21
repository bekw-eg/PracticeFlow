"""Remove the report/template authoring flow and its tables.

PracticeFlow is now a teacher-only document checking tool. The student report
authoring workflow (templates, internships, reports, comments, exports and the
editor image store) is gone, so its tables and enum types are dropped. The
``audit_event_type`` enum is intentionally left untouched: historical audit
rows may still carry the removed event labels and PostgreSQL cannot drop
individual enum values.
"""
from alembic import op

revision = "9b0c1d2e3f4a"
down_revision = "8a9b0c1d2e3f"
branch_labels = None
depends_on = None

# Foreign-key safe order. ``reports`` and ``report_versions`` reference each
# other (reports.current_version_id), so that cycle is broken first.
_TABLES_IN_DROP_ORDER = (
    "comments",
    "export_jobs",
    "report_writing_snapshots",
    "report_versions",
    "reports",
    "internships",
    "template_versions",
    "templates",
    "files",
)
_ENUM_TYPES = ("comment_status", "report_status", "internship_status")


def upgrade() -> None:
    op.drop_constraint("fk_reports_current_version_id", "reports", type_="foreignkey")
    for table in _TABLES_IN_DROP_ORDER:
        op.drop_table(table)
    for enum_type in _ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_type}")


def downgrade() -> None:
    raise NotImplementedError(
        "Irreversible migration: the report/template flow tables (templates, "
        "template_versions, internships, reports, report_versions, "
        "report_writing_snapshots, comments, export_jobs, files) were "
        "permanently removed. Restore from a database backup taken before this "
        "revision instead of downgrading."
    )
