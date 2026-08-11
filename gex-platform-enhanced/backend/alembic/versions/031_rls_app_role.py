"""RLS application role — make Row-Level Security actually apply.

Revision ID: 031
Revises: 021

THE PROBLEM THIS FIXES
----------------------
Migration 020 enables RLS on `projects` and `project_access`, marks both
FORCE ROW LEVEL SECURITY, and writes tenant-isolation policies keyed on
`app.current_company_id`. All of that is correct — and all of it was inert.

`gex_user`, the role the application connects as, is a Postgres **SUPERUSER**.
Superusers bypass RLS unconditionally, and FORCE does not apply to them. With
the policies in place and RLS enabled, this was still true:

    SET LOCAL app.current_company_id = 'acme_totally_unrelated';
    SELECT count(*) FROM projects;   -- 12  (i.e. all of them)

A company that does not exist could read every project. The security doctrine
names RLS the "final backstop"; it was a backstop that never engaged.

THE FIX
-------
A least-privilege role, `gex_app`, with DML rights and nothing else. RLS
applies to it because it is neither superuser nor table owner.

    gex_user  — owner/migrator. Runs alembic. Keeps superuser.
    gex_app   — the APPLICATION connects as this. RLS applies.

Created NOLOGIN deliberately: a password does not belong in a migration.
Deployment grants LOGIN and a secret out of band, e.g.

    ALTER ROLE gex_app WITH LOGIN PASSWORD '<from secret store>';

and points DATABASE_URL at it. Until then the role is still usable — and
testable — via `SET ROLE gex_app`, which is how the guardrail test proves
isolation without needing a second credential.

CONNECTING AS A SUPERUSER SILENTLY DISABLES ALL OF THIS. That is what
tests/test_rls_isolation.py exists to catch.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "031"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotent: CREATE ROLE has no IF NOT EXISTS.
    conn.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END
        $$;
    """))

    # Least privilege: DML only. No DDL, no ownership, no BYPASSRLS.
    conn.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))

    # Tables created by later migrations must be covered too, or the app
    # silently loses access to whatever the next slice adds.
    conn.execute(sa.text(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"))

    # Explicitly NOT granted: BYPASSRLS, SUPERUSER, CREATEDB, CREATEROLE.
    # Stated here because the absence of a grant is easy to "helpfully" add
    # later while debugging a permissions error — which would re-break RLS.


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"))
    conn.execute(sa.text(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}"))
    conn.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}"))
    conn.execute(sa.text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
