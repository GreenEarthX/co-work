"""Risk passes by the Incoterm (GreenMesh Phase 2 Step 3, amendment B1; sub-step 2).

Revision ID: 106
Revises: 105

Risk is its own record, governed by the Incoterm and named place of the confirmed terms
(ruling R1: the Incoterm governs risk only). It is DERIVED, with no party act: the delivery
record writes `DELIVERY_FACT_RISK_PASSED` in the same transaction as the act that passes it.

    FCA FAS FOB CFR CIF CPT CIP   at dispatch (IN_TRANSIT), at the shipment point
    EXW                           at dispatch at the latest (placing at the buyer's disposal
                                  is not recorded separately)
    DAP DDP                       on ARRIVED
    DPU                           on ARRIVED with unloading recorded (DELIVERY_FACT_UNLOADED,
                                  the buyer's, naming an unloading record on file)
    C terms (CPT CIP CFR CIF)     the named place is the destination, so the confirmed terms
                                  must also name the shipment point; without it risk is
                                  refused, and the delivery says so.

Facts are events that do not change the state: 103 read the state from the LATEST
`DELIVERY_*` event; from 106 it reads the latest STATE event, skipping `DELIVERY_FACT_*`.

  deliveries.shipment_point   read from the confirmed terms at scheduling, fixed by trigger.
  delivery_document           documents on file by sha256 for a delivery (unloading record now;
                              B/L, certificate, waiver later). Append-only; read by whoever
                              may read the delivery; written only by the operator connection.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "106"
down_revision: Union[str, None] = "105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
BASE_TYPES = ("CREATED_FROM_MATCH", "MIGRATED", "VERSION", "COUNTERPARTY_SET", "CONFIRMED", "DISPUTED",
              "STATUS_CHANGED", "ADVERSE_FACT_REPORTED", "ADVERSE_FACT_CLEARED", "NOVATION")
STATES = ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION", "ACCEPTED", "REJECTED",
          "TITLE_TRANSFERRED", "SETTLED", "DISPUTED")
FACTS_103 = ()
FACTS = ("RISK_PASSED", "UNLOADED")
DOC_KINDS = ("UNLOADING_RECORD", "BILL_OF_LADING", "DELIVERY_ORDER", "INSPECTION_CERTIFICATE",
             "INSPECTOR_APPOINTMENT", "WAIVER", "DISPUTE_RESOLUTION")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _event_types(facts) -> tuple:
    return BASE_TYPES + tuple(f"DELIVERY_{s}" for s in STATES) + tuple(f"DELIVERY_FACT_{f}" for f in facts)


# The state of a delivery: its latest STATE event (facts skipped).
LATEST_STATE = ("SELECT substr(e.event_type, 10) FROM tb_contract_event e WHERE e.delivery_id = {d} "
                "AND e.event_type NOT LIKE 'DELIVERY\\_FACT\\_%' ORDER BY e.seq DESC LIMIT 1")

EVENT_CHECK = """CREATE OR REPLACE FUNCTION delivery_event_check() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE d record; prev text; nxt text; fact text;
    BEGIN
      IF NEW.delivery_id IS NULL THEN RETURN NEW; END IF;
      SELECT * INTO d FROM deliveries WHERE id = NEW.delivery_id;
      IF d.contract_id IS DISTINCT FROM NEW.contract_id THEN
        RAISE EXCEPTION 'DELIVERY_CONTRACT: delivery % is not on contract %', NEW.delivery_id, NEW.contract_id
          USING ERRCODE = 'check_violation';
      END IF;
      prev := coalesce((""" + LATEST_STATE.format(d="NEW.delivery_id") + """), '');

      IF NEW.event_type LIKE 'DELIVERY\\_FACT\\_%' THEN
        fact := substr(NEW.event_type, 15);
        IF EXISTS (SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
                   AND e.event_type = NEW.event_type) THEN
          RAISE EXCEPTION 'DELIVERY_FACT_ONCE: % is already recorded for delivery %', fact, NEW.delivery_id
            USING ERRCODE = 'check_violation';
        END IF;
        IF fact = 'UNLOADED' THEN
          IF d.incoterm IS DISTINCT FROM 'DPU' THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: unloading is recorded for a DPU delivery'
              USING ERRCODE = 'check_violation';
          END IF;
          IF prev NOT IN ('ARRIVED', 'QUALITY_VERIFICATION') THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: unloading follows arrival, not %', nullif(prev, '')
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
            RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: the buyer records unloading' USING ERRCODE = 'check_violation';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                         AND x.kind = 'UNLOADING_RECORD') THEN
            RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: unloading names an unloading record on file'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;
        IF fact = 'RISK_PASSED' THEN
          IF NEW.company_id IS NOT NULL THEN
            RAISE EXCEPTION 'DELIVERY_RISK_DERIVED: risk passes by the Incoterm, not by a party''s act'
              USING ERRCODE = 'check_violation';
          END IF;
          IF d.incoterm IS NULL THEN
            RAISE EXCEPTION 'DELIVERY_RISK_NO_INCOTERM: the confirmed terms name no Incoterm and place'
              USING ERRCODE = 'check_violation';
          END IF;
          IF d.incoterm IN ('CPT', 'CIP', 'CFR', 'CIF') AND d.shipment_point IS NULL THEN
            RAISE EXCEPTION 'DELIVERY_RISK_NO_SHIPMENT_POINT: % names the destination; the terms name no shipment point',
              d.incoterm USING ERRCODE = 'check_violation';
          END IF;
          IF (d.incoterm IN ('EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP') AND prev IS DISTINCT FROM 'IN_TRANSIT')
             OR (d.incoterm IN ('DAP', 'DDP') AND prev IS DISTINCT FROM 'ARRIVED')
             OR (d.incoterm = 'DPU' AND NOT (prev IN ('ARRIVED', 'QUALITY_VERIFICATION') AND EXISTS (
                   SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
                   AND e.event_type = 'DELIVERY_FACT_UNLOADED'))) THEN
            RAISE EXCEPTION 'DELIVERY_RISK_ORDER: under % risk does not pass at %', d.incoterm, nullif(prev, '')
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';
      END IF;

      nxt := substr(NEW.event_type, 10);
      IF nxt IN ('ACCEPTED', 'REJECTED', 'TITLE_TRANSFERRED', 'SETTLED') THEN
        RAISE EXCEPTION 'DELIVERY_STEP_NOT_BUILT: % needs quality before title (Phase 2 Step 3)', nxt
          USING ERRCODE = 'check_violation';
      END IF;
      IF NOT ((prev = '' AND nxt = 'SCHEDULED')
           OR (prev = 'SCHEDULED' AND nxt = 'IN_TRANSIT')
           OR (prev = 'IN_TRANSIT' AND nxt = 'ARRIVED')
           OR (prev = 'ARRIVED' AND nxt = 'QUALITY_VERIFICATION')
           OR (prev = 'QUALITY_VERIFICATION' AND nxt IN ('ACCEPTED', 'REJECTED'))
           OR (prev = 'ACCEPTED' AND nxt = 'TITLE_TRANSFERRED')
           OR (prev = 'TITLE_TRANSFERRED' AND nxt = 'SETTLED')
           OR (prev IN ('SCHEDULED', 'IN_TRANSIT', 'ARRIVED', 'QUALITY_VERIFICATION', 'ACCEPTED',
                        'TITLE_TRANSFERRED') AND nxt = 'DISPUTED')) THEN
        RAISE EXCEPTION 'DELIVERY_STATE_ORDER: % cannot follow %', nxt, coalesce(nullif(prev, ''), 'nothing')
          USING ERRCODE = 'check_violation';
      END IF;
      IF (nxt IN ('SCHEDULED', 'IN_TRANSIT') AND NEW.company_id IS DISTINCT FROM d.seller_company_id)
         OR (nxt = 'ARRIVED' AND NEW.company_id IS DISTINCT FROM d.buyer_company_id)
         OR (nxt IN ('QUALITY_VERIFICATION', 'DISPUTED')
             AND NEW.company_id IS DISTINCT FROM d.seller_company_id
             AND NEW.company_id IS DISTINCT FROM d.buyer_company_id) THEN
        RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: % is not the party that records %', NEW.company_id, nxt
          USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$"""

CONSISTENT = """CREATE OR REPLACE FUNCTION delivery_consistent() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE did text; st text; latest text; drawn numeric;
    BEGIN
      IF TG_TABLE_NAME = 'deliveries' THEN did := NEW.id; ELSE did := NEW.delivery_id; END IF;
      IF did IS NULL THEN RETURN NULL; END IF;
      SELECT status INTO st FROM deliveries WHERE id = did;
      latest := (""" + LATEST_STATE.format(d="did") + """);
      IF latest IS DISTINCT FROM st THEN
        RAISE EXCEPTION 'DELIVERY_STATE_MISMATCH: delivery % is % but its latest state event says %',
          did, st, coalesce(latest, 'nothing') USING ERRCODE = 'check_violation';
      END IF;
      SELECT coalesce(sum(kg), 0) INTO drawn FROM delivery_draw WHERE delivery_id = did;
      IF drawn <> (SELECT nominated_kg FROM deliveries WHERE id = did) THEN
        RAISE EXCEPTION 'DELIVERY_DRAWS: delivery % nominates a quantity its draws (% kg) do not make up',
          did, drawn USING ERRCODE = 'check_violation';
      END IF;
      RETURN NULL;
    END $$"""


def upgrade() -> None:
    have = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'tb_contract_event_event_type_check'").scalar()
    expected = _event_types(FACTS_103)
    assert have and all(f"'{t}'" in have for t in expected) and have.count("'") == 2 * len(expected), have
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       f"{_in(_event_types(FACTS))})")

    _q("ALTER TABLE deliveries ADD COLUMN shipment_point text")
    _q("""CREATE FUNCTION delivery_shipment_point_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.shipment_point IS DISTINCT FROM OLD.shipment_point THEN
            RAISE EXCEPTION 'DELIVERY_FIXED: a delivery''s shipment point is read from its terms once'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER deliveries_shipment_point_fixed BEFORE UPDATE OF shipment_point ON deliveries "
       "FOR EACH ROW EXECUTE FUNCTION delivery_shipment_point_fixed()")

    _q(f"""CREATE TABLE delivery_document (
            id bigserial PRIMARY KEY,
            delivery_id text NOT NULL REFERENCES deliveries(id),
            kind text NOT NULL CHECK (kind IN {_in(DOC_KINDS)}),
            sha256 character(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
            filename text NOT NULL,
            size_bytes integer NOT NULL CHECK (size_bytes > 0),
            stored_path text NOT NULL,
            uploaded_by text NOT NULL,
            company_id text NOT NULL REFERENCES tenants(company_id),
            uploaded_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (delivery_id, kind, sha256))""")
    _q("ALTER TABLE delivery_document ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE delivery_document FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY delivery_document_read ON delivery_document FOR SELECT USING "
       f"(app_company_sees_delivery(delivery_id, {CURRENT}))")
    _q(f"CREATE POLICY delivery_document_operator_insert ON delivery_document FOR INSERT WITH CHECK {ADMIN}")
    _q("REVOKE ALL ON delivery_document FROM gex_app")
    _q("GRANT SELECT, INSERT ON delivery_document TO gex_app")
    _q("GRANT USAGE ON SEQUENCE delivery_document_id_seq TO gex_app")
    _q("""CREATE FUNCTION delivery_document_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'DELIVERY_APPEND_ONLY: a document on file is never changed or removed'
            USING ERRCODE = 'check_violation';
        END $$""")
    _q("CREATE TRIGGER delivery_document_append_only BEFORE UPDATE OR DELETE ON delivery_document "
       "FOR EACH ROW EXECUTE FUNCTION delivery_document_append_only()")

    _q(EVENT_CHECK)
    _q(CONSISTENT)

    assert _q("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'delivery_document'").scalar()
    held = set(_q("SELECT privilege_type FROM information_schema.role_table_grants "
                  "WHERE grantee = 'gex_app' AND table_name = 'delivery_document'").scalars())
    assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on delivery_document"


