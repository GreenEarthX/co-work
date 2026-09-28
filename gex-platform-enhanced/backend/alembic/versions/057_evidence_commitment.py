"""evidence commitment — the assignee commits to a due date.

Revision ID: 057
Revises: 056
Create Date: 2026-09-26

A request is CREATED by assignment and ACCEPTED when its assignee commits to a
date. Until then it is "not yet committed" — visibly, because an open request
nobody has put a date on is a request nobody has accepted.

    bankability_evidence.committed_at / committed_by   who accepted, and when
    evidence_events.old_due_date / new_due_date         every date change, audited

Only the assignee can commit (routes_bankability_proxy.commit_evidence). A
reassignment clears the date and the commitment: a date is one person's word and
does not transfer to the next person. The platform never sets a date itself —
a defaulted deadline is one nobody owns, and "overdue" computed from it would be
fiction. Overdue is derived at read time (app/core/evidence_due_dates.py), not
stored, so it cannot go stale.

Mirrored for SQLite in routes_bankability_proxy._ensure_tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "057"
down_revision: Union[str, None] = "056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("bankability_evidence", sa.Column("committed_at", sa.Text(), nullable=True))
    op.add_column("bankability_evidence", sa.Column("committed_by", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("old_due_date", sa.Text(), nullable=True))
    op.add_column("evidence_events", sa.Column("new_due_date", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_events", "new_due_date")
    op.drop_column("evidence_events", "old_due_date")
    op.drop_column("bankability_evidence", "committed_by")
    op.drop_column("bankability_evidence", "committed_at")
