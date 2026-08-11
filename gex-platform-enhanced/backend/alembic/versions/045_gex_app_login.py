"""Grant gex_app LOGIN so the runtime can stop connecting as a superuser.

Revision ID: 045
Revises: 044
Create Date: 2026-08-10

WHAT THIS FINISHES
------------------
Migration 031 created `gex_app` — not superuser, no BYPASSRLS — and granted it
DML on every table plus USAGE (deliberately NOT CREATE) on the schema. It was
left NOLOGIN, so the only way to use it was `SET ROLE` from a superuser session,
which is what the RLS tests do.

That meant RLS was *proven* but *inert*: the application connected as `gex_user`,
which is SUPERUSER and BYPASSRLS, so no policy was ever evaluated in production.
"89 tables under forced RLS" described the schema, not the running system.

This grants LOGIN. It does NOT set a password — a password in a migration is a
credential in version control. Set one per environment, out of band:

    ALTER ROLE gex_app WITH PASSWORD '<from your secret store>';

WHAT gex_app DELIBERATELY CANNOT DO
-----------------------------------
Verified by tests/test_gex_app_runtime_role.py, not just intended here:

  · no BYPASSRLS  — every tenant policy actually binds
  · no SUPERUSER  — cannot disable RLS, cannot read the filesystem
  · no CREATE on schema public — cannot add or alter tables, so a compromised
    runtime cannot create an unprotected table and copy data into it
  · not the table owner — FORCE ROW LEVEL SECURITY means even the owner is
    bound, but gex_app is not the owner in any case

CREDENTIAL SEPARATION
---------------------
DDL still needs the owner. After this migration the two credentials are
different and must stay different:

    ALEMBIC_DATABASE_URL  ->  gex_owner / gex_user  (DDL, migrations only)
    DATABASE_URL          ->  gex_app              (runtime, RLS applies)

alembic/env.py prefers ALEMBIC_DATABASE_URL, so pointing DATABASE_URL at
gex_app does not silently break migrations — and, more importantly, running a
migration cannot silently become an exfiltration path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    conn = op.get_bind()

    exists = conn.exec_driver_sql(
        "SELECT 1 FROM pg_roles WHERE rolname = %(r)s", {"r": APP_ROLE}
    ).scalar()
    if not exists:
        # 031 should have created it; be explicit rather than fail obscurely.
        raise RuntimeError(
            f"role {APP_ROLE} does not exist — migration 031 must run first"
        )

    conn.exec_driver_sql(f"ALTER ROLE {APP_ROLE} WITH LOGIN")

    # Re-assert the privilege envelope. 031 granted these, but a role that can
    # now log in is worth being explicit about: this migration is the one place
    # that describes what the runtime identity may do.
    conn.exec_driver_sql(f"REVOKE CREATE ON SCHEMA public FROM {APP_ROLE}")
    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    conn.exec_driver_sql(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        f"IN SCHEMA public TO {APP_ROLE}"
    )
    conn.exec_driver_sql(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"
    )
    # Tables created by later migrations must inherit the same envelope, or the
    # runtime silently loses access to new tables and the failure looks like a
    # bug in the feature rather than a missing grant.
    conn.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    conn.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )

    # These must never be granted. Assert rather than trust.
    bad = conn.exec_driver_sql(
        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
        "FROM pg_roles WHERE rolname = %(r)s", {"r": APP_ROLE}
    ).fetchone()
    if any(bad):
        raise RuntimeError(
            f"{APP_ROLE} holds an elevated attribute "
            f"(super/bypassrls/createdb/createrole = {bad}) — it must not, or "
            "RLS does not constrain the runtime"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(f"ALTER ROLE {APP_ROLE} WITH NOLOGIN")
