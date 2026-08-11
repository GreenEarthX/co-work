"""Event chain — permit exactly one root.

Revision ID: 040
Revises: 039

039 added UNIQUE(previous_hash) so two events cannot claim the same
predecessor. SQL UNIQUE permits multiple NULLs, so the ROOT of the chain was
still forkable — and measurement confirmed it: 12 concurrent appends produced
1 fork at the NULL root even with the constraint in place.

A partial unique index closes that: at most one event may have no predecessor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        CREATE UNIQUE INDEX uq_platform_events_single_root
        ON platform_events ((previous_hash IS NULL))
        WHERE previous_hash IS NULL
    """))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DROP INDEX IF EXISTS uq_platform_events_single_root"))
