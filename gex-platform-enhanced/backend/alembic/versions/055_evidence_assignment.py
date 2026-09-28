"""evidence assignment — a named person owns each evidence request.

Adds bankability_evidence.assignee_user_id / assigned_by / assigned_at /
due_date, evidence_events.old_assignee / new_assignee, and the
bankability_evidence_archive table.

Revision ID: 055
Revises: 054
Create Date: 2026-09-26

Why. Until this revision an evidence item had an owner FUNCTION (LEGAL,
ENGINEERING, ...) and no owner. "Ownership is labels, not assignments" was a
standing open item: nothing said which person at the client had to produce the
document, or by when, so a gate could sit incomplete with nobody accountable.

assignee_user_id is an auth_users.user_id. It is text with no foreign key on
purpose: auth_users lives behind the AUTH_ switch and may sit in another store.
The write path (routes_bankability_proxy.assign_evidence) checks that the
assignee is an ACTIVE account of the company that owns the project.

due_date is nullable and nothing here sets it. A deadline is the client's
commitment to make; defaulting one would be the platform inventing it.

The append-only audit trail records reassignment (old_assignee/new_assignee)
for the same reason it records maturity changes: who is answerable for a
document is a fact someone may later need to prove.

bankability_evidence_archive holds evidence rows removed from the live table,
verbatim, with who removed them, when, why, and what replaced them. It exists
because the 127 rows present on 2026-09-26 were all invented — 125 written by
the demo seed endpoint removed on 2026-09-23 and 2 entered by hand with
invented content — and the system of record must not lose them silently
either. Same tenant-isolation policy as every other evidence table (034);
the runtime role may READ it, never write it — which the GRANT below does NOT
achieve on its own: migration 031's default privileges had already given
gex_app full DML. Migration 056 revokes it.

Mirrored for SQLite in routes_bankability_proxy._ensure_tables (columns only;
the archive is written by scripts/convert_invented_evidence.py, which runs on
PostgreSQL with the migration credential).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    for col in ("assignee_user_id", "assigned_by", "assigned_at", "due_date"):
        op.add_column("bankability_evidence", sa.Column(col, sa.Text(), nullable=True))
    op.create_index("idx_bev_assignee", "bankability_evidence", ["assignee_user_id"])
    op.add_column("evidence_events", sa.Column("old_assignee", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("new_assignee", sa.Text(), nullable=True))

    op.create_table(
        "bankability_evidence_archive",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("original_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text()),
        sa.Column("submitted_by", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("submitted_at", sa.Text()),
        sa.Column("verified_at", sa.Text()),
        sa.Column("document_hash", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.Column("maturity", sa.Text()),
        sa.Column("archived_at", sa.Text(), nullable=False),
        sa.Column("archived_by", sa.Text(), nullable=False),
        sa.Column("archive_reason", sa.Text(), nullable=False),
        # REQUESTED: the live row was reset to an open request for the same key.
        # REPLACED:  the key was retired; an open request for `replaced_by` exists.
        # REMOVED:   nothing replaces it (e.g. the row had no owning project).
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("replaced_by", sa.Text()),
    )
    op.create_index("idx_bev_archive_project", "bankability_evidence_archive", ["project_id"])

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE bankability_evidence_archive ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE bankability_evidence_archive FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        CREATE POLICY bankability_evidence_archive_tenant_isolation
        ON bankability_evidence_archive
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
            OR app_company_owns_project(
                   project_id, current_setting('app.current_company_id', true))
            OR app_company_has_project_access(
                   project_id, current_setting('app.current_company_id', true))
        )
    """))
    # Read-only for the runtime. The archive is history; only the migration
    # credential writes it.
    conn.execute(sa.text(f"GRANT SELECT ON bankability_evidence_archive TO {APP_ROLE}"))


def downgrade() -> None:
    op.drop_table("bankability_evidence_archive")
    op.drop_column("evidence_events", "new_assignee")
    op.drop_column("evidence_events", "old_assignee")
    op.drop_index("idx_bev_assignee", table_name="bankability_evidence")
    for col in ("due_date", "assigned_at", "assigned_by", "assignee_user_id"):
        op.drop_column("bankability_evidence", col)
