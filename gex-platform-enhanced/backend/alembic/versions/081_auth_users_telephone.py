"""An account's telephone number: auth_users.telephone (JML, 2026-11-03).

Revision ID: 081
Revises: 080

Registration has required a telephone since the vetting policy, but stored it only
as free text inside `vetting_note` ("Telephone supplied: …"), so nobody could read
it as a field and its owner could not change it. JML: users may change their
number later. The column holds the CURRENT number; the owner changes it through
PUT /api/v1/auth/telephone, and each change is an `account.telephone_changed`
event (without the numbers: the ledger is append-only, and a telephone number is
personal data that must be correctable).

Nullable: the 23 existing accounts never gave one in a field. Nothing is parsed
out of `vetting_note` — that note stays the record of what was supplied at
registration. A recorded verification call (phone_verified_*) is unaffected by a
later change of number. PostgreSQL only: no SQLite mirror (JML, 2026-11-03); the routes
that read or write it refuse with 503 POSTGRES_REQUIRED on any other backend.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "081"
down_revision: Union[str, None] = "080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("auth_users", sa.Column("telephone", sa.Text(), nullable=True))
    n = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM information_schema.columns WHERE table_name='auth_users' "
        "AND column_name='telephone'")).scalar()
    assert n == 1, "telephone was not added"


def downgrade() -> None:
    op.drop_column("auth_users", "telephone")
