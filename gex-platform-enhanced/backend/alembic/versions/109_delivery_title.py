"""Title transfer and the token split (GreenMesh Phase 2 Step 3, sub-step 5; amendment B1, B2;
rulings R2, R3; decision T1 open). Stops before SETTLED.

Revision ID: 109
Revises: 108

Title follows the contract's TITLE clause (B1, R1), read at scheduling into
`deliveries.title_passes` (fixed by trigger). GEX moves the token holder at the LATER of
ACCEPTED and the title trigger (T1), writing DELIVERY_TITLE_TRANSFERRED — derived, no party:

    ON_ACCEPTANCE          at ACCEPTED
    ON_RISK                at ACCEPTED, once RISK_PASSED is recorded
    ON_DOCUMENT_TRANSFER   at ACCEPTED, once the buyer acknowledges the B/L or delivery order
                           (DELIVERY_FACT_DOCUMENT_TRANSFERRED, naming one on file)
    ON_PAYMENT_IN_FULL     REFUSED: payment in full is not recorded on a delivery before
                           settlement, which is after this sub-step.
    no clause              REFUSED, naming the missing clause (no default).

B2, one holder per token: for less than a token's quantity the parent goes to the new
terminal state SPLIT and two children are made (`parent_token_id`): the transferred kg
(holder the buyer) and the remainder (holder the seller). `token_split` records each child's
kg; at commit the two children of a parent sum EXACTLY to its kg (numeric; the root's kg is
its custody allocation, a child's its split). The split and the holder change are in the
same transaction as the one TITLE_TRANSFERRED event, whose hash each split row carries.

Tokens (invariant 2, build notes): a SPLIT token never changes again and is never deleted;
`holder_company_id` changes only on the operator connection (PLATFORM_ADMIN); a company
that owns the capacity but no longer holds the token loses UPDATE and DELETE on it. Read
rules are unchanged.
"""
import importlib.util
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "109"
down_revision: Union[str, None] = "108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
TOKEN_STATES = ("MINTED", "RESERVED", "MATCHED", "SETTLED", "RETIRED", "ANNULLED", "VOIDED")
TITLE_PASSES = ("ON_RISK", "ON_ACCEPTANCE", "ON_PAYMENT_IN_FULL", "ON_DOCUMENT_TRANSFER")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


DOCUMENT_FACT = """        IF fact = 'DOCUMENT_TRANSFERRED' THEN
          IF prev NOT IN ('IN_TRANSIT', 'ARRIVED', 'QUALITY_VERIFICATION', 'ACCEPTED') THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ORDER: documents are transferred after dispatch, not at %', nullif(prev, '')
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
            RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: the buyer acknowledges the documents' USING ERRCODE = 'check_violation';
          END IF;
          IF EXISTS (SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
                     AND e.event_type = NEW.event_type) THEN
            RAISE EXCEPTION 'DELIVERY_FACT_ONCE: the documents are already acknowledged' USING ERRCODE = 'check_violation';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                         AND x.kind IN ('BILL_OF_LADING', 'DELIVERY_ORDER') AND x.sha256 = n ->> 'document_sha256') THEN
            RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: the B/L or delivery order is on file' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';"""

TITLE_RULE = """      IF nxt = 'TITLE_TRANSFERRED' THEN
        IF NEW.company_id IS NOT NULL THEN
          RAISE EXCEPTION 'DELIVERY_TITLE_DERIVED: GEX records title by the title clause, not by a party''s act'
            USING ERRCODE = 'check_violation';
        END IF;
        IF d.title_passes IS NULL THEN
          RAISE EXCEPTION 'DELIVERY_TITLE_NO_CLAUSE: the confirmed terms carry no title clause' USING ERRCODE = 'check_violation';
        END IF;
        IF d.title_passes = 'ON_PAYMENT_IN_FULL' THEN
          RAISE EXCEPTION 'DELIVERY_TITLE_ON_PAYMENT_NOT_BUILT: payment in full is recorded with settlement, after Step 3'
            USING ERRCODE = 'check_violation';
        END IF;
        IF (d.title_passes = 'ON_RISK' AND NOT EXISTS (SELECT 1 FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id
              AND e.event_type = 'DELIVERY_FACT_RISK_PASSED'))
           OR (d.title_passes = 'ON_DOCUMENT_TRANSFER' AND NOT EXISTS (SELECT 1 FROM tb_contract_event e
              WHERE e.delivery_id = NEW.delivery_id AND e.event_type = 'DELIVERY_FACT_DOCUMENT_TRANSFERRED')) THEN
          RAISE EXCEPTION 'DELIVERY_TITLE_TRIGGER: the title clause (%) is not yet met', d.title_passes
            USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
      END IF;
      IF nxt = 'ACCEPTED' THEN"""


