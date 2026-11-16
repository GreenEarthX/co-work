"""Cross-company hydrogen: an input backed by a token the company holds (gap G-23).

Revision ID: 110
Revises: 109

Since 101 an H2 input named its source LOT, which only the lot's owner (or GEX) may lock, so a
company buying hydrogen from another company could not name it, and its hydrogen stayed
UNVERIFIED downstream (G-23).

The authorised supply relationship is the token: the buyer HOLDS a hydrogen token by title
transfer (109). An H2 input may now name `source_token_id` instead of a lot:

  * the token is held by the company that owns the consuming period's project, in state
    SETTLED (delivered to it), and is a hydrogen token;
  * the inputs citing it never exceed its kg (`app_token_kg`: custody allocation, or its split);
  * once cited, the token cannot be RETIRED: its attribute went into the downstream product, so
    it cannot also be claimed or sold on.

The proof itself is computed by the application on the operator connection after it has
checked the holder (core/upstream_proof.py): token -> root -> lot -> period, the period's
statement re-verified, and only the proof fields returned. The buyer never reads the
seller's lot or period rows, and cannot ask about a token it does not hold.

The two sources are exclusive. Inputs stay append-only (097).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "110"
down_revision: Union[str, None] = "109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("ALTER TABLE coc_input ADD COLUMN source_token_id text REFERENCES tokens(id)")
    _q("ALTER TABLE coc_input ADD CONSTRAINT ck_coc_input_source_token_h2 "
       "CHECK (source_token_id IS NULL OR input_type = 'H2')")
    _q("ALTER TABLE coc_input ADD CONSTRAINT ck_coc_input_one_source "
       "CHECK (source_token_id IS NULL OR source_lot_id IS NULL)")
    _q("CREATE INDEX ix_coc_input_source_token ON coc_input (source_token_id) WHERE source_token_id IS NOT NULL")
    _q("""CREATE FUNCTION coc_input_source_token_guard() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE t record; owner text; cited numeric;
        BEGIN
          IF NEW.source_token_id IS NULL THEN RETURN NEW; END IF;
          SELECT * INTO t FROM tokens WHERE id = NEW.source_token_id FOR UPDATE;
          SELECT owner_tenant_id INTO owner FROM projects WHERE project_id = NEW.project_id;
          IF t.id IS NULL OR t.holder_company_id IS DISTINCT FROM owner THEN
            RAISE EXCEPTION 'COC_SOURCE_TOKEN_NOT_HELD: token % is not held by the company consuming it', NEW.source_token_id
              USING ERRCODE = 'check_violation';
          END IF;
          IF t.lifecycle_state IS DISTINCT FROM 'SETTLED' OR t.molecule IS DISTINCT FROM 'H2' THEN
            RAISE EXCEPTION 'COC_SOURCE_TOKEN_STATE: token % is % %; an input names a delivered (SETTLED) hydrogen token',
              NEW.source_token_id, t.molecule, t.lifecycle_state USING ERRCODE = 'check_violation';
          END IF;
          SELECT coalesce(sum(quantity_normalised), 0)::numeric INTO cited FROM coc_input
           WHERE source_token_id = NEW.source_token_id;
          IF cited + NEW.quantity_normalised::numeric > app_token_kg(NEW.source_token_id) THEN
            RAISE EXCEPTION 'COC_SOURCE_TOKEN_EXHAUSTED: token % carries % kg, % kg already used as an input',
              NEW.source_token_id, app_token_kg(NEW.source_token_id), cited USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER coc_input_source_token_guard BEFORE INSERT ON coc_input FOR EACH ROW "
       "EXECUTE FUNCTION coc_input_source_token_guard()")
    _q("""CREATE FUNCTION tokens_consumed_guard() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          IF NEW.lifecycle_state = 'RETIRED' AND OLD.lifecycle_state IS DISTINCT FROM 'RETIRED'
             AND EXISTS (SELECT 1 FROM coc_input i WHERE i.source_token_id = NEW.id) THEN
            RAISE EXCEPTION 'TOKEN_CONSUMED_DOWNSTREAM: token % was used as a custody input; its attribute is in the downstream product',
              NEW.id USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER tokens_consumed_guard BEFORE UPDATE OF lifecycle_state ON tokens FOR EACH ROW "
       "EXECUTE FUNCTION tokens_consumed_guard()")
    bad = _q("SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants WHERE grantee = 'gex_app' "
             "AND table_name = 'coc_input' AND privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')").scalar()
    assert not bad, f"gex_app holds {bad} on coc_input: append-only is off"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM coc_input WHERE source_token_id IS NOT NULL").scalar()
    assert n == 0, f"{n} input(s) name a source token; refusing to drop the column"
    _q("DROP TRIGGER IF EXISTS tokens_consumed_guard ON tokens")
    _q("DROP FUNCTION IF EXISTS tokens_consumed_guard()")
    _q("DROP TRIGGER IF EXISTS coc_input_source_token_guard ON coc_input")
    _q("DROP FUNCTION IF EXISTS coc_input_source_token_guard()")
    _q("DROP INDEX IF EXISTS ix_coc_input_source_token")
    _q("ALTER TABLE coc_input DROP CONSTRAINT IF EXISTS ck_coc_input_one_source")
    _q("ALTER TABLE coc_input DROP CONSTRAINT IF EXISTS ck_coc_input_source_token_h2")
    _q("ALTER TABLE coc_input DROP COLUMN IF EXISTS source_token_id")
