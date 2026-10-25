"""Information barriers — a real store for the CISO workspace.

Revision ID: 070
Revises: 069

The CISO workspace listed invented barriers and "created" new ones that were
never saved (JML, 2026-10-25: replace the CISO demo with real data). A barrier
belongs to one company: its CISO (or GEX) creates it; only that company and GEX
read it. Violations are not recorded anywhere yet, so none are stored here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "070"
down_revision: Union[str, None] = "069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
OWN = f"({ME} = 'PLATFORM_ADMIN' OR company_id = {ME})"


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE information_barrier (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           company_id text NOT NULL REFERENCES tenants(company_id),
           side_a text NOT NULL, side_b text NOT NULL,
           barrier_type text NOT NULL CHECK (barrier_type IN ('HARD', 'SOFT', 'CHINESE_WALL')),
           applies_to_data text[] NOT NULL DEFAULT '{}',
           description text,
           active boolean NOT NULL DEFAULT true,
           created_by text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now(),
           CHECK (side_a <> side_b))""")
    _q("ALTER TABLE information_barrier ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE information_barrier FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY information_barrier_read ON information_barrier FOR SELECT USING {OWN}")
    _q(f"CREATE POLICY information_barrier_insert ON information_barrier FOR INSERT WITH CHECK {OWN}")
    _q(f"CREATE POLICY information_barrier_update ON information_barrier FOR UPDATE USING {OWN} WITH CHECK {OWN}")
    _q(f"CREATE POLICY information_barrier_delete ON information_barrier FOR DELETE USING {OWN}")


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS information_barrier")
