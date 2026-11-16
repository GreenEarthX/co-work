"""RLS — only the project owner and GEX write custody lots and deliveries (G-21).

Revision ID: 100
Revises: 099

THE BUG
-------
044 gave `mass_balance_lots` and `deliveries` one `FOR ALL` policy each, with no WITH CHECK:

    USING ( current company = 'PLATFORM_ADMIN'
            OR app_company_owns_project(project_id, current company)
            OR app_company_has_project_access(project_id, current company) )

With no WITH CHECK, PostgreSQL uses USING as the write check. Any company holding a
`project_access` row on a project — a reviewer, a lender, a stakeholder — could INSERT,
UPDATE and DELETE that project's custody lots and deliveries. Reproduced 2026-11-12 as
gex_app in tests/test_custody_write_policies_pg.py: a REVIEWER company inserted and
rewrote both. 097 had already closed the same hole for allocations and the new custody
tables; these two were left (gap G-21, and the GreenMesh Phase 2 brief, Step 1).

THE FIX
-------
Reads keep the 044 rule exactly. INSERT, UPDATE and DELETE need the project's owner or
PLATFORM_ADMIN, with WITH CHECK on INSERT and UPDATE so a row cannot be moved onto another
project either. Phase 2 Step 2 will give deliveries their party rules (seller dispatches,
buyer receives); until then nothing writes them at all. FORCE RLS is untouched. The
migration ASSERTS the resulting policy set (the lesson of 059).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "100"
down_revision: Union[str, None] = "099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
OWNER = f"app_company_owns_project(project_id, {CURRENT})"
READ = f"({ADMIN} OR {OWNER} OR app_company_has_project_access(project_id, {CURRENT}))"
WRITE = f"({ADMIN} OR {OWNER})"

TABLES = {"mass_balance_lots": "mass_balance_lots_tenant_isolation",
          "deliveries": "deliveries_tenant_isolation"}


def _expected(t: str) -> dict:
    return {f"{t}_read": "SELECT", f"{t}_owner_insert": "INSERT",
            f"{t}_owner_update": "UPDATE", f"{t}_owner_delete": "DELETE"}


def upgrade() -> None:
    conn = op.get_bind()
    for t, old in TABLES.items():
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {old} ON {t}"))
        conn.execute(sa.text(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING {READ}"))
        conn.execute(sa.text(f"CREATE POLICY {t}_owner_insert ON {t} FOR INSERT WITH CHECK {WRITE}"))
        conn.execute(sa.text(f"CREATE POLICY {t}_owner_update ON {t} FOR UPDATE USING {WRITE} WITH CHECK {WRITE}"))
        conn.execute(sa.text(f"CREATE POLICY {t}_owner_delete ON {t} FOR DELETE USING {WRITE}"))

        rows = conn.execute(sa.text("SELECT policyname, cmd FROM pg_policies WHERE tablename = :t"), {"t": t}).fetchall()
        found = {r[0]: r[1] for r in rows}
        if found != _expected(t):
            raise RuntimeError(f"{t} policies are {found}, expected {_expected(t)}")
        forced = conn.execute(sa.text(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": t}).scalar()
        if not forced:
            raise RuntimeError(f"{t} no longer has FORCED row-level security")


def downgrade() -> None:
    conn = op.get_bind()
    for t, old in TABLES.items():
        for name in _expected(t):
            conn.execute(sa.text(f"DROP POLICY IF EXISTS {name} ON {t}"))
        # Back to 044's single FOR ALL policy, hole included: a downgrade restores the state it found.
        conn.execute(sa.text(f"CREATE POLICY {old} ON {t} USING {READ}"))
