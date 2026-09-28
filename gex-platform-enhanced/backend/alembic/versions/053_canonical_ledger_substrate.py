"""canonical ledger on a ruled substrate — Decision 4, PostgreSQL not SQLite.

Revision ID: 053
Revises: 052
Create Date: 2026-09-24

`app/core/canonical_ledger.py` refuses to accumulate canonical truth on an
unruled substrate: without `CANONICAL_DATABASE_URL` it raises SubstrateError, and
`GEX_CANONICAL_DEV=1` only waives that onto a local SQLite file that every entry
is then stamped `substrate: "sqlite-dev"` to disclose. That file sits outside the
PostgreSQL backups and outside RLS, so it is a dev crutch, not the substrate.

This migration owns the schema so the runtime does not have to. `gex_app` holds no
CREATE on schema public — measured, it is refused even for
`CREATE TABLE IF NOT EXISTS` against a table that already exists — so the module's
`init_db()` cannot create these at runtime, and a runtime-created table would carry
no RLS policy anyway. Same division as 044/049: DDL here, rows there.

RLS follows the shape of the data, per the two tail-slice guardrails:
  - `canonical_ledger_entries` carries `project_id`, so it gets a real tenant
    policy (owner OR granted access OR PLATFORM_ADMIN).
  - `evidence_links` and `ledger_migration_map` carry no project column, so no
    honest tenant policy exists for them and they are admin-only — the same call
    036 made for `tb_*`. A policy that only appears to isolate is worse than none.
All three are FORCED so the table owner does not bypass.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"

_TABLES = ("canonical_ledger_entries", "evidence_links", "ledger_migration_map")


def upgrade() -> None:
    op.create_table(
        "canonical_ledger_entries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("produced_by", sa.Text(), nullable=False),
        sa.Column("verified_by", sa.Text()),
        sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("valid_to", sa.Text()),
        sa.Column("recorded_at", sa.Text(), nullable=False),
        sa.Column("regulatory_cliff", sa.Text()),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes", sa.Text()),
        sa.Column("reconciliation_group_id", sa.Text()),
    )
    op.create_index("idx_cle_project", "canonical_ledger_entries", ["project_id"])

    op.create_table(
        "evidence_links",
        sa.Column("link_id", sa.Text(), primary_key=True),
        sa.Column("claim_id", sa.Text(), nullable=False),
        sa.Column("ledger_entry_id", sa.Text(), nullable=False),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.Column("linked_at", sa.Text(), nullable=False),
        sa.Column("linked_by", sa.Text(), nullable=False),
        sa.Column("evidence_hash_at_link", sa.Text(), nullable=False),
        sa.Column("migration_run_id", sa.Text()),
        sa.UniqueConstraint("claim_id", "ledger_entry_id", "link_type",
                            name="uq_evidence_links_claim_entry_type"),
    )

    op.create_table(
        "ledger_migration_map",
        sa.Column("map_id", sa.Text(), primary_key=True),
        sa.Column("legacy_table", sa.Text(), nullable=False),
        sa.Column("legacy_record_id", sa.Text(), nullable=False),
        sa.Column("new_ledger_entry_id", sa.Text()),
        sa.Column("migration_version", sa.Text(), nullable=False),
        sa.Column("migration_run_id", sa.Text(), nullable=False),
        sa.Column("migration_timestamp", sa.Text(), nullable=False),
        sa.Column("migrated_by", sa.Text(), nullable=False),
        sa.Column("legacy_content_hash", sa.Text(), nullable=False),
        sa.Column("new_content_hash", sa.Text()),
        sa.Column("migration_status", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.Text(), nullable=False,
                  server_default="pending"),
        sa.Column("quarantine_reason", sa.Text()),
        sa.UniqueConstraint("legacy_table", "legacy_record_id", "migration_version",
                            name="uq_ledger_migration_map_legacy_version"),
    )

    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

    # project-scoped: a real tenant policy
    conn.execute(sa.text(
        "CREATE POLICY canonical_ledger_entries_tenant_isolation "
        "ON canonical_ledger_entries "
        f"FOR ALL USING ({ADMIN} OR app_company_owns_project(project_id, {ME}) "
        f"OR app_company_has_project_access(project_id, {ME}))"))

    # no project column -> admin-only, rather than a policy that only looks like one
    for table in ("evidence_links", "ledger_migration_map"):
        conn.execute(sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ({ADMIN})"))

    for table in _TABLES:
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.drop_table("ledger_migration_map")
    op.drop_table("evidence_links")
    op.drop_index("idx_cle_project", table_name="canonical_ledger_entries")
    op.drop_table("canonical_ledger_entries")
