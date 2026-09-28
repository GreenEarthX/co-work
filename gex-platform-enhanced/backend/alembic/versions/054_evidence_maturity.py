"""evidence maturity — a separate axis from verification (rules 3.0.0).

Adds bankability_evidence.maturity, and evidence_events.old_maturity /
new_maturity so the append-only audit trail records maturity changes.

Revision ID: 054
Revises: 053
Create Date: 2026-09-26

Adds bankability_evidence.maturity. Evidence rules 3.0.0 ("the stronger bar",
decided 2026-09-25) make maturity load-bearing: a VERIFIED item counts toward its
gate only when its declared maturity meets REQUIRED_MATURITY for that item —
INTENT < INDICATIVE < AGREED < EXECUTED < EFFECTIVE.

Why a column and not a key name. Before 3.0.0 the only maturity signal was the
evidence key's name, so a letter of intent uploaded into a slot called
"binding_offtake_contract_executed" and marked VERIFIED satisfied that slot. The
engine never learned what had been uploaded. Verification answers "is this
document authentic?"; it does not make a term sheet into a contract.

Nullable, and deliberately so. The 127 rows present at this revision — 125 of
them demo_seed — predate the axis and have no declared maturity. NULL fails
closed in the engine: an instrument item with undeclared maturity does not count
until someone declares it. Backfilling a value here would be the engine
inventing a fact about a document nobody has looked at.

The column is text rather than an enum type so the maturity vocabulary can be
widened without a type migration; the write path validates it against
MATURITY_LEVELS in app/core/bankability_engine.py.

Mirrored in the inline DDL at app/api/v1/routes_bankability_proxy.py, which
creates the SQLite table for local fallback. A runtime ALTER without this
migration would 500 on PostgreSQL while every SQLite-backed test stayed green.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "054"
down_revision: Union[str, None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "bankability_evidence",
        sa.Column("maturity", sa.Text(), nullable=True),
    )
    # The append-only audit trail must record maturity changes too. A change
    # from INTENT to EXECUTED that leaves the status untouched would otherwise
    # be the most consequential edit and the only invisible one.
    op.add_column("evidence_events", sa.Column("old_maturity", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("new_maturity", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_events", "new_maturity")
    op.drop_column("evidence_events", "old_maturity")
    op.drop_column("bankability_evidence", "maturity")
