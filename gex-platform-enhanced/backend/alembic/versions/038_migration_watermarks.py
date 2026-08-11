"""Migration watermarks — record what each copy actually covered.

Revision ID: 038
Revises: 037

WHY THIS EXISTS
---------------
During a strangler migration BOTH stores are live: whichever backend the app
(or the test suite) is pointed at keeps writing while the other holds a
snapshot. So "SQLite and PostgreSQL contain the same rows" is not a property
that can ever hold, and a verification asserting it fails for reasons unrelated
to the migration.

The property that IS verifiable: *everything that existed when the copy ran
must be in PostgreSQL.* That needs the copy to say what it covered.

Inferring it from `max(timestamp)` does not work — `entitlement_audit.at` has
SECOND precision and many rows share a value, so `at <= max` sweeps in source
rows written in the same second that were never copied. The watermark has to be
recorded, not deduced.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "migration_watermarks",
        sa.Column("table_name", sa.Text(), primary_key=True),
        sa.Column("copied_at", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        # The primary keys the copy actually wrote. Explicit beats inferred:
        # membership is exact, with no timestamp-granularity guesswork.
        sa.Column("copied_keys", sa.Text(), nullable=False, server_default="[]"),
    )
    # Platform metadata, not tenant data — admin only.
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE migration_watermarks ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE migration_watermarks FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        CREATE POLICY migration_watermarks_admin_only ON migration_watermarks
        FOR ALL USING (
            current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN')
    """))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON migration_watermarks TO gex_app"))


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "DROP POLICY IF EXISTS migration_watermarks_admin_only ON migration_watermarks"))
    op.drop_table("migration_watermarks")
