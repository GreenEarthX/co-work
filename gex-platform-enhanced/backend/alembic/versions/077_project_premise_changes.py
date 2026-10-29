"""Project premises change only on a document and a second party.

Revision ID: 077
Revises: 076

JML, 2026-10-28. The financing model and the power model decide which evidence
applies: balance-sheet funding drops the lender-protection items and waives G6
and G8; a power model drops the PPA items or the behind-the-meter items. The
owner's executive used to change them alone. Now a change that REMOVES items
stays PENDING and removes nothing until a supporting document is registered and
a second party confirms it — a funder, the counterparty, or GEX staff. Any
project party may register a document contesting it, which keeps the lender
protections in place until GEX staff decide.

  project_premise_change     one proposed change and its decision
  project_premise_document   the documents supporting or contesting it (sha256)

A contest or a rejection of a change already APPLIED restores the protective
premise for the engine (project finance; no declared power model, i.e. the full
evidence set) until GEX staff confirm it again.

Premises declared before this rule are recorded as CONFIRMED by
'PRE_RULE_DECLARATION' with no document — findable, and open to contest.

RLS: the project's companies read and write (the routes decide who may do
what); only GEX deletes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "077"
down_revision: Union[str, None] = "076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
ON_PROJECT = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE project_premise_change (
           id bigserial PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           field text NOT NULL CHECK (field IN ('financing_model', 'power_model')),
           from_value text, to_value text NOT NULL,
           status text NOT NULL CHECK (status IN ('PENDING', 'CONTESTED', 'CONFIRMED', 'REJECTED', 'WITHDRAWN')),
           proposed_by text NOT NULL, proposed_company text,
           proposed_at timestamptz NOT NULL DEFAULT now(),
           decided_by text, decided_company text, decided_at timestamptz,
           decision_note text,
           -- true once the change has been put into project_context. A contest
           -- or rejection of an APPLIED change restores the protective premise.
           applied boolean NOT NULL DEFAULT false)""")
    _q("""CREATE UNIQUE INDEX ux_premise_one_open ON project_premise_change (project_id, field)
          WHERE status IN ('PENDING', 'CONTESTED')""")
    _q("""CREATE TABLE project_premise_document (
           id bigserial PRIMARY KEY,
           change_id bigint NOT NULL REFERENCES project_premise_change(id),
           project_id text NOT NULL REFERENCES projects(project_id),
           role text NOT NULL CHECK (role IN ('SUPPORT', 'CONTEST')),
           sha256 text NOT NULL CHECK (length(sha256) = 64),
           filename text NOT NULL, stored_path text NOT NULL, size_bytes integer NOT NULL,
           uploaded_by text NOT NULL, company_id text,
           note text,
           uploaded_at timestamptz NOT NULL DEFAULT now())""")
    for t in ("project_premise_change", "project_premise_document"):
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING {ON_PROJECT}")
        _q(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK {ON_PROJECT}")
        _q(f"CREATE POLICY {t}_update ON {t} FOR UPDATE USING {ON_PROJECT} WITH CHECK {ON_PROJECT}")
        _q(f"CREATE POLICY {t}_delete ON {t} FOR DELETE USING {ADMIN}")
    # A supporting or contesting document is evidence of a decision: never rewritten.
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON project_premise_document FROM gex_app")
    # The premises in force before the rule: recorded, undocumented, contestable.
    _q("""INSERT INTO project_premise_change (project_id, field, from_value, to_value, status, proposed_by,
                                              decided_by, decided_at, decision_note, applied)
          SELECT c.project_id, f.field, NULL, f.value, 'CONFIRMED', 'PRE_RULE_DECLARATION',
                 'PRE_RULE_DECLARATION', now(), 'Declared before 2026-10-28; no supporting document on file.', true
          FROM project_context c
          JOIN projects p ON p.project_id = c.project_id
          CROSS JOIN LATERAL (VALUES ('power_model', c.power_model),
                                     ('financing_model', c.financing_model)) AS f(field, value)
          WHERE f.value IS NOT NULL
            AND (f.field = 'power_model' OR f.value = 'BALANCE_SHEET')""")


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS project_premise_document")
    _q("DROP TABLE IF EXISTS project_premise_change")
