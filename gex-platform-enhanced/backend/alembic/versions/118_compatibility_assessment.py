"""Decisions keep their inputs: stored compatibility assessments (discovery Phase 1, R7; report §6.3).

Revision ID: 118
Revises: 117

`core/compatibility.assess` compares a listing, as an anonymous member sees it, with an RFQ's
requirements: per requirement Compatible, Incompatible (reason) or Needs evidence (what). It is
computed on view and STORED when a company acts on it (a proposal now; an enquiry or acceptance
later), with everything it used: the requirements and their sha256, the listing snapshot, each
outcome. A row is never changed or removed; a re-run adds one. A proposal keeps the assessment it
was made on (`proposal_order_id`).

Readers: the company that acted, and GEX. Writer: the market operator connection, after
`market_engine` authorises the party (as every market write).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "118"
down_revision: Union[str, None] = "117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE compatibility_assessment (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            rfq_id uuid NOT NULL REFERENCES tb_rfq(id),
            listing_order_id uuid NOT NULL REFERENCES tb_order(id),
            proposal_order_id uuid REFERENCES tb_order(id),
            purpose text NOT NULL CHECK (purpose IN ('proposal', 'enquiry', 'acceptance')),
            requirements jsonb NOT NULL,
            requirements_sha256 text NOT NULL CHECK (requirements_sha256 ~ '^[0-9a-f]{64}$'),
            listing jsonb NOT NULL,
            outcomes jsonb NOT NULL CHECK (jsonb_typeof(outcomes) = 'array'),
            status text NOT NULL CHECK (status IN ('compatible', 'incompatible', 'needs_evidence')),
            company_id text NOT NULL,
            actor_id text NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now())""")
    _q("CREATE INDEX compatibility_assessment_rfq ON compatibility_assessment (rfq_id, listing_order_id)")
    _q("ALTER TABLE compatibility_assessment ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE compatibility_assessment FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY compatibility_assessment_read ON compatibility_assessment FOR SELECT "
       f"USING ({ADMIN} OR company_id = {CURRENT})")
    _q(f"CREATE POLICY compatibility_assessment_operator_insert ON compatibility_assessment FOR INSERT WITH CHECK {ADMIN}")
    _q("REVOKE ALL ON compatibility_assessment FROM gex_app")
    _q("GRANT SELECT, INSERT ON compatibility_assessment TO gex_app")
    _q("""CREATE FUNCTION compatibility_assessment_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'APPEND_ONLY: a stored assessment is never changed or removed; add a new one'
                USING ERRCODE = 'check_violation'; END $$""")
    _q("CREATE TRIGGER compatibility_assessment_append_only BEFORE UPDATE OR DELETE ON compatibility_assessment "
       "FOR EACH ROW EXECUTE FUNCTION compatibility_assessment_append_only()")
    bad = op.get_bind().execute(sa.text(
        "SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'compatibility_assessment' "
        "AND privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')")).scalar()
    assert not bad, f"gex_app must not hold {bad} on compatibility_assessment"


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS compatibility_assessment")
    _q("DROP FUNCTION IF EXISTS compatibility_assessment_append_only()")
