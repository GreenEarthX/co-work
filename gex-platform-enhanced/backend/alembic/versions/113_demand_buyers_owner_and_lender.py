"""A project's buyer list is read by its owner, its mandated lender and GEX only.

Revision ID: 113
Revises: 112

`project_dataset` kind `demand_buyers` names every buyer recorded for a project. Its read
rule (069) was the generic "may see this project" (`app_company_can_see_capacity`), so a
prospective buyer holding project access read the names of the buyers it competes with,
through GET /api/v1/projects/{id}/datasets/demand_buyers. Measured 2026-11-13: BremenThree
AG (OFFTAKER, STAKEHOLDER on proj_hamburgone_emethanol) read that project's list. Today
each list names only one buyer, so nothing competing was exposed yet; the rule was wrong.

Now a `demand_buyers` row needs GEX, the owning company, or a company holding
`project_access` with access_role MANDATED_LENDER on that project (the Sales screen is a
producer and bank screen, and a lender needs the offtakers for credit). Every other kind
keeps 069's rule unchanged. The lender test is a SECURITY DEFINER helper, like 032's,
so the policy does not depend on `project_access`'s own RLS.

Decided in the session of 2026-11-13 ("close it"); who besides the owner reads the list
is JML's to widen — add an access_role here, never fall back to "may see the project".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "113"
down_revision: Union[str, None] = "112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
SEES = f"app_company_can_see_capacity(project_id, {CURRENT})"
BUYER_LIST_READERS = (f"(app_company_owns_project(project_id, {CURRENT}) "
                      f"OR app_company_is_mandated_lender(project_id, {CURRENT}))")
NEW_READ = (f"({ADMIN} OR (kind <> 'demand_buyers' AND {SEES}) "
            f"OR (kind = 'demand_buyers' AND {BUYER_LIST_READERS}))")
OLD_READ = f"({ADMIN} OR {SEES})"                                   # 069's rule


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _set_read(rule: str) -> None:
    _q("DROP POLICY project_dataset_read ON project_dataset")
    _q(f"CREATE POLICY project_dataset_read ON project_dataset FOR SELECT USING {rule}")


def upgrade() -> None:
    _q("""CREATE OR REPLACE FUNCTION app_company_is_mandated_lender(p_project_id text, p_company_id text)
          RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
          AS $$ SELECT EXISTS (SELECT 1 FROM project_access
                               WHERE project_id = p_project_id AND company_id = p_company_id
                                 AND access_role = 'MANDATED_LENDER') $$""")
    _q("REVOKE ALL ON FUNCTION app_company_is_mandated_lender(text, text) FROM PUBLIC")
    _q("GRANT EXECUTE ON FUNCTION app_company_is_mandated_lender(text, text) TO gex_app")
    _set_read(NEW_READ)
    qual = op.get_bind().execute(sa.text(
        "SELECT qual FROM pg_policies WHERE tablename = 'project_dataset' AND cmd = 'SELECT'")).scalar()
    assert "demand_buyers" in qual and "app_company_is_mandated_lender" in qual, \
        f"project_dataset read policy does not restrict demand_buyers: {qual}"


def downgrade() -> None:
    _set_read(OLD_READ)
    _q("DROP FUNCTION IF EXISTS app_company_is_mandated_lender(text, text)")
