"""The PF engine's run log moves into PostgreSQL (JML, 2026-11-04).

Revision ID: 082
Revises: 081

WHY
---
The PF engine (:8001) logged every pricing run and every parameter change to a
local SQLite file, gex_pf_engine/backend/engine_model_runs.db: 665 runs and one
parameter change on 4 Nov. That file sat outside the nightly pg_dump, so losing
it lost the audit trail, and it broke the rule that the platform's data lives in
PostgreSQL only.

WHAT
----
Two append-only tables, the SQLite schema kept column for column:

    engine_model_runs           run_id (PK), endpoint, molecule, model_version,
                                calibration_id, calibration_status, input_hash,
                                n_violations, violations_json, computed_at
    engine_param_change_events  id, molecule, old_calibration_id,
                                new_calibration_id, changed_fields_json,
                                n_observations, source, at

WHO
---
Only `gex_engine`, the engine's own role (scripts/setup_postgres_rls.sql
creates it, since roles are not in a dump): SELECT, INSERT and nothing else.
The runtime role gex_app holds NOTHING on them — 031's DEFAULT PRIVILEGES hand
it full DML on every new table, so that is revoked here. FORCED RLS with one
policy for gex_engine, so a later grant to anyone else still reads nothing.
The migration ASSERTS the result (the lesson of 059): gex_engine holds exactly
INSERT and SELECT on these two tables and no privilege on any other table, and
gex_app holds none on them.

The rows are molecule pricing runs: no project, no tenant, no client data.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "082"
down_revision: Union[str, None] = "081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ENGINE_ROLE = "gex_engine"
TABLES = ("engine_model_runs", "engine_param_change_events")


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ENGINE_ROLE}).first():
        raise RuntimeError(
            f"role {ENGINE_ROLE} does not exist: run scripts/setup_postgres_rls.sql first "
            "(it creates the roles a dump does not carry)")

    op.execute("""
        CREATE TABLE engine_model_runs (
            run_id             text PRIMARY KEY,
            endpoint           text NOT NULL,
            molecule           text,
            model_version      text NOT NULL,
            calibration_id     text NOT NULL,
            calibration_status text NOT NULL,
            input_hash         text NOT NULL,
            n_violations       integer NOT NULL DEFAULT 0,
            violations_json    text,
            computed_at        text NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_engine_model_runs_computed_at ON engine_model_runs (computed_at DESC)")
    op.execute("""
        CREATE TABLE engine_param_change_events (
            id                  bigserial PRIMARY KEY,
            molecule            text NOT NULL,
            old_calibration_id  text,
            new_calibration_id  text NOT NULL,
            changed_fields_json text NOT NULL,
            n_observations      integer NOT NULL,
            source              text NOT NULL,
            at                  text NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_engine_param_change_events_molecule ON engine_param_change_events (molecule, id DESC)")

    for t in TABLES:
        op.execute(f"REVOKE ALL ON {t} FROM PUBLIC, gex_app")
        op.execute(f"GRANT SELECT, INSERT ON {t} TO {ENGINE_ROLE}")
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {t}_engine_only ON {t} TO {ENGINE_ROLE} USING (true) WITH CHECK (true)")
    op.execute("REVOKE ALL ON SEQUENCE engine_param_change_events_id_seq FROM PUBLIC, gex_app")
    op.execute(f"GRANT USAGE ON SEQUENCE engine_param_change_events_id_seq TO {ENGINE_ROLE}")

    # Assert rather than trust.
    held = conn.execute(sa.text(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = :r AND table_schema = 'public' ORDER BY 1, 2"), {"r": ENGINE_ROLE}).fetchall()
    want = sorted((t, p) for t in TABLES for p in ("INSERT", "SELECT"))
    if sorted(tuple(r) for r in held) != want:
        raise RuntimeError(f"{ENGINE_ROLE} privileges are {[tuple(r) for r in held]}, expected {want}")
    app_held = conn.execute(sa.text(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = ANY(:t)"), {"t": list(TABLES)}).fetchall()
    if app_held:
        raise RuntimeError(f"gex_app holds privileges on the engine run log: {[tuple(r) for r in app_held]}")


def downgrade() -> None:
    # The rows go with the tables: take a pg_dump first if they matter.
    for t in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t}")