def downgrade() -> None:
    for t in ("DELIVERY_FACT_RISK_PASSED", "DELIVERY_FACT_UNLOADED"):
        n = _q(f"SELECT count(*) FROM tb_contract_event WHERE event_type = '{t}'").scalar()
        assert n == 0, f"{n} {t} event(s) exist; refusing to drop the facts"
    n = _q("SELECT count(*) FROM delivery_document").scalar()
    assert n == 0, f"{n} delivery document(s) on file; refusing to drop the table"
    _q("DROP TABLE delivery_document")
    _q("DROP FUNCTION IF EXISTS delivery_document_append_only()")
    _q("DROP TRIGGER IF EXISTS deliveries_shipment_point_fixed ON deliveries")
    _q("DROP FUNCTION IF EXISTS delivery_shipment_point_fixed()")
    _q("ALTER TABLE deliveries DROP COLUMN shipment_point")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       f"{_in(_event_types(FACTS_103))})")
    # 103's state rule (the latest DELIVERY_* event). The fact branch stays in the function but
    # is unreachable: the event-type check above admits no DELIVERY_FACT_* type any more.
    old_latest = ("SELECT substr(e.event_type, 10) FROM tb_contract_event e WHERE e.delivery_id = {d} "
                  "ORDER BY e.seq DESC LIMIT 1")
    _q(EVENT_CHECK.replace(LATEST_STATE.format(d="NEW.delivery_id"), old_latest.format(d="NEW.delivery_id")))
    _q(CONSISTENT.replace(LATEST_STATE.format(d="did"), old_latest.format(d="did")))
