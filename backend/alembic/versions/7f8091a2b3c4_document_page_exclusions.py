"""Document-owned preview page exclusions; immutable runs keep their own snapshot."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "7f8091a2b3c4"
down_revision = "6e7f8091a2b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_check_settings", sa.Column("page_exclusions", pg.JSONB(),
                                                     nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_check_constraint("ck_document_settings_page_exclusions", "document_check_settings",
                               "jsonb_typeof(page_exclusions) = 'object'")


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM document_check_settings
                 WHERE coalesce(jsonb_array_length(page_exclusions->'pages'), 0) > 0) THEN
        RAISE EXCEPTION 'Cannot discard saved page exclusions; clear them explicitly or roll forward';
      END IF;
    END $$;
    """)
    op.drop_constraint("ck_document_settings_page_exclusions", "document_check_settings", type_="check")
    op.drop_column("document_check_settings", "page_exclusions")
