"""Screen access rules — per-company tailoring of which screens each function opens.

Revision ID: 060
Revises: 059
Create Date: 2026-10-19

The menu's `visible_to` lists (frontend/src/config/menuArchitecture.ts) are the
platform DEFAULT for who may open a screen. A client's CISO tailors that default
for their own company: open a screen to a function that does not have it, or
close one that does. One row per (company, screen, business function).

COMPANY-SCOPED, like data_residency_policies (042 shape 4): a company reads and
writes only its own rules. Writes are additionally limited by the governance
domain (domain_authorization.py: EXECUTIVE only) and by the CISO password in the
interface. What a rule may grant is bounded by the frontend: an ALLOW only takes
effect for a screen that some function of the same company type already has by
default, so a company cannot open itself a screen meant for another kind of party.
These rules govern navigation only; data access stays with ABAC and the
permission engine.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "060"
down_revision: Union[str, None] = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"


def upgrade() -> None:
    op.create_table(
        "screen_access_rules",
        sa.Column("company_id", sa.Text(), primary_key=True),
        sa.Column("screen_id", sa.Text(), primary_key=True),
        sa.Column("business_function", sa.Text(), primary_key=True),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.CheckConstraint("effect IN ('ALLOW', 'DENY')", name="ck_screen_access_effect"),
    )
    op.create_index("idx_sar_company", "screen_access_rules", ["company_id"])

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE screen_access_rules ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE screen_access_rules FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text(
        "CREATE POLICY screen_access_rules_tenant_isolation ON screen_access_rules "
        f"FOR ALL USING ({ADMIN} OR company_id = {ME}) "
        f"WITH CHECK ({ADMIN} OR company_id = {ME})"))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON screen_access_rules TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS screen_access_rules_tenant_isolation ON screen_access_rules"))
    op.drop_table("screen_access_rules")
