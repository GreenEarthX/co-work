"""Trading book revision M1 — terms → legs → flows, orders, RFQs, fills, contract versions.

Revision ID: 065
Revises: 064

WHY (docs/GEX_Trading_Book_Revision spec, JML 2026-10-23; handoff §8 item 46)
---------------------------------------------------------------------------
One generic structure for every trade (D1): a contract is stored ONCE, each leg
names its payer and receiver (D2), orders are one-sided (D3), and orders, RFQ
quotes and contracts share one terms schema (D4). JML's decisions the same day:
this becomes the ONLY contract model — the market engine moves onto it in M3/M4,
replacing offers/rfqs/matches/contracts (whose float prices D8 forbids; they are
replaced, not altered); automated matching stays off (decision 2B); a contract
token is separate from the capacity tokens it delivers and refers to them (3).

ADDITIVE. Nothing existing is dropped. Two touches to existing tables, both
empty on 2026-10-23:
  * tb_counterparty.company_id — the platform company a counterparty is, so
    payer/receiver can be resolved to a tenant. NULL for off-platform parties.
  * tb_contract — the legacy JTI columns lose NOT NULL and the new contract
    columns are added (contract_ref, trade_status, verification_state, fill_id).
    A CHECK keeps each row wholly legacy or wholly new. `status` is the legacy
    enum, so the new lifecycle is `trade_status` (spec §3.4 calls it `status`);
    M6 drops the legacy columns.

Kept actual names where they differ from the spec: tb_index_definition keeps
provider/index_code/unit_basis/frequency (adds commodity_id);
tb_index_history keeps index_definition_id/observation_date.

TENANCY. Every new table is under FORCED RLS with read and write policies
(WITH CHECK on every write — the 062 lesson). Cross-table lookups are SECURITY
DEFINER functions with a pinned search_path (036/064's pattern) so policies do
not recurse. Orders and RFQs are visible to their owner (and invitees); the
anonymised market view is served by the market engine, as today. The views are
security_invoker, so they inherit the caller's RLS instead of bypassing it.

FROZEN TERMS (D7, §6). Once frozen_at is set, a terms row and its legs and flows
cannot change or be deleted — a trigger, so it holds for every role.

ONE TOKEN PER CONTRACT (JML, 2026-10-23). A change to a contract is a new
version with new frozen terms, and it is a MODIFICATION OF THE SAME TOKEN, never
a new token. tb_contract.token_ref is the contract's token — unique, and fixed
once set. Each version records the token operation that carried its terms hash
in token_event_ref: the mint for version 1, a modification for every later one.
Neither reference can change once written (trigger). Token technology and issuer
are still open, so both stay NULL until then.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "065"
down_revision: Union[str, None] = "064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
SIGNED_IN = f"(coalesce({ME}, '') NOT IN ('', 'GUEST', '__no_tenant_context__'))"

ENUMS = {
    "tb_settlement": ("physical", "cash_net", "cash_gross"),
    "tb_leg_role": ("product", "payment", "fixed", "floating"),
    "tb_flow_type": ("physical", "fixed_cash", "float_cash"),
    "tb_quantity_basis": ("contracted", "delivered"),
    "tb_fixing_method": ("average", "first", "last"),
    "tb_unit": ("t", "MWh", "kg", "m3"),
    "tb_side": ("buy", "sell"),
    "tb_order_type": ("firm", "indicative"),
    "tb_order_status": ("draft", "open", "partially_filled", "filled", "cancelled", "expired", "rejected"),
    "tb_visibility": ("private", "invited", "platform"),
    "tb_rfq_status": ("draft", "published", "closed", "expired", "withdrawn"),
    "tb_trade_status": ("pending_confirmation", "confirmed", "active", "completed", "cancelled",
                        "terminated"),
    "tb_verification_state": ("UNVERIFIED", "SUBMITTED", "CONFIRMED", "AUDITED"),
}

# Reference data: the codes the market already uses map to the spec's codes.
COMMODITIES = (  # code, name, default unit, the market's molecule code
    ("H2", "Hydrogen", "t", "H2"),
    ("NH3", "Ammonia", "t", "NH3"),
    ("EMEOH", "e-Methanol", "t", "e-Methanol"),
    ("ENG", "e-NG (synthetic natural gas)", "MWh", "e-NG"),
    ("SAF", "Sustainable aviation fuel", "t", "SAF"),
)

AUDIT = """created_at timestamptz NOT NULL DEFAULT now(),
           created_by text NOT NULL DEFAULT current_user,
           updated_at timestamptz NOT NULL DEFAULT now()"""

NEW_TABLES = ("tb_commodity", "tb_counterparty_restriction", "tb_terms", "tb_leg", "tb_flow",
              "tb_rfq", "tb_order", "tb_order_invitee", "tb_order_event", "tb_fill",
              "tb_contract_version", "tb_contract_version_token")

FUNCTIONS = {
    # The platform company behind a counterparty (NULL when off-platform).
    "app_tb_cp_company(p_cp uuid)": (
        "text", "SELECT company_id FROM tb_counterparty WHERE id = p_cp"),
    # Is the company a payer or receiver on any leg of these terms?
    "app_tb_terms_party(p_terms uuid, p_company text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM tb_leg l JOIN tb_counterparty c "
                   "ON c.id IN (l.payer_id, l.receiver_id) WHERE l.terms_id = p_terms "
                   "AND c.company_id = p_company)"),
    # Is the company a party to any version of the contract?
    "app_tb_contract_party(p_contract uuid, p_company text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM tb_contract_version v WHERE v.contract_id = p_contract "
                   "AND app_tb_terms_party(v.terms_id, p_company))"),
    # May the company read these terms: it owns them, or is a contract party on them.
    "app_tb_terms_readable(p_terms uuid, p_company text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM tb_terms t WHERE t.id = p_terms AND "
                   "(t.owner_company_id = p_company OR app_tb_terms_party(t.id, p_company)))"),
    "app_tb_terms_owner(p_terms uuid)": (
        "text", "SELECT owner_company_id FROM tb_terms WHERE id = p_terms"),
    "app_tb_order_owner(p_order uuid)": (
        "text", "SELECT app_tb_cp_company(owner_id) FROM tb_order WHERE id = p_order"),
}

# table -> (read, write)
POLICIES = {
    "tb_commodity": ("true", ADMIN),
    "tb_counterparty_restriction": (f"{ADMIN} OR app_tb_cp_company(counterparty_id) = {ME}",
                                    f"{ADMIN} OR app_tb_cp_company(counterparty_id) = {ME}"),
    "tb_terms": (f"{ADMIN} OR owner_company_id = {ME} OR app_tb_terms_party(id, {ME})",
                 f"{ADMIN} OR owner_company_id = {ME}"),
    "tb_leg": (f"{ADMIN} OR app_tb_terms_readable(terms_id, {ME})",
               f"{ADMIN} OR app_tb_terms_owner(terms_id) = {ME}"),
    "tb_flow": (f"{ADMIN} OR EXISTS (SELECT 1 FROM tb_leg l WHERE l.id = leg_id)",
                f"{ADMIN} OR EXISTS (SELECT 1 FROM tb_leg l WHERE l.id = leg_id "
                f"AND app_tb_terms_owner(l.terms_id) = {ME})"),
    "tb_rfq": (f"{ADMIN} OR app_tb_cp_company(requester_id) = {ME}",
               f"{ADMIN} OR app_tb_cp_company(requester_id) = {ME}"),
    "tb_order": (f"{ADMIN} OR app_tb_cp_company(owner_id) = {ME} OR EXISTS (SELECT 1 FROM "
                 f"tb_order_invitee i WHERE i.order_id = tb_order.id AND app_tb_cp_company(i.counterparty_id) = {ME})",
                 f"{ADMIN} OR app_tb_cp_company(owner_id) = {ME}"),
    "tb_order_invitee": (f"{ADMIN} OR app_tb_order_owner(order_id) = {ME} "
                         f"OR app_tb_cp_company(counterparty_id) = {ME}",
                         f"{ADMIN} OR app_tb_order_owner(order_id) = {ME}"),
    "tb_order_event": (f"{ADMIN} OR app_tb_order_owner(order_id) = {ME}",
                       f"{ADMIN} OR app_tb_order_owner(order_id) = {ME}"),
    "tb_fill": (f"{ADMIN} OR app_tb_order_owner(buy_order_id) = {ME} "
                f"OR app_tb_order_owner(sell_order_id) = {ME}", ADMIN),
    "tb_contract_version": (f"{ADMIN} OR app_tb_terms_party(terms_id, {ME})", ADMIN),
    "tb_contract_version_token": (f"{ADMIN} OR EXISTS (SELECT 1 FROM tb_contract_version v "
                                  f"WHERE v.id = version_id)", ADMIN),
}


def _q(sql: str, params: dict | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT count(*) FROM tb_contract")).scalar()
    assert n == 0, f"tb_contract holds {n} rows; 065 relaxes its legacy columns and expects it empty"

    for name, values in ENUMS.items():
        _q(f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in values)})")

    # ── reference data ──────────────────────────────────────────────────────
    _q(f"""CREATE TABLE tb_commodity (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           code text NOT NULL UNIQUE, name text NOT NULL, default_unit tb_unit NOT NULL,
           market_molecule text UNIQUE, {AUDIT})""")
    for code, name, unit, molecule in COMMODITIES:
        _q("INSERT INTO tb_commodity (code, name, default_unit, market_molecule, created_by) "
           "VALUES (:c, :n, CAST(:u AS tb_unit), :m, 'MIGRATION_065')",
           {"c": code, "n": name, "u": unit, "m": molecule})
    _q("ALTER TABLE tb_counterparty ADD COLUMN company_id text REFERENCES tenants(company_id)")
    _q("CREATE UNIQUE INDEX uq_tb_counterparty_company ON tb_counterparty (company_id) "
       "WHERE company_id IS NOT NULL")
    _q("ALTER TABLE tb_index_definition ADD COLUMN commodity_id uuid REFERENCES tb_commodity(id)")
    _q(f"""CREATE TABLE tb_counterparty_restriction (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           counterparty_id uuid NOT NULL REFERENCES tb_counterparty(id),
           restricted_counterparty_id uuid NOT NULL REFERENCES tb_counterparty(id),
           reason text NOT NULL, set_by text NOT NULL, active boolean NOT NULL DEFAULT true, {AUDIT},
           UNIQUE (counterparty_id, restricted_counterparty_id),
           CHECK (counterparty_id <> restricted_counterparty_id))""")

    # ── terms → legs → flows ────────────────────────────────────────────────
    _q(f"""CREATE TABLE tb_terms (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           owner_company_id text NOT NULL,
           settlement tb_settlement NOT NULL,
           commodity_id uuid NOT NULL REFERENCES tb_commodity(id),
           quality_spec jsonb NOT NULL DEFAULT '{{}}'::jsonb,
           currency char(3) NOT NULL,
           frozen_at timestamptz, terms_hash char(64),
           CHECK ((frozen_at IS NULL) = (terms_hash IS NULL)), {AUDIT})""")
    _q(f"""CREATE TABLE tb_leg (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           terms_id uuid NOT NULL REFERENCES tb_terms(id) ON DELETE CASCADE,
           leg_role tb_leg_role NOT NULL,
           payer_id uuid REFERENCES tb_counterparty(id),
           receiver_id uuid REFERENCES tb_counterparty(id),
           seq smallint NOT NULL, {AUDIT},
           UNIQUE (terms_id, seq),
           CHECK (payer_id IS NULL OR receiver_id IS NULL OR payer_id <> receiver_id))""")
    _q(f"""CREATE TABLE tb_flow (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           leg_id uuid NOT NULL REFERENCES tb_leg(id) ON DELETE CASCADE,
           seq int NOT NULL,
           flow_type tb_flow_type NOT NULL,
           period_start date NOT NULL, period_end date NOT NULL, settle_date date NOT NULL,
           quantity numeric(20,6) NOT NULL CHECK (quantity > 0),
           unit tb_unit NOT NULL,
           is_notional boolean NOT NULL DEFAULT false,
           quantity_basis tb_quantity_basis,
           quantity_source_flow_id uuid REFERENCES tb_flow(id),
           tolerance_min_pct numeric(7,4), tolerance_max_pct numeric(7,4),
           delivery_id text REFERENCES deliveries(id),
           asset_id uuid REFERENCES tb_asset(id),
           unit_price numeric(20,8),
           index_id uuid REFERENCES tb_index_definition(id),
           index_multiplier numeric(20,8) NOT NULL DEFAULT 1,
           spread numeric(20,8) NOT NULL DEFAULT 0,
           cap numeric(20,8), floor numeric(20,8),
           fixing_method tb_fixing_method, fixing_start date, fixing_end date, {AUDIT},
           UNIQUE (leg_id, seq),
           CHECK (period_start <= period_end),
           CHECK (flow_type <> 'physical' OR (unit_price IS NULL AND index_id IS NULL AND cap IS NULL
                  AND floor IS NULL AND is_notional = false)),
           CHECK (flow_type <> 'fixed_cash' OR (unit_price IS NOT NULL AND index_id IS NULL)),
           CHECK (flow_type <> 'float_cash' OR (index_id IS NOT NULL AND fixing_method IS NOT NULL
                  AND fixing_start IS NOT NULL AND fixing_end IS NOT NULL AND unit_price IS NULL
                  AND (floor IS NULL OR cap IS NULL OR floor <= cap))))""")

    # ── RFQs, orders, events, fills ─────────────────────────────────────────
    _q(f"""CREATE TABLE tb_rfq (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           requester_id uuid NOT NULL REFERENCES tb_counterparty(id),
           side tb_side NOT NULL,
           terms_id uuid NOT NULL UNIQUE REFERENCES tb_terms(id),
           valid_until timestamptz NOT NULL,
           status tb_rfq_status NOT NULL DEFAULT 'draft', {AUDIT})""")
    _q(f"""CREATE TABLE tb_order (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           owner_id uuid NOT NULL REFERENCES tb_counterparty(id),
           side tb_side NOT NULL,
           terms_id uuid NOT NULL UNIQUE REFERENCES tb_terms(id),
           order_type tb_order_type NOT NULL DEFAULT 'firm',
           all_or_nothing boolean NOT NULL DEFAULT false,
           min_fill_quantity numeric(20,6),
           valid_from timestamptz NOT NULL DEFAULT now(), valid_until timestamptz NOT NULL,
           status tb_order_status NOT NULL DEFAULT 'draft',
           rfq_id uuid REFERENCES tb_rfq(id),
           visibility tb_visibility NOT NULL DEFAULT 'platform', {AUDIT},
           CHECK (valid_from < valid_until),
           CHECK (NOT (all_or_nothing AND status = 'partially_filled')))""")
    _q("""CREATE TABLE tb_order_invitee (
           order_id uuid NOT NULL REFERENCES tb_order(id) ON DELETE CASCADE,
           counterparty_id uuid NOT NULL REFERENCES tb_counterparty(id),
           PRIMARY KEY (order_id, counterparty_id))""")
    _q("""CREATE TABLE tb_order_event (
           id bigserial PRIMARY KEY,
           order_id uuid NOT NULL REFERENCES tb_order(id),
           from_status tb_order_status, to_status tb_order_status NOT NULL,
           actor_id text NOT NULL, at timestamptz NOT NULL DEFAULT now(), reason text)""")

    # ── contracts ───────────────────────────────────────────────────────────
    for col in ("contract_number", "buy_side_id", "sell_side_id", "fuel_type", "trade_date",
                "effective_date", "termination_date", "notional_quantity", "quantity_unit",
                "currency", "status", "owner_company_id"):
        _q(f"ALTER TABLE tb_contract ALTER COLUMN {col} DROP NOT NULL")
    _q("ALTER TABLE tb_contract ADD COLUMN contract_ref text UNIQUE")
    _q("ALTER TABLE tb_contract ADD COLUMN trade_status tb_trade_status")
    _q("ALTER TABLE tb_contract ADD COLUMN verification_state tb_verification_state "
       "NOT NULL DEFAULT 'UNVERIFIED'")
    _q("""CREATE TABLE tb_fill (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           buy_order_id uuid NOT NULL REFERENCES tb_order(id),
           sell_order_id uuid NOT NULL REFERENCES tb_order(id),
           quantity numeric(20,6) NOT NULL CHECK (quantity > 0),
           contract_id uuid REFERENCES tb_contract(id),
           at timestamptz NOT NULL DEFAULT now(),
           CHECK (buy_order_id <> sell_order_id))""")
    _q("ALTER TABLE tb_contract ADD COLUMN fill_id uuid REFERENCES tb_fill(id)")
    _q("ALTER TABLE tb_contract ADD COLUMN token_ref text UNIQUE")
    # Each row wholly legacy (JTI, until M6) or wholly new (terms model).
    _q("""ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_one_model CHECK (
           (contract_type = 'terms' AND contract_ref IS NOT NULL AND trade_status IS NOT NULL)
        OR (contract_type <> 'terms' AND contract_number IS NOT NULL AND buy_side_id IS NOT NULL
            AND sell_side_id IS NOT NULL AND status IS NOT NULL AND owner_company_id IS NOT NULL))""")
    _q(f"""CREATE TABLE tb_contract_version (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           contract_id uuid NOT NULL REFERENCES tb_contract(id),
           version int NOT NULL CHECK (version >= 1),
           terms_id uuid NOT NULL UNIQUE REFERENCES tb_terms(id),
           terms_hash char(64) NOT NULL,
           token_event_ref text UNIQUE,      -- v1: the mint; later versions: the modification
           valid_from timestamptz NOT NULL DEFAULT now(), superseded_at timestamptz,
           reason text NOT NULL, {AUDIT},
           UNIQUE (contract_id, version))""")
    _q("CREATE UNIQUE INDEX uq_tb_contract_current_version ON tb_contract_version (contract_id) "
       "WHERE superseded_at IS NULL")
    # Decision 3: the contract token refers to the capacity tokens it delivers.
    _q("""CREATE TABLE tb_contract_version_token (
           version_id uuid NOT NULL REFERENCES tb_contract_version(id),
           token_id text NOT NULL REFERENCES tokens(id),
           PRIMARY KEY (version_id, token_id))""")

    # ── frozen terms are immutable, for every role ──────────────────────────
    _q("""CREATE FUNCTION tb_refuse_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE t uuid;
        BEGIN
          -- Each branch reads only its own table's fields: PL/pgSQL resolves a
          -- record field when the expression runs, and tb_leg has no frozen_at.
          IF TG_TABLE_NAME = 'tb_terms' THEN
            IF OLD.frozen_at IS NOT NULL THEN       -- freezing itself (NULL -> set) is allowed
              RAISE EXCEPTION 'TERMS_FROZEN: terms % are frozen; amend by a new contract version', OLD.id
                USING ERRCODE = 'check_violation';
            END IF;
          ELSE
            IF TG_TABLE_NAME = 'tb_leg' THEN
              t := OLD.terms_id;
            ELSE
              SELECT l.terms_id INTO t FROM tb_leg l WHERE l.id = OLD.leg_id;
            END IF;
            IF EXISTS (SELECT 1 FROM tb_terms WHERE id = t AND frozen_at IS NOT NULL) THEN
              RAISE EXCEPTION 'TERMS_FROZEN: terms % are frozen; amend by a new contract version', t
                USING ERRCODE = 'check_violation';
            END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$""")
    for table in ("tb_terms", "tb_leg", "tb_flow"):
        _q(f"CREATE TRIGGER {table}_frozen BEFORE UPDATE OR DELETE ON {table} "
           "FOR EACH ROW EXECUTE FUNCTION tb_refuse_frozen()")
    # A leg or flow cannot be ADDED to frozen terms either.
    _q("""CREATE FUNCTION tb_refuse_add_to_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE t uuid;
        BEGIN
          IF TG_TABLE_NAME = 'tb_leg' THEN t := NEW.terms_id;
          ELSE SELECT l.terms_id INTO t FROM tb_leg l WHERE l.id = NEW.leg_id;
          END IF;
          IF EXISTS (SELECT 1 FROM tb_terms WHERE id = t AND frozen_at IS NOT NULL) THEN
            RAISE EXCEPTION 'TERMS_FROZEN: terms % are frozen', t USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    for table in ("tb_leg", "tb_flow"):
        _q(f"CREATE TRIGGER {table}_frozen_insert BEFORE INSERT ON {table} "
           "FOR EACH ROW EXECUTE FUNCTION tb_refuse_add_to_frozen()")

    # ── one token per contract: its references never change once written ────
    _q("""CREATE FUNCTION tb_refuse_token_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_TABLE_NAME = 'tb_contract' THEN
            IF OLD.token_ref IS NOT NULL AND NEW.token_ref IS DISTINCT FROM OLD.token_ref THEN
              RAISE EXCEPTION 'TOKEN_FIXED: contract % keeps its token; amend by modifying it', OLD.id
                USING ERRCODE = 'check_violation';
            END IF;
          ELSIF OLD.token_event_ref IS NOT NULL
                AND NEW.token_event_ref IS DISTINCT FROM OLD.token_event_ref THEN
            RAISE EXCEPTION 'TOKEN_FIXED: version % already records its token operation', OLD.id
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    for table in ("tb_contract", "tb_contract_version"):
        _q(f"CREATE TRIGGER {table}_token_fixed BEFORE UPDATE ON {table} "
           "FOR EACH ROW EXECUTE FUNCTION tb_refuse_token_rewrite()")
    # A later version's token operation is a modification of the contract's token,
    # so the contract must already have one.
    _q("""CREATE FUNCTION tb_require_contract_token() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.token_event_ref IS NOT NULL AND NEW.version > 1 AND NOT EXISTS (
               SELECT 1 FROM tb_contract c WHERE c.id = NEW.contract_id AND c.token_ref IS NOT NULL) THEN
            RAISE EXCEPTION 'TOKEN_MISSING: version % modifies a token contract % does not have',
              NEW.version, NEW.contract_id USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER tb_contract_version_token_required BEFORE INSERT OR UPDATE ON tb_contract_version "
       "FOR EACH ROW EXECUTE FUNCTION tb_require_contract_token()")

    # ── RLS ─────────────────────────────────────────────────────────────────
    for signature, (returns, body) in FUNCTIONS.items():
        _q(f"CREATE FUNCTION {signature} RETURNS {returns} LANGUAGE sql STABLE SECURITY DEFINER "
           f"SET search_path = public, pg_temp AS $$ {body} $$")
        _q(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        _q(f"GRANT EXECUTE ON FUNCTION {signature} TO gex_app")
    for table in NEW_TABLES:
        read, write = POLICIES[table]
        _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
        _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({write})")
        _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({write}) WITH CHECK ({write})")
        _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({write})")
    # Contracts on the new model are read by their parties too.
    _q("DROP POLICY tb_contract_read ON tb_contract")
    _q(f"CREATE POLICY tb_contract_read ON tb_contract FOR SELECT USING ({ADMIN} OR owner_company_id = {ME} "
       f"OR app_tb_contract_linked_visible(id, {ME}) OR app_tb_contract_party(id, {ME}))")
    # The order trail is append-only.
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON tb_order_event FROM gex_app")

    # ── derived per-party views (D2: no stored per-party data) ──────────────
    _q("""CREATE VIEW v_party_leg WITH (security_invoker = true) AS
        SELECT cp.company_id AS party_company_id, side.party_id, v.contract_id, l.id AS leg_id,
               l.leg_role, side.direction,
               CASE WHEN side.direction = 1 THEN l.payer_id ELSE l.receiver_id END AS counterparty_id
        FROM tb_contract_version v
        JOIN tb_leg l ON l.terms_id = v.terms_id
        CROSS JOIN LATERAL (VALUES (l.receiver_id, 1), (l.payer_id, -1)) AS side(party_id, direction)
        JOIN tb_counterparty cp ON cp.id = side.party_id
        WHERE v.superseded_at IS NULL""")
    _q("""CREATE VIEW v_party_flow WITH (security_invoker = true) AS
        SELECT pl.*, f.id AS flow_id, f.flow_type, f.period_start, f.period_end, f.settle_date,
               f.unit, f.index_id, f.index_multiplier,
               pl.direction * f.quantity AS signed_quantity,
               CASE WHEN f.flow_type = 'fixed_cash'
                    THEN pl.direction * f.quantity * (f.unit_price + f.spread) END AS signed_fixed_amount
        FROM v_party_leg pl JOIN tb_flow f ON f.leg_id = pl.leg_id""")
    # Planned (capacities) joins in M5, once capacities carry commodity and quantity.
    _q("""CREATE VIEW v_position WITH (security_invoker = true) AS
        SELECT pf.party_company_id, t.commodity_id, pf.index_id,
               date_trunc('month', pf.period_start)::date AS period, 'contracted'::text AS status_class,
               sum(pf.signed_quantity) FILTER (WHERE pf.flow_type = 'physical') AS physical_qty,
               sum(pf.signed_fixed_amount) AS fixed_cash_amount,
               sum(pf.signed_quantity * pf.index_multiplier) FILTER (WHERE pf.flow_type = 'float_cash')
                   AS index_exposure_qty
        FROM v_party_flow pf JOIN tb_contract_version v ON v.contract_id = pf.contract_id
             AND v.superseded_at IS NULL
        JOIN tb_terms t ON t.id = v.terms_id
        GROUP BY 1, 2, 3, 4""")

    forced = conn.execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(NEW_TABLES)}).scalar()
    assert forced == len(NEW_TABLES), f"only {forced} of {len(NEW_TABLES)} new tables under FORCED RLS"


