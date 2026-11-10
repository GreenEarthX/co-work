"""M6, drop 1 of 4: the JTI contract model goes (Phase 3 of "One contract record").

Revision ID: 088
Revises: 087

A contract is the one record (065/083/085): terms -> legs -> flows, versions and
events, written by trading_book/record.py. The B1 joined-table model it replaces
— tb_contract_fixed_price, tb_contract_index_linked and the JTI columns of
tb_contract — has had no writer since the booking routes were removed (Phase 3)
and holds nothing: on 2026-11-10, 0 rows in either subtype table and 0
tb_contract rows other than contract_type 'terms'. The cashflow engine reads the
record's flows (M4, trading_book/flows.py), proven line by line against the old
engine (T10), which stays in code as the frozen reference over in-memory objects.

  dropped  tb_contract_fixed_price, tb_contract_index_linked; on tb_contract
           contract_number, buy_side_id, sell_side_id, fuel_type,
           effective_date, termination_date, notional_quantity, quantity_unit,
           currency, status; the type contract_status_enum
  kept     trade_date, owner_company_id (a folded 078 card's project owner) and
           contract_type, which is now 'terms' and nothing else
  changed  ck_tb_contract_one_model is terms-only. The link table's write
           policies (064) allowed only tb_contract.owner_company_id, which a
           contract written by an agreed match or an accepted order does not
           carry; they now also admit a party to the contract — the seller
           allocates its revenue, the buyer its cost.

Refuses to run while any JTI row exists. The downgrade rebuilds the tables, the
columns, their constraints, indexes, policies and grants as 087 left them
(empty: there was nothing to keep).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "088"
down_revision: Union[str, None] = "087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CO = "current_setting('app.current_company_id', true)"
ADMIN = f"{CO} = 'PLATFORM_ADMIN'"
LEGACY_COLUMNS = ("contract_number", "buy_side_id", "sell_side_id", "fuel_type", "effective_date",
                  "termination_date", "notional_quantity", "quantity_unit", "currency", "status")
STATUS = ("draft", "proposed", "committed", "terminated", "expired")


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def _one(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar()


def _link_policies(write_rule: str) -> None:
    for cmd in ("insert", "update", "delete"):
        _q(f"DROP POLICY IF EXISTS tb_project_finance_link_{cmd} ON tb_project_finance_link")
    _q(f"CREATE POLICY tb_project_finance_link_insert ON tb_project_finance_link FOR INSERT "
       f"WITH CHECK ({write_rule})")
    _q(f"CREATE POLICY tb_project_finance_link_update ON tb_project_finance_link FOR UPDATE "
       f"USING ({write_rule}) WITH CHECK ({write_rule})")
    _q(f"CREATE POLICY tb_project_finance_link_delete ON tb_project_finance_link FOR DELETE USING ({write_rule})")


OLD_LINK_RULE = (f"({ADMIN}) OR (app_tb_asset_owned(project_asset_id, {CO}) "
                 f"AND app_tb_contract_owner(contract_id) = {CO})")
NEW_LINK_RULE = (f"({ADMIN}) OR (app_tb_asset_owned(project_asset_id, {CO}) "
                 f"AND (app_tb_contract_owner(contract_id) = {CO} OR app_tb_contract_party(contract_id, {CO})))")


def upgrade() -> None:
    for table in ("tb_contract_fixed_price", "tb_contract_index_linked"):
        n = _one(f"SELECT count(*) FROM {table}")
        assert n == 0, f"{table} holds {n} rows; convert them to the record first"
    n = _one("SELECT count(*) FROM tb_contract WHERE contract_type <> 'terms'")
    assert n == 0, f"tb_contract holds {n} JTI rows; convert them to the record first"

    _q("DROP TABLE tb_contract_fixed_price")
    _q("DROP TABLE tb_contract_index_linked")
    _q("ALTER TABLE tb_contract DROP CONSTRAINT ck_tb_contract_one_model")
    for col in LEGACY_COLUMNS:
        _q(f"ALTER TABLE tb_contract DROP COLUMN {col}")          # their indexes and FKs go with them
    _q("DROP TYPE contract_status_enum")
    _q("ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_one_model CHECK (contract_type = 'terms' "
       "AND contract_ref IS NOT NULL AND (kind <> 'trade' OR trade_status IS NOT NULL))")
    _link_policies(NEW_LINK_RULE)

    left = _one("SELECT count(*) FROM information_schema.columns WHERE table_name = 'tb_contract' "
                f"AND column_name IN ({', '.join(repr(c) for c in LEGACY_COLUMNS)})")
    assert left == 0, "a JTI column survived on tb_contract"
    assert _one("SELECT count(*) FROM pg_class WHERE relname IN "
                "('tb_contract_fixed_price', 'tb_contract_index_linked')") == 0


def _subtype_policies(table: str) -> None:
    owner = f"app_tb_contract_owner(id) = {CO}"
    _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (({ADMIN}) OR ({owner}) "
       f"OR app_tb_contract_linked_visible(id, {CO}))")
    _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK (({ADMIN}) OR ({owner}))")
    _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING (({ADMIN}) OR ({owner})) "
       f"WITH CHECK (({ADMIN}) OR ({owner}))")
    _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING (({ADMIN}) OR ({owner}))")
    _q(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app")
    _q(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gex_admin') THEN "
       f"GRANT ALL ON {table} TO gex_admin; END IF; END $$")


def downgrade() -> None:
    _link_policies(OLD_LINK_RULE)
    _q("ALTER TABLE tb_contract DROP CONSTRAINT ck_tb_contract_one_model")
    _q(f"CREATE TYPE contract_status_enum AS ENUM ({', '.join(repr(s.upper()) for s in STATUS)})")
    for col, kind in (("contract_number", "varchar(50)"), ("buy_side_id", "uuid REFERENCES tb_counterparty(id)"),
                      ("sell_side_id", "uuid REFERENCES tb_counterparty(id)"), ("fuel_type", "varchar(50)"),
                      ("effective_date", "date"), ("termination_date", "date"),
                      ("notional_quantity", "numeric(18,6)"), ("quantity_unit", "varchar(10)"),
                      ("currency", "varchar(3)"), ("status", "contract_status_enum")):
        _q(f"ALTER TABLE tb_contract ADD COLUMN {col} {kind}")
    _q("ALTER TABLE tb_contract ADD CONSTRAINT tb_contract_contract_number_key UNIQUE (contract_number)")
    for name, col in (("ix_contract_buy_side", "buy_side_id"), ("ix_contract_sell_side", "sell_side_id"),
                      ("ix_contract_status", "status"), ("ix_contract_termination", "termination_date")):
        _q(f"CREATE INDEX {name} ON tb_contract ({col})")
    _q("ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_one_model CHECK ((contract_type = 'terms' "
       "AND contract_ref IS NOT NULL AND (kind <> 'trade' OR trade_status IS NOT NULL)) OR (contract_type <> 'terms' "
       "AND contract_number IS NOT NULL AND buy_side_id IS NOT NULL AND sell_side_id IS NOT NULL "
       "AND status IS NOT NULL AND owner_company_id IS NOT NULL))")
    _q("CREATE TABLE tb_contract_fixed_price (id uuid NOT NULL PRIMARY KEY REFERENCES tb_contract(id) "
       "ON DELETE CASCADE, fixed_price numeric(18,6) NOT NULL, price_basis varchar(50) NOT NULL)")
    _q("CREATE TABLE tb_contract_index_linked (id uuid NOT NULL PRIMARY KEY REFERENCES tb_contract(id) "
       "ON DELETE CASCADE, index_definition_id uuid NOT NULL REFERENCES tb_index_definition(id), "
       "spread numeric(18,6) NOT NULL, floor numeric(18,6), cap numeric(18,6), fixing_rule varchar(50) NOT NULL)")
    for table in ("tb_contract_fixed_price", "tb_contract_index_linked"):
        _subtype_policies(table)
