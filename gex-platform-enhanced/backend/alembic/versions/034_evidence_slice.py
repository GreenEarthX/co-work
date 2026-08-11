"""Evidence & bankability slice — investor-facing data under RLS.

Revision ID: 034
Revises: 033

Strangler slice 4 of docs/postgres-migration-plan.md, which calls this the
"highest business value under RLS (investor-facing data)". Everything here is
project-scoped, so every table gets a tenant-isolation policy that DELEGATES to
the SECURITY DEFINER helpers from 032 rather than restating the visibility rule
— one place decides who can see a project.

IN SCOPE (the plan's stated set)
    bankability_evidence   116 rows   the evidence grid behind every gate
    bankability_snapshots    8 rows   last evaluated gate state per project
    evidence_documents       3 rows   uploaded artifacts (sha256 + path)
    evidence_events          4 rows   append-only status transitions
    evidence_ledger          0 rows   hash-chained immutable ledger

DELIBERATELY NOT IN SCOPE
    package_evidence          -> slice 5 (development packages) owns it
    pre_cod_snapshots,
    pre_cod_metric_snapshots  -> derived metrics, not evidence
    gateway_registry          -> OT boundary, unrelated

TYPE FIDELITY, AGAIN
--------------------
Timestamps stay TEXT and the boolean-ish columns stay as they are, for the same
reason as 030: the application compares ISO strings as strings, and a slice that
moves storage AND changes types has ambiguous failures. The INTEGER
AUTOINCREMENT primary keys DO become real identity columns, because Postgres has
no AUTOINCREMENT — the copy script resets each sequence past the copied maximum.

THE HASH CHAIN
--------------
`evidence_ledger` is hash-chained: each row's `hash` covers its own fields plus
`prev_hash`. It is EMPTY today, so there is no existing chain to preserve — but
the chain must still work after the move, and a chain that cannot be validated
in its new home is worse than no chain. tests/test_evidence_slice.py builds a
chain in PostgreSQL and validates it, then tampers with a row and confirms
validation fails.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"

# Every table here is project-scoped, so the same policy shape applies to all.
_PROJECT_SCOPED = (
    "bankability_evidence",
    "bankability_snapshots",
    "evidence_documents",
    "evidence_events",
    "evidence_ledger",
)


def upgrade() -> None:
    op.create_table(
        "bankability_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False, server_default="default"),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="NOT_STARTED"),
        sa.Column("submitted_by", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("submitted_at", sa.Text()),
        sa.Column("verified_at", sa.Text()),
        sa.Column("document_hash", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.UniqueConstraint("project_id", "evidence_key",
                            name="uq_bankability_evidence_project_key"),
    )
    op.create_index("idx_bev_project", "bankability_evidence", ["project_id"])

    op.create_table(
        "bankability_snapshots",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("current_state", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text()),
        sa.Column("evaluated_at", sa.Text()),
    )

    op.create_table(
        "evidence_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_evdoc_project", "evidence_documents", ["project_id"])

    op.create_table(
        "evidence_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("old_status", sa.Text()),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("document_sha256", sa.Text()),
    )
    op.create_index("idx_evev_project", "evidence_events", ["project_id"])

    op.create_table(
        "evidence_ledger",
        sa.Column("evidence_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("document_ref", sa.Text(), nullable=False),
        # Two ORTHOGONAL axes — do not merge them. An artifact can be AUDITED
        # (assurance) and SUPERSEDED (lifecycle) at the same time.
        sa.Column("verification_state", sa.Text(), nullable=False,
                  server_default="UNVERIFIED"),
        sa.Column("claim_state", sa.Text(), nullable=False, server_default="asserted"),
        sa.Column("reviewer_id", sa.Text()),
        sa.Column("submitted_by", sa.Text(), nullable=False),
        # Custody: mandatory above UNVERIFIED and inside the hash. Chain of
        # custody without the custodian is not chain of custody.
        sa.Column("verified_by", sa.Text()),
        sa.Column("valid_until", sa.Text()),
        sa.Column("superseded_by", sa.Text()),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("timestamp", sa.Text(), nullable=False),
    )
    op.create_index("idx_evledger_project", "evidence_ledger", ["project_id"])
    # The chain is walked per project in insertion order.
    op.create_index("idx_evledger_chain", "evidence_ledger", ["project_id", "timestamp"])

    conn = op.get_bind()
    for table in _PROJECT_SCOPED:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
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
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))

    for seq_table in ("bankability_evidence", "evidence_documents", "evidence_events"):
        conn.execute(sa.text(
            f"GRANT USAGE, SELECT ON SEQUENCE {seq_table}_id_seq TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in _PROJECT_SCOPED:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.drop_table("evidence_ledger")
    op.drop_table("evidence_events")
    op.drop_table("evidence_documents")
    op.drop_table("bankability_snapshots")
    op.drop_table("bankability_evidence")
