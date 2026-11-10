"""The ledger anchor outbox (Phase 4 of "One contract record"; Phase 0 Q11, Q12).

Revision ID: 095
Revises: 094

WHY
---
Per contract event, a hash goes to a public ledger so a lender or a court can
check that GEX did not rewrite a contract's history. Only hashes and a
pseudonymous id ever leave: no terms, prices, volumes, names or company ids.
The ledger is Hedera Consensus Service messages only — no token of any kind
(rule 3). This migration builds the mechanism; the provider is not chosen and
anchoring stays OFF (LEDGER_ANCHOR_BACKEND = none) until JML switches it on.

WHAT
----
tb_contract.pseudo_id   HMAC-SHA256(salt, contract_ref), one per contract for its
                        life (Q12). Computed by the application (the salt is in
                        files/.env, never in the database), set once and fixed by
                        trigger: NULL -> value is allowed once, nothing after.
ledger_anchor_outbox    One row per contract event, written IN THE SAME TRANSACTION
                        by an AFTER INSERT trigger on tb_contract_event — so every
                        writer of the record, present or future, fills it, and a
                        rolled-back event leaves no row. Status PENDING | ANCHORED |
                        FAILED | NOT_ANCHORED, attempts, the next attempt (backoff and
                        the worker's lease), the ledger reference (network, topic,
                        sequence number, consensus timestamp, transaction id).
                        The identity columns never change; a row is never deleted;
                        an ANCHORED row keeps its reference for good (trigger).

WHO
---
gex_app     SELECT only, under FORCED RLS: the rule that reads the contract's
            events (the parties, the project's companies, GEX staff) reads its
            anchors. It writes nothing here; the trigger does.
gex_anchor  The worker's own role (scripts/setup_postgres_rls.sql creates it; a
            dump does not carry roles): SELECT on the outbox and column-level
            UPDATE on the anchoring columns, and no privilege on any other table.
Asserted below (059's lesson).

Existing events get their outbox rows here, PENDING; existing contracts their
pseudo_id when LEDGER_ANCHOR_SALT is exported (else they stay NULL and
`scripts/drain_anchor_outbox.py --assign-pseudo-ids` sets them later).
"""
import hashlib
import hmac
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "095"
down_revision: Union[str, None] = "094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANCHOR_ROLE = "gex_anchor"
ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
READ = (f"{ADMIN} OR app_tb_contract_party(contract_id, {ME}) "
        f"OR app_tb_contract_project_visible(contract_id, {ME})")      # = tb_contract_event's read rule (085)
STATUSES = ("PENDING", "ANCHORED", "FAILED", "NOT_ANCHORED")
WORKER_COLUMNS = ("status", "attempts", "next_attempt_at", "last_error", "ledger_network", "ledger_topic_id",
                  "ledger_sequence_number", "ledger_consensus_timestamp", "ledger_transaction_id", "anchored_at")


