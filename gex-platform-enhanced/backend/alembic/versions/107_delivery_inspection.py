"""Quality before title: the inspector, the certificate, ACCEPTED and REJECTED
(GreenMesh Phase 2 Step 3, sub-step 3; D1, D2, D3, amendment B4).

Revision ID: 107
Revises: 106

Facts on the delivery's contract chain (all `DELIVERY_FACT_*`, so the state does not move):

  INSPECTOR_PROPOSED  a party names an inspector company, with the appointment on file (D1).
                      Never the seller's or the buyer's company, never GEX, an active tenant
                      with an ACTIVE account. A new proposal replaces an unagreed one.
  INSPECTOR_AGREED    the OTHER party agrees the latest proposal (four eyes inside it, as
                      TRADE_CONFIRM: core/delivery_inspection.py). Until then there is no
                      inspector. A replacement takes the same two steps, before certification.
  CERTIFIED           the agreed inspector's company, with the certificate on file and the
                      measured value of every parameter of the confirmed spec sheet (D2),
                      judged PASS/FAIL per parameter. Once.
  WAIVER_PROPOSED     after a FAIL certificate, a party proposes accepting it anyway, with the
                      waiver on file (D3).
  WAIVER_CONFIRMED    the other party confirms it (four eyes). Once.

States now built: ACCEPTED (derived, no party: a PASS certificate, or a FAIL certificate with
a confirmed waiver) and REJECTED (the buyer, after a FAIL certificate with no confirmed
waiver). Both from QUALITY_VERIFICATION; the DISPUTED exit is sub-step 4. TITLE_TRANSFERRED
and SETTLED stay refused (sub-step 5; stop before SETTLED).

`deliveries.inspector_company_id` is the agreed inspector, checked at commit against the latest
INSPECTOR_AGREED fact; the agreed inspector READS the delivery (103's read rule widened).
B4: a REJECTED delivery's draws no longer count against its tokens (the draws stay on record).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "107"
down_revision: Union[str, None] = "106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
BASE_TYPES = ("CREATED_FROM_MATCH", "MIGRATED", "VERSION", "COUNTERPARTY_SET", "CONFIRMED", "DISPUTED",
              "STATUS_CHANGED", "ADVERSE_FACT_REPORTED", "ADVERSE_FACT_CLEARED", "NOVATION")
STATES = ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION", "ACCEPTED", "REJECTED",
          "TITLE_TRANSFERRED", "SETTLED", "DISPUTED")
FACTS_106 = ("RISK_PASSED", "UNLOADED")
FACTS = FACTS_106 + ("INSPECTOR_PROPOSED", "INSPECTOR_AGREED", "CERTIFIED", "WAIVER_PROPOSED", "WAIVER_CONFIRMED")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _event_types(facts) -> tuple:
    return BASE_TYPES + tuple(f"DELIVERY_{s}" for s in STATES) + tuple(f"DELIVERY_FACT_{f}" for f in facts)


LATEST_STATE = ("SELECT substr(e.event_type, 10) FROM tb_contract_event e WHERE e.delivery_id = {d} "
                "AND e.event_type NOT LIKE 'DELIVERY\\_FACT\\_%' ORDER BY e.seq DESC LIMIT 1")
# The latest fact of a kind for the delivery, as jsonb (its note), or NULL.
LATEST_FACT = ("(SELECT e.note::jsonb FROM tb_contract_event e WHERE e.delivery_id = {d} "
               "AND e.event_type = 'DELIVERY_FACT_{f}' ORDER BY e.seq DESC LIMIT 1)")
LATEST_FACT_COMPANY = ("(SELECT e.company_id FROM tb_contract_event e WHERE e.delivery_id = {d} "
                       "AND e.event_type = 'DELIVERY_FACT_{f}' ORDER BY e.seq DESC LIMIT 1)")


def _f(f: str) -> str:
    return LATEST_FACT.format(d="NEW.delivery_id", f=f)


def _fc(f: str) -> str:
    return LATEST_FACT_COMPANY.format(d="NEW.delivery_id", f=f)


EVENT_CHECK = """CREATE OR REPLACE FUNCTION delivery_event_check() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE d record; prev text; nxt text; fact text; n jsonb; other text; insp text; cert jsonb;
    BEGIN
      IF NEW.delivery_id IS NULL THEN RETURN NEW; END IF;
      SELECT * INTO d FROM deliveries WHERE id = NEW.delivery_id;
      IF d.contract_id IS DISTINCT FROM NEW.contract_id THEN
        RAISE EXCEPTION 'DELIVERY_CONTRACT: delivery % is not on contract %', NEW.delivery_id, NEW.contract_id
          USING ERRCODE = 'check_violation';
      END IF;
      prev := coalesce((""" + LATEST_STATE.format(d="NEW.delivery_id") + """), '');
      n := CASE WHEN NEW.note IS NOT NULL AND left(NEW.note, 1) = '{' THEN NEW.note::jsonb ELSE '{}'::jsonb END;
      cert := """ + _f("CERTIFIED") + """;

      IF NEW.event_type LIKE 'DELIVERY\\_FACT\\_%' THEN
        fact := substr(NEW.event_type, 15);
        IF fact IN ('RISK_PASSED', 'UNLOADED', 'CERTIFIED', 'WAIVER_CONFIRMED') AND EXISTS (
             SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id AND e.event_type = NEW.event_type) THEN
          RAISE EXCEPTION 'DELIVERY_FACT_ONCE: % is already recorded for delivery %', fact, NEW.delivery_id
            USING ERRCODE = 'check_violation';
        END IF;
        IF fact = 'UNLOADED' THEN
          IF d.incoterm IS DISTINCT FROM 'DPU' THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: unloading is recorded for a DPU delivery' USING ERRCODE = 'check_violation';
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

        IF fact IN ('INSPECTOR_PROPOSED', 'INSPECTOR_AGREED') THEN
          IF prev NOT IN ('SCHEDULED', 'IN_TRANSIT', 'ARRIVED', 'QUALITY_VERIFICATION') OR cert IS NOT NULL THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: an inspector is appointed before certification, not at %',
              nullif(prev, '') USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS DISTINCT FROM d.seller_company_id AND NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
            RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: a party to the delivery appoints the inspector'
              USING ERRCODE = 'check_violation';
          END IF;
          insp := n ->> 'inspector_company_id';
          IF fact = 'INSPECTOR_PROPOSED' THEN
            IF insp IS NULL OR insp IN (d.seller_company_id, d.buyer_company_id) OR insp = 'greenearthx'
               OR NOT EXISTS (SELECT 1 FROM tenants t WHERE t.company_id = insp AND t.is_active)
               OR NOT EXISTS (SELECT 1 FROM auth_users u WHERE u.company_id = insp AND u.account_state = 'ACTIVE')
               OR EXISTS (SELECT 1 FROM auth_users u WHERE u.company_id = insp AND coalesce(u.is_platform_admin, 0) <> 0) THEN
              RAISE EXCEPTION 'DELIVERY_INSPECTOR_NOT_INDEPENDENT: % is not an independent, active, registered company', insp
                USING ERRCODE = 'check_violation';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                           AND x.kind = 'INSPECTOR_APPOINTMENT' AND x.sha256 = n ->> 'document_sha256') THEN
              RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: the proposal names the appointment on file'
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF """ + _f("INSPECTOR_PROPOSED") + """ IS NULL
             OR insp IS DISTINCT FROM (""" + _f("INSPECTOR_PROPOSED") + """ ->> 'inspector_company_id') THEN
            RAISE EXCEPTION 'DELIVERY_INSPECTOR_NOT_PROPOSED: % is not the inspector last proposed', insp
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS NOT DISTINCT FROM """ + _fc("INSPECTOR_PROPOSED") + """ THEN
            RAISE EXCEPTION 'DELIVERY_INSPECTOR_SAME_PARTY: the other party agrees the inspector'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;

        IF fact = 'CERTIFIED' THEN
          IF prev IS DISTINCT FROM 'QUALITY_VERIFICATION' THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: a certificate is recorded in QUALITY_VERIFICATION, not %',
              nullif(prev, '') USING ERRCODE = 'check_violation';
          END IF;
          IF d.inspector_company_id IS NULL OR NEW.company_id IS DISTINCT FROM d.inspector_company_id THEN
            RAISE EXCEPTION 'DELIVERY_NOT_THE_AGREED_INSPECTOR: % is not the inspector both parties agreed',
              NEW.company_id USING ERRCODE = 'check_violation';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                         AND x.kind = 'INSPECTION_CERTIFICATE' AND x.sha256 = n ->> 'document_sha256') THEN
            RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: the certificate is on file' USING ERRCODE = 'check_violation';
          END IF;
          IF n ->> 'result' NOT IN ('PASS', 'FAIL') THEN
            RAISE EXCEPTION 'DELIVERY_CERTIFICATE_RESULT: a certificate is PASS or FAIL' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;

        IF fact IN ('WAIVER_PROPOSED', 'WAIVER_CONFIRMED') THEN
          IF prev IS DISTINCT FROM 'QUALITY_VERIFICATION' OR cert IS NULL OR cert ->> 'result' IS DISTINCT FROM 'FAIL' THEN
            RAISE EXCEPTION 'DELIVERY_WAIVER_ORDER: a waiver follows a FAIL certificate, in QUALITY_VERIFICATION'
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS DISTINCT FROM d.seller_company_id AND NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
            RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: a party to the delivery records a waiver' USING ERRCODE = 'check_violation';
          END IF;
          IF fact = 'WAIVER_PROPOSED' THEN
            IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                           AND x.kind = 'WAIVER' AND x.sha256 = n ->> 'document_sha256') THEN
              RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: the waiver is on file' USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF """ + _fc("WAIVER_PROPOSED") + """ IS NULL OR NEW.company_id IS NOT DISTINCT FROM """ + _fc("WAIVER_PROPOSED") + """ THEN
            RAISE EXCEPTION 'DELIVERY_WAIVER_SAME_PARTY: the other party confirms the waiver'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';
      END IF;

      nxt := substr(NEW.event_type, 10);
      IF nxt IN ('TITLE_TRANSFERRED', 'SETTLED') THEN
        RAISE EXCEPTION 'DELIVERY_STEP_NOT_BUILT: % is Phase 2 Step 3 sub-step 5 (and SETTLED after it)', nxt
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
      IF nxt = 'ACCEPTED' THEN
        IF NEW.company_id IS NOT NULL THEN
          RAISE EXCEPTION 'DELIVERY_ACCEPTANCE_DERIVED: acceptance follows the certificate (or a confirmed waiver), not a party''s act'
            USING ERRCODE = 'check_violation';
        END IF;
        IF cert IS NULL OR NOT (cert ->> 'result' = 'PASS' OR EXISTS (
             SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
             AND e.event_type = 'DELIVERY_FACT_WAIVER_CONFIRMED')) THEN
          RAISE EXCEPTION 'DELIVERY_NOT_ACCEPTABLE: no PASS certificate and no confirmed waiver'
            USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
      END IF;
      IF nxt = 'REJECTED' THEN
        IF NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
          RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: the buyer rejects a delivery' USING ERRCODE = 'check_violation';
        END IF;
        IF cert IS NULL OR cert ->> 'result' IS DISTINCT FROM 'FAIL' OR EXISTS (
             SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
             AND e.event_type = 'DELIVERY_FACT_WAIVER_CONFIRMED') THEN
          RAISE EXCEPTION 'DELIVERY_NOT_REJECTABLE: a delivery is rejected on a FAIL certificate with no confirmed waiver'
            USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
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
    DECLARE did text; st text; latest text; drawn numeric; agreed text; holder text;
    BEGIN
      IF TG_TABLE_NAME = 'deliveries' THEN did := NEW.id; ELSE did := NEW.delivery_id; END IF;
      IF did IS NULL THEN RETURN NULL; END IF;
      SELECT status, inspector_company_id INTO st, holder FROM deliveries WHERE id = did;
      latest := (""" + LATEST_STATE.format(d="did") + """);
      IF latest IS DISTINCT FROM st THEN
        RAISE EXCEPTION 'DELIVERY_STATE_MISMATCH: delivery % is % but its latest state event says %',
          did, st, coalesce(latest, 'nothing') USING ERRCODE = 'check_violation';
      END IF;
      agreed := (""" + LATEST_FACT.format(d="did", f="INSPECTOR_AGREED") + """ ->> 'inspector_company_id');
      IF agreed IS DISTINCT FROM holder THEN
        RAISE EXCEPTION 'DELIVERY_INSPECTOR_MISMATCH: delivery % names inspector % but the agreed one is %',
          did, holder, agreed USING ERRCODE = 'check_violation';
      END IF;
      SELECT coalesce(sum(kg), 0) INTO drawn FROM delivery_draw WHERE delivery_id = did;
      IF drawn <> (SELECT nominated_kg FROM deliveries WHERE id = did) THEN
        RAISE EXCEPTION 'DELIVERY_DRAWS: delivery % nominates a quantity its draws (% kg) do not make up',
          did, drawn USING ERRCODE = 'check_violation';
      END IF;
      RETURN NULL;
    END $$"""

DRAW_GUARD = """CREATE OR REPLACE FUNCTION delivery_draw_guard() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE allocated numeric; drawn numeric;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'DELIVERY_APPEND_ONLY: a draw never changes' USING ERRCODE = 'check_violation';
      END IF;
      IF (SELECT status FROM deliveries WHERE id = NEW.delivery_id) <> 'SCHEDULED' THEN
        RAISE EXCEPTION 'DELIVERY_FIXED: draws are recorded when the delivery is scheduled'
          USING ERRCODE = 'check_violation';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM tb_contract_version_token vt JOIN tb_contract_version v ON v.id = vt.version_id
                     JOIN deliveries d ON d.contract_id = v.contract_id
                     WHERE d.id = NEW.delivery_id AND vt.token_id = NEW.token_id) THEN
        RAISE EXCEPTION 'DELIVERY_TOKEN_NOT_ON_CONTRACT: token % is not on this delivery''s contract', NEW.token_id
          USING ERRCODE = 'check_violation';
      END IF;
      PERFORM 1 FROM tokens WHERE id = NEW.token_id FOR UPDATE;
      SELECT coalesce(sum(volume_kg), 0)::numeric INTO allocated FROM mass_balance_allocations
       WHERE token_id = NEW.token_id;
      -- B4 (107): a REJECTED delivery's draws are released; they stay on record.
      SELECT coalesce(sum(x.kg), 0) INTO drawn FROM delivery_draw x JOIN deliveries y ON y.id = x.delivery_id
       WHERE x.token_id = NEW.token_id AND y.status <> 'REJECTED';
      IF drawn + NEW.kg > allocated THEN
        RAISE EXCEPTION 'DELIVERY_OVER_ALLOCATION: token % has % kg allocated from custody, % kg already drawn',
          NEW.token_id, allocated, drawn USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$"""

SEES = """CREATE OR REPLACE FUNCTION app_company_sees_delivery(p_delivery text, p_company text) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
      SELECT EXISTS (SELECT 1 FROM deliveries d WHERE d.id = p_delivery AND (
               p_company = 'PLATFORM_ADMIN' OR d.seller_company_id = p_company OR d.buyer_company_id = p_company
               OR d.inspector_company_id = p_company
               OR app_company_owns_project(d.project_id, p_company)
               OR app_company_has_project_access(d.project_id, p_company))) $$"""


def upgrade() -> None:
    have = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'tb_contract_event_event_type_check'").scalar()
    expected = _event_types(FACTS_106)
    assert have and all(f"'{t}'" in have for t in expected) and have.count("'") == 2 * len(expected), have
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       f"{_in(_event_types(FACTS))})")
    _q("ALTER TABLE deliveries ADD COLUMN inspector_company_id text REFERENCES tenants(company_id)")
    _q(EVENT_CHECK)
    _q(CONSISTENT)
    _q(DRAW_GUARD)
    _q(SEES)
    _q("DROP POLICY deliveries_read ON deliveries")
    _q(f"""CREATE POLICY deliveries_read ON deliveries FOR SELECT USING (
            {ADMIN} OR seller_company_id = {CURRENT} OR buyer_company_id = {CURRENT}
            OR inspector_company_id = {CURRENT}
            OR app_company_owns_project(project_id, {CURRENT})
            OR app_company_has_project_access(project_id, {CURRENT}))""")
    pols = dict(_q("SELECT policyname, cmd FROM pg_policies WHERE tablename = 'deliveries'").fetchall())
    assert pols == {"deliveries_read": "SELECT", "deliveries_operator_insert": "INSERT",
                    "deliveries_operator_update": "UPDATE"}, pols


def _m106():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("m106", Path(__file__).with_name("106_delivery_risk.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def downgrade() -> None:
    for f in FACTS[len(FACTS_106):]:
        n = _q(f"SELECT count(*) FROM tb_contract_event WHERE event_type = 'DELIVERY_FACT_{f}'").scalar()
        assert n == 0, f"{n} DELIVERY_FACT_{f} event(s) exist; refusing to downgrade"
    n = _q("SELECT count(*) FROM tb_contract_event WHERE event_type IN ('DELIVERY_ACCEPTED', 'DELIVERY_REJECTED')").scalar()
    assert n == 0, f"{n} accepted or rejected deliveries exist; refusing to downgrade"
    m106 = _m106()
    _q(m106.EVENT_CHECK)
    _q(m106.CONSISTENT)
    _q(DRAW_GUARD.replace("SELECT coalesce(sum(x.kg), 0) INTO drawn FROM delivery_draw x JOIN deliveries y ON y.id = x.delivery_id\n"
                          "       WHERE x.token_id = NEW.token_id AND y.status <> 'REJECTED';",
                          "SELECT coalesce(sum(kg), 0) INTO drawn FROM delivery_draw WHERE token_id = NEW.token_id;"))
    _q(SEES.replace("               OR d.inspector_company_id = p_company\n", ""))
    _q("DROP POLICY deliveries_read ON deliveries")
    _q(f"""CREATE POLICY deliveries_read ON deliveries FOR SELECT USING (
            {ADMIN} OR seller_company_id = {CURRENT} OR buyer_company_id = {CURRENT}
            OR app_company_owns_project(project_id, {CURRENT})
            OR app_company_has_project_access(project_id, {CURRENT}))""")
    _q("ALTER TABLE deliveries DROP COLUMN inspector_company_id")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       f"{_in(_event_types(FACTS_106))})")