def downgrade() -> None:
    for view in ("v_position", "v_party_flow", "v_party_leg"):
        _q(f"DROP VIEW IF EXISTS {view}")
    _q("DROP POLICY IF EXISTS tb_contract_read ON tb_contract")
    _q("CREATE POLICY tb_contract_read ON tb_contract FOR SELECT USING ("
       f"{ADMIN} OR owner_company_id = {ME} OR app_tb_contract_linked_visible(id, {ME}))")
    _q("ALTER TABLE tb_contract DROP CONSTRAINT IF EXISTS ck_tb_contract_one_model")
    for table in NEW_TABLES:                 # policies reference each other's tables
        for suffix in ("read", "insert", "update", "delete"):
            _q(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
    for table in ("tb_contract_version_token", "tb_contract_version"):
        _q(f"DROP TABLE IF EXISTS {table}")
    _q("ALTER TABLE tb_contract DROP COLUMN IF EXISTS fill_id")
    for table in ("tb_fill", "tb_order_event", "tb_order_invitee", "tb_order", "tb_rfq",
                  "tb_flow", "tb_leg", "tb_terms", "tb_counterparty_restriction"):
        _q(f"DROP TABLE IF EXISTS {table}")
    for signature in reversed(list(FUNCTIONS)):
        _q(f"DROP FUNCTION IF EXISTS {signature}")
    _q("DROP FUNCTION IF EXISTS tb_refuse_frozen()")
    _q("DROP FUNCTION IF EXISTS tb_refuse_token_rewrite() CASCADE")
    _q("DROP FUNCTION IF EXISTS tb_require_contract_token() CASCADE")
    _q("DROP FUNCTION IF EXISTS tb_refuse_add_to_frozen()")
    for col in ("token_ref", "verification_state", "trade_status", "contract_ref"):
        _q(f"ALTER TABLE tb_contract DROP COLUMN IF EXISTS {col}")
    for col in ("contract_number", "buy_side_id", "sell_side_id", "fuel_type", "trade_date",
                "effective_date", "termination_date", "notional_quantity", "quantity_unit",
                "currency", "status", "owner_company_id"):
        _q(f"ALTER TABLE tb_contract ALTER COLUMN {col} SET NOT NULL")
    _q("ALTER TABLE tb_index_definition DROP COLUMN IF EXISTS commodity_id")
    _q("DROP INDEX IF EXISTS uq_tb_counterparty_company")
    _q("ALTER TABLE tb_counterparty DROP COLUMN IF EXISTS company_id")
    _q("DROP TABLE IF EXISTS tb_commodity")
    for name in ENUMS:
        _q(f"DROP TYPE IF EXISTS {name}")
