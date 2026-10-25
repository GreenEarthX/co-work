"""Project datasets and id aliases — the last per-project data in backend code.

Revision ID: 069
Revises: 068

WHY (JML, 2026-10-25: project data out of code, part 2)
-------------------------------------------------------
Four modules held per-project figures as dictionaries, each with a DEFAULT that
answered for every project it did not know:
  core/project_truth.PROJECT_TRUTH          deal-killer and task-router inputs (7)
  api/v1/routes_structuring.DEMO_CONTEXTS   structuring context (3; default "Breizh SAF")
  api/v1/routes_finance_model._DRAWDOWN_BY_PROJECT  milestones and drawdowns (2)
  api/v1/adjacency.MOCK_PROJECTS            adjacency metadata (1 real project)
and PROJECT_ID_ALIASES (retired id -> current id) was copied in two modules.

WHAT
----
  project_dataset   (project_id, kind) -> payload jsonb, verbatim, UNVERIFIED by
                    default, with verified_by / verified_at / source as 066-068.
                    kind: deal_inputs | task_router_inputs | structuring_context
                          | drawdown_layer | adjacency_profile
  project_id_alias  retired id -> project_id (reference data).
The defaults are NOT moved: a project without a dataset now has no such data
("not recorded"), and the engines that read it fail closed. Rows come from
scripts/move_project_datasets_20261025.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "069"
down_revision: Union[str, None] = "068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
KINDS = ("deal_inputs", "task_router_inputs", "structuring_context", "drawdown_layer", "adjacency_profile")
POLICIES = {"project_dataset": f"{ADMIN} OR app_company_can_see_capacity(project_id, {ME})",
            "project_id_alias": "true"}


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    _q(f"""CREATE TABLE project_dataset (
           project_id text NOT NULL REFERENCES projects(project_id),
           kind text NOT NULL CHECK (kind IN ({kinds})),
           payload jsonb NOT NULL,
           verification_state tb_verification_state NOT NULL DEFAULT 'UNVERIFIED',
           verified_by text, verified_at timestamptz,
           source text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now(),
           created_by text NOT NULL DEFAULT current_user,
           updated_at timestamptz NOT NULL DEFAULT now(),
           PRIMARY KEY (project_id, kind),
           CHECK ((verification_state = 'UNVERIFIED') = (verified_by IS NULL AND verified_at IS NULL)))""")
    _q("""CREATE TABLE project_id_alias (
           alias text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           note text,
           created_at timestamptz NOT NULL DEFAULT now(),
           CHECK (alias <> project_id))""")
    for t, read in POLICIES.items():
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING ({read})")
        _q(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {t}_update ON {t} FOR UPDATE USING ({ADMIN}) WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {t}_delete ON {t} FOR DELETE USING ({ADMIN})")


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS project_id_alias")
    _q("DROP TABLE IF EXISTS project_dataset")
