"""Additionality no longer stores typed IRRs or rates (handoff v4, task 6).

Revision ID: 122
Revises: 121
Create Date: 2026-11-17

The additionality assessment used to require an IRR with and without the DFI,
a sponsor hurdle and two WACCs, all typed by the caller, and decided on an IRR
comparison against hard-coded DFI hurdles. It is now an assessment of evidenced
criteria; the IRRs, when present, are engine-computed and may be absent (no
returns case supplied). These columns therefore become nullable. The table held
no rows when this was written (2026-11-17).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "122"
down_revision: Union[str, None] = "121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("irr_with_dfi", "irr_without_dfi", "commercial_hurdle_rate", "blended_wacc",
           "all_commercial_wacc", "commercial_debt_pct", "total_concessional_pct", "grant_pct")


def upgrade() -> None:
    for col in COLUMNS:
        op.alter_column("additionality_assessments", col, nullable=True)


def downgrade() -> None:
    import sqlalchemy as sa
    n = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM additionality_assessments WHERE "
        + " OR ".join(f"{c} IS NULL" for c in COLUMNS))).scalar()
    if n:
        raise RuntimeError(f"{n} assessment(s) have no typed IRR; downgrading would need to delete "
                           "them. Refused: archive them first.")
    for col in COLUMNS:
        op.alter_column("additionality_assessments", col, nullable=False)
