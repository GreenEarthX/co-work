"""Trading book tenancy — assets name a project, contracts name the company that books them.

Revision ID: 064
Revises: 063

WHY (docs/COMMERCIAL_PLATFORM_GAP_REGISTER.md, G-05, 2026-10-23)
---------------------------------------------------------------
036 locked the eight tb_* tables to PLATFORM_ADMIN because `tb_asset` had no
path to a project, so there was no honest tenant policy to write. That also
meant no tenant could book anything: the trading book had a cashflow reader and
no way to put a contract in. Both tables were empty in both stores on
2026-10-23, so the columns below are NOT NULL with nothing to backfill.

WHAT
----
  tb_asset.project_id          NOT NULL. The GEX project the asset is. Read by any
                               company with access to the project; written only
                               by its owner.
  tb_contract.owner_company_id NOT NULL. The company whose book it is. NOT a
                               project: models.py deliberately keeps contracts
                               project-free (paper hedges, one contract allocated
                               to several projects), and that is kept. Written by
                               the owner company; also read by any company that
                               can see an asset the contract is linked to (a
                               lender sees the offtake behind the project it
                               finances).
  tb_contract_fixed_price / _index_linked
                               follow their parent row.
  tb_project_finance_link      read with the asset; written only by the asset's
                               project owner, and only for a contract in its own
                               book.
  tb_counterparty              a shared register of legal entities: read and
                               added by any signed-in company, changed by GEX.
  tb_index_definition / _history
                               reference data, like fuel_catalog: read by all,
                               written by GEX only.

Every policy carries WITH CHECK (the 062 lesson: a FOR ALL policy without one
makes the read rule the write rule).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "064"
down_revision: Union[str, None] = "063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
SIGNED_IN = f"(coalesce({ME}, '') NOT IN ('', 'GUEST', '__no_tenant_context__'))"
SEES_PROJECT = "app_company_can_see_capacity({col}, " + ME + ")"
OWNS_PROJECT = "app_company_owns_project({col}, " + ME + ")"

ASSET_SEEN = f"{ADMIN} OR {SEES_PROJECT.format(col='project_id')}"
ASSET_OWNED = f"{ADMIN} OR {OWNS_PROJECT.format(col='project_id')}"
# Contract and link policies would read each other's tables and recurse, so the
# cross-table lookups are SECURITY DEFINER functions (036's pattern), each
# checking visibility explicitly since they do not pass through RLS.
CONTRACT_SEEN = f"{ADMIN} OR owner_company_id = {ME} OR app_tb_contract_linked_visible(id, {ME})"
CONTRACT_OWNED = f"{ADMIN} OR owner_company_id = {ME}"
CHILD_SEEN = (f"{ADMIN} OR app_tb_contract_owner(id) = {ME} OR app_tb_contract_linked_visible(id, {ME})")
CHILD_OWNED = f"{ADMIN} OR app_tb_contract_owner(id) = {ME}"
LINK_SEEN = f"{ADMIN} OR app_tb_asset_visible(project_asset_id, {ME})"
LINK_OWNED = (f"{ADMIN} OR (app_tb_asset_owned(project_asset_id, {ME}) "
              f"AND app_tb_contract_owner(contract_id) = {ME})")

FUNCTIONS = {
    "app_tb_asset_visible(p_asset uuid, p_company text)": (
        "boolean", "SELECT coalesce((SELECT app_company_can_see_capacity(a.project_id, p_company) "
                   "FROM tb_asset a WHERE a.id = p_asset), false)"),
    "app_tb_asset_owned(p_asset uuid, p_company text)": (
        "boolean", "SELECT coalesce((SELECT app_company_owns_project(a.project_id, p_company) "
                   "FROM tb_asset a WHERE a.id = p_asset), false)"),
    "app_tb_contract_owner(p_contract uuid)": (
        "text", "SELECT c.owner_company_id FROM tb_contract c WHERE c.id = p_contract"),
    "app_tb_contract_linked_visible(p_contract uuid, p_company text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM tb_project_finance_link l JOIN tb_asset a "
                   "ON a.id = l.project_asset_id WHERE l.contract_id = p_contract "
                   "AND app_company_can_see_capacity(a.project_id, p_company))"),
}

TB_TABLES = (
    "tb_asset", "tb_counterparty", "tb_index_definition", "tb_index_history",
    "tb_contract", "tb_contract_fixed_price", "tb_contract_index_linked",
    "tb_project_finance_link",
)

# table -> (read rule, write rule). Writes get INSERT, UPDATE and DELETE policies.
POLICIES = {
    "tb_asset": (ASSET_SEEN, ASSET_OWNED),
    "tb_contract": (CONTRACT_SEEN, CONTRACT_OWNED),
    "tb_contract_fixed_price": (CHILD_SEEN.format(t="tb_contract_fixed_price"),
                                CHILD_OWNED.format(t="tb_contract_fixed_price")),
    "tb_contract_index_linked": (CHILD_SEEN.format(t="tb_contract_index_linked"),
                                 CHILD_OWNED.format(t="tb_contract_index_linked")),
    "tb_project_finance_link": (LINK_SEEN, LINK_OWNED),
    "tb_counterparty": (SIGNED_IN, ADMIN),
    "tb_index_definition": ("true", ADMIN),
    "tb_index_history": ("true", ADMIN),
}


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("tb_asset", "tb_contract"):
        n = conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
        assert n == 0, f"{table} holds {n} rows; this migration adds a NOT NULL column with no backfill"

    # 036 builds tb_* from app/trading_book/models.py AS IT IS NOW, so on a fresh
    # rebuild these columns already exist (the models carry them). Add only what
    # is missing; the FK and indexes are 064's either way.
    def has(table, column):
        return conn.execute(sa.text("SELECT 1 FROM information_schema.columns WHERE table_name = :t "
                                    "AND column_name = :c"), {"t": table, "c": column}).first() is not None

    if not has("tb_asset", "project_id"):
        op.add_column("tb_asset", sa.Column("project_id", sa.Text(), nullable=False))
    if not has("tb_contract", "owner_company_id"):
        op.add_column("tb_contract", sa.Column("owner_company_id", sa.Text(), nullable=False))
    op.create_foreign_key("fk_tb_asset_project", "tb_asset", "projects", ["project_id"], ["project_id"])
    _q("CREATE INDEX IF NOT EXISTS ix_tb_asset_project ON tb_asset (project_id)")
    _q("CREATE INDEX IF NOT EXISTS ix_tb_contract_owner ON tb_contract (owner_company_id)")

    for signature, (returns, body) in FUNCTIONS.items():
        _q(f"CREATE FUNCTION {signature} RETURNS {returns} LANGUAGE sql STABLE SECURITY DEFINER "
           f"SET search_path = public, pg_temp AS $$ {body} $$")
        _q(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        _q(f"GRANT EXECUTE ON FUNCTION {signature} TO gex_app")

    for table in TB_TABLES:
        _q(f"DROP POLICY IF EXISTS {table}_admin_only ON {table}")
        read, write = POLICIES[table]
        _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
        _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({write})")
        _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({write}) WITH CHECK ({write})")
        _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({write})")
    # A counterparty is added by whoever books against it.
    _q(f"DROP POLICY tb_counterparty_insert ON tb_counterparty")
    _q(f"CREATE POLICY tb_counterparty_insert ON tb_counterparty FOR INSERT WITH CHECK ({SIGNED_IN})")

    forced = conn.execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(TB_TABLES)}).scalar()
    assert forced == len(TB_TABLES), f"only {forced} of {len(TB_TABLES)} tb_* tables are under FORCED RLS"
    n = conn.execute(sa.text("SELECT count(*) FROM pg_policies WHERE tablename = ANY(:t)"),
                     {"t": list(TB_TABLES)}).scalar()
    assert n == 4 * len(TB_TABLES), f"expected {4 * len(TB_TABLES)} tb_* policies, found {n}"


def downgrade() -> None:
    admin = ADMIN
    for table in TB_TABLES:
        for suffix in ("read", "insert", "update", "delete"):
            _q(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
        _q(f"CREATE POLICY {table}_admin_only ON {table} FOR ALL USING ({admin})")
    for signature in FUNCTIONS:
        _q(f"DROP FUNCTION IF EXISTS {signature}")
    op.drop_index("ix_tb_contract_owner", table_name="tb_contract")
    op.drop_column("tb_contract", "owner_company_id")
    op.drop_index("ix_tb_asset_project", table_name="tb_asset")
    op.drop_constraint("fk_tb_asset_project", "tb_asset", type_="foreignkey")
    op.drop_column("tb_asset", "project_id")