def _pseudo_id(salt: str, contract_ref: str) -> str:
    # Frozen here on purpose: the same formula as app.core.ledger_anchor.pseudo_id
    # (a test holds them equal). It may never change, or existing anchors stop matching.
    return hmac.new(salt.encode("utf-8"), contract_ref.encode("utf-8"), hashlib.sha256).hexdigest()


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ANCHOR_ROLE}).first():
        raise RuntimeError(f"role {ANCHOR_ROLE} does not exist: run scripts/setup_postgres_rls.sql first "
                           "(it creates the roles a dump does not carry)")

    # ── the pseudonymous id, fixed once set ─────────────────────────────────
    _q("ALTER TABLE tb_contract ADD COLUMN pseudo_id char(64) UNIQUE")
    _q("""CREATE FUNCTION tb_refuse_pseudo_id_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.pseudo_id IS NOT NULL AND NEW.pseudo_id IS DISTINCT FROM OLD.pseudo_id THEN
            RAISE EXCEPTION 'PSEUDO_ID_FIXED: a contract keeps its pseudonymous id for life'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER tb_contract_pseudo_id_fixed BEFORE UPDATE OF pseudo_id ON tb_contract "
       "FOR EACH ROW EXECUTE FUNCTION tb_refuse_pseudo_id_change()")

    # ── the outbox ──────────────────────────────────────────────────────────
    statuses = ", ".join(f"'{s}'" for s in STATUSES)
    _q(f"""CREATE TABLE ledger_anchor_outbox (
           id bigserial PRIMARY KEY,
           event_id bigint NOT NULL UNIQUE REFERENCES tb_contract_event(id),
           contract_id uuid NOT NULL REFERENCES tb_contract(id),
           pseudo_id char(64),
           event_type text NOT NULL,
           event_hash char(64) NOT NULL UNIQUE,
           prev_hash char(64),
           created_at timestamptz NOT NULL DEFAULT now(),
           status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ({statuses})),
           attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
           next_attempt_at timestamptz NOT NULL DEFAULT now(),
           last_error text,
           ledger_network text,
           ledger_topic_id text,
           ledger_sequence_number bigint,
           ledger_consensus_timestamp text,
           ledger_transaction_id text,
           anchored_at timestamptz,
           CONSTRAINT ck_anchor_reference CHECK ((status = 'ANCHORED') = (ledger_network IS NOT NULL
               AND ledger_topic_id IS NOT NULL AND ledger_sequence_number IS NOT NULL AND anchored_at IS NOT NULL)),
           CONSTRAINT ck_anchor_pseudo_id CHECK (status <> 'ANCHORED' OR pseudo_id IS NOT NULL))""")
    _q("CREATE INDEX ix_ledger_anchor_outbox_due ON ledger_anchor_outbox (next_attempt_at, id) "
       "WHERE status = 'PENDING'")
    _q("CREATE INDEX ix_ledger_anchor_outbox_contract ON ledger_anchor_outbox (contract_id, id)")

    _q("""CREATE FUNCTION ledger_anchor_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'ANCHOR_OUTBOX_KEPT: an outbox row is never removed' USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.event_id <> OLD.event_id OR NEW.contract_id <> OLD.contract_id
             OR NEW.event_type <> OLD.event_type OR NEW.event_hash <> OLD.event_hash
             OR NEW.prev_hash IS DISTINCT FROM OLD.prev_hash OR NEW.created_at <> OLD.created_at
             OR (OLD.pseudo_id IS NOT NULL AND NEW.pseudo_id IS DISTINCT FROM OLD.pseudo_id) THEN
            RAISE EXCEPTION 'ANCHOR_OUTBOX_IDENTITY: what is anchored never changes' USING ERRCODE = 'check_violation';
          END IF;
          IF OLD.status = 'ANCHORED' AND (NEW.status <> 'ANCHORED'
             OR NEW.ledger_network IS DISTINCT FROM OLD.ledger_network
             OR NEW.ledger_topic_id IS DISTINCT FROM OLD.ledger_topic_id
             OR NEW.ledger_sequence_number IS DISTINCT FROM OLD.ledger_sequence_number
             OR NEW.ledger_transaction_id IS DISTINCT FROM OLD.ledger_transaction_id
             OR NEW.anchored_at IS DISTINCT FROM OLD.anchored_at
             OR (OLD.ledger_consensus_timestamp IS NOT NULL
                 AND NEW.ledger_consensus_timestamp IS DISTINCT FROM OLD.ledger_consensus_timestamp)) THEN
            RAISE EXCEPTION 'ANCHOR_REFERENCE_FIXED: an anchored event keeps its ledger reference'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER ledger_anchor_outbox_guard BEFORE UPDATE OR DELETE ON ledger_anchor_outbox "
       "FOR EACH ROW EXECUTE FUNCTION ledger_anchor_outbox_guard()")

    # Every event writes its row in the event's own transaction. SECURITY DEFINER with a
    # pinned search_path: the writer (gex_app) holds no privilege on the outbox at all.
    _q("""CREATE FUNCTION ledger_anchor_enqueue() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          INSERT INTO ledger_anchor_outbox (event_id, contract_id, pseudo_id, event_type, event_hash, prev_hash)
          SELECT NEW.id, NEW.contract_id, c.pseudo_id, NEW.event_type, NEW.event_hash, NEW.prev_hash
          FROM tb_contract c WHERE c.id = NEW.contract_id;
          RETURN NULL;
        END $$""")
    _q("REVOKE ALL ON FUNCTION ledger_anchor_enqueue() FROM PUBLIC")
    _q("CREATE TRIGGER tb_contract_event_anchor AFTER INSERT ON tb_contract_event "
       "FOR EACH ROW EXECUTE FUNCTION ledger_anchor_enqueue()")
    # A pseudo_id set late (no salt when the contract began) reaches its earlier rows.
    _q("""CREATE FUNCTION ledger_anchor_pseudo_id_assigned() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          UPDATE ledger_anchor_outbox SET pseudo_id = NEW.pseudo_id
          WHERE contract_id = NEW.id AND pseudo_id IS NULL;
          RETURN NULL;
        END $$""")
    _q("REVOKE ALL ON FUNCTION ledger_anchor_pseudo_id_assigned() FROM PUBLIC")
    _q("CREATE TRIGGER tb_contract_pseudo_id_assigned AFTER UPDATE OF pseudo_id ON tb_contract "
       "FOR EACH ROW WHEN (OLD.pseudo_id IS NULL AND NEW.pseudo_id IS NOT NULL) "
       "EXECUTE FUNCTION ledger_anchor_pseudo_id_assigned()")

    # ── RLS ─────────────────────────────────────────────────────────────────
    _q("ALTER TABLE ledger_anchor_outbox ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE ledger_anchor_outbox FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY ledger_anchor_outbox_read ON ledger_anchor_outbox FOR SELECT USING ({READ})")
    _q("CREATE POLICY ledger_anchor_outbox_insert ON ledger_anchor_outbox FOR INSERT WITH CHECK (false)")
    _q(f"CREATE POLICY ledger_anchor_outbox_worker_read ON ledger_anchor_outbox FOR SELECT TO {ANCHOR_ROLE} "
       "USING (true)")
    _q(f"CREATE POLICY ledger_anchor_outbox_worker_update ON ledger_anchor_outbox FOR UPDATE TO {ANCHOR_ROLE} "
       f"USING (true) WITH CHECK (status IN ({statuses}))")

    # ── privileges: 031's DEFAULT PRIVILEGES gave gex_app full DML; take it back ──
    _q(f"REVOKE ALL ON ledger_anchor_outbox FROM PUBLIC, gex_app, {ANCHOR_ROLE}")
    _q("REVOKE ALL ON SEQUENCE ledger_anchor_outbox_id_seq FROM PUBLIC, gex_app")
    _q("GRANT SELECT ON ledger_anchor_outbox TO gex_app")
    _q(f"GRANT SELECT ON ledger_anchor_outbox TO {ANCHOR_ROLE}")
    _q(f"GRANT UPDATE ({', '.join(WORKER_COLUMNS)}) ON ledger_anchor_outbox TO {ANCHOR_ROLE}")

    # ── existing contracts and events ───────────────────────────────────────
    salt = os.environ.get("LEDGER_ANCHOR_SALT", "")
    refs = conn.execute(sa.text("SELECT id, contract_ref FROM tb_contract WHERE contract_ref IS NOT NULL "
                                "AND pseudo_id IS NULL")).fetchall()
    if salt:
        for cid, ref in refs:
            _q("UPDATE tb_contract SET pseudo_id = :p WHERE id = :i", {"p": _pseudo_id(salt, ref), "i": cid})
    elif refs:
        print(f"095: LEDGER_ANCHOR_SALT not exported; {len(refs)} contract(s) keep pseudo_id NULL "
              "(scripts/drain_anchor_outbox.py --assign-pseudo-ids sets them)")
    _q("""INSERT INTO ledger_anchor_outbox (event_id, contract_id, pseudo_id, event_type, event_hash, prev_hash)
          SELECT e.id, e.contract_id, c.pseudo_id, e.event_type, e.event_hash, e.prev_hash
          FROM tb_contract_event e JOIN tb_contract c ON c.id = e.contract_id ORDER BY e.contract_id, e.seq""")

    # ── assert rather than trust ────────────────────────────────────────────
    forced = conn.execute(sa.text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                                  "WHERE relname = 'ledger_anchor_outbox'")).scalar()
    assert forced, "ledger_anchor_outbox is not under FORCED RLS"
    app_held = set(conn.execute(sa.text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'ledger_anchor_outbox'")).scalars())
    assert app_held == {"SELECT"}, f"gex_app holds {sorted(app_held)} on the outbox; it must read only"
    tables = set(conn.execute(sa.text(
        "SELECT table_name || ':' || privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = :r AND table_schema = 'public'"), {"r": ANCHOR_ROLE}).scalars())
    assert tables == {"ledger_anchor_outbox:SELECT"}, f"{ANCHOR_ROLE} table privileges are {sorted(tables)}"
    cols = set(conn.execute(sa.text(
        "SELECT table_name || ':' || column_name FROM information_schema.column_privileges "
        "WHERE grantee = :r AND privilege_type IN ('UPDATE', 'INSERT', 'REFERENCES')"), {"r": ANCHOR_ROLE}).scalars())
    assert cols == {f"ledger_anchor_outbox:{c}" for c in WORKER_COLUMNS}, f"{ANCHOR_ROLE} may write {sorted(cols)}"
    missing = conn.execute(sa.text(
        "SELECT count(*) FROM tb_contract_event e WHERE NOT EXISTS "
        "(SELECT 1 FROM ledger_anchor_outbox o WHERE o.event_id = e.id)")).scalar()
    assert missing == 0, f"{missing} contract event(s) have no outbox row"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM ledger_anchor_outbox WHERE status = 'ANCHORED'").scalar()
    assert n == 0, (f"{n} event(s) are anchored on a public ledger; dropping the outbox would lose their "
                    "ledger references. Refusing to downgrade.")
    _q("DROP TRIGGER IF EXISTS tb_contract_pseudo_id_assigned ON tb_contract")
    _q("DROP TRIGGER IF EXISTS tb_contract_event_anchor ON tb_contract_event")
    _q("DROP TABLE IF EXISTS ledger_anchor_outbox")
    for fn in ("ledger_anchor_pseudo_id_assigned", "ledger_anchor_enqueue", "ledger_anchor_outbox_guard"):
        _q(f"DROP FUNCTION IF EXISTS {fn}()")
    _q("DROP TRIGGER IF EXISTS tb_contract_pseudo_id_fixed ON tb_contract")
    _q("DROP FUNCTION IF EXISTS tb_refuse_pseudo_id_change()")
    _q("ALTER TABLE tb_contract DROP COLUMN IF EXISTS pseudo_id")
