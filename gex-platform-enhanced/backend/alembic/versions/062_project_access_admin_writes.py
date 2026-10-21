"""RLS — only GEX administration writes project_access.

Revision ID: 062
Revises: 061

THE BUG
-------
project_access decides what every tenant-scoped policy lets a company read:
app_company_has_project_access (032) is called by the policies on evidence,
commitment cards, project context, projects and more. Its own policy, from 020
and 032, is ONE `FOR ALL` policy with no WITH CHECK:

    USING ( current company = 'PLATFORM_ADMIN'
            OR company_id = current company
            OR app_company_owns_project(project_id, current company) )

With no WITH CHECK, PostgreSQL uses the USING expression as the write check, so
`company_id = current company` let a tenant INSERT a row naming ITSELF on any
project. Reproduced 2026-10-21 as gex_app: madrid2_com, with no access to
proj_hamburgone_emethanol, inserted one row and could then read all 47 of
HamburgOne's evidence rows (rolled back). The owner clause likewise let an owner
grant any company access, and a tenant could rewrite or delete its own row.

No application route exposed it — the only runtime writers, app/core/tenant_admin.py
and app/core/reviewer_appointments.py, run as PLATFORM_ADMIN — so this is defence
in depth against injection. But RLS is documented as the access control, and this
one write defeated every policy that consults the table.

THE FIX
-------
Reads keep the existing rule exactly. Writes (INSERT, UPDATE, DELETE) need
PLATFORM_ADMIN. Granting access is GEX administration, consistent with JML's
decision of 2026-10-21 that GEX staff appoint reviewers. Letting an owner grant
would be one more OR in the write policies; it is deliberately not there.
FORCE RLS is untouched. The migration ASSERTS the resulting policy set.

Scripts that load fixtures connect as the migration role (gex_user, BYPASSRLS)
and are unaffected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id', true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN')"
READ = (f"({ADMIN} OR (company_id = {CURRENT}) "
        f"OR app_company_owns_project(project_id, {CURRENT}))")

EXPECTED = {
    "project_access_read": "SELECT",
    "project_access_admin_insert": "INSERT",
    "project_access_admin_update": "UPDATE",
    "project_access_admin_delete": "DELETE",
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP POLICY IF EXISTS project_access_tenant_isolation ON project_access"))
    conn.execute(sa.text(f"CREATE POLICY project_access_read ON project_access FOR SELECT USING {READ}"))
    conn.execute(sa.text(f"CREATE POLICY project_access_admin_insert ON project_access FOR INSERT WITH CHECK {ADMIN}"))
    conn.execute(sa.text(f"CREATE POLICY project_access_admin_update ON project_access FOR UPDATE "
                         f"USING {ADMIN} WITH CHECK {ADMIN}"))
    conn.execute(sa.text(f"CREATE POLICY project_access_admin_delete ON project_access FOR DELETE USING {ADMIN}"))

    # Assert rather than trust (the lesson of 059): exactly these four, RLS still forced.
    rows = conn.execute(sa.text(
        "SELECT policyname, cmd FROM pg_policies WHERE tablename = 'project_access'")).fetchall()
    found = {r[0]: r[1] for r in rows}
    if found != EXPECTED:
        raise RuntimeError(f"project_access policies are {found}, expected {EXPECTED}")
    forced = conn.execute(sa.text(
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'project_access'")).scalar()
    if not forced:
        raise RuntimeError("project_access no longer has FORCED row-level security")


def downgrade() -> None:
    conn = op.get_bind()
    for name in EXPECTED:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {name} ON project_access"))
    # Back to 032's single FOR ALL policy, bug included: a downgrade restores the
    # state it found, it does not invent a third one.
    conn.execute(sa.text(f"CREATE POLICY project_access_tenant_isolation ON project_access USING {READ}"))
