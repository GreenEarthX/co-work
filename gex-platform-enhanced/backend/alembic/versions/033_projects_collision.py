"""Resolve the `projects` table collision — the PostgreSQL shape wins.

Revision ID: 033
Revises: 032

THE COLLISION
-------------
Two different tables were both called `projects`:

  SQLite  (project_registry.ensure_project_table, 2 rows, written by the
          /projects/new on-ramp)
      project_id, name, molecule, country, location, capacity_mtpd, capex_eur,
      owner_company_name, power_model, financing_model, phase, created_by,
      created_at
      — owner is a company *NAME*, no tenant FK, no RLS.

  Postgres (migration 020, 12 rows, seeded from project_registry)
      project_id, project_name, owner_tenant_id FK→tenants, molecule, status,
      jurisdiction, capex_eur, capacity_mtpd, completion_date, metadata_json,
      is_active, created_at, updated_at
      — RLS-protected, tenant-scoped.

Ruling (user, 2026-08-07): **the PostgreSQL shape wins.**

WHAT THIS MIGRATION ADDS, AND WHY
---------------------------------
Three runtime columns have no home in the 020 shape and are real project data,
not junk. They get real columns rather than being buried in metadata_json,
because ABAC and the on-ramp read them by name:

  location    — free text site ("Bremerhaven"). No equivalent in 020.
  country     — ISO-3166 alpha-2 ("DE"). NOT the same thing as `jurisdiction`
                ("EU"), which is the regulatory regime. The old runtime code
                served `country` AS the profile's jurisdiction, conflating the
                two; keeping both columns lets that be untangled without
                changing behaviour today.
  created_by  — the user who created the project. Provenance; belongs on the row.

DELIBERATELY NOT COPIED: power_model / financing_model / phase.
The SQLite `projects` table stored these AND `project_context` stores them.
That duplication does not travel: `project_context` is their canonical home
(it is what the bankability engine and the PATCH endpoint read). `projects`
keeps only `status`, which 020 already defined.

project_context and project_context_events move too — not scope creep, but
atomicity: `create_project()` writes all three in ONE transaction. Leaving
context in SQLite while projects moved to Postgres would split that across two
stores with no way to roll back a partial create.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    op.add_column("projects", sa.Column("location", sa.Text()))
    op.add_column("projects", sa.Column("country", sa.Text()))
    op.add_column("projects", sa.Column("created_by", sa.Text()))

    op.create_table(
        "project_context",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("power_model", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("financing_model", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "project_context_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
    )
    op.create_index("idx_pce_project", "project_context_events", ["project_id"])

    conn = op.get_bind()

    # ── RLS on the context tables ───────────────────────────────────────────
    # These are per-project, and a project's visibility is already decided by
    # the policy on `projects`. Rather than restate that logic (and risk it
    # drifting), both policies DELEGATE to it via the SECURITY DEFINER helpers
    # from 032 — which is also what keeps this free of the mutual recursion
    # that 032 had to fix.
    for table in ("project_context", "project_context_events"):
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

    conn.execute(sa.text(
        f"GRANT USAGE, SELECT ON SEQUENCE project_context_events_id_seq TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("project_context_events", "project_context"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.drop_index("idx_pce_project", table_name="project_context_events")
    op.drop_table("project_context_events")
    op.drop_table("project_context")
    op.drop_column("projects", "created_by")
    op.drop_column("projects", "country")
    op.drop_column("projects", "location")
