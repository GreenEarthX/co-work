"""Project records — the project data the code held, now in PostgreSQL.

Revision ID: 068
Revises: 067

WHY (JML, 2026-10-25: "move project data out of code", PostgreSQL as reference)
-----------------------------------------------------------------------------
Four copies of project data lived in code: frontend/src/data/customerProjects.ts
(2,257 lines: bankability snapshot, gates, capital status, offtakes, energy,
electrolyser, certifications, incentives, timeline, narrative), the backend's
routes_projects._PROJECT_META (a second, disagreeing copy of the headline
fields), project_registry.PROJECT_ACCESS_PROFILES (owners, associated
companies — moved by scripts/move_project_registry_20261025.py into the existing
projects / tenants / project_access tables) and risk_flags.RISK_FLAGS (15 flags).

WHAT
----
  project_profile     one row per project: the rich detail as jsonb, verbatim
                      from customerProjects.ts. The headline fields stay in
                      `projects`, which is the reference where it holds a value.
  project_risk_flag   one row per risk flag (ABAC classification as a column).
Both carry verification_state / verified_by / verified_at / source (as 066/067).
Read by the project's companies (app_company_can_see_capacity), written by GEX.
Rows come from scripts/move_project_profiles_20261025.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "068"
down_revision: Union[str, None] = "067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
READ = f"{ADMIN} OR app_company_can_see_capacity(project_id, {ME})"
RECORD = """verification_state tb_verification_state NOT NULL DEFAULT 'UNVERIFIED',
           verified_by text, verified_at timestamptz,
           source text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now(),
           created_by text NOT NULL DEFAULT current_user,
           updated_at timestamptz NOT NULL DEFAULT now(),
           CHECK ((verification_state = 'UNVERIFIED') = (verified_by IS NULL AND verified_at IS NULL))"""
TABLES = ("project_profile", "project_risk_flag")


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q(f"""CREATE TABLE project_profile (
           project_id text PRIMARY KEY REFERENCES projects(project_id),
           profile jsonb NOT NULL,
           {RECORD})""")
    _q(f"""CREATE TABLE project_risk_flag (
           id text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           claim text NOT NULL,
           severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
           confidence text NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
           category text NOT NULL,
           owner_function text NOT NULL,
           classification text NOT NULL CHECK (classification IN
             ('PUBLIC', 'STAKEHOLDER', 'CONFIDENTIAL', 'RESTRICTED')),
           source_ids text[] NOT NULL DEFAULT '{{}}',
           status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'WAIVED', 'RESOLVED')),
           seq int NOT NULL DEFAULT 0,
           {RECORD})""")
    _q("CREATE INDEX ix_project_risk_flag_project ON project_risk_flag (project_id, seq)")
    for t in TABLES:
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING ({READ})")
        _q(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {t}_update ON {t} FOR UPDATE USING ({ADMIN}) WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {t}_delete ON {t} FOR DELETE USING ({ADMIN})")
    n = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relforcerowsecurity"), {"t": list(TABLES)}).scalar()
    assert n == len(TABLES), "068 tables must be under FORCED RLS"


def downgrade() -> None:
    for t in reversed(TABLES):
        _q(f"DROP TABLE IF EXISTS {t}")
