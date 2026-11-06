"""One contract record, Phase 2 — the contract tokens (078) fold into the record.

Revision ID: 085
Revises: 084

WHY (docs/CONTRACT_RECORD_PHASE0.md; JML's prompt of 5 Nov, Phase 2)
-------------------------------------------------------------------
078 built a second contract store beside 065 because M2–M6 were not done.
This moves every project_contract / project_contract_event row into the one
record and makes the record the only place a project's contract terms are kept:

  tb_terms           `card` terms (Q3): card_projection holds the exact
                     {card.field: value}; settlement, commodity and currency are
                     required only for `complete` terms.
  tb_contract        confirming_company_id (the registered counterparty, 078's
                     counterparty_company_id); trade_status is required only for
                     kind `trade` — a project contract's state is its chain.
  tb_contract_version  legacy_terms_sha256: the 078 hash a confirmation names,
                     for every card version (folded or new).
  visibility         (Q5) a project-bound contract (kind <> 'trade', project_id
                     set) is read by the project's companies — 078's rule — as
                     well as its parties: app_tb_contract_project_visible and
                     app_tb_terms_project_visible, SECURITY DEFINER, pinned
                     search_path; app_tb_terms_readable extended the same way.
                     Writes stay on the operator connection (events and versions:
                     PLATFORM_ADMIN only, as 083), so a project party can no longer
                     insert a CONFIRMED row of its own (Phase 0 §7, finding 5).
  v_engine_contract_terms  the ONE view the gate engine reads: per project and
                     kind, the projection of the version named by the last
                     CONFIRMED event with no DISPUTED after it — exactly 078's
                     confirmed_terms(), which this replaces.
  the fold           app/trading_book/migrate/fold_contract_tokens.py: hashes,
                     order, actors and timestamps preserved; every chain and terms
                     hash re-verified before commit.
  078 tables         kept (dropped in Phase 3 once nothing reads them) but no
                     longer writable by the runtime: one record, nothing beside it.

On 2026-11-06 the fold moves 4 contracts and 4 events, all of the TEST
comprehension fixture.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "085"
down_revision: Union[str, None] = "084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"

FUNCTIONS = {
    "app_tb_contract_project_visible(p_contract uuid, p_company text)": (
        "SELECT EXISTS (SELECT 1 FROM tb_contract c WHERE c.id = p_contract AND c.contract_type = 'terms' "
        "AND c.kind <> 'trade' AND c.project_id IS NOT NULL AND app_company_can_see_capacity(c.project_id, p_company))"),
    "app_tb_terms_project_visible(p_terms uuid, p_company text)": (
        "SELECT EXISTS (SELECT 1 FROM tb_contract_version v WHERE v.terms_id = p_terms "
        "AND app_tb_contract_project_visible(v.contract_id, p_company))"),
}
READABLE_065 = ("SELECT EXISTS (SELECT 1 FROM tb_terms t WHERE t.id = p_terms AND "
                "(t.owner_company_id = p_company OR app_tb_terms_party(t.id, p_company)))")
READABLE_085 = ("SELECT EXISTS (SELECT 1 FROM tb_terms t WHERE t.id = p_terms AND "
                "(t.owner_company_id = p_company OR app_tb_terms_party(t.id, p_company) "
                "OR app_tb_terms_project_visible(t.id, p_company)))")
# table -> (read before 085, read from 085)
READS = {
    "tb_contract": (f"{ADMIN} OR owner_company_id = {ME} OR app_tb_contract_linked_visible(id, {ME}) "
                    f"OR app_tb_contract_party(id, {ME})",
                    f"{ADMIN} OR owner_company_id = {ME} OR app_tb_contract_linked_visible(id, {ME}) "
                    f"OR app_tb_contract_party(id, {ME}) OR app_tb_contract_project_visible(id, {ME})"),
    "tb_contract_version": (f"{ADMIN} OR app_tb_terms_party(terms_id, {ME})",
                            f"{ADMIN} OR app_tb_terms_party(terms_id, {ME}) "
                            f"OR app_tb_contract_project_visible(contract_id, {ME})"),
    "tb_terms": (f"{ADMIN} OR owner_company_id = {ME} OR app_tb_terms_party(id, {ME})",
                 f"{ADMIN} OR owner_company_id = {ME} OR app_tb_terms_party(id, {ME}) "
                 f"OR app_tb_terms_project_visible(id, {ME})"),
    "tb_contract_event": (f"{ADMIN} OR app_tb_contract_party(contract_id, {ME})",
                          f"{ADMIN} OR app_tb_contract_party(contract_id, {ME}) "
                          f"OR app_tb_contract_project_visible(contract_id, {ME})"),
}
ONE_MODEL_065 = """CHECK (
       (contract_type = 'terms' AND contract_ref IS NOT NULL AND trade_status IS NOT NULL)
    OR (contract_type <> 'terms' AND contract_number IS NOT NULL AND buy_side_id IS NOT NULL
        AND sell_side_id IS NOT NULL AND status IS NOT NULL AND owner_company_id IS NOT NULL))"""
ONE_MODEL_085 = """CHECK (
       (contract_type = 'terms' AND contract_ref IS NOT NULL AND (kind <> 'trade' OR trade_status IS NOT NULL))
    OR (contract_type <> 'terms' AND contract_number IS NOT NULL AND buy_side_id IS NOT NULL
        AND sell_side_id IS NOT NULL AND status IS NOT NULL AND owner_company_id IS NOT NULL))"""
VIEW = """CREATE VIEW v_engine_contract_terms WITH (security_invoker = true) AS
    WITH decisive AS (
        SELECT DISTINCT ON (e.contract_id) e.contract_id, e.event_type, e.version_id
        FROM tb_contract_event e
        WHERE e.event_type = 'DISPUTED' OR (e.event_type = 'CONFIRMED' AND e.version_id IS NOT NULL)
        ORDER BY e.contract_id, e.seq DESC)
    SELECT c.project_id, c.kind, c.id AS contract_id, v.version, v.legacy_terms_sha256,
           t.card_projection AS terms
    FROM decisive d
    JOIN tb_contract c ON c.id = d.contract_id
    JOIN tb_contract_version v ON v.id = d.version_id
    JOIN tb_terms t ON t.id = v.terms_id
    WHERE d.event_type = 'CONFIRMED' AND c.contract_type = 'terms' AND c.kind <> 'trade'
      AND c.project_id IS NOT NULL AND t.profile = 'card'"""


def _q(sql: str, params: dict | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def _read_policy(table: str, expr: str) -> None:
    _q(f"DROP POLICY IF EXISTS {table}_read ON {table}")
    _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({expr})")


def upgrade() -> None:
    conn = op.get_bind()
    # ── card terms ──────────────────────────────────────────────────────────
    for col in ("settlement", "commodity_id", "currency"):
        _q(f"ALTER TABLE tb_terms ALTER COLUMN {col} DROP NOT NULL")
    _q("ALTER TABLE tb_terms ADD COLUMN card_projection jsonb")
    _q("ALTER TABLE tb_terms ADD CONSTRAINT ck_tb_terms_profile CHECK ("
       "(profile = 'complete' AND settlement IS NOT NULL AND commodity_id IS NOT NULL AND currency IS NOT NULL) "
       "OR (profile = 'card' AND card_projection IS NOT NULL))")
    _q("ALTER TABLE tb_contract ADD COLUMN confirming_company_id text REFERENCES tenants(company_id)")
    _q("ALTER TABLE tb_contract DROP CONSTRAINT ck_tb_contract_one_model")
    _q(f"ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_one_model {ONE_MODEL_085}")
    _q("ALTER TABLE tb_contract_version ADD COLUMN legacy_terms_sha256 char(64)")

    # ── project-bound contracts are read by the project's companies (Q5) ────
    for signature, body in FUNCTIONS.items():
        _q(f"CREATE FUNCTION {signature} RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER "
           f"SET search_path = public, pg_temp AS $$ {body} $$")
        _q(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        _q(f"GRANT EXECUTE ON FUNCTION {signature} TO gex_app")
    _q(f"CREATE OR REPLACE FUNCTION app_tb_terms_readable(p_terms uuid, p_company text) RETURNS boolean "
       f"LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$ {READABLE_085} $$")
    for table, (_, after) in READS.items():
        _read_policy(table, after)

    # ── the one view the gate engine reads ──────────────────────────────────
    _q(VIEW)

    # ── the fold ────────────────────────────────────────────────────────────
    from app.trading_book.migrate.fold_contract_tokens import SAConnection, fold

    before = conn.execute(sa.text("SELECT count(*) FROM project_contract")).scalar()
    events_before = conn.execute(sa.text("SELECT count(*) FROM project_contract_event")).scalar()
    report = fold(SAConnection(conn))
    assert len(report["folded"]) == before, report
    folded_events = conn.execute(sa.text(
        "SELECT count(*) FROM tb_contract_event WHERE hash_scheme = '078'")).scalar()
    assert folded_events == events_before, f"{folded_events} of {events_before} 078 events folded"

    # ── one record, nothing beside it ───────────────────────────────────────
    _q("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON project_contract, project_contract_event FROM gex_app")


def downgrade() -> None:
    conn = op.get_bind()
    later = conn.execute(sa.text(
        "SELECT count(*) FROM tb_contract c WHERE c.contract_type = 'terms' AND c.kind <> 'trade' AND ("
        "c.origin_ref NOT IN (SELECT 'project:' || project_id || ':' || kind FROM project_contract) "
        "OR EXISTS (SELECT 1 FROM tb_contract_event e WHERE e.contract_id = c.id AND e.hash_scheme = '2'))")).scalar()
    assert later == 0, (f"{later} project contracts have events written after the fold; 078 cannot hold them. "
                        "Refusing to downgrade and lose them.")
    _q("GRANT INSERT, UPDATE, DELETE ON project_contract TO gex_app")
    _q("GRANT INSERT ON project_contract_event TO gex_app")
    # The folded rows are frozen and append-only by trigger; as the owner, skip the triggers
    # for this one transaction to remove exactly what the fold wrote.
    _q("SET LOCAL session_replication_role = replica")
    folded = "SELECT id FROM tb_contract WHERE contract_type = 'terms' AND kind <> 'trade'"
    terms = f"SELECT terms_id FROM tb_contract_version WHERE contract_id IN ({folded})"
    _q(f"DELETE FROM tb_contract_event WHERE contract_id IN ({folded})")
    _q(f"CREATE TEMP TABLE _fold_terms ON COMMIT DROP AS {terms}")
    _q(f"DELETE FROM tb_contract_version WHERE contract_id IN ({folded})")
    _q("DELETE FROM tb_flow WHERE leg_id IN (SELECT id FROM tb_leg WHERE terms_id IN (SELECT terms_id FROM _fold_terms))")
    for table in ("tb_leg", "tb_clause", "tb_sub_leg"):
        _q(f"DELETE FROM {table} WHERE terms_id IN (SELECT terms_id FROM _fold_terms)")
    _q("DELETE FROM tb_terms WHERE id IN (SELECT terms_id FROM _fold_terms)")
    _q(f"DELETE FROM tb_contract WHERE id IN ({folded})")
    _q("SET LOCAL session_replication_role = origin")
    _q("DROP VIEW IF EXISTS v_engine_contract_terms")
    for table, (before, _) in READS.items():
        _read_policy(table, before)
    _q(f"CREATE OR REPLACE FUNCTION app_tb_terms_readable(p_terms uuid, p_company text) RETURNS boolean "
       f"LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$ {READABLE_065} $$")
    for signature in reversed(list(FUNCTIONS)):
        _q(f"DROP FUNCTION IF EXISTS {signature}")
    _q("ALTER TABLE tb_contract_version DROP COLUMN IF EXISTS legacy_terms_sha256")
    _q("ALTER TABLE tb_contract DROP CONSTRAINT ck_tb_contract_one_model")
    _q(f"ALTER TABLE tb_contract ADD CONSTRAINT ck_tb_contract_one_model {ONE_MODEL_065}")
    _q("ALTER TABLE tb_contract DROP COLUMN IF EXISTS confirming_company_id")
    _q("ALTER TABLE tb_terms DROP CONSTRAINT IF EXISTS ck_tb_terms_profile")
    _q("ALTER TABLE tb_terms DROP COLUMN IF EXISTS card_projection")
    for col in ("settlement", "commodity_id", "currency"):
        _q(f"ALTER TABLE tb_terms ALTER COLUMN {col} SET NOT NULL")
