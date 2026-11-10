"""M6, drop 2 of 4: `contracts` (063) goes (Phase 3 of "One contract record").

Revision ID: 089
Revises: 088

063 made `contracts` the market's contract table. Since Phase 1 (084, 2026-11-06)
an agreed match writes its contract in the one record (trading_book/record.py,
065/083) in the same transaction, and nothing has written `contracts` since: on
2026-11-10 it holds 0 rows and no foreign key, view or function refers to it.

Refuses to run while it holds a row. The downgrade rebuilds it, empty, exactly
as 063 left it (columns, indexes, its one policy, FORCED RLS, the grant), from
pg_dump -s of the database at 088.

Not this table: app/api/endpoints/finance.py reads a SQLite demo table also
called `contracts` (other columns), a separate store this migration does not touch.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "089"
down_revision: Union[str, None] = "088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# pg_dump -s -t contracts at 088 (comments, SET lines and "public." removed).
CONTRACTS_DDL = """
CREATE TABLE contracts (
    id text NOT NULL,
    project_id text NOT NULL,
    match_id text,
    offer_id text,
    rfq_id text,
    token_id text,
    seller_company_id text,
    buyer_company_id text,
    contract_id_external text,
    counterparty text,
    molecule text,
    volume_mtpd double precision,
    price_eur_kg double precision,
    pricing_basis text,
    delivery_terms text,
    payment_terms text,
    start_date text,
    end_date text,
    tenor_years integer,
    credit_rating text,
    status text DEFAULT 'active'::text NOT NULL,
    correlation_id text,
    created_by text,
    created_at text NOT NULL,
    updated_at text
);
ALTER TABLE ONLY contracts FORCE ROW LEVEL SECURITY;
ALTER TABLE ONLY contracts
    ADD CONSTRAINT contracts_pkey PRIMARY KEY (id);
CREATE INDEX idx_contracts_buyer ON contracts USING btree (buyer_company_id);
CREATE UNIQUE INDEX idx_contracts_match ON contracts USING btree (match_id);
CREATE INDEX idx_contracts_project ON contracts USING btree (project_id);
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
CREATE POLICY contracts_parties ON contracts USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_can_see_capacity(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)))) WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_can_see_capacity(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true))));
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE contracts TO gex_app;
"""


def upgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT count(*) FROM contracts")).scalar()
    assert n == 0, f"contracts holds {n} rows; carry them into the record first"
    conn.execute(sa.text("DROP TABLE contracts"))
    assert conn.execute(sa.text("SELECT to_regclass('public.contracts')")).scalar() is None


def downgrade() -> None:
    op.get_bind().exec_driver_sql(CONTRACTS_DDL)
