"""One contract record, Phase 1 — sub-legs, clauses and the contract's event chain.

Revision ID: 083
Revises: 082

WHY (docs/CONTRACT_RECORD_PHASE0.md; JML's decisions of 2026-11-05/06)
---------------------------------------------------------------------
065 is the one contract schema. Phase 1 makes the market write it: an agreed
match creates a draft contract here and no longer in `contracts` (063). This adds
what 065 lacked for that, as decided in Phase 0:

  tb_sub_leg         Q1/Q2: one row per buyer within a version's terms. Each
                     buyer's product and payment legs hang off it (tb_leg.sub_leg_id),
                     so V01 becomes "two legs per sub-leg"; a bilateral trade is a
                     frame with one sub-leg. Its own hash, so a buyer confirms its
                     own part and only the buyers whose part changed re-confirm.
  tb_clause          Q1/Q3/Q6: terms with no cashflow (delivery and payment terms,
                     take-or-pay, CPs, damages, FM, …), shared or per sub-leg,
                     frozen with the terms and inside the hash.
  tb_contract_event  §4: ONE append-only, hash-chained event log per contract
                     (scheme '2'; scheme '078' is reserved for the Phase 2 fold).
                     Immutable for every role (trigger), not only for gex_app.
  tb_terms           profile (complete | card) and shared_hash; a frozen row
                     carries both hashes.
  tb_contract        kind, project_id, origin_ref (what created it — 'match:<id>'
                     or 'fill:<id>'), correlation_id (the market trail), and a
                     sequence for human references (GEX-TB-<year>-<nnnnnn>).
  matches            delivery_terms, payment_terms — Q6: agreed with the proposal,
                     so nothing is typed after both sides accept.
  approval_policies  TRADE_CONFIRM (Q7): four eyes inside each party.

TENANCY. Both new term tables follow tb_leg (read: who can read the terms;
write: the terms' owner). Events are read by the contract's parties and written
only on the market/order connection, which authorises the Party first (as
tb_contract_version). Everything under FORCED RLS, asserted below.

ADDITIVE. Every table touched is empty on 2026-11-06 except approval_policies
(one row added) and matches (0 rows; two nullable columns).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "083"
down_revision: Union[str, None] = "082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
AUDIT = """created_at timestamptz NOT NULL DEFAULT now(),
           created_by text NOT NULL DEFAULT current_user,
           updated_at timestamptz NOT NULL DEFAULT now()"""

CLAUSE_TYPES = ("delivery", "payment", "parties", "commitment", "conditions_precedent", "damages",
                "force_majeure", "change_in_law", "credit", "performance", "price", "declaration")
EVENT_TYPES = ("CREATED_FROM_MATCH", "MIGRATED", "VERSION", "COUNTERPARTY_SET", "CONFIRMED", "DISPUTED",
               "STATUS_CHANGED", "ADVERSE_FACT_REPORTED", "ADVERSE_FACT_CLEARED", "NOVATION")
KINDS = ("trade", "offtake", "ppa", "supply", "epc", "licence", "technical", "model")
NEW_TABLES = ("tb_sub_leg", "tb_clause", "tb_contract_event")

POLICIES = {   # table -> (read, write)
    "tb_sub_leg": (f"{ADMIN} OR app_tb_terms_readable(terms_id, {ME})",
                   f"{ADMIN} OR app_tb_terms_owner(terms_id) = {ME}"),
    "tb_clause": (f"{ADMIN} OR app_tb_terms_readable(terms_id, {ME})",
                  f"{ADMIN} OR app_tb_terms_owner(terms_id) = {ME}"),
    "tb_contract_event": (f"{ADMIN} OR app_tb_contract_party(contract_id, {ME})", ADMIN),
}

# 065's bodies, extended to the two new term tables (which carry terms_id like tb_leg).
REFUSE_FROZEN = """CREATE OR REPLACE FUNCTION tb_refuse_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE t uuid;
    BEGIN
      IF TG_TABLE_NAME = 'tb_terms' THEN
        IF OLD.frozen_at IS NOT NULL THEN       -- freezing itself (NULL -> set) is allowed
          RAISE EXCEPTION 'TERMS_FROZEN: terms % are frozen; amend by a new contract version', OLD.id
            USING ERRCODE = 'check_violation';
        END IF;
      ELSE
        IF TG_TABLE_NAME IN ({tables}) THEN
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
    END $$"""
REFUSE_ADD = """CREATE OR REPLACE FUNCTION tb_refuse_add_to_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE t uuid;
    BEGIN
      IF TG_TABLE_NAME IN ({tables}) THEN t := NEW.terms_id;
      ELSE SELECT l.terms_id INTO t FROM tb_leg l WHERE l.id = NEW.leg_id;
      END IF;
      IF EXISTS (SELECT 1 FROM tb_terms WHERE id = t AND frozen_at IS NOT NULL) THEN
        RAISE EXCEPTION 'TERMS_FROZEN: terms % are frozen', t USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$"""
WITH_TERMS_ID_083 = "'tb_leg', 'tb_sub_leg', 'tb_clause'"
WITH_TERMS_ID_065 = "'tb_leg'"


def _q(sql: str, params: dict | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT (SELECT count(*) FROM tb_terms) + (SELECT count(*) FROM tb_contract)")).scalar()
    assert n == 0, f"083 expects tb_terms and tb_contract empty; they hold {n} rows"

    # ── terms: profile, shared hash, sub-legs, clauses ──────────────────────
    _q("ALTER TABLE tb_terms ADD COLUMN profile text NOT NULL DEFAULT 'complete' "
       "CHECK (profile IN ('complete', 'card'))")
    _q("ALTER TABLE tb_terms ADD COLUMN shared_hash char(64)")
    _q("ALTER TABLE tb_terms ADD CONSTRAINT ck_tb_terms_frozen_hashes "
       "CHECK (frozen_at IS NULL OR shared_hash IS NOT NULL)")
    _q(f"""CREATE TABLE tb_sub_leg (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           terms_id uuid NOT NULL REFERENCES tb_terms(id) ON DELETE CASCADE,
           seq smallint NOT NULL CHECK (seq >= 1),
           buyer_id uuid REFERENCES tb_counterparty(id),      -- NULL in order terms (D3)
           rank smallint,                                     -- tranching (Q2)
           sub_leg_hash char(64),
           {AUDIT},
           UNIQUE (terms_id, seq))""")
    _q("ALTER TABLE tb_leg ADD COLUMN sub_leg_id uuid REFERENCES tb_sub_leg(id) ON DELETE CASCADE")
    types = ", ".join(f"'{t}'" for t in CLAUSE_TYPES)
    _q(f"""CREATE TABLE tb_clause (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           terms_id uuid NOT NULL REFERENCES tb_terms(id) ON DELETE CASCADE,
           sub_leg_id uuid REFERENCES tb_sub_leg(id) ON DELETE CASCADE,   -- NULL: a shared clause
           clause_type text NOT NULL CHECK (clause_type IN ({types})),
           seq smallint NOT NULL CHECK (seq >= 1),
           attrs jsonb NOT NULL DEFAULT '{{}}'::jsonb,
           {AUDIT},
           UNIQUE (terms_id, seq))""")
    _q(REFUSE_FROZEN.format(tables=WITH_TERMS_ID_083))
    _q(REFUSE_ADD.format(tables=WITH_TERMS_ID_083))
    for table in ("tb_sub_leg", "tb_clause"):
        _q(f"CREATE TRIGGER {table}_frozen BEFORE UPDATE OR DELETE ON {table} "
           "FOR EACH ROW EXECUTE FUNCTION tb_refuse_frozen()")
        _q(f"CREATE TRIGGER {table}_frozen_insert BEFORE INSERT ON {table} "
           "FOR EACH ROW EXECUTE FUNCTION tb_refuse_add_to_frozen()")

    # ── contracts: kind, project, origin, trail, human reference ────────────
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    _q(f"ALTER TABLE tb_contract ADD COLUMN kind text CHECK (kind IN ({kinds}))")
    _q("ALTER TABLE tb_contract ADD COLUMN project_id text REFERENCES projects(project_id)")
    _q("ALTER TABLE tb_contract ADD COLUMN origin_ref text UNIQUE")
    _q("ALTER TABLE tb_contract ADD COLUMN correlation_id text")
    _q("ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_terms_kind "
       "CHECK (contract_type <> 'terms' OR kind IS NOT NULL)")
    _q("CREATE SEQUENCE tb_contract_ref_seq")
    _q("GRANT USAGE ON SEQUENCE tb_contract_ref_seq TO gex_app")

    # ── the contract's event chain ──────────────────────────────────────────
    events = ", ".join(f"'{e}'" for e in EVENT_TYPES)
    _q(f"""CREATE TABLE tb_contract_event (
           id bigserial PRIMARY KEY,
           contract_id uuid NOT NULL REFERENCES tb_contract(id),
           seq integer NOT NULL CHECK (seq >= 1),
           event_type text NOT NULL CHECK (event_type IN ({events})),
           version_id uuid REFERENCES tb_contract_version(id),
           sub_leg_id uuid REFERENCES tb_sub_leg(id),
           terms_hash char(64),
           actor text NOT NULL,
           company_id text,
           note text,
           at timestamptz NOT NULL,
           prev_hash char(64),
           event_hash char(64) NOT NULL UNIQUE,
           hash_scheme text NOT NULL CHECK (hash_scheme IN ('078', '2')),
           legacy_contract_id bigint,
           UNIQUE (contract_id, seq),
           CHECK ((seq = 1) = (prev_hash IS NULL)))""")
    _q("""CREATE FUNCTION tb_refuse_event_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'EVENT_APPEND_ONLY: contract events are never rewritten or removed'
            USING ERRCODE = 'check_violation';
        END $$""")
    _q("CREATE TRIGGER tb_contract_event_append_only BEFORE UPDATE OR DELETE ON tb_contract_event "
       "FOR EACH ROW EXECUTE FUNCTION tb_refuse_event_rewrite()")

    # ── RLS ─────────────────────────────────────────────────────────────────
    for table in NEW_TABLES:
        read, write = POLICIES[table]
        _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
        _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({write})")
        if table != "tb_contract_event":
            _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({write}) WITH CHECK ({write})")
            _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({write})")
    # 031's DEFAULT PRIVILEGES gave gex_app full DML on the new tables: take it back.
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON tb_contract_event FROM gex_app")
    _q("GRANT USAGE ON SEQUENCE tb_contract_event_id_seq TO gex_app")

    # ── Q6: delivery and payment terms are agreed with the proposal ─────────
    _q("ALTER TABLE matches ADD COLUMN delivery_terms text")
    _q("ALTER TABLE matches ADD COLUMN payment_terms text")

    # ── Q7: TRADE_CONFIRM, four eyes inside each party ──────────────────────
    _q("""INSERT INTO approval_policies (id, action_type, threshold_currency, threshold_volume,
              required_roles, min_approvers, escalation_timeout_hours, escalation_role, active, created_at)
          VALUES ('pol-trade-confirm', 'TRADE_CONFIRM', NULL, NULL, '["EXECUTIVE"]', 1, 48, 'CEO', 1,
                  to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'))
          ON CONFLICT (id) DO NOTHING""")

    forced = conn.execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(NEW_TABLES)}).scalar()
    assert forced == len(NEW_TABLES), f"only {forced} of {len(NEW_TABLES)} new tables under FORCED RLS"
    held = set(conn.execute(sa.text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'tb_contract_event'")).scalars())
    assert {"INSERT", "SELECT"} <= held and not held & {"UPDATE", "DELETE", "TRUNCATE"}, \
        f"gex_app holds {sorted(held)} on tb_contract_event; it must append and read, never rewrite"


def downgrade() -> None:
    _q("DELETE FROM approval_policies WHERE id = 'pol-trade-confirm'")
    _q("ALTER TABLE matches DROP COLUMN IF EXISTS payment_terms")
    _q("ALTER TABLE matches DROP COLUMN IF EXISTS delivery_terms")
    _q("DROP TABLE IF EXISTS tb_contract_event")
    _q("DROP FUNCTION IF EXISTS tb_refuse_event_rewrite()")
    _q("DROP SEQUENCE IF EXISTS tb_contract_ref_seq")
    _q("ALTER TABLE tb_contract DROP CONSTRAINT IF EXISTS ck_tb_contract_terms_kind")
    for col in ("correlation_id", "origin_ref", "project_id", "kind"):
        _q(f"ALTER TABLE tb_contract DROP COLUMN IF EXISTS {col}")
    _q("DROP TABLE IF EXISTS tb_clause")
    _q("ALTER TABLE tb_leg DROP COLUMN IF EXISTS sub_leg_id")
    _q("DROP TABLE IF EXISTS tb_sub_leg")
    _q(REFUSE_FROZEN.format(tables=WITH_TERMS_ID_065))
    _q(REFUSE_ADD.format(tables=WITH_TERMS_ID_065))
    _q("ALTER TABLE tb_terms DROP CONSTRAINT IF EXISTS ck_tb_terms_frozen_hashes")
    _q("ALTER TABLE tb_terms DROP COLUMN IF EXISTS shared_hash")
    _q("ALTER TABLE tb_terms DROP COLUMN IF EXISTS profile")
