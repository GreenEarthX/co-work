"""A capacity is never over-tokenised, whoever writes the token (discovery review F10).

Revision ID: 115
Revises: 114

114's mint route locks the capacity row and checks the peak rate per delivery window. That
protects the API only: the re-run probe (docs/discovery/assets/probe_results_after_phase0.json,
probe 06) showed a writer inserting a token WITHOUT taking the lock still over-issued — 120
MTPD on a 100 MTPD capacity.

This is the database's rule. A deferred constraint trigger on `tokens` (INSERT, and UPDATE of
rate, window or capacity) runs at COMMIT: it locks the capacity row (so two committing
transactions are checked one after the other, each seeing the other's committed rows) and
refuses if, on any day, the total rate of the capacity's live tokens exceeds capacity_mtpd.
Live = not SPLIT (its rate lives in its children) and not VOIDED (never valid). A token with
no window counts on every day. A capacity without capacity_mtpd is not checked (nothing to
check against). Deferred, because a split inserts its children before marking the parent SPLIT.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "115"
down_revision: Union[str, None] = "114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE OR REPLACE FUNCTION tokens_capacity_guard() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE cap_mtpd double precision; peak double precision;
        BEGIN
          IF NEW.capacity_id IS NULL THEN RETURN NULL; END IF;
          SELECT capacity_mtpd INTO cap_mtpd FROM capacities WHERE id = NEW.capacity_id FOR UPDATE;
          IF cap_mtpd IS NULL THEN RETURN NULL; END IF;
          WITH live AS (
            SELECT tokenised_mtpd AS r,
                   coalesce(left(delivery_start, 10)::date, DATE '0001-01-01') AS a,
                   coalesce(left(delivery_end, 10)::date, DATE '9999-12-31') AS b
              FROM tokens
             WHERE capacity_id = NEW.capacity_id
               AND coalesce(lifecycle_state, 'MINTED') NOT IN ('SPLIT', 'VOIDED')
               AND coalesce(tokenised_mtpd, 0) > 0)
          SELECT coalesce(max((SELECT sum(l.r) FROM live l WHERE l.a <= d.a AND l.b >= d.a)), 0)
            INTO peak FROM live d;
          IF peak > cap_mtpd + 1e-9 THEN
            RAISE EXCEPTION 'CAPACITY_EXCEEDED: capacity % (% MTPD) would carry % MTPD on one day',
              NEW.capacity_id, cap_mtpd, peak USING ERRCODE = 'check_violation';
          END IF;
          RETURN NULL;
        END $$""")
    _q("""CREATE CONSTRAINT TRIGGER tokens_capacity_guard
          AFTER INSERT OR UPDATE OF tokenised_mtpd, delivery_start, delivery_end, capacity_id ON tokens
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tokens_capacity_guard()""")
    over = op.get_bind().execute(sa.text("""
        SELECT c.id FROM capacities c WHERE c.capacity_mtpd IS NOT NULL AND EXISTS (
          SELECT 1 FROM tokens d WHERE d.capacity_id = c.id
             AND coalesce(d.lifecycle_state, 'MINTED') NOT IN ('SPLIT', 'VOIDED')
             AND (SELECT sum(l.tokenised_mtpd) FROM tokens l WHERE l.capacity_id = c.id
                    AND coalesce(l.lifecycle_state, 'MINTED') NOT IN ('SPLIT', 'VOIDED')
                    AND coalesce(left(l.delivery_start, 10)::date, DATE '0001-01-01')
                        <= coalesce(left(d.delivery_start, 10)::date, DATE '0001-01-01')
                    AND coalesce(left(l.delivery_end, 10)::date, DATE '9999-12-31')
                        >= coalesce(left(d.delivery_start, 10)::date, DATE '0001-01-01'))
                 > c.capacity_mtpd + 1e-9)""")).fetchall()
    assert not over, f"capacities already over-tokenised, resolve before 115: {[r[0] for r in over]}"


def downgrade() -> None:
    _q("DROP TRIGGER IF EXISTS tokens_capacity_guard ON tokens")
    _q("DROP FUNCTION IF EXISTS tokens_capacity_guard()")