def _build():
    m107, m108 = _load("107_delivery_inspection"), _load("108_delivery_dispute_exit")
    text, _ = m108._build(m107)
    replacements = (
        ("        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';", DOCUMENT_FACT),
        ("      IF nxt IN ('TITLE_TRANSFERRED', 'SETTLED') THEN\n"
         "        RAISE EXCEPTION 'DELIVERY_STEP_NOT_BUILT: % is Phase 2 Step 3 sub-step 5 (and SETTLED after it)', nxt",
         "      IF nxt = 'SETTLED' THEN\n"
         "        RAISE EXCEPTION 'DELIVERY_STEP_NOT_BUILT: % comes after Phase 2 Step 3 (stop before SETTLED)', nxt"),
        ("      IF nxt = 'ACCEPTED' THEN", TITLE_RULE),
    )
    for old, new in replacements:
        assert text.count(old) == 1, f"109: anchor not found once: {old[:60]!r}"
        text = text.replace(old, new)
    facts = m107.FACTS + ("RESOLUTION_PROPOSED", "RESOLUTION_CONFIRMED", "DOCUMENT_TRANSFERRED")
    return m107, text, "CHECK (event_type IN " + m107._in(m107._event_types(facts)) + ")", facts


TOKEN_KG = """CREATE FUNCTION app_token_kg(p_token text) RETURNS numeric LANGUAGE sql STABLE SECURITY DEFINER
      SET search_path = public, pg_temp AS $$
      SELECT coalesce((SELECT s.kg FROM token_split s WHERE s.child_token_id = p_token),
                      (SELECT coalesce(sum(a.volume_kg), 0)::numeric FROM mass_balance_allocations a
                       WHERE a.token_id = p_token)) $$"""

SPLIT_CHECK = """CREATE FUNCTION token_split_consistent() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE n integer; total numeric; whole numeric; st text;
    BEGIN
      SELECT count(*), coalesce(sum(kg), 0) INTO n, total FROM token_split WHERE parent_token_id = NEW.parent_token_id;
      whole := app_token_kg(NEW.parent_token_id);
      SELECT lifecycle_state INTO st FROM tokens WHERE id = NEW.parent_token_id;
      IF n <> 2 OR total <> whole OR st IS DISTINCT FROM 'SPLIT' THEN
        RAISE EXCEPTION 'TOKEN_SPLIT_UNBALANCED: % splits into % children of % kg in all, against % kg (state %)',
          NEW.parent_token_id, n, total, whole, st USING ERRCODE = 'check_violation';
      END IF;
      RETURN NULL;
    END $$"""

TOKEN_GUARD = f"""CREATE FUNCTION tokens_split_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        IF OLD.lifecycle_state = 'SPLIT' OR EXISTS (SELECT 1 FROM token_split s WHERE s.child_token_id = OLD.id) THEN
          RAISE EXCEPTION 'TOKEN_SPLIT_FROZEN: a split token and its children are never deleted' USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
      END IF;
      IF OLD.lifecycle_state = 'SPLIT' THEN
        RAISE EXCEPTION 'TOKEN_SPLIT_FROZEN: token % is SPLIT; its children carry it', OLD.id USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.parent_token_id IS DISTINCT FROM OLD.parent_token_id THEN
        RAISE EXCEPTION 'TOKEN_PARENT_FIXED: a token''s parent never changes' USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.holder_company_id IS DISTINCT FROM OLD.holder_company_id
         AND coalesce({CURRENT}, '') <> 'PLATFORM_ADMIN' THEN
        RAISE EXCEPTION 'TOKEN_HOLDER_OPERATOR_ONLY: the holder changes only through a title transfer or settlement'
          USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$"""

WRITE = (f"({ADMIN} OR holder_company_id = {CURRENT} OR (holder_company_id IS NULL AND "
         f"app_company_owns_capacity(capacity_id, {CURRENT})))")
WRITE_036 = (f"({ADMIN} OR (app_company_owns_capacity(capacity_id, {CURRENT}) OR "
             f"(holder_company_id = {CURRENT})))")


