"""The delivery record on the one contract model (GreenMesh Phase 2, Step 2; gap G-08).

Revision ID: 103
Revises: 102

`deliveries` (044) was an empty table of integer flags and text dates that nothing wrote.
It becomes a real record. Its history is NOT a second history: every state change is a
contract event on `tb_contract_event` (trading_book/record.py), hash-chained and in the
ledger-anchor outbox, carrying the delivery's id.

  tb_contract_event.delivery_id   the delivery an event moves. In the event hash only when
                                  set, so every hash written before 103 is unchanged.
  deliveries                      typed: timestamptz, numeric kg, the contract (uuid FK), the
                                  physical flow it fulfils, seller and buyer, transport mode,
                                  origin and destination (UN/LOCODE or a facility), Incoterm
                                  and named place READ FROM the confirmed terms (D4).
                                  `volume_mt` is now GENERATED from delivered_kg, so
                                  trading_book/flows.py keeps reading tonnes.
  delivery_draw                   the tokens a delivery draws on, kg per token.

States: SCHEDULED -> IN_TRANSIT -> ARRIVED -> QUALITY_VERIFICATION -> ACCEPTED ->
TITLE_TRANSFERRED -> SETTLED; REJECTED after QUALITY_VERIFICATION; DISPUTED from any
non-final state. The event trigger enforces the ORDER and WHO acts:
  SCHEDULED, IN_TRANSIT          the seller
  ARRIVED                        the buyer
  QUALITY_VERIFICATION, DISPUTED either party
  ACCEPTED, REJECTED, TITLE_TRANSFERRED, SETTLED
                                 REFUSED until Step 3 builds quality before title
                                 (D1-D3): nothing can pass title on this migration.
A delivery row's status must equal the state of its latest event, checked at COMMIT from
both sides (deferred constraint triggers), so neither can move without the other.

Quantities: nominated = the sum of its draws; dispatched and delivered never exceed it; a
token's draws across all deliveries never exceed the kg allocated to it from custody lots
(mass_balance_allocations), and the token must be on the contract. Once set, a quantity or
time never changes, and nothing is deleted.

RLS: the seller, the buyer, the project's owner, its project-access holders and GEX read;
only the operator connection (PLATFORM_ADMIN) writes, after the application has authorised
the acting party (core/delivery_record.py) — the same pattern as the market. gex_app holds
no DELETE or TRUNCATE on either table (asserted).

Refuses to run while `deliveries` holds rows (it has never held one).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "103"
down_revision: Union[str, None] = "102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"

STATES = ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION", "ACCEPTED", "REJECTED",
          "TITLE_TRANSFERRED", "SETTLED", "DISPUTED")
INCOTERMS = ("EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF")
SEA_ONLY = ("FAS", "FOB", "CFR", "CIF")
MODES = ("PIPELINE", "SHIP", "TRUCK", "RAIL", "ISO_CONTAINER")
EVENT_TYPES = ("CREATED_FROM_MATCH", "MIGRATED", "VERSION", "COUNTERPARTY_SET", "CONFIRMED", "DISPUTED",
               "STATUS_CHANGED", "ADVERSE_FACT_REPORTED", "ADVERSE_FACT_CLEARED", "NOVATION")   # as 092 left it
OLD_COLUMNS = ("volume_mt", "quality_verified", "verified_ghg_intensity", "quality_certificate_number",
               "title_transferred", "title_transfer_date", "delivery_status", "invoice_amount", "payment_received")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    n = _q("SELECT count(*) FROM deliveries").scalar()
    if n:
        raise RuntimeError(f"deliveries holds {n} row(s); convert them before rebuilding the table")

    # ── deliveries: the typed record ─────────────────────────────────────────
    for t in ("deliveries_read", "deliveries_owner_insert", "deliveries_owner_update", "deliveries_owner_delete"):
        _q(f"DROP POLICY IF EXISTS {t} ON deliveries")
    for col in OLD_COLUMNS:
        _q(f"ALTER TABLE deliveries DROP COLUMN {col}")
    _q("ALTER TABLE deliveries ALTER COLUMN contract_id TYPE uuid USING contract_id::uuid")
    _q("ALTER TABLE deliveries ADD CONSTRAINT deliveries_contract_fk FOREIGN KEY (contract_id) REFERENCES tb_contract(id)")
    _q("ALTER TABLE deliveries ADD CONSTRAINT deliveries_project_fk FOREIGN KEY (project_id) REFERENCES projects(project_id)")
    _q(f"""ALTER TABLE deliveries
        ADD COLUMN flow_id uuid NOT NULL REFERENCES tb_flow(id),
        ADD COLUMN sub_leg_id uuid REFERENCES tb_sub_leg(id),
        ADD COLUMN frame_sub_leg_id uuid REFERENCES tb_sub_leg(id),
        ADD COLUMN terms_hash character(64) NOT NULL,
        ADD COLUMN seller_company_id text NOT NULL REFERENCES tenants(company_id),
        ADD COLUMN buyer_company_id text NOT NULL REFERENCES tenants(company_id),
        ADD COLUMN molecule text NOT NULL,
        ADD COLUMN status text NOT NULL CHECK (status IN {_in(STATES)}),
        ADD COLUMN window_start timestamptz NOT NULL,
        ADD COLUMN window_end timestamptz NOT NULL,
        ADD COLUMN dispatched_at timestamptz,
        ADD COLUMN arrived_at timestamptz,
        ADD COLUMN nominated_kg numeric NOT NULL CHECK (nominated_kg > 0),
        ADD COLUMN dispatched_kg numeric CHECK (dispatched_kg >= 0),
        ADD COLUMN delivered_kg numeric CHECK (delivered_kg >= 0),
        ADD COLUMN transport_mode text NOT NULL CHECK (transport_mode IN {_in(MODES)}),
        ADD COLUMN origin_locode text CHECK (origin_locode ~ '^[A-Z]{{2}}[A-Z2-9]{{3}}$'),
        ADD COLUMN origin_facility_id text,
        ADD COLUMN destination_locode text CHECK (destination_locode ~ '^[A-Z]{{2}}[A-Z2-9]{{3}}$'),
        ADD COLUMN destination_facility_id text,
        ADD COLUMN incoterm text CHECK (incoterm IN {_in(INCOTERMS)}),
        ADD COLUMN named_place text,
        ADD COLUMN created_by text NOT NULL,
        ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()""")
    _q("ALTER TABLE deliveries ADD COLUMN volume_mt double precision "
       "GENERATED ALWAYS AS ((delivered_kg / 1000)::double precision) STORED")
    for name, check in (
            ("ck_deliveries_parties", "seller_company_id <> buyer_company_id"),
            ("ck_deliveries_window", "window_end > window_start"),
            ("ck_deliveries_origin", "num_nonnulls(origin_locode, origin_facility_id) = 1"),
            ("ck_deliveries_destination", "num_nonnulls(destination_locode, destination_facility_id) = 1"),
            ("ck_deliveries_incoterm_place", "(incoterm IS NULL) = (named_place IS NULL)"),
            ("ck_deliveries_sea_rules", f"incoterm IS NULL OR incoterm NOT IN {_in(SEA_ONLY)} OR transport_mode = 'SHIP'"),
            ("ck_deliveries_dispatch", "(dispatched_at IS NULL) = (dispatched_kg IS NULL) AND dispatched_kg <= nominated_kg"),
            ("ck_deliveries_arrival", "(arrived_at IS NULL) = (delivered_kg IS NULL) AND delivered_kg <= nominated_kg "
                                      "AND (arrived_at IS NULL OR dispatched_at IS NOT NULL) AND arrived_at >= dispatched_at")):
        _q(f"ALTER TABLE deliveries ADD CONSTRAINT {name} CHECK ({check})")
    _q("CREATE INDEX ix_deliveries_contract ON deliveries (contract_id)")

    _q("""CREATE TABLE delivery_draw (
            delivery_id text NOT NULL REFERENCES deliveries(id),
            token_id text NOT NULL REFERENCES tokens(id),
            kg numeric NOT NULL CHECK (kg > 0),
            PRIMARY KEY (delivery_id, token_id))""")
    _q("CREATE INDEX ix_delivery_draw_token ON delivery_draw (token_id)")

    # ── the event carries the delivery ───────────────────────────────────────
    _q("ALTER TABLE tb_contract_event ADD COLUMN delivery_id text REFERENCES deliveries(id)")
    have = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'tb_contract_event_event_type_check'").scalar()
    assert have and all(f"'{t}'" in have for t in EVENT_TYPES) and have.count("'") == 2 * len(EVENT_TYPES), have
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q("ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       + _in(EVENT_TYPES + tuple(f"DELIVERY_{s}" for s in STATES)) + ")")
    _q("ALTER TABLE tb_contract_event ADD CONSTRAINT ck_event_delivery "
       "CHECK ((delivery_id IS NOT NULL) = (event_type LIKE 'DELIVERY\\_%'))")
    _q("CREATE INDEX ix_tb_contract_event_delivery ON tb_contract_event (delivery_id) WHERE delivery_id IS NOT NULL")

    # ── who may read ─────────────────────────────────────────────────────────
    _q("""CREATE FUNCTION app_company_sees_delivery(p_delivery text, p_company text) RETURNS boolean
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
          SELECT EXISTS (SELECT 1 FROM deliveries d WHERE d.id = p_delivery AND (
                   p_company = 'PLATFORM_ADMIN' OR d.seller_company_id = p_company OR d.buyer_company_id = p_company
                   OR app_company_owns_project(d.project_id, p_company)
                   OR app_company_has_project_access(d.project_id, p_company))) $$""")
    _q("REVOKE ALL ON FUNCTION app_company_sees_delivery(text, text) FROM PUBLIC")
    _q("GRANT EXECUTE ON FUNCTION app_company_sees_delivery(text, text) TO gex_app")
    _q(f"""CREATE POLICY deliveries_read ON deliveries FOR SELECT USING (
            {ADMIN} OR seller_company_id = {CURRENT} OR buyer_company_id = {CURRENT}
            OR app_company_owns_project(project_id, {CURRENT})
            OR app_company_has_project_access(project_id, {CURRENT}))""")
    _q(f"CREATE POLICY deliveries_operator_insert ON deliveries FOR INSERT WITH CHECK {ADMIN}")
    _q(f"CREATE POLICY deliveries_operator_update ON deliveries FOR UPDATE USING {ADMIN} WITH CHECK {ADMIN}")
    _q("ALTER TABLE delivery_draw ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE delivery_draw FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY delivery_draw_read ON delivery_draw FOR SELECT USING "
       f"(app_company_sees_delivery(delivery_id, {CURRENT}))")
    _q(f"CREATE POLICY delivery_draw_operator_insert ON delivery_draw FOR INSERT WITH CHECK {ADMIN}")
    _q("REVOKE DELETE, TRUNCATE ON deliveries FROM gex_app")
    _q("REVOKE ALL ON delivery_draw FROM gex_app")
    _q("GRANT SELECT, INSERT ON delivery_draw TO gex_app")

    # ── the state machine, enforced on the event ────────────────────────────
    _q("""CREATE FUNCTION delivery_event_check() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE d record; prev text; nxt text;
        BEGIN
          IF NEW.delivery_id IS NULL THEN RETURN NEW; END IF;
          SELECT * INTO d FROM deliveries WHERE id = NEW.delivery_id;
          IF d.contract_id IS DISTINCT FROM NEW.contract_id THEN
            RAISE EXCEPTION 'DELIVERY_CONTRACT: delivery % is not on contract %', NEW.delivery_id, NEW.contract_id
              USING ERRCODE = 'check_violation';
          END IF;
          nxt := substr(NEW.event_type, 10);
          SELECT substr(e.event_type, 10) INTO prev FROM tb_contract_event e
           WHERE e.delivery_id = NEW.delivery_id ORDER BY e.seq DESC LIMIT 1;
          IF nxt IN ('ACCEPTED', 'REJECTED', 'TITLE_TRANSFERRED', 'SETTLED') THEN
            RAISE EXCEPTION 'DELIVERY_STEP_NOT_BUILT: % needs quality before title (Phase 2 Step 3)', nxt
              USING ERRCODE = 'check_violation';
          END IF;
          IF NOT ((prev IS NULL AND nxt = 'SCHEDULED')
               OR (prev = 'SCHEDULED' AND nxt = 'IN_TRANSIT')
               OR (prev = 'IN_TRANSIT' AND nxt = 'ARRIVED')
               OR (prev = 'ARRIVED' AND nxt = 'QUALITY_VERIFICATION')
               OR (prev = 'QUALITY_VERIFICATION' AND nxt IN ('ACCEPTED', 'REJECTED'))
               OR (prev = 'ACCEPTED' AND nxt = 'TITLE_TRANSFERRED')
               OR (prev = 'TITLE_TRANSFERRED' AND nxt = 'SETTLED')
               OR (prev IN ('SCHEDULED', 'IN_TRANSIT', 'ARRIVED', 'QUALITY_VERIFICATION', 'ACCEPTED',
                            'TITLE_TRANSFERRED') AND nxt = 'DISPUTED')) THEN
            RAISE EXCEPTION 'DELIVERY_STATE_ORDER: % cannot follow %', nxt, coalesce(prev, 'nothing')
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
        END $$""")
    _q("CREATE TRIGGER tb_contract_event_delivery_check BEFORE INSERT ON tb_contract_event "
       "FOR EACH ROW EXECUTE FUNCTION delivery_event_check()")

    # ── the row: what may change, and only together with its event ──────────
    _q("""CREATE FUNCTION delivery_row_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'DELIVERY_APPEND_ONLY: a delivery is never deleted' USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'SCHEDULED' OR NEW.dispatched_at IS NOT NULL OR NEW.arrived_at IS NOT NULL THEN
              RAISE EXCEPTION 'DELIVERY_STATE_ORDER: a delivery starts SCHEDULED, with nothing dispatched'
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF (NEW.id, NEW.project_id, NEW.contract_id, NEW.flow_id, NEW.sub_leg_id, NEW.frame_sub_leg_id,
              NEW.terms_hash, NEW.seller_company_id, NEW.buyer_company_id, NEW.molecule, NEW.window_start,
              NEW.window_end, NEW.nominated_kg, NEW.transport_mode, NEW.origin_locode, NEW.origin_facility_id,
              NEW.destination_locode, NEW.destination_facility_id, NEW.incoterm, NEW.named_place,
              NEW.created_by, NEW.created_at)
             IS DISTINCT FROM
             (OLD.id, OLD.project_id, OLD.contract_id, OLD.flow_id, OLD.sub_leg_id, OLD.frame_sub_leg_id,
              OLD.terms_hash, OLD.seller_company_id, OLD.buyer_company_id, OLD.molecule, OLD.window_start,
              OLD.window_end, OLD.nominated_kg, OLD.transport_mode, OLD.origin_locode, OLD.origin_facility_id,
              OLD.destination_locode, OLD.destination_facility_id, OLD.incoterm, OLD.named_place,
              OLD.created_by, OLD.created_at)
             OR (OLD.dispatched_at IS NOT NULL AND (NEW.dispatched_at, NEW.dispatched_kg)
                                                   IS DISTINCT FROM (OLD.dispatched_at, OLD.dispatched_kg))
             OR (OLD.arrived_at IS NOT NULL AND (NEW.arrived_at, NEW.delivered_kg)
                                                IS DISTINCT FROM (OLD.arrived_at, OLD.delivered_kg)) THEN
            RAISE EXCEPTION 'DELIVERY_FIXED: a delivery''s terms and recorded quantities never change'
              USING ERRCODE = 'check_violation';
          END IF;
          IF (OLD.dispatched_at IS NULL AND NEW.dispatched_at IS NOT NULL AND NEW.status <> 'IN_TRANSIT')
             OR (OLD.arrived_at IS NULL AND NEW.arrived_at IS NOT NULL AND NEW.status <> 'ARRIVED') THEN
            RAISE EXCEPTION 'DELIVERY_STATE_ORDER: a dispatch is recorded with IN_TRANSIT, a receipt with ARRIVED'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER deliveries_guard BEFORE INSERT OR UPDATE OR DELETE ON deliveries "
       "FOR EACH ROW EXECUTE FUNCTION delivery_row_guard()")

    # ── at commit: the row's state is its latest event's; nominated = draws ──
    _q("""CREATE FUNCTION delivery_consistent() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE did text; st text; latest text; drawn numeric;
        BEGIN
          IF TG_TABLE_NAME = 'deliveries' THEN did := NEW.id; ELSE did := NEW.delivery_id; END IF;
          IF did IS NULL THEN RETURN NULL; END IF;
          SELECT status INTO st FROM deliveries WHERE id = did;
          SELECT substr(event_type, 10) INTO latest FROM tb_contract_event
           WHERE delivery_id = did ORDER BY seq DESC LIMIT 1;
          IF latest IS DISTINCT FROM st THEN
            RAISE EXCEPTION 'DELIVERY_STATE_MISMATCH: delivery % is % but its latest event says %',
              did, st, coalesce(latest, 'nothing') USING ERRCODE = 'check_violation';
          END IF;
          SELECT coalesce(sum(kg), 0) INTO drawn FROM delivery_draw WHERE delivery_id = did;
          IF drawn <> (SELECT nominated_kg FROM deliveries WHERE id = did) THEN
            RAISE EXCEPTION 'DELIVERY_DRAWS: delivery % nominates a quantity its draws (% kg) do not make up',
              did, drawn USING ERRCODE = 'check_violation';
          END IF;
          RETURN NULL;
        END $$""")
    # Only rows that concern a delivery queue a check: an UPDATE of any other contract event (a
    # test tampering below the append-only trigger, say) must leave no pending trigger event.
    for t, when, ops in (("deliveries", "", "INSERT OR UPDATE"),
                         ("tb_contract_event", " WHEN (NEW.delivery_id IS NOT NULL)", "INSERT"),
                         ("delivery_draw", "", "INSERT")):
        _q(f"CREATE CONSTRAINT TRIGGER {t}_delivery_consistent AFTER {ops} ON {t} "
           f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW{when} EXECUTE FUNCTION delivery_consistent()")

    # ── a draw: a token of the contract, never beyond what custody allocated to it ──
    _q("""CREATE FUNCTION delivery_draw_guard() RETURNS trigger LANGUAGE plpgsql
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
          SELECT coalesce(sum(kg), 0) INTO drawn FROM delivery_draw WHERE token_id = NEW.token_id;
          IF drawn + NEW.kg > allocated THEN
            RAISE EXCEPTION 'DELIVERY_OVER_ALLOCATION: token % has % kg allocated from custody, % kg already drawn',
              NEW.token_id, allocated, drawn USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER delivery_draw_guard BEFORE INSERT OR UPDATE OR DELETE ON delivery_draw "
       "FOR EACH ROW EXECUTE FUNCTION delivery_draw_guard()")

    # ── assert rather than trust ─────────────────────────────────────────────
    for t in ("deliveries", "delivery_draw"):
        assert _q(f"SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = '{t}'").scalar(), \
            f"{t} not FORCED"
        bad = _q(f"SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants WHERE "
                 f"grantee = 'gex_app' AND table_name = '{t}' AND privilege_type IN ('DELETE', 'TRUNCATE')").scalar()
        assert not bad, f"gex_app holds {bad} on {t}"
    pols = dict(_q("SELECT policyname, cmd FROM pg_policies WHERE tablename = 'deliveries'").fetchall())
    assert pols == {"deliveries_read": "SELECT", "deliveries_operator_insert": "INSERT",
                    "deliveries_operator_update": "UPDATE"}, pols
    held = set(_q("SELECT privilege_type FROM information_schema.role_table_grants "
                  "WHERE grantee = 'gex_app' AND table_name = 'delivery_draw'").scalars())
    assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on delivery_draw"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM deliveries").scalar()
    assert n == 0, f"{n} delivery record(s) exist; refusing to drop the delivery record"
    for t in ("deliveries", "tb_contract_event", "delivery_draw"):
        _q(f"DROP TRIGGER IF EXISTS {t}_delivery_consistent ON {t}")
    _q("DROP TRIGGER IF EXISTS tb_contract_event_delivery_check ON tb_contract_event")
    _q("DROP TRIGGER IF EXISTS deliveries_guard ON deliveries")
    _q("DROP TABLE IF EXISTS delivery_draw")
    for f in ("delivery_consistent()", "delivery_event_check()", "delivery_row_guard()", "delivery_draw_guard()"):
        _q(f"DROP FUNCTION IF EXISTS {f}")
    _q("DROP INDEX IF EXISTS ix_tb_contract_event_delivery")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT IF EXISTS ck_event_delivery")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q("ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       + _in(EVENT_TYPES) + ")")
    _q("ALTER TABLE tb_contract_event DROP COLUMN IF EXISTS delivery_id")
    for p in ("deliveries_read", "deliveries_operator_insert", "deliveries_operator_update"):
        _q(f"DROP POLICY IF EXISTS {p} ON deliveries")
    _q("DROP FUNCTION IF EXISTS app_company_sees_delivery(text, text)")
    _q("DROP INDEX IF EXISTS ix_deliveries_contract")
    for col in ("volume_mt", "flow_id", "sub_leg_id", "frame_sub_leg_id", "terms_hash", "seller_company_id",
                "buyer_company_id", "molecule", "status", "window_start", "window_end", "dispatched_at", "arrived_at",
                "nominated_kg", "dispatched_kg", "delivered_kg", "transport_mode", "origin_locode",
                "origin_facility_id", "destination_locode", "destination_facility_id", "incoterm", "named_place",
                "created_by", "created_at"):
        _q(f"ALTER TABLE deliveries DROP COLUMN IF EXISTS {col}")
    _q("ALTER TABLE deliveries DROP CONSTRAINT IF EXISTS deliveries_contract_fk")
    _q("ALTER TABLE deliveries DROP CONSTRAINT IF EXISTS deliveries_project_fk")
    _q("ALTER TABLE deliveries ALTER COLUMN contract_id TYPE text USING contract_id::text")
    _q("""ALTER TABLE deliveries
        ADD COLUMN volume_mt double precision NOT NULL,
        ADD COLUMN quality_verified integer, ADD COLUMN verified_ghg_intensity double precision,
        ADD COLUMN quality_certificate_number text, ADD COLUMN title_transferred integer,
        ADD COLUMN title_transfer_date text, ADD COLUMN delivery_status text NOT NULL,
        ADD COLUMN invoice_amount double precision, ADD COLUMN payment_received integer""")
    _q("GRANT DELETE ON deliveries TO gex_app")
    # 100's policies, exactly
    read = (f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}) "
            f"OR app_company_has_project_access(project_id, {CURRENT}))")
    write = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
    _q(f"CREATE POLICY deliveries_read ON deliveries FOR SELECT USING {read}")
    _q(f"CREATE POLICY deliveries_owner_insert ON deliveries FOR INSERT WITH CHECK {write}")
    _q(f"CREATE POLICY deliveries_owner_update ON deliveries FOR UPDATE USING {write} WITH CHECK {write}")
    _q(f"CREATE POLICY deliveries_owner_delete ON deliveries FOR DELETE USING {write}")
