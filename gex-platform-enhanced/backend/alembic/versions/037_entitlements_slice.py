"""Entitlements — slice 6b-1.

Revision ID: 037
Revises: 036

The largest remaining data set: `entitlement_audit` (~2,665) and
`finance_entitlements` (~720) — together **97% of everything still outside
PostgreSQL**, from one module (`core/entitlements.py`), both project-scoped.

WHY THE ROW COUNTS ARE APPROXIMATE
----------------------------------
`entitlement_audit` is written on EVERY finance-access decision, including by
the test suite (`access_allowed` / `access_denied`). The count moves whenever
tests run — 2,622 at inventory, 2,665 an hour later, all from local test runs.

That is not drift to be fixed; it is what an access log does. It means the
migration must be verified **by primary key**, not by absolute count: every row
present at copy time must exist in PostgreSQL, and the destination is allowed to
have gained more. The copy is idempotent, so it can be re-run to catch up.

RLS
---
Both tables carry `project_id`, so the standard delegation applies.

`entitlement_audit.project_id` is NULLABLE, and a NULL cannot resolve to a
project — those rows are PLATFORM_ADMIN-only. That is correct rather than
unfortunate: an access decision that names no project is a platform-level event
(a denial before scope was established), and it should not surface in a
tenant's view of their own project's audit trail.

APPEND-ONLY IN PRACTICE, NOT BY CONSTRAINT
------------------------------------------
`_audit()` only ever INSERTs — there is no UPDATE or DELETE against
entitlement_audit anywhere in the module. That is a property of the code, not
of the schema, and this migration does not add a database-level guarantee:
doing so in the same change as the move would make a permission error
indistinguishable from a copy failure. Recorded as a follow-up.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    op.create_table(
        "finance_entitlements",
        sa.Column("entitlement_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("capability", sa.Text(), nullable=False,
                  server_default="FINANCE_REVIEW"),
        sa.Column("granted_by", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("expires_at", sa.Text()),
        sa.Column("revoked_at", sa.Text()),
        sa.Column("revoked_by", sa.Text()),
    )
    op.create_index("idx_fe_user", "finance_entitlements", ["user_id"])
    op.create_index("idx_fe_project", "finance_entitlements", ["project_id"])
    # The hot lookup: has_active_project_entitlement(user, project, capability).
    op.create_index("idx_fe_lookup", "finance_entitlements",
                    ["user_id", "project_id", "capability"])

    op.create_table(
        "entitlement_audit",
        sa.Column("audit_id", sa.Text(), primary_key=True),
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        # NULLABLE on purpose — a denial can precede any project scope.
        sa.Column("user_id", sa.Text()),
        sa.Column("project_id", sa.Text()),
        sa.Column("actor", sa.Text()),
        sa.Column("basis", sa.Text()),
        sa.Column("detail", sa.Text()),
        sa.CheckConstraint(
            "action IN ('granted','revoked','access_allowed','access_denied')",
            name="ck_entitlement_audit_action"),
    )
    op.create_index("idx_ea_project", "entitlement_audit", ["project_id"])
    op.create_index("idx_ea_user", "entitlement_audit", ["user_id"])
    op.create_index("idx_ea_at", "entitlement_audit", ["at"])

    conn = op.get_bind()
    admin = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
    me = "current_setting('app.current_company_id', true)"

    for table in ("finance_entitlements", "entitlement_audit"):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            FOR ALL
            USING (
                {admin}
                OR app_company_owns_project(project_id, {me})
                OR app_company_has_project_access(project_id, {me})
            )
        """))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("finance_entitlements", "entitlement_audit"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.drop_table("entitlement_audit")
    op.drop_table("finance_entitlements")
