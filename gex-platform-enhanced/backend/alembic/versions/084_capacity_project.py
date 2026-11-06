"""A capacity names its project — the supply-side fix (Phase 0 §5).

Revision ID: 084
Revises: 083

WHY
---
036 used `capacities.id` as the project id ("nothing in the schema says so"),
and every market policy resolved tenancy through that assumption:
app_company_can_see_capacity(id) read the capacity id as a project id. But
POST /capacities mints a random uuid, and 036's policy is FOR ALL USING (…)
with no WITH CHECK, so the USING clause doubled as the INSERT check: every
capacity a producer created as gex_app was refused by RLS. The market refused
every producer offer. (The five live rows were seeded with project ids.)

WHAT
----
* capacities.project_id — NOT NULL, FK projects. Backfilled with `id` where the
  id is a project id; any other row stops the migration and is listed, never
  guessed (M5's rule). On 2026-11-06 all five rows are project ids.
* app_company_can_see_capacity is NOT changed. Despite its name it is the
  generic "this company may see this PROJECT" helper: 063, 064, 066, 068 and
  069 call it with a project id (contracts, tb_asset, project_profile,
  project_dataset, project_sales_detail, …). Two new SECURITY DEFINER
  functions (pinned search_path) resolve a CAPACITY through its project_id:
    app_company_sees_capacity(capacity, company)   the project's companies
    app_company_owns_capacity(capacity, company)   the project's owner
* The four policies are split into read and write, WITH CHECK on every write:
    capacities  read: the project's companies     write: its owner
    tokens      read: + the holder                write: owner or holder (the holder retires)
    offers      read: the token's project's companies   write: its owner
    matches     read: the project's companies, the buyer, and (as 063) via its offer's
                token   write: the same (the market
                engine writes as PLATFORM_ADMIN after authorising the Party)
* capacities.correlation_id — POST /capacities always wrote it; the column was
  missing in PostgreSQL, so the insert failed even before RLS.
* matches.project_id held the capacity id (market_engine copied it); it now
  holds the project id. 0 rows on 2026-11-06; the UPDATE is for completeness.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "084"
down_revision: Union[str, None] = "083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
ON_PROJECT = "(app_company_owns_project({p}, {me}) OR app_company_has_project_access({p}, {me}))"


def _q(sql: str, params: dict | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def _function(name: str, body: str) -> None:
    _q(f"""CREATE OR REPLACE FUNCTION {name}(p_capacity_id text, p_company_id text) RETURNS boolean
           LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$ {body} $$""")
    _q(f"REVOKE ALL ON FUNCTION {name}(text, text) FROM PUBLIC")
    _q(f"GRANT EXECUTE ON FUNCTION {name}(text, text) TO gex_app")


def _policies(table: str, read: str, write: str) -> None:
    for name in (f"{table}_tenant_isolation", f"{table}_parties", f"{table}_seller_or_holder"):
        _q(f"DROP POLICY IF EXISTS {name} ON {table}")
    _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({ADMIN} OR {read})")
    _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({ADMIN} OR {write})")
    _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({ADMIN} OR {write}) "
       f"WITH CHECK ({ADMIN} OR {write})")
    _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({ADMIN} OR {write})")


def upgrade() -> None:
    conn = op.get_bind()
    _q("ALTER TABLE capacities ADD COLUMN project_id text REFERENCES projects(project_id)")
    _q("UPDATE capacities SET project_id = id WHERE id IN (SELECT project_id FROM projects)")
    orphans = list(conn.execute(sa.text("SELECT id FROM capacities WHERE project_id IS NULL")).scalars())
    assert not orphans, f"capacities with no determinable project (not guessed): {orphans}"
    _q("ALTER TABLE capacities ALTER COLUMN project_id SET NOT NULL")
    _q("CREATE INDEX ix_capacities_project ON capacities (project_id)")
    # POST /capacities has always written a correlation_id (the chain-of-custody id a
    # token inherits), but the column was never in PostgreSQL: the insert could not succeed.
    _q("ALTER TABLE capacities ADD COLUMN IF NOT EXISTS correlation_id text")
    _q("UPDATE matches m SET project_id = c.project_id FROM capacities c WHERE m.project_id = c.id")

    _function("app_company_sees_capacity",
              "SELECT EXISTS (SELECT 1 FROM capacities c WHERE c.id = p_capacity_id "
              "AND app_company_can_see_capacity(c.project_id, p_company_id))")
    _function("app_company_owns_capacity",
              "SELECT EXISTS (SELECT 1 FROM capacities c WHERE c.id = p_capacity_id "
              "AND app_company_owns_project(c.project_id, p_company_id))")

    on_project = ON_PROJECT.format(p="project_id", me=ME)
    _policies("capacities", on_project, f"app_company_owns_project(project_id, {ME})")
    _policies("tokens",
              f"(app_company_sees_capacity(capacity_id, {ME}) OR holder_company_id = {ME})",
              f"(app_company_owns_capacity(capacity_id, {ME}) OR holder_company_id = {ME})")
    _policies("offers",
              f"EXISTS (SELECT 1 FROM tokens t WHERE t.id = offers.token_id "
              f"AND app_company_sees_capacity(t.capacity_id, {ME}))",
              f"EXISTS (SELECT 1 FROM tokens t WHERE t.id = offers.token_id "
              f"AND app_company_owns_capacity(t.capacity_id, {ME}))")
    # 063 also reached a match through its offer's token; kept, so a match is never
    # narrower than before (its project_id may be unset on a hand-made row).
    party = (f"({on_project} OR buyer_company_id = {ME} OR EXISTS (SELECT 1 FROM offers o "
             f"JOIN tokens t ON t.id = o.token_id WHERE o.id = matches.offer_id "
             f"AND app_company_sees_capacity(t.capacity_id, {ME})))")
    _policies("matches", party, party)

    forced = conn.execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname IN ('capacities','tokens','offers','matches') "
        "AND relrowsecurity AND relforcerowsecurity")).scalar()
    assert forced == 4, f"only {forced} of the four market tables under FORCED RLS"
    unchecked = conn.execute(sa.text(
        "SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
        "WHERE c.relname IN ('capacities','tokens','offers','matches') "
        "AND p.polcmd IN ('a', 'w') AND p.polwithcheck IS NULL")).scalar()
    assert unchecked == 0, f"{unchecked} write policies without WITH CHECK"


def downgrade() -> None:
    for table in ("capacities", "tokens", "offers", "matches"):
        for suffix in ("read", "insert", "update", "delete"):
            _q(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
    _q("UPDATE matches m SET project_id = c.id FROM capacities c WHERE m.project_id = c.project_id")
    _q(f"CREATE POLICY capacities_tenant_isolation ON capacities FOR ALL USING "
       f"({ADMIN} OR app_company_can_see_capacity(id, {ME}))")
    _q(f"CREATE POLICY tokens_seller_or_holder ON tokens FOR ALL USING "
       f"({ADMIN} OR app_company_can_see_capacity(capacity_id, {ME}) OR holder_company_id = {ME}) "
       f"WITH CHECK ({ADMIN} OR app_company_can_see_capacity(capacity_id, {ME}) OR holder_company_id = {ME})")
    _q(f"CREATE POLICY offers_tenant_isolation ON offers FOR ALL USING ({ADMIN} OR EXISTS (SELECT 1 FROM tokens t "
       f"WHERE t.id = offers.token_id AND app_company_can_see_capacity(t.capacity_id, {ME})))")
    m = (f"({ADMIN} OR app_company_can_see_capacity(project_id, {ME}) OR buyer_company_id = {ME} OR EXISTS "
         f"(SELECT 1 FROM offers o JOIN tokens t ON t.id = o.token_id WHERE o.id = matches.offer_id "
         f"AND app_company_can_see_capacity(t.capacity_id, {ME})))")
    _q(f"CREATE POLICY matches_parties ON matches FOR ALL USING {m} WITH CHECK {m}")
    _q("DROP FUNCTION IF EXISTS app_company_owns_capacity(text, text)")
    _q("DROP FUNCTION IF EXISTS app_company_sees_capacity(text, text)")
    _q("ALTER TABLE capacities DROP COLUMN IF EXISTS correlation_id")
    _q("DROP INDEX IF EXISTS ix_capacities_project")
    _q("ALTER TABLE capacities DROP COLUMN IF EXISTS project_id")
