"""Event store — slice 6b-2.

Revision ID: 039
Revises: 038

`platform_events` is the platform's append-only, hash-chained event ledger.
**Ten modules write to it** — account vetting, tokens, TEA, packages, projects —
so this slice touches every slice already migrated. Done alone, and while the
table is EMPTY, which is the cheapest possible moment.

THE CHAIN IS GLOBAL, AND THE APPEND IS NOT CONCURRENCY-SAFE
-----------------------------------------------------------
`append_event()` does:

    SELECT event_hash FROM platform_events ORDER BY id DESC LIMIT 1   -- read
    INSERT INTO platform_events (... previous_hash = that ...)        -- write

with no lock between them, and the chain is GLOBAL (one chain for the whole
platform, not one per stream). Two concurrent appends therefore read the same
`previous_hash` and both write it — a FORK. Chain validation then sees two
events claiming the same predecessor.

SQLite hides this: it serialises writers, so the window is small and single-
process test runs never hit it. **PostgreSQL does not hide it** — a connection
pool with concurrent workers makes the fork likely rather than theoretical.

Migrating this table without addressing that would introduce a regression, not
merely move data. So the serialisation moves WITH it (advisory lock in
core/event_store.py), the same reasoning that moved project_context alongside
projects in 033 to preserve atomicity.

RLS
---
`project_id` is nullable — a platform-level event (account registration, for
instance) has no project. Those rows are PLATFORM_ADMIN-only, which is correct:
they are not any tenant's business.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column("stream", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text()),
        sa.Column("object_id", sa.Text()),
        sa.Column("project_id", sa.Text()),
        sa.Column("company_id", sa.Text()),
        sa.Column("actor_user_id", sa.Text()),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("causation_id", sa.Text()),
        sa.Column("previous_state", sa.Text()),
        sa.Column("new_state", sa.Text()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("previous_hash", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        # A fork is two events claiming the same predecessor. This makes the
        # database refuse it outright, rather than relying on the application
        # lock alone — belt and braces on the one table where a silent fork
        # would corrupt the audit trail.
        sa.UniqueConstraint("previous_hash", name="uq_platform_events_prev_hash"),
    )
    op.create_index("idx_pe_stream", "platform_events", ["stream"])
    op.create_index("idx_pe_project", "platform_events", ["project_id"])
    op.create_index("idx_pe_object", "platform_events", ["object_type", "object_id"])
    op.create_index("idx_pe_correlation", "platform_events", ["correlation_id"])
    op.create_index("idx_pe_created", "platform_events", ["created_at"])

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE platform_events ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE platform_events FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        CREATE POLICY platform_events_tenant_isolation
        ON platform_events
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
            OR app_company_owns_project(
                   project_id, current_setting('app.current_company_id', true))
            OR app_company_has_project_access(
                   project_id, current_setting('app.current_company_id', true))
        )
    """))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON platform_events TO gex_app"))
    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON SEQUENCE platform_events_id_seq TO gex_app"))


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "DROP POLICY IF EXISTS platform_events_tenant_isolation ON platform_events"))
    op.drop_table("platform_events")
