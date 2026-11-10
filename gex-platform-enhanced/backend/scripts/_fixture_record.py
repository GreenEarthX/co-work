"""
A TEST fixture's contract record: written through the card-save path, removed with it.

Since Phase 3 of "One contract record" (Q9, alembic 093) a project's commitment
cards ARE its contract record: a fixture writes them with
core/contract_tokens.record_versions, the path a card save takes, and its
--remove deletes the project's record contracts. Record rows are append-only and
frozen by trigger, so the removal runs with triggers skipped for its own
transaction only, as gex_user, scoped to the one project.
"""
from __future__ import annotations

_RECORD = "SELECT id FROM tb_contract WHERE project_id = %s AND contract_type = 'terms'"
_TERMS = f"SELECT terms_id FROM tb_contract_version WHERE contract_id IN ({_RECORD})"


def count(cur, project_id: str) -> int:
    cur.execute("SELECT count(*) FROM tb_contract WHERE project_id = %s AND contract_type = 'terms'", (project_id,))
    return cur.fetchone()[0]


def remove(cur, project_id: str, execute: bool) -> int:
    n = count(cur, project_id)
    if not n:
        return 0
    print(f"  {'delete' if execute else 'would delete'} {n} record contract(s)")
    if not execute:
        return n
    cur.execute("SET LOCAL session_replication_role = replica")
    cur.execute(f"CREATE TEMP TABLE _fixture_terms ON COMMIT DROP AS {_TERMS}", (project_id,))
    cur.execute(f"DELETE FROM tb_contract_event WHERE contract_id IN ({_RECORD})", (project_id,))
    for child in ("tb_flow WHERE leg_id IN (SELECT id FROM tb_leg WHERE terms_id IN "
                  "(SELECT terms_id FROM _fixture_terms))",
                  "tb_leg WHERE terms_id IN (SELECT terms_id FROM _fixture_terms)",
                  "tb_clause WHERE terms_id IN (SELECT terms_id FROM _fixture_terms)",
                  "tb_sub_leg WHERE terms_id IN (SELECT terms_id FROM _fixture_terms)"):
        cur.execute(f"DELETE FROM {child}")
    cur.execute(f"DELETE FROM tb_contract_version WHERE contract_id IN ({_RECORD})", (project_id,))
    cur.execute("DELETE FROM tb_terms WHERE id IN (SELECT terms_id FROM _fixture_terms)")
    cur.execute("DELETE FROM tb_contract WHERE project_id = %s AND contract_type = 'terms'", (project_id,))
    cur.execute("DROP TABLE _fixture_terms")
    cur.execute("SET LOCAL session_replication_role = origin")
    return n


def write_cards(project_id: str, cards: dict, marker: str, owner: str) -> list[str]:
    """The cards' versions, written once for all cards as the loaders always did."""
    from app.core import contract_tokens as ct
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(owner)
    try:
        return ct.record_versions(project_id, {k: v for k, v in cards.items() if v}, marker, owner)
    finally:
        reset_current_company(t)
