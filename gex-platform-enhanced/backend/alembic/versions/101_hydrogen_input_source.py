"""Chain of custody — a hydrogen input names the lot it came from (GreenMesh Phase 2, Step 1).

Revision ID: 101
Revises: 100

An ammonia (or methanol, e-fuel) period that takes hydrogen as an input is only as RFNBO as
that hydrogen. Until 101 a `coc_input` of type H2 carried nothing but a free-text evidence
reference, so a downstream period could not know whether its hydrogen passed the RFNBO
correlation checks (handoff item 65).

`coc_input.source_lot_id` names the upstream hydrogen lot. The correlation of the downstream
period then reads the upstream period's CLOSED, re-verified statement
(app/core/rfnbo_correlation.py, `upstream_hydrogen`). An H2 input that names no lot stays
UNVERIFIED — never assumed. Only H2 inputs may name a lot (CHECK). coc_input stays
append-only (097); the column is fixed at insert like every other.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "101"
down_revision: Union[str, None] = "100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE coc_input ADD COLUMN source_lot_id text REFERENCES mass_balance_lots(lot_id)"))
    conn.execute(sa.text(
        "ALTER TABLE coc_input ADD CONSTRAINT ck_coc_input_source_lot_h2 "
        "CHECK (source_lot_id IS NULL OR input_type = 'H2')"))
    conn.execute(sa.text("CREATE INDEX ix_coc_input_source_lot ON coc_input (source_lot_id) "
                         "WHERE source_lot_id IS NOT NULL"))
    # Assert: the runtime still cannot rewrite an input (097's append-only revoke).
    bad = conn.execute(sa.text(
        "SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'coc_input' "
        "AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')")).scalar()
    if bad:
        raise RuntimeError(f"gex_app holds {bad} on coc_input: append-only is off")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_coc_input_source_lot"))
    conn.execute(sa.text("ALTER TABLE coc_input DROP CONSTRAINT IF EXISTS ck_coc_input_source_lot_h2"))
    conn.execute(sa.text("ALTER TABLE coc_input DROP COLUMN IF EXISTS source_lot_id"))
