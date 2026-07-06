"""Project profile intelligence table

Revision ID: 021
Revises: 020
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "project_profile_intelligence",
        sa.Column("record_id", sa.Text, primary_key=True),
        sa.Column(
            "project_id",
            sa.Text,
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("source_scope", sa.Text, nullable=False, server_default="GEX_PUBLIC_PREFILL"),
        sa.Column("access_tier", sa.Text, nullable=False, server_default="STAKEHOLDER"),
        sa.Column("backend_store", sa.Text, nullable=False, server_default="project_profile_intelligence"),
        sa.Column("linked_records", postgresql.JSONB, server_default="'[]'"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_project_profile_intelligence_project",
        "project_profile_intelligence",
        ["project_id"],
    )

    conn.execute(sa.text("ALTER TABLE project_profile_intelligence ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE project_profile_intelligence FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        CREATE POLICY project_profile_intelligence_tenant_isolation
        ON project_profile_intelligence
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) IN ('', 'PLATFORM_ADMIN')
            OR EXISTS (
                SELECT 1 FROM projects p
                WHERE p.project_id = project_profile_intelligence.project_id
            )
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS project_profile_intelligence_tenant_isolation "
        "ON project_profile_intelligence"
    ))
    op.drop_index("idx_project_profile_intelligence_project", table_name="project_profile_intelligence")
    op.drop_table("project_profile_intelligence")
