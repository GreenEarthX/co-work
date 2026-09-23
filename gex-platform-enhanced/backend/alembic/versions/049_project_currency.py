"""project_currency — the project's working base currency, under RLS.

Revision ID: 049
Revises: 048
Create Date: 2026-09-22

`routes_tea.py` created this table at runtime with CREATE TABLE IF NOT EXISTS
against SQLite, so it was the last thing keeping that module on the old store
once the 043/044 domain tail moved. One row today.

It is project-scoped and gets the same policy as the project-scoped tables in
044 — owner company, or a company with explicit project access, or
PLATFORM_ADMIN. Not `USING (true)`: the working currency of a project is a
commercial fact about that project, and 044 already decided that a table with a
`project_id` has no excuse to be readable platform-wide.

`base_currency` carries no default here. SQLite's copy had none either; the
"default is EUR" lives in `_project_currency()`, which returns None when unset
and lets the caller apply EUR. A column default would turn "nobody has chosen"
into "somebody chose EUR", which is the distinction the TEA currency work
(G5) exists to keep.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"


def upgrade() -> None:
    op.create_table(
        "project_currency",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("base_currency", sa.Text(), nullable=False),
        sa.Column("set_by", sa.Text()),
        sa.Column("set_at", sa.Text(), nullable=False),
    )

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE project_currency ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE project_currency FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text(
        "CREATE POLICY project_currency_tenant_isolation ON project_currency "
        f"FOR ALL USING ({ADMIN} OR app_company_owns_project(project_id, {ME}) "
        f"OR app_company_has_project_access(project_id, {ME}))"))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON project_currency TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS project_currency_tenant_isolation ON project_currency"))
    op.drop_table("project_currency")
