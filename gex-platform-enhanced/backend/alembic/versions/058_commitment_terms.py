"""commitment terms — structured cards behind the offtake, EPC, schedule, supply and model.

Revision ID: 058
Revises: 057
Create Date: 2026-09-27

Evidence rules 4.0.0 grade the offtake (O0–O7) and the EPC (E0–E6) and run ten
coherence checks across contracts. Those need facts no evidence status carries:
the commitment form and take-or-pay share, the longstop and first delivery
dates, guaranteed capacity and availability, damages caps, the certification
scheme each side names, force-majeure references. They are recorded once per
project in five cards and passed to the engine with the evidence.

    commitment_terms          one row per (project, card); replaced, never deleted
    commitment_terms_events   every change, old and new JSON, with its actor

Both are tenant-scoped under the same policy as every evidence table (034).
Privileges are REVOKED explicitly: migration 031's DEFAULT PRIVILEGES give every
new table full DML for gex_app, so a GRANT alone restricts nothing (found in 056).

    commitment_terms          runtime may SELECT, INSERT, UPDATE — not DELETE
    commitment_terms_events   runtime may SELECT, INSERT only

Mirrored for SQLite in routes_bankability_proxy._ensure_tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "058"
down_revision: Union[str, None] = "057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

APP_ROLE = "gex_app"
_POLICY = """
    CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL USING (
        current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
        OR app_company_owns_project(project_id, current_setting('app.current_company_id', true))
        OR app_company_has_project_access(project_id, current_setting('app.current_company_id', true))
    )
"""


def upgrade() -> None:
    op.create_table(
        "commitment_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("card_type", sa.Text(), nullable=False),
        sa.Column("terms_json", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.UniqueConstraint("project_id", "card_type", name="uq_commitment_terms_project_card"),
    )
    op.create_index("idx_commitment_terms_project", "commitment_terms", ["project_id"])
    op.create_table(
        "commitment_terms_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("card_type", sa.Text(), nullable=False),
        sa.Column("old_json", sa.Text()),
        sa.Column("new_json", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
    )
    op.create_index("idx_commitment_terms_events_project", "commitment_terms_events", ["project_id"])

    conn = op.get_bind()
    for table in ("commitment_terms", "commitment_terms_events"):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(_POLICY.format(table=table)))
        conn.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE DELETE, TRUNCATE ON commitment_terms FROM {APP_ROLE}"))
    conn.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON commitment_terms TO {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE UPDATE, DELETE, TRUNCATE ON commitment_terms_events FROM {APP_ROLE}"))
    conn.execute(sa.text(f"GRANT SELECT, INSERT ON commitment_terms_events TO {APP_ROLE}"))


def downgrade() -> None:
    op.drop_table("commitment_terms_events")
    op.drop_table("commitment_terms")
