"""The gate clock: when each gate was first seen satisfied (rules 4.8.0).

Revision ID: 080
Revises: 079

JML, 2026-10-31. The claim that the gate structure accelerates projects had no measurement: no
clock ran on any gate. One row per (project, gate), written the first time an evaluation finds
the gate SATISFIED, with the rules version and the state at that moment. First wins and nothing
rewrites it: the row is append-only (UPDATE, DELETE and TRUNCATE are revoked and no policy
allows them), so a gate that is later lost and regained keeps its first date — the current
standing is the snapshot's job, not this table's.

What it measures, honestly: the first EVALUATION that saw the gate satisfied, not the day the last
document was filed (re-evaluation is immediate on every write, so the lag is seconds, but a gate
satisfied before this migration has no row and is simply not measured). The project's own start
is projects.created_at.

RLS: the project's companies read and append, as for the report tables (076).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "080"
down_revision: Union[str, None] = "079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
ON_PROJECT = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE project_gate_clock (
           project_id text NOT NULL REFERENCES projects(project_id),
           gate_id text NOT NULL,
           first_satisfied_at timestamptz NOT NULL DEFAULT now(),
           rules_version text,
           state_at_time text,
           PRIMARY KEY (project_id, gate_id))""")
    _q("ALTER TABLE project_gate_clock ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE project_gate_clock FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY pgc_read ON project_gate_clock FOR SELECT USING {ON_PROJECT}")
    _q(f"CREATE POLICY pgc_insert ON project_gate_clock FOR INSERT WITH CHECK {ON_PROJECT}")
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON project_gate_clock FROM gex_app")
    n = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='gex_app' "
        "AND table_name='project_gate_clock' AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')")).scalar()
    assert n == 0, "the gate clock must be append-only for the runtime role"


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS project_gate_clock")
