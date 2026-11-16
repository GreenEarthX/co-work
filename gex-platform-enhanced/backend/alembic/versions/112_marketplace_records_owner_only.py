"""Marketplace records are the owning company's alone (and GEX's).

Revision ID: 112
Revises: 111

066 let any company that may see a project read its `project_sales_detail` and
`project_input_line` (`app_company_can_see_capacity`, the generic "may see this
project" helper). Those rows are the producer's confidential economics — supplier
names and prices, break-even, and its sales pipeline with OTHER buyers' names,
volumes and prices. Measured 2026-11-13: BremenThree AG, a STAKEHOLDER on
proj_hamburgone_emethanol, read HamburgOne's PPA supplier at 62 EUR/MWh, its
break-even, and a pending 18 MTPD sale to a third buyer at 960 EUR/t, through
GET /api/v1/market/project-economics and on Commercial Overview and Purchase.

Now SELECT needs the owning company (`app_company_owns_project`) or GEX. A stakeholder
reads nothing; sharing a projection with a stakeholder is a separate, owner-approved
feature, not this table. Writes are unchanged (GEX only). `input_classification` is
reference data and stays readable by all. `app_company_can_see_capacity` is NOT
redefined: eight other policies use it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "112"
down_revision: Union[str, None] = "111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
TABLES = ("project_sales_detail", "project_input_line")
OWNER_READ = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
SEES_READ = f"({ADMIN} OR app_company_can_see_capacity(project_id, {CURRENT}))"   # 066's rule


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _replace_read(rule: str) -> None:
    for table in TABLES:
        _q(f"DROP POLICY {table}_read ON {table}")
        _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING {rule}")


def upgrade() -> None:
    _replace_read(OWNER_READ)
    rows = op.get_bind().execute(sa.text(
        "SELECT tablename, qual FROM pg_policies WHERE tablename = ANY(:t) AND cmd = 'SELECT'"),
        {"t": list(TABLES)}).fetchall()
    assert len(rows) == len(TABLES), f"expected one SELECT policy per table, found {rows}"
    for table, qual in rows:
        assert "app_company_owns_project" in qual and "app_company_can_see_capacity" not in qual, \
            f"{table}: read policy is not owner-only: {qual}"
    forced = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(TABLES)}).scalar()
    assert forced == len(TABLES), f"only {forced} of {len(TABLES)} tables under FORCED RLS"


def downgrade() -> None:
    _replace_read(SEES_READ)
