"""An order-book sell order may name a token (gap G-25; GreenMesh Phase 2 Step 3, JML P2).

Revision ID: 105
Revises: 104

A delivery draws on a contract's TOKENS (103). Only market listings put a token on a
contract, and market terms carry no typed clauses (G-24); order-book orders carry typed
clauses but could name no token. JML (13 Nov 2026): the order book names a token.

`tb_order.token_id` exists since 087 (a market listing is a firm sell `tb_order`), so this
adds only `tb_order.origin_book`, set to 'order_book' by trading_book's order book. The
market treats every token-bearing top-level order as ITS listing; its two listing queries
now leave out `origin_book = 'order_book'`, which is the only change to market code. NULL
is a market or pre-105 order. 087's partial unique index already allows one live order per
token across both books.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "105"
down_revision: Union[str, None] = "104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE tb_order ADD COLUMN origin_book text "
                         "CHECK (origin_book IS NULL OR origin_book = 'order_book')"))
    conn.execute(sa.text("ALTER TABLE tb_order ADD CONSTRAINT ck_tb_order_token_sell CHECK "
                         "(origin_book IS NULL OR token_id IS NULL OR (side = 'sell' AND all_or_nothing))"))


def downgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT count(*) FROM tb_order WHERE origin_book = 'order_book' "
                             "AND token_id IS NOT NULL")).scalar()
    assert n == 0, f"{n} order-book order(s) name a token; refusing to drop origin_book"
    conn.execute(sa.text("ALTER TABLE tb_order DROP CONSTRAINT IF EXISTS ck_tb_order_token_sell"))
    conn.execute(sa.text("ALTER TABLE tb_order DROP COLUMN IF EXISTS origin_book"))
