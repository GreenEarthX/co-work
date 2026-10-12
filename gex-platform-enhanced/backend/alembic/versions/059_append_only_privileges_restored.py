"""the append-only revokes of 056 and 058, restored after the rebuild undid them.

Revision ID: 059
Revises: 058
Create Date: 2026-09-30

056 revoked INSERT/UPDATE/DELETE/TRUNCATE on bankability_evidence_archive and
UPDATE/DELETE/TRUNCATE on evidence_events. 058 revoked UPDATE/DELETE/TRUNCATE on
commitment_terms_events. Head was 058, both had run, and yet on 2026-09-30 the
runtime held INSERT, SELECT, UPDATE on all three — DELETE and TRUNCATE gone, but
UPDATE back. A REVOKE is atomic, so nothing "partly failed": something re-granted
after Alembic, and granted UPDATE without granting DELETE.

That something is `scripts/setup_postgres_rls.sql`. Its second block loops over
every table in `public` and runs

    GRANT SELECT, INSERT, UPDATE ON <tbl> TO gex_app

exempting a hardcoded list — 'audit_log', 'commitment_records',
'verification_log' — from UPDATE only. Its own comment invites a re-run "after
every Alembic migration adds new tables", and during the 2026-09-30 rebuild it
was re-run with all 120 tables present: gex_admin holds ALL PRIVILEGES on 120
tables, which it can only have got from that loop finding a populated schema.
So the grant shape measured afterwards is exactly what that script produces —
UPDATE restored everywhere except `commitment_records`, the one name on its list
that exists here, and DELETE nowhere because line 47 never grants DELETE.

The tables were never dropped and recreated: had they been, 031's DEFAULT
PRIVILEGES would have handed back DELETE too, and it is absent.

This migration restores the three revokes. `scripts/setup_postgres_rls.sql` is
fixed in the same change to read the append-only set from the database instead
of a hardcoded list, so a future re-run cannot undo this again.

    bankability_evidence_archive   runtime may SELECT only
    evidence_events                runtime may SELECT and INSERT only
    commitment_terms_events        runtime may SELECT and INSERT only

`commitment_terms` deliberately KEEPS UPDATE — cards are replaced in place, and
058 grants it on purpose. Only its history is append-only.

Guarded by tests/test_evidence_history_pg.py and tests/test_commitment_terms_pg.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "059"
down_revision: Union[str, None] = "058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

APP_ROLE = "gex_app"

# table -> what the runtime keeps. Everything else is revoked.
APPEND_ONLY = {
    "bankability_evidence_archive": "SELECT",
    "evidence_events": "SELECT, INSERT",
    "commitment_terms_events": "SELECT, INSERT",
}


def upgrade() -> None:
    conn = op.get_bind()
    for table, keep in APPEND_ONLY.items():
        # REVOKE first, then GRANT back the envelope: a GRANT alone cannot take
        # away what 031's DEFAULT PRIVILEGES already gave (the lesson of 056).
        conn.execute(sa.text(
            f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {table} FROM {APP_ROLE}"))
        conn.execute(sa.text(f"GRANT {keep} ON {table} TO {APP_ROLE}"))

    # Assert rather than trust: this migration exists because a previous pair of
    # revokes was silently undone, and nothing noticed until three tests failed.
    held = conn.execute(sa.text(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = :role AND table_name = ANY(:tables) "
        "AND privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')"
    ), {"role": APP_ROLE, "tables": list(APPEND_ONLY)}).fetchall()
    if held:
        raise RuntimeError(
            f"{APP_ROLE} still holds rewrite privileges on append-only tables: "
            f"{[tuple(r) for r in held]}"
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Back to the state this migration found: INSERT, SELECT, UPDATE on all
    # three, no DELETE, no TRUNCATE. Not to 031's full DML — that was never the
    # state at 058, and restoring DELETE here would be a downgrade to something
    # the database has not been in since 056.
    for table in APPEND_ONLY:
        conn.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}"))
