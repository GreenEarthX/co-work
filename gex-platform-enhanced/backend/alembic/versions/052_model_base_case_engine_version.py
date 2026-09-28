"""model_base_case.engine_version — the engine that priced a basis is part of that basis.

Revision ID: 052
Revises: 051
Create Date: 2026-09-23

Exactly the 046 situation, one column later. `app/api/v1/routes_tea.py` adds
`engine_version` to the SQLite table at runtime (`ALTER TABLE model_base_case ADD
COLUMN engine_version TEXT`), writes it on every compute and SELECTs it in
`release_ready_state`. That ALTER never runs under PostgreSQL — `init_db()`
returns early when `domain_is_postgres()`, because `gex_app` holds no DDL rights
and a runtime-created table would carry no RLS policy. Without this migration the
INSERT and the SELECT both raise UndefinedColumn: `POST /api/v1/tea/compute`
500s, and every release-gated PF call fails in `_require_release_ready`.

Why the column exists at all: `cost_basis_hash` previously covered only the
request, so the OpenPyTEA 2.1.0 -> 3.0.0 upgrade moved e-methanol CAPEX +2.0%
(171,833,372 -> 175,255,929) on byte-identical inputs while the hash was
unchanged — a verified base case silently changed meaning. The hash now covers
the engine, and this column records it on the stored claim so a re-verification
pass can select on it.

Nullable TEXT, same as SQLite. NULL means "priced before this column existed";
that NULL is how you find the bases that predate it. Inventing a version for
them would be worse than leaving it empty.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("model_base_case", sa.Column("engine_version", sa.Text()))


def downgrade() -> None:
    op.drop_column("model_base_case", "engine_version")
