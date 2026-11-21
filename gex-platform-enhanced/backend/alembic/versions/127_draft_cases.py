"""Draft financing cases and draft cost bases; a stable financing case id (19 Nov).

Revision ID: 127
Revises: 126
Create Date: 2026-11-19

JML, 19 Nov: a newly formed producer has indicative terms before any independently
reviewed TEA. "Allow incomplete draft cases" and "retain the reviewed-TEA requirement
for promotion while allowing draft financing to be recorded". So:

  · financing_case_version.case_id     the stable id of ONE financing case across its
                                       versions (a workbook re-import names it; never a
                                       name or a TEA run is matched instead)
  · financing_case_version.status      DRAFT | ELIGIBLE. A DRAFT may lack a TEA run, terms
                                       and fixed capital, and may exceed it; its
                                       `limitations` say what stops it. Only ELIGIBLE
                                       (the 124 rules: an independently reviewed TEA, every
                                       term with a source, debt + grant <= fixed capital)
                                       may feed a returns version. Promotion is a NEW
                                       version; nothing is updated.
  · cost_basis_version.status          DRAFT | READY. A DRAFT keeps `open_issues` (an open
                                       plant boundary, a conflict); no TEA runs from it.

Existing rows passed the old rules: they become ELIGIBLE / READY, and each existing
financing version takes its first version's id as case id (one case per project then).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "127"
down_revision: Union[str, None] = "126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

F = "financing_case_version"
C = "cost_basis_version"
ELIGIBLE_NOT_NULL = ("tea_claim_id", "tea_cost_basis_hash", "fci_eur", "debt_eur", "interest_rate",
                     "debt_tenor_years")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q(f"ALTER TABLE {F} ADD COLUMN case_id TEXT")
    _q(f"ALTER TABLE {F} ADD COLUMN status TEXT NOT NULL DEFAULT 'ELIGIBLE' CHECK (status IN ('DRAFT', 'ELIGIBLE'))")
    _q(f"ALTER TABLE {F} ADD COLUMN limitations JSONB NOT NULL DEFAULT '[]'::jsonb")
    _q(f"ALTER TABLE {F} DISABLE TRIGGER {F}_immutable")
    _q(f"""UPDATE {F} f SET case_id = (SELECT g.version_id FROM {F} g WHERE g.project_id = f.project_id
                                         ORDER BY g.version_number LIMIT 1)""")
    _q(f"ALTER TABLE {F} ENABLE TRIGGER {F}_immutable")
    _q(f"ALTER TABLE {F} ALTER COLUMN case_id SET NOT NULL")
    _q(f"ALTER TABLE {F} ALTER COLUMN status DROP DEFAULT")
    for col in ELIGIBLE_NOT_NULL:
        _q(f"ALTER TABLE {F} ALTER COLUMN {col} DROP NOT NULL")
    _q(f"ALTER TABLE {F} DROP CONSTRAINT {F}_check")
    cond = " AND ".join(f"{c} IS NOT NULL" for c in ELIGIBLE_NOT_NULL)
    _q(f"ALTER TABLE {F} ADD CONSTRAINT {F}_eligible_complete CHECK (status = 'DRAFT' OR ({cond} "
       "AND debt_eur + grant_eur <= fci_eur AND jsonb_array_length(limitations) = 0))")
    _q(f"CREATE INDEX idx_{F}_case ON {F}(case_id, version_number)")

    _q(f"ALTER TABLE {C} ADD COLUMN status TEXT NOT NULL DEFAULT 'READY' CHECK (status IN ('DRAFT', 'READY'))")
    _q(f"ALTER TABLE {C} ADD COLUMN open_issues JSONB NOT NULL DEFAULT '[]'::jsonb")
    _q(f"ALTER TABLE {C} ALTER COLUMN status DROP DEFAULT")
    _q(f"ALTER TABLE {C} ADD CONSTRAINT {C}_ready_has_no_issues CHECK (status = 'DRAFT' OR "
       "jsonb_array_length(open_issues) = 0)")


def downgrade() -> None:
    n = _q(f"SELECT count(*) FROM {F} WHERE status = 'DRAFT'").scalar() + \
        _q(f"SELECT count(*) FROM {C} WHERE status = 'DRAFT'").scalar()
    if n:
        raise RuntimeError(f"{n} draft version(s) exist; refusing to drop them. Dump the tables first.")
    _q(f"ALTER TABLE {C} DROP CONSTRAINT {C}_ready_has_no_issues")
    _q(f"ALTER TABLE {C} DROP COLUMN open_issues")
    _q(f"ALTER TABLE {C} DROP COLUMN status")
    _q(f"DROP INDEX idx_{F}_case")
    _q(f"ALTER TABLE {F} DROP CONSTRAINT {F}_eligible_complete")
    _q(f"ALTER TABLE {F} ADD CONSTRAINT {F}_check CHECK (debt_eur + grant_eur <= fci_eur)")
    for col in ELIGIBLE_NOT_NULL:
        _q(f"ALTER TABLE {F} ALTER COLUMN {col} SET NOT NULL")
    _q(f"ALTER TABLE {F} DROP COLUMN limitations")
    _q(f"ALTER TABLE {F} DROP COLUMN status")
    _q(f"ALTER TABLE {F} DROP COLUMN case_id")
