"""A non-binding enquiry, and contact released only by consent (discovery Phase 1, R9; D-D).

Revision ID: 119
Revises: 118

Before 119 the only way to reach a counterparty was a binding proposal (F18), and the contact an
RFQ promised to reveal "at match" was never released at all (F19). D-D (JML 2026-11-14): an enquiry,
separate from a proposal, on ONE listing or ONE RFQ; the receiving party shares contact or declines.

  market_enquiry          who asks (company, user) whom, about which listing or RFQ (exactly one),
                          optionally citing the asker's own RFQ (so the assessment it was sent on is
                          stored, 118); status open -> contact_shared | declined | withdrawn, and
                          contact_shared -> closed. Nothing else changes, and nothing is deleted.
  market_enquiry_message  the thread; append-only for every role.

Identity is not stored here: the market engine releases names and the named persons from
tenants / auth_users only while status is contact_shared, to both parties.

Readers: the two parties and GEX. Writer: the market operator connection, after market_engine
authorises the party (as every market write).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "119"
down_revision: Union[str, None] = "118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
PARTY = f"({ADMIN} OR from_company_id = {CURRENT} OR to_company_id = {CURRENT})"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE market_enquiry (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_order_id uuid REFERENCES tb_order(id),
            rfq_id uuid REFERENCES tb_rfq(id),
            about_rfq_id uuid REFERENCES tb_rfq(id),
            from_company_id text NOT NULL,
            from_user_id text NOT NULL,
            to_company_id text NOT NULL,
            status text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'contact_shared', 'declined', 'withdrawn', 'closed')),
            assessment_id uuid REFERENCES compatibility_assessment(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            decided_at timestamptz,
            decided_by text,
            CHECK ((listing_order_id IS NULL) <> (rfq_id IS NULL)),
            CHECK (from_company_id <> to_company_id))""")
    _q("CREATE UNIQUE INDEX market_enquiry_one_open_listing ON market_enquiry (from_company_id, listing_order_id) "
       "WHERE status = 'open' AND listing_order_id IS NOT NULL")
    _q("CREATE UNIQUE INDEX market_enquiry_one_open_rfq ON market_enquiry (from_company_id, rfq_id) "
       "WHERE status = 'open' AND rfq_id IS NOT NULL")
    _q("""CREATE TABLE market_enquiry_message (
            id bigserial PRIMARY KEY,
            enquiry_id uuid NOT NULL REFERENCES market_enquiry(id),
            company_id text NOT NULL,
            actor_id text NOT NULL,
            body text NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 4000),
            evidence_request text CHECK (evidence_request IS NULL OR length(btrim(evidence_request)) BETWEEN 1 AND 1000),
            created_at timestamptz NOT NULL DEFAULT now())""")
    _q("CREATE INDEX market_enquiry_message_thread ON market_enquiry_message (enquiry_id, id)")

    for t, read in (("market_enquiry", PARTY),
                    ("market_enquiry_message", f"({ADMIN} OR EXISTS (SELECT 1 FROM market_enquiry e WHERE e.id = enquiry_id "
                                               f"AND (e.from_company_id = {CURRENT} OR e.to_company_id = {CURRENT})))")):
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING {read}")
        _q(f"CREATE POLICY {t}_operator_insert ON {t} FOR INSERT WITH CHECK {ADMIN}")
        _q(f"REVOKE ALL ON {t} FROM gex_app")
        _q(f"GRANT SELECT, INSERT ON {t} TO gex_app")
    _q(f"CREATE POLICY market_enquiry_operator_update ON market_enquiry FOR UPDATE USING {ADMIN} WITH CHECK {ADMIN}")
    _q("GRANT UPDATE (status, decided_at, decided_by) ON market_enquiry TO gex_app")
    _q("GRANT USAGE ON SEQUENCE market_enquiry_message_id_seq TO gex_app")

    _q("""CREATE FUNCTION market_enquiry_transition() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF TG_OP = 'DELETE' THEN
              RAISE EXCEPTION 'ENQUIRY_KEPT: an enquiry is never deleted' USING ERRCODE = 'check_violation';
            END IF;
            IF (NEW.id, NEW.listing_order_id, NEW.rfq_id, NEW.about_rfq_id, NEW.from_company_id, NEW.from_user_id,
                NEW.to_company_id, NEW.assessment_id, NEW.created_at)
               IS DISTINCT FROM (OLD.id, OLD.listing_order_id, OLD.rfq_id, OLD.about_rfq_id, OLD.from_company_id,
                OLD.from_user_id, OLD.to_company_id, OLD.assessment_id, OLD.created_at) THEN
              RAISE EXCEPTION 'ENQUIRY_FIXED: who asked whom about what never changes' USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
                 (OLD.status = 'open' AND NEW.status IN ('contact_shared', 'declined', 'withdrawn'))
              OR (OLD.status = 'contact_shared' AND NEW.status = 'closed')) THEN
              RAISE EXCEPTION 'ENQUIRY_STATE: % -> % is not a transition', OLD.status, NEW.status
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END $$""")
    _q("CREATE TRIGGER market_enquiry_transition BEFORE UPDATE OR DELETE ON market_enquiry "
       "FOR EACH ROW EXECUTE FUNCTION market_enquiry_transition()")
    _q("""CREATE FUNCTION market_enquiry_message_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'APPEND_ONLY: a message is never changed or removed' USING ERRCODE = 'check_violation'; END $$""")
    _q("CREATE TRIGGER market_enquiry_message_append_only BEFORE UPDATE OR DELETE ON market_enquiry_message "
       "FOR EACH ROW EXECUTE FUNCTION market_enquiry_message_append_only()")

    bad = op.get_bind().execute(sa.text(
        "SELECT string_agg(table_name || ':' || privilege_type, ',') FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name IN ('market_enquiry', 'market_enquiry_message') "
        "AND privilege_type IN ('DELETE', 'TRUNCATE') "
        "OR grantee = 'gex_app' AND table_name = 'market_enquiry_message' AND privilege_type = 'UPDATE'")).scalar()
    assert not bad, f"gex_app must not hold {bad}"


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS market_enquiry_message")
    _q("DROP TABLE IF EXISTS market_enquiry")
    _q("DROP FUNCTION IF EXISTS market_enquiry_message_append_only()")
    _q("DROP FUNCTION IF EXISTS market_enquiry_transition()")
