"""Who confirmed a Marketplace record, and when.

Revision ID: 067
Revises: 066

066 gave the Marketplace records a verification_state but nowhere to say who
moved it off UNVERIFIED. JML confirmed them on 2026-10-25; a confirmation must
name its confirmer. verified_by / verified_at are set together, and set exactly
when the state is no longer UNVERIFIED (CHECK).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "067"
down_revision: Union[str, None] = "066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("project_sales_detail", "project_input_line", "input_classification")


def upgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN verified_by text, ADD COLUMN verified_at timestamptz")
        op.execute(f"ALTER TABLE {t} ADD CONSTRAINT ck_{t}_verified CHECK ("
                   "(verification_state = 'UNVERIFIED') = (verified_by IS NULL AND verified_at IS NULL))")


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS ck_{t}_verified")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS verified_at, DROP COLUMN IF EXISTS verified_by")
