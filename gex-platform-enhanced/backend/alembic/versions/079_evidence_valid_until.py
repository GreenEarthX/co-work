"""Evidence expires: bankability_evidence.valid_until (rules 4.5.0).

Revision ID: 079
Revises: 078

JML, 2026-10-30, from the outside review of the process: "evidence expiry should trigger
reassessment without a new upload". A permit lapses, a letter of credit expires, a policy
period ends; until now a VERIFIED item stayed VERIFIED for ever, because the evidence
record had no validity date and nothing assigned EXPIRED.

`valid_until` is a date as text ('YYYY-MM-DD', like the other dates in this table),
declared with the document: the submitter sets it, a reviewer may shorten it or add one
but never extend it (extending needs a new document). Nullable on purpose — an item with
no date never expires, and the engine does not invent one. From that date the engine
reads the item EXPIRED (evidence rules 4.5.0).

The append-only audit trail records every change of it (evidence_events.old_valid_until /
new_valid_until), as it does for maturity. Mirrored in the SQLite fallback by
_ensure_tables in app/api/v1/routes_bankability_proxy.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "079"
down_revision: Union[str, None] = "078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("bankability_evidence", sa.Column("valid_until", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("old_valid_until", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("new_valid_until", sa.Text(), nullable=True))
    conn = op.get_bind()
    n = conn.execute(sa.text(
        "SELECT count(*) FROM information_schema.columns WHERE table_name='bankability_evidence' "
        "AND column_name='valid_until'")).scalar()
    assert n == 1, "valid_until was not added"


def downgrade() -> None:
    op.drop_column("evidence_events", "new_valid_until")
    op.drop_column("evidence_events", "old_valid_until")
    op.drop_column("bankability_evidence", "valid_until")
