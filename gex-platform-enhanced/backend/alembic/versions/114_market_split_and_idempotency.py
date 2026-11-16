"""Market token splits, and idempotent create requests (discovery review Phase 0, F12/F13).

Revision ID: 114
Revises: 113

1. `token_split` (109) recorded only partial TITLE transfers of a delivery. The market had
   no partial at all: opening a listing reserved the WHOLE token, and accepting a match
   moved the whole reserved token to MATCHED and, at settlement, its whole title to the
   buyer — though the contract was for min(listing, RFQ) over the overlap of the windows.
   Measured in test_market_chain: a 50 MTPD 2027-2029 token sold to an RFQ for 40 MTPD
   2027-2028 passed title to all 50 MTPD for three years.

   The market now carves the token at the two points where the quantity is decided —
   listing open and acceptance — into a kept child (exactly the listed / agreed rate and
   window) and remainder children (back to MINTED, available). The same table records
   them, so app_token_kg, the SPLIT freeze (tokens_split_guard) and lineage work unchanged.
   The delivery draw guard (103/107) now limits a token to app_token_kg — a carved child's
   recorded kg — instead of only allocations made to that very token, which no child has:
     reason          'delivery_title' (109) | 'market_listing' | 'market_acceptance'
     delivery_id     required for delivery_title only (was NOT NULL)
     order_id        the listing or proposal that decided the quantity (market reasons)
     capacity_id     the child's capacity, for the read rule of market rows
     tokenised_mtpd, delivery_start, delivery_end   the piece, as carved
     kg              custody kg apportioned by tonnes; may be 0 for a market piece of a
                     forward token (no custody kg exists yet), never for a delivery title.
   Read: GEX; delivery rows as before; market rows by whoever sees the capacity (the
   tokens rule, 084). Insert stays operator-only; no update or delete for anyone.

2. `idempotency_record`: an `Idempotency-Key` on a create request is stored per company
   with the request's hash and, once done, its response. A repeat returns the stored
   response; the same key with a different request is refused. RLS: a company sees and
   writes only its own keys (GEX all).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "114"
down_revision: Union[str, None] = "113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    # 1. token_split takes market pieces
    _q("ALTER TABLE token_split ALTER COLUMN delivery_id DROP NOT NULL")
    _q("ALTER TABLE token_split ADD COLUMN reason text NOT NULL DEFAULT 'delivery_title' "
       "CHECK (reason IN ('delivery_title', 'market_listing', 'market_acceptance'))")
    _q("ALTER TABLE token_split ADD COLUMN order_id uuid REFERENCES tb_order(id)")
    _q("ALTER TABLE token_split ADD COLUMN capacity_id text")
    _q("ALTER TABLE token_split ADD COLUMN tokenised_mtpd double precision")
    _q("ALTER TABLE token_split ADD COLUMN delivery_start text")
    _q("ALTER TABLE token_split ADD COLUMN delivery_end text")
    _q("ALTER TABLE token_split DROP CONSTRAINT token_split_kg_check")
    _q("ALTER TABLE token_split ADD CONSTRAINT token_split_kg_check CHECK "
       "((reason = 'delivery_title' AND kg > 0) OR (reason <> 'delivery_title' AND kg >= 0))")
    _q("ALTER TABLE token_split ADD CONSTRAINT token_split_reason_refs CHECK "
       "((reason = 'delivery_title' AND delivery_id IS NOT NULL AND order_id IS NULL) OR "
       " (reason <> 'delivery_title' AND delivery_id IS NULL AND order_id IS NOT NULL "
       "  AND capacity_id IS NOT NULL AND tokenised_mtpd > 0 AND delivery_start IS NOT NULL "
       "  AND delivery_end IS NOT NULL))")
    # 109's deferred consistency check assumed every split is a delivery title: exactly two
    # children whose kg sum to the parent's. A market split has two to four children, all of one
    # reason and one order, and must partition the parent's TONNES (rate x days) exactly too.
    _q("""CREATE OR REPLACE FUNCTION token_split_consistent() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE n integer; total numeric; whole numeric; st text; reasons integer; orders integer;
                why text; pieces numeric; parent_t numeric;
        BEGIN
          SELECT count(*), coalesce(sum(kg), 0), count(DISTINCT reason), count(DISTINCT order_id), min(reason)
            INTO n, total, reasons, orders, why FROM token_split WHERE parent_token_id = NEW.parent_token_id;
          whole := app_token_kg(NEW.parent_token_id);
          SELECT lifecycle_state INTO st FROM tokens WHERE id = NEW.parent_token_id;
          IF why = 'delivery_title' THEN
            IF n <> 2 OR reasons <> 1 OR total <> whole OR st IS DISTINCT FROM 'SPLIT' THEN
              RAISE EXCEPTION 'TOKEN_SPLIT_UNBALANCED: % splits into % children of % kg in all, against % kg (state %)',
                NEW.parent_token_id, n, total, whole, st USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
          END IF;
          IF n < 2 OR n > 4 OR reasons <> 1 OR orders <> 1 OR total <> whole OR st IS DISTINCT FROM 'SPLIT' THEN
            RAISE EXCEPTION 'TOKEN_SPLIT_UNBALANCED: % splits into % market pieces of % kg in all, against % kg (state %)',
              NEW.parent_token_id, n, total, whole, st USING ERRCODE = 'check_violation';
          END IF;
          SELECT sum(s.tokenised_mtpd::numeric * (s.delivery_end::date - s.delivery_start::date + 1)) INTO pieces
            FROM token_split s WHERE s.parent_token_id = NEW.parent_token_id;
          SELECT t.tokenised_mtpd::numeric * (left(t.delivery_end, 10)::date - left(t.delivery_start, 10)::date + 1)
            INTO parent_t FROM tokens t WHERE t.id = NEW.parent_token_id;
          IF parent_t IS NULL OR abs(pieces - parent_t) > 0.000001 * greatest(parent_t, 1) THEN
            RAISE EXCEPTION 'TOKEN_SPLIT_TONNES: the pieces of % hold % t, the token % t',
              NEW.parent_token_id, pieces, parent_t USING ERRCODE = 'check_violation';
          END IF;
          RETURN NULL;
        END $$""")
    _q("""CREATE OR REPLACE FUNCTION delivery_draw_guard() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
      -- 114: a carved token holds the kg its split recorded (app_token_kg), not a direct allocation.
      allocated := app_token_kg(NEW.token_id);
      -- B4 (107): a REJECTED delivery's draws are released; they stay on record.
      SELECT coalesce(sum(x.kg), 0) INTO drawn FROM delivery_draw x JOIN deliveries y ON y.id = x.delivery_id
       WHERE x.token_id = NEW.token_id AND y.status <> 'REJECTED';
      IF drawn + NEW.kg > allocated THEN
        RAISE EXCEPTION 'DELIVERY_OVER_ALLOCATION: token % has % kg allocated from custody, % kg already drawn',
          NEW.token_id, allocated, drawn USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$""")
    _q("DROP POLICY token_split_read ON token_split")
    _q(f"CREATE POLICY token_split_read ON token_split FOR SELECT USING ({ADMIN} "
       f"OR (delivery_id IS NOT NULL AND app_company_sees_delivery(delivery_id, {CURRENT})) "
       f"OR (delivery_id IS NULL AND app_company_sees_capacity(capacity_id, {CURRENT})))")

    # 2. idempotency
    _q("""CREATE TABLE idempotency_record (
            id bigserial PRIMARY KEY,
            company_id text NOT NULL,
            user_id text NOT NULL,
            idem_key text NOT NULL CHECK (length(idem_key) BETWEEN 8 AND 128),
            method_path text NOT NULL,
            request_sha256 character(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
            status text NOT NULL CHECK (status IN ('in_progress', 'done')),
            status_code integer,
            response jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz,
            UNIQUE (company_id, idem_key),
            CHECK ((status = 'done') = (status_code IS NOT NULL AND completed_at IS NOT NULL)))""")
    _q("ALTER TABLE idempotency_record ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE idempotency_record FORCE ROW LEVEL SECURITY")
    own = f"({ADMIN} OR company_id = {CURRENT})"
    _q(f"CREATE POLICY idempotency_record_read ON idempotency_record FOR SELECT USING {own}")
    _q(f"CREATE POLICY idempotency_record_insert ON idempotency_record FOR INSERT WITH CHECK {own}")
    _q(f"CREATE POLICY idempotency_record_update ON idempotency_record FOR UPDATE USING {own} WITH CHECK {own}")
    _q(f"CREATE POLICY idempotency_record_delete ON idempotency_record FOR DELETE USING "
       f"({own} AND status = 'in_progress')")           # only an unfinished reservation is released
    _q("REVOKE ALL ON idempotency_record FROM gex_app")
    _q("GRANT SELECT, INSERT, UPDATE, DELETE ON idempotency_record TO gex_app")
    _q("GRANT USAGE ON SEQUENCE idempotency_record_id_seq TO gex_app")

    conn = op.get_bind()
    forced = conn.execute(sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'idempotency_record'")).scalar()
    assert forced, "idempotency_record is not under FORCED RLS"
    grants = conn.execute(sa.text(
        "SELECT string_agg(privilege_type, ',' ORDER BY privilege_type) FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'token_split'")).scalar()
    assert grants == "INSERT,SELECT", f"token_split must stay append-only for gex_app, found {grants}"


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS idempotency_record")
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM token_split WHERE reason <> 'delivery_title'")).scalar()
    assert n == 0, f"{n} market split rows exist; 113's token_split cannot hold them"
    _q("""CREATE OR REPLACE FUNCTION token_split_consistent() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
        END $$""")
    _q("""CREATE OR REPLACE FUNCTION delivery_draw_guard() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
    END $$""")
    _q("DROP POLICY token_split_read ON token_split")
    _q(f"CREATE POLICY token_split_read ON token_split FOR SELECT USING "
       f"(app_company_sees_delivery(delivery_id, {CURRENT}))")
    _q("ALTER TABLE token_split DROP CONSTRAINT token_split_reason_refs")
    _q("ALTER TABLE token_split DROP CONSTRAINT token_split_kg_check")
    _q("ALTER TABLE token_split ADD CONSTRAINT token_split_kg_check CHECK (kg > 0::numeric)")
    for col in ("delivery_end", "delivery_start", "tokenised_mtpd", "capacity_id", "order_id", "reason"):
        _q(f"ALTER TABLE token_split DROP COLUMN {col}")
    _q("ALTER TABLE token_split ALTER COLUMN delivery_id SET NOT NULL")
