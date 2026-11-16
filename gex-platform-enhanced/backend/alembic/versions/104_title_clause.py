"""Typed clauses — the `title` clause type (GreenMesh Phase 2 Step 3, amendment B1; sub-step 1).

Revision ID: 104
Revises: 103

Risk, title and payment are three records, each governed by a clause of the confirmed terms
(JML, 12 Nov 2026; ruling R1: the Incoterm governs risk only). The delivery and payment
clause types exist since 083; their typed fields (incoterm, named_place, shipment_point;
trigger, quantity_basis) live in `attrs` and are checked by validation rule V15
(trading_book/clauses.py). Title had no clause type at all, so 083's CHECK on
`tb_clause.clause_type` refuses one. This widens it by exactly `title`.

Frozen terms are untouched: no existing row changes, and a clause is still added only to
unfrozen terms (083's triggers).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "104"
down_revision: Union[str, None] = "103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must equal trading_book/terms.py CLAUSE_TYPES (tests/test_contract_record.py reads the
# latest migration that defines it).
CLAUSE_TYPES = ("delivery", "payment", "parties", "commitment", "conditions_precedent", "damages",
                "force_majeure", "change_in_law", "credit", "performance", "price", "declaration",
                "title")
BEFORE = CLAUSE_TYPES[:-1]


def _check(types) -> str:
    return "CHECK (clause_type IN (" + ", ".join(f"'{t}'" for t in types) + "))"


def upgrade() -> None:
    conn = op.get_bind()
    have = conn.execute(sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                                "WHERE conname = 'tb_clause_clause_type_check'")).scalar()
    assert have and all(f"'{t}'" in have for t in BEFORE) and have.count("'") == 2 * len(BEFORE), have
    conn.execute(sa.text("ALTER TABLE tb_clause DROP CONSTRAINT tb_clause_clause_type_check"))
    conn.execute(sa.text(f"ALTER TABLE tb_clause ADD CONSTRAINT tb_clause_clause_type_check {_check(CLAUSE_TYPES)}"))


def downgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT count(*) FROM tb_clause WHERE clause_type = 'title'")).scalar()
    assert n == 0, f"{n} title clause(s) exist; refusing to narrow the clause types"
    conn.execute(sa.text("ALTER TABLE tb_clause DROP CONSTRAINT tb_clause_clause_type_check"))
    conn.execute(sa.text(f"ALTER TABLE tb_clause ADD CONSTRAINT tb_clause_clause_type_check {_check(BEFORE)}"))
