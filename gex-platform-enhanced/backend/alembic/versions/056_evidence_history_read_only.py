"""evidence history is read-only for the runtime role.

Revision ID: 056
Revises: 055
Create Date: 2026-09-26

Found while verifying 055 as gex_app: a DELETE on bankability_evidence_archive
succeeded. 055 granted SELECT only, but migration 031 set DEFAULT PRIVILEGES so
every table created afterwards is born with SELECT, INSERT, UPDATE, DELETE for
gex_app. A GRANT cannot take away what a default already gave; only REVOKE can.

The same default had quietly made evidence_events — documented since 034 as
"append-only, never UPDATEd, never DELETEd" — updatable and deletable by the
runtime. Append-only was a comment, not a control. Nothing in app/ or scripts/
updates or deletes it (checked 2026-09-26), so the revoke removes no capability
the platform uses.

    bankability_evidence_archive   runtime may SELECT only
    evidence_events                runtime may SELECT and INSERT only

RLS still decides WHICH rows a tenant sees; this decides what any tenant can DO.
Guarded by tests/test_evidence_history_pg.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056"
down_revision: Union[str, None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON bankability_evidence_archive FROM {APP_ROLE}"))
    conn.execute(sa.text(f"GRANT SELECT ON bankability_evidence_archive TO {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE UPDATE, DELETE, TRUNCATE ON evidence_events FROM {APP_ROLE}"))
    conn.execute(sa.text(f"GRANT SELECT, INSERT ON evidence_events TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(f"GRANT UPDATE, DELETE ON evidence_events TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"GRANT INSERT, UPDATE, DELETE ON bankability_evidence_archive TO {APP_ROLE}"))
