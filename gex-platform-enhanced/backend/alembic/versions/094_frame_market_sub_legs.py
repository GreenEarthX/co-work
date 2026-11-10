"""A market trade joins its project's offtake frame (Phase 3 of "One contract record", Q6.4).

Revision ID: 094
Revises: 093

Phase 0 Q6.4: an accepted market trade for a project's output joins the project's
offtake frame as that buyer's sub-leg, and an acceptance that would exceed the
frame's output is refused. JML decided 2026-11-10 how: the sub-leg is LOCKED
against the owner's card saves (it changes only with its trade), and a project that
records no planned output keeps the trade a trade (it never reaches the engine).

The trade stays the one record of its terms (legs, flows, settlement, four-eye
confirmation); the frame's sub-leg names it — source_contract_id and the trade
version's terms hash, both inside the sub-leg hash — and carries the projection
derived from it at acceptance (Q4: first delivery, whole years, smallest full year).
The buyer's four-eye TRADE_CONFIRM is what confirms the sub-leg (Q7.3).

Frozen with the terms by 083's trigger, like every other column of tb_sub_leg.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "094"
down_revision: Union[str, None] = "093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg ADD COLUMN source_contract_id uuid REFERENCES tb_contract(id)"))
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg ADD COLUMN source_terms_hash char(64)"))
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg ADD CONSTRAINT ck_tb_sub_leg_source CHECK "
                                  "((source_contract_id IS NULL) = (source_terms_hash IS NULL) "
                                  "AND (source_contract_id IS NULL OR card_projection IS NOT NULL))"))


def downgrade() -> None:
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM tb_sub_leg WHERE source_contract_id IS NOT NULL")).scalar()
    assert n == 0, f"{n} frame sub-leg(s) come from a market trade; 093 has nowhere to keep that"
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg DROP CONSTRAINT ck_tb_sub_leg_source"))
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg DROP COLUMN source_terms_hash"))
    op.get_bind().execute(sa.text("ALTER TABLE tb_sub_leg DROP COLUMN source_contract_id"))
