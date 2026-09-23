"""model_base_case.result_status — carry the plausibility verdict into PostgreSQL.

Revision ID: 046
Revises: 045
Create Date: 2026-09-22

`app/api/v1/routes_tea.py` adds `result_status` to the SQLite table at runtime
(`ALTER TABLE model_base_case ADD COLUMN result_status TEXT`) and reads it back
when a base case is promoted. 044 was written from the older SQLite shape, so
PostgreSQL never had the column and `migrate_tail_slices.py` stopped the
cutover with "columns lost: ['result_status']". Nullable TEXT, same as SQLite:
rows written before the plausibility gate carry no verdict, and inventing one
would be worse than leaving it empty.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("model_base_case", sa.Column("result_status", sa.Text()))


def downgrade() -> None:
    op.drop_column("model_base_case", "result_status")
