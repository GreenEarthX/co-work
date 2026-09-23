"""Directory slice — GEX's internal staff directory, under RLS.

Revision ID: 047
Revises: 046
Create Date: 2026-09-22

WHY THIS EXISTS
---------------
`app/core/directory_store.py` refuses to run on PostgreSQL:

    directory tables hold personal data and need RLS policies from an Alembic
    migration; refusing to create them unprotected

That refusal is correct — a `CREATE TABLE IF NOT EXISTS` from the runtime
would produce the one unprotected PII table on a database where 89 tables are
under FORCED RLS. This migration is the policy the store is waiting for, so
`GOVERNANCE_DB_BACKEND=postgres` can boot.

THE POLICY, AND WHY IT IS NOT "READABLE BY ALL"
-----------------------------------------------
`routes_directory.py` already answers **403 with no rows** to any caller who is
not GEX staff, and in this codebase GEX staff *is* `is_platform_admin`. All
three platform admins sit in company `greenearthx`, and all three directory
members are GreenEarthX people. The database policy therefore states the same
rule the API states, one layer down: the row is visible to a PLATFORM_ADMIN
connection or to a caller bound to the `greenearthx` tenant, and to nobody
else. Reference data like `fuel_catalog` is `USING (true)` because failing
closed would blackhole it; a staff directory is the opposite case — nothing
outside GEX should ever read it, so `true` would be wrong here.

`greenearthx` is written literally because it is the platform operator's own
tenant, not a customer: it is the one company_id whose meaning is fixed by the
deployment rather than by data. It exists in `tenants` (seeded by 020).

The email/phone withholding in `directory_store.PII_FIELDS` stays exactly as it
is. This migration narrows who reaches the table at all; it does not replace
the column-level rule that decides who sees a phone number.

`directory_gate_status.member_id` keeps its name — it points at a directory
member, not at an authenticated user, and calling it `user_id` is precisely the
dual-identity mistake the store documents.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
GEX = "current_setting('app.current_company_id', true) = 'greenearthx'"

TABLES = ("directory_teams", "directory_roles", "directory_members",
          "directory_gates", "directory_gate_status")


def upgrade() -> None:
    op.create_table(
        "directory_teams",
        sa.Column("team_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("primary_modules", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "directory_roles",
        sa.Column("role_id", sa.Text(), primary_key=True),
        sa.Column("role_code", sa.Text(), nullable=False),
        sa.Column("role_name", sa.Text(), nullable=False),
        sa.Column("permission_tier", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_default_admin", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("team_id", sa.Text(), nullable=False),
    )
    op.create_index("idx_directory_roles_team", "directory_roles", ["team_id"])

    op.create_table(
        "directory_members",
        sa.Column("member_id", sa.Text(), primary_key=True),
        # NULL until reconcile_with_auth_users() matches by email. A directory
        # entry is not an account, so this stays nullable.
        sa.Column("auth_user_id", sa.Text()),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False, server_default=""),
        sa.Column("organisation", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.Column("primary_team_id", sa.Text(), nullable=False),
        sa.Column("primary_role_id", sa.Text(), nullable=False),
        sa.Column("secondary_team_id", sa.Text()),
        sa.Column("secondary_role_id", sa.Text()),
    )
    op.create_index("idx_directory_members_team", "directory_members", ["primary_team_id"])

    op.create_table(
        "directory_gates",
        sa.Column("gate_id", sa.Text(), primary_key=True),
        sa.Column("gate_name", sa.Text(), nullable=False),
        sa.Column("trigger_description", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "directory_gate_status",
        sa.Column("member_id", sa.Text(), primary_key=True),
        sa.Column("gate_id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
    )

    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_gex_staff_only ON {table} "
            f"FOR ALL USING ({ADMIN} OR {GEX})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_gex_staff_only ON {table}"))
    for table in reversed(TABLES):
        op.drop_table(table)
