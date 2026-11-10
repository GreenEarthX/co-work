"""The market runs on the order model (Phase 3 of "One contract record", step 3; M3).

Revision ID: 087
Revises: 086

Phase 1 (scope B) left the market's listings, RFQs and matches in their own tables
(offers, rfqs, matches) and made only the agreed match write the record. Now they
are the order model's (Phase 0 Q6, Q8):

  a listing   a firm SELL tb_order, platform visibility, its terms built from the
              listing (product leg, fixed-price payment leg, monthly flows; delivery
              and price basis as clauses; certification and ESG tier in the quality
              spec); token_id ties it to the capacity token it reserves
  an RFQ      a BUY tb_rfq with indicative terms (a product leg, and a payment leg
              when the buyer names a maximum price)
  a proposal  an invited firm tb_order answering an RFQ against a listing
              (listing_order_id + rfq_id) — the proposer's acceptance; the other
              party's acceptance makes the fill and the draft contract (order_book)

The few things that are not terms get columns: the token, the market trail
(correlation_id), the seller-only location and the score on an order; the buyer's
name, contact, location and compliance list on an RFQ (never shown in a listing).
Additive; offers/rfqs/matches are dropped in M6 after a parity check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "087"
down_revision: Union[str, None] = "086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_COLUMNS = (("token_id", "text REFERENCES tokens(id)"), ("correlation_id", "text"), ("location", "text"),
                 ("listing_order_id", "uuid REFERENCES tb_order(id)"), ("match_score", "integer"),
                 ("created_by_user", "text"))
RFQ_COLUMNS = (("buyer_name", "text"), ("buyer_contact", "text"), ("location", "text"),
               ("compliance_requirements", "jsonb NOT NULL DEFAULT '[]'::jsonb"), ("correlation_id", "text"),
               ("created_by_user", "text"))


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    for col, kind in ORDER_COLUMNS:
        _q(f"ALTER TABLE tb_order ADD COLUMN {col} {kind}")
    for col, kind in RFQ_COLUMNS:
        _q(f"ALTER TABLE tb_rfq ADD COLUMN {col} {kind}")
    # One live listing per token: a token is one tradeable lot (the market's rule since 063).
    _q("CREATE UNIQUE INDEX uq_tb_order_live_listing_token ON tb_order (token_id) "
       "WHERE token_id IS NOT NULL AND listing_order_id IS NULL AND rfq_id IS NULL "
       "AND status IN ('draft', 'open', 'partially_filled', 'filled')")
    _q("CREATE INDEX ix_tb_order_listing ON tb_order (listing_order_id) WHERE listing_order_id IS NOT NULL")
    _q("CREATE INDEX ix_tb_order_correlation ON tb_order (correlation_id) WHERE correlation_id IS NOT NULL")


def downgrade() -> None:
    _q("DROP INDEX IF EXISTS ix_tb_order_correlation")
    _q("DROP INDEX IF EXISTS ix_tb_order_listing")
    _q("DROP INDEX IF EXISTS uq_tb_order_live_listing_token")
    for col, _ in reversed(RFQ_COLUMNS):
        _q(f"ALTER TABLE tb_rfq DROP COLUMN IF EXISTS {col}")
    for col, _ in reversed(ORDER_COLUMNS):
        _q(f"ALTER TABLE tb_order DROP COLUMN IF EXISTS {col}")
