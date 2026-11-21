"""The funding plan inside the financing case; the ceiling becomes the case's total uses (19 Nov).

Revision ID: 128
Revises: 127
Create Date: 2026-11-19

JML, 19 Nov: "replace the fixed-capital funding ceiling with a scoped sources-and-uses rule";
apply reconciliation to the SELECTED financing case, keep pipeline opportunities separate.

  · financing_case_version.funding_plan    the case's sources (each with the substance of its
                                           obligation: none, indicative, conditional or binding;
                                           its conditions; amounts received and available to
                                           draw; in the plan or pipeline) and its uses
                                           (development, construction, owner's costs, financing
                                           costs, reserves, working capital). Versioned with the
                                           case: an amendment is a new version. Hashed.
  · financing_case_version.uses_total_eur  the plan's defined uses at the version (NULL: none
                                           defined, e.g. every version before 128).

An ELIGIBLE case's debt + grant may not exceed its defined uses (or, with none defined, its
fixed capital, as before). A DRAFT is unconstrained and states its limitations.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "128"
down_revision: Union[str, None] = "127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

F = "financing_case_version"
NOT_NULL = ("tea_claim_id", "tea_cost_basis_hash", "fci_eur", "debt_eur", "interest_rate", "debt_tenor_years")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _eligible(ceiling: str) -> str:
    cond = " AND ".join(f"{c} IS NOT NULL" for c in NOT_NULL)
    return (f"ALTER TABLE {F} ADD CONSTRAINT {F}_eligible_complete CHECK (status = 'DRAFT' OR ({cond} "
            f"AND debt_eur + grant_eur <= {ceiling} AND jsonb_array_length(limitations) = 0))")


def upgrade() -> None:
    _q(f"ALTER TABLE {F} ADD COLUMN funding_plan JSONB NOT NULL DEFAULT '{{}}'::jsonb")
    _q(f"ALTER TABLE {F} ADD COLUMN uses_total_eur DOUBLE PRECISION CHECK (uses_total_eur IS NULL OR uses_total_eur > 0)")
    _q(f"ALTER TABLE {F} DROP CONSTRAINT {F}_eligible_complete")
    _q(_eligible("coalesce(uses_total_eur, fci_eur)"))


def downgrade() -> None:
    n = _q(f"SELECT count(*) FROM {F} WHERE funding_plan <> '{{}}'::jsonb").scalar()
    if n:
        raise RuntimeError(f"{n} version(s) carry a funding plan; refusing to drop them. Dump the table first.")
    _q(f"ALTER TABLE {F} DROP CONSTRAINT {F}_eligible_complete")
    _q(_eligible("fci_eur"))
    _q(f"ALTER TABLE {F} DROP COLUMN uses_total_eur")
    _q(f"ALTER TABLE {F} DROP COLUMN funding_plan")
