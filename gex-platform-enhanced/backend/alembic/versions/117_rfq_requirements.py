"""What a buyer requires: structured RFQ requirements (discovery Phase 1; F22).

Revision ID: 117
Revises: 116

Before 117 a buyer could state molecule, rate, window and a price ceiling, nothing else; the API's
`compliance_requirements` list was never collected by a screen nor shown (discovery review F22).
`tb_rfq.requirements` holds the buyer's limits, validated by core/requirements.py:

    max_ci_gco2e_mj, ci_min_basis (estimate|calculated|measured), regimes [...], accepted_schemes [...],
    min_evidence_state (submitted|verified), physical_form, quality_limits {parameter: {min|max}},
    incoterms [...], named_place, delivery_country, mandatory [...]   (which of these must hold)

A published RFQ's requirements never change (trigger), as its terms are frozen: a seller who
answered it answered THESE requirements.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "117"
down_revision: Union[str, None] = "116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("ALTER TABLE tb_rfq ADD COLUMN requirements jsonb NOT NULL DEFAULT '{}'::jsonb "
       "CHECK (jsonb_typeof(requirements) = 'object')")
    _q("""CREATE FUNCTION tb_rfq_requirements_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.requirements IS DISTINCT FROM OLD.requirements AND OLD.status <> 'draft' THEN
              RAISE EXCEPTION 'RFQ_REQUIREMENTS_FIXED: a published RFQ''s requirements never change'
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END $$""")
    _q("CREATE TRIGGER tb_rfq_requirements_fixed BEFORE UPDATE OF requirements ON tb_rfq "
       "FOR EACH ROW EXECUTE FUNCTION tb_rfq_requirements_fixed()")


def downgrade() -> None:
    _q("DROP TRIGGER IF EXISTS tb_rfq_requirements_fixed ON tb_rfq")
    _q("DROP FUNCTION IF EXISTS tb_rfq_requirements_fixed()")
    _q("ALTER TABLE tb_rfq DROP COLUMN IF EXISTS requirements")