def upgrade() -> None:
    m107, check, types, facts = _build()
    have = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'tb_contract_event_event_type_check'").scalar()
    expected = m107._event_types(facts[:-1])
    assert have and all(f"'{t}'" in have for t in expected) and have.count("'") == 2 * len(expected), have
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check {types}")

    # tokens: SPLIT, the parent link, the guard, the write rule
    _q("ALTER TABLE tokens DROP CONSTRAINT ck_tokens_lifecycle_state")
    _q(f"ALTER TABLE tokens ADD CONSTRAINT ck_tokens_lifecycle_state CHECK (lifecycle_state IN {_in(TOKEN_STATES + ('SPLIT',))})")
    _q("ALTER TABLE tokens ADD COLUMN parent_token_id text REFERENCES tokens(id)")
    _q("CREATE INDEX ix_tokens_parent ON tokens (parent_token_id) WHERE parent_token_id IS NOT NULL")
    _q("""CREATE TABLE token_split (
            id bigserial PRIMARY KEY,
            delivery_id text NOT NULL REFERENCES deliveries(id),
            parent_token_id text NOT NULL REFERENCES tokens(id),
            child_token_id text NOT NULL UNIQUE REFERENCES tokens(id),
            kg numeric NOT NULL CHECK (kg > 0),
            holder_company_id text NOT NULL REFERENCES tenants(company_id),
            event_hash character(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now())""")
    _q("ALTER TABLE token_split ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE token_split FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY token_split_read ON token_split FOR SELECT USING (app_company_sees_delivery(delivery_id, {CURRENT}))")
    _q(f"CREATE POLICY token_split_operator_insert ON token_split FOR INSERT WITH CHECK {ADMIN}")
    _q("REVOKE ALL ON token_split FROM gex_app")
    _q("GRANT SELECT, INSERT ON token_split TO gex_app")
    _q("GRANT USAGE ON SEQUENCE token_split_id_seq TO gex_app")
    _q("""CREATE FUNCTION token_split_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'TOKEN_SPLIT_APPEND_ONLY: a split is never changed or removed' USING ERRCODE = 'check_violation'; END $$""")
    _q("CREATE TRIGGER token_split_append_only BEFORE UPDATE OR DELETE ON token_split FOR EACH ROW "
       "EXECUTE FUNCTION token_split_append_only()")
    _q(TOKEN_KG)
    _q(SPLIT_CHECK)
    _q("CREATE CONSTRAINT TRIGGER token_split_consistent AFTER INSERT ON token_split DEFERRABLE INITIALLY DEFERRED "
       "FOR EACH ROW EXECUTE FUNCTION token_split_consistent()")
    _q(TOKEN_GUARD)
    _q("CREATE TRIGGER tokens_split_guard BEFORE UPDATE OR DELETE ON tokens FOR EACH ROW EXECUTE FUNCTION tokens_split_guard()")
    _q("DROP POLICY tokens_update ON tokens")
    _q("DROP POLICY tokens_delete ON tokens")
    _q(f"CREATE POLICY tokens_update ON tokens FOR UPDATE USING {WRITE} WITH CHECK {WRITE}")
    _q(f"CREATE POLICY tokens_delete ON tokens FOR DELETE USING {WRITE}")

    # deliveries: the title clause, read once
    _q(f"ALTER TABLE deliveries ADD COLUMN title_passes text CHECK (title_passes IN {_in(TITLE_PASSES)})")
    _q("""CREATE FUNCTION delivery_title_passes_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.title_passes IS DISTINCT FROM OLD.title_passes THEN
            RAISE EXCEPTION 'DELIVERY_FIXED: a delivery''s title clause is read from its terms once' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER deliveries_title_passes_fixed BEFORE UPDATE OF title_passes ON deliveries "
       "FOR EACH ROW EXECUTE FUNCTION delivery_title_passes_fixed()")
    _q(check)

    assert _q("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'token_split'").scalar()
    held = set(_q("SELECT privilege_type FROM information_schema.role_table_grants "
                  "WHERE grantee = 'gex_app' AND table_name = 'token_split'").scalars())
    assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on token_split"


def downgrade() -> None:
    m107, _, _, facts = _build()
    m108 = _load("108_delivery_dispute_exit")
    for sql, what in (("SELECT count(*) FROM token_split", "token split(s)"),
                      ("SELECT count(*) FROM tokens WHERE lifecycle_state = 'SPLIT' OR parent_token_id IS NOT NULL", "split token(s)"),
                      ("SELECT count(*) FROM tb_contract_event WHERE event_type IN ('DELIVERY_TITLE_TRANSFERRED', "
                       "'DELIVERY_FACT_DOCUMENT_TRANSFERRED')", "title event(s)")):
        n = _q(sql).scalar()
        assert n == 0, f"{n} {what} exist; refusing to downgrade"
    check108, types108 = m108._build(m107)
    _q(check108)
    _q("DROP TRIGGER deliveries_title_passes_fixed ON deliveries")
    _q("DROP FUNCTION delivery_title_passes_fixed()")
    _q("ALTER TABLE deliveries DROP COLUMN title_passes")
    _q("DROP POLICY tokens_update ON tokens")
    _q("DROP POLICY tokens_delete ON tokens")
    _q(f"CREATE POLICY tokens_update ON tokens FOR UPDATE USING {WRITE_036} WITH CHECK {WRITE_036}")
    _q(f"CREATE POLICY tokens_delete ON tokens FOR DELETE USING {WRITE_036}")
    _q("DROP TRIGGER tokens_split_guard ON tokens")
    _q("DROP FUNCTION tokens_split_guard()")
    _q("DROP TABLE token_split")
    for f in ("token_split_consistent()", "token_split_append_only()", "app_token_kg(text)"):
        _q(f"DROP FUNCTION IF EXISTS {f}")
    _q("DROP INDEX IF EXISTS ix_tokens_parent")
    _q("ALTER TABLE tokens DROP COLUMN parent_token_id")
    _q("ALTER TABLE tokens DROP CONSTRAINT ck_tokens_lifecycle_state")
    _q(f"ALTER TABLE tokens ADD CONSTRAINT ck_tokens_lifecycle_state CHECK (lifecycle_state IN {_in(TOKEN_STATES)})")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check {types108}")
