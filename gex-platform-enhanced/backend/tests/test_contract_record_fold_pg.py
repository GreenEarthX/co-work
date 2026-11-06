"""
Phase 2 of "One contract record" — the contract tokens (078) fold into the record (alembic 085).

In the throwaway database (conftest.pg_store), 078 rows are written the way 078
wrote them — hash-chained by 078's own formula — and then folded. Asserted:
every event arrives verbatim (seq, type, actor, company, note, timestamp,
prev_hash, event_hash) and every chain still verifies; the engine's view answers
exactly what 078's confirmed_terms() answered; the fold is idempotent; the next
event continues the same chain under scheme 2; a rewrite of a folded event or of
folded terms is detected; the runtime role cannot write a contract event of its
own, nor touch the 078 tables any more; the view follows the project's companies.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from pg_support import connect_dsn

OWNER, CP, OUTSIDER = "test_fold_owner", "test_fold_buyer", "test_fold_outsider"
PID = "proj_TEST_fold"
T0 = datetime(2026, 10, 28, 17, 0, tzinfo=timezone.utc)
TERMS_A = {"offtake.contracted_tonnes_per_year": 40000.0, "offtake.tenor_years": 15.0}
TERMS_B = {"offtake.contracted_tonnes_per_year": 45000.0, "offtake.tenor_years": 15.0}
TERMS_E = {"epc.contracting_model": "LSTK"}


def _owner_dsn(pg_store):
    return os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1]


def _sha(terms):
    return hashlib.sha256(json.dumps(terms, sort_keys=True, default=str).encode()).hexdigest()


def _write_078(cur, kind, steps, counterparty=None):
    """078's own write path, replayed: one project_contract and its hash-chained events."""
    cur.execute("INSERT INTO project_contract (project_id, kind, counterparty_company_id, created_at) "
                "VALUES (%s, %s, %s, %s) RETURNING id", (PID, kind, counterparty, T0))
    cid = cur.fetchone()["id"]
    prev = None
    for seq, (event_type, terms, actor, company, note) in enumerate(steps, start=1):
        sha = _sha(terms) if terms is not None else None
        if event_type == "CONFIRMED":
            sha = note.pop("sha")
            note = None
        body = json.dumps({"contract": cid, "seq": seq, "type": event_type, "terms_sha256": sha, "actor": actor,
                           "company": company, "note": note, "prev": prev}, sort_keys=True)
        digest = hashlib.sha256(body.encode()).hexdigest()
        cur.execute("INSERT INTO project_contract_event (contract_id, project_id, seq, event_type, terms_json, "
                    "terms_sha256, actor, company_id, note, prev_hash, event_hash, at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (cid, PID, seq, event_type, json.dumps(terms) if terms is not None else None, sha, actor,
                     company, note, prev, digest, T0 + timedelta(minutes=seq)))
        prev = digest
    return cid


def _confirmed_078(cur) -> dict:
    """078's confirmed_terms(), verbatim, over the 078 tables."""
    out = {}
    cur.execute("SELECT * FROM project_contract WHERE project_id = %s", (PID,))
    for c in cur.fetchall():
        cur.execute("SELECT * FROM project_contract_event WHERE contract_id = %s ORDER BY seq", (c["id"],))
        evs = cur.fetchall()
        versions = {e["terms_sha256"]: e["terms_json"] for e in evs if e["event_type"] == "VERSION"}
        current = None
        for e in evs:
            if e["event_type"] == "CONFIRMED" and e["terms_sha256"] in versions:
                current = versions[e["terms_sha256"]]
            elif e["event_type"] == "DISPUTED":
                current = None
        if current is not None:
            out[c["kind"]] = current
    return out


@pytest.fixture(scope="module")
def folded(pg_store):
    from app.db import session

    saved = session._sync_engine            # projects_store's cached engine: never leak the throwaway one
    session._sync_engine = None
    yield from _folded(pg_store)
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _folded(pg_store):
    from sqlalchemy import create_engine

    from app.trading_book.migrate.fold_contract_tokens import SAConnection, fold

    conn = connect_dsn(_owner_dsn(pg_store))
    cur = conn.cursor()
    for company in (OWNER, CP, OUTSIDER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST fold plant', %s, 'H2')", (PID, OWNER))
    cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (PID, CP))
    # offtake: v1, counterparty set (and its DISPUTED), v1 confirmed, then an unconfirmed v2:
    # 078 keeps v1's terms in force. epc: v1 confirmed, then disputed: nothing in force.
    _write_078(cur, "offtake", [
        ("VERSION", TERMS_A, "u_fold_exec", OWNER, None),
        ("COUNTERPARTY_SET", None, "u_fold_exec", OWNER, f"counterparty {CP}"),
        ("DISPUTED", None, "u_fold_exec", OWNER, "counterparty changed"),
        ("CONFIRMED", None, "u_fold_buyer", CP, {"sha": _sha(TERMS_A)}),
        ("VERSION", TERMS_B, "u_fold_exec", OWNER, None)], counterparty=CP)
    _write_078(cur, "epc", [
        ("VERSION", TERMS_E, "u_fold_exec", OWNER, None),
        ("CONFIRMED", None, "u_fold_buyer", CP, {"sha": _sha(TERMS_E)}),
        ("DISPUTED", None, "u_fold_buyer", CP, "the price is not the contract's")])
    conn.commit()
    expected = _confirmed_078(cur)
    cur.execute("SELECT * FROM project_contract_event WHERE project_id = %s ORDER BY contract_id, seq", (PID,))
    legacy = cur.fetchall()
    conn.close()
    engine = create_engine(_owner_dsn(pg_store))
    with engine.begin() as sa_conn:
        first = fold(SAConnection(sa_conn))
    with engine.begin() as sa_conn:
        second = fold(SAConnection(sa_conn))
    engine.dispose()
    yield {"expected": expected, "legacy": legacy, "first": first, "second": second, "dsn": pg_store}


def _as(company, fn):
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company(company)
    try:
        return fn()
    finally:
        reset_current_company(token)


def test_every_078_event_arrives_verbatim_and_the_fold_is_idempotent(folded):
    from app.core import contract_tokens as ct

    assert sorted(folded["first"]["folded"]) == [f"project:{PID}:epc", f"project:{PID}:offtake"]
    assert folded["second"]["folded"] == [] and len(folded["second"]["already_folded"]) >= 2
    by_contract = {}
    for e in folded["legacy"]:
        by_contract.setdefault(e["contract_id"], []).append(e)
    for kind in ("offtake", "epc"):
        c = ct.contract(PID, kind, create=False)
        got = ct.events(c["id"])
        legacy = next(evs for evs in by_contract.values() if evs[0]["event_hash"] == got[0]["event_hash"])
        assert [(e["seq"], e["event_type"], e["actor"], e["company_id"], e["note"], e["prev_hash"], e["event_hash"],
                 e["terms_sha256"]) for e in got] == \
               [(e["seq"], e["event_type"], e["actor"], e["company_id"], e["note"], e["prev_hash"], e["event_hash"],
                 e["terms_sha256"]) for e in legacy], kind
        assert [str(e["at"]) for e in got] == [str(e["at"]) for e in legacy]
        assert {e["hash_scheme"] for e in got} == {"078"}
        assert ct.chain_intact(c["id"])


def test_the_engine_view_answers_exactly_what_078_answered(folded):
    from app.core import contract_tokens as ct

    assert folded["expected"] == {"offtake": TERMS_A}             # v1 confirmed; v2 not; epc disputed
    assert ct.confirmed_terms(PID) == folded["expected"]
    tok = ct.latest_version(ct.contract(PID, "offtake", create=False)["id"])
    assert tok["terms_sha256"] == _sha(TERMS_B) and tok["terms_json"] == TERMS_B


def test_the_next_event_continues_the_same_chain_under_scheme_2(folded):
    from app.core import contract_tokens as ct

    c = ct.contract(PID, "offtake", create=False)
    before = ct.events(c["id"])
    ct.append(c, "CONFIRMED", "u_fold_buyer", CP, sha=_sha(TERMS_B))
    after = ct.events(c["id"])
    assert after[-1]["hash_scheme"] == "2" and after[-1]["prev_hash"] == before[-1]["event_hash"]
    assert ct.chain_intact(c["id"])
    assert ct.confirmed_terms(PID) == {"offtake": TERMS_B}


def test_a_rewritten_folded_event_or_folded_terms_are_detected(folded):
    from app.core import contract_tokens as ct
    from app.core import market_engine as me
    from app.trading_book import record

    c = ct.contract(PID, "epc", create=False)
    conn = connect_dsn(_owner_dsn(folded["dsn"]))
    cur = conn.cursor()
    cur.execute("SET session_replication_role = replica")         # the owner, skipping the triggers
    cur.execute("UPDATE tb_contract_event SET note = 'rewritten' WHERE contract_id = %s AND seq = 3", (c["id"],))
    cur.execute("SELECT terms_id FROM tb_contract_version WHERE contract_id = %s", (c["id"],))
    terms_id = cur.fetchone()["terms_id"]
    cur.execute("UPDATE tb_terms SET card_projection = '{\"epc.contracting_model\": \"EPCM\"}' WHERE id = %s",
                (terms_id,))
    conn.commit()
    try:
        assert not ct.chain_intact(c["id"])
        mconn = me._conn()
        try:
            assert not record.stored_hashes_hold(mconn, str(terms_id))
        finally:
            mconn.close()
    finally:
        cur.execute("UPDATE tb_contract_event SET note = %s WHERE contract_id = %s AND seq = 3",
                    ("the price is not the contract's", c["id"]))
        cur.execute("UPDATE tb_terms SET card_projection = %s WHERE id = %s", (json.dumps(TERMS_E), terms_id))
        conn.commit()
        conn.close()
    assert ct.chain_intact(c["id"])


def test_a_project_party_cannot_write_a_contract_event_of_its_own_nor_the_078_tables(folded):
    """Phase 0 §7 finding 5: under 078 any project company could INSERT a CONFIRMED row."""
    from app.core import contract_tokens as ct

    c = ct.contract(PID, "offtake", create=False)
    conn = connect_dsn(folded["dsn"])
    cur = conn.cursor()
    for sql, params, refused in (
            ("INSERT INTO tb_contract_event (contract_id, seq, event_type, actor, company_id, at, prev_hash, "
             "event_hash, hash_scheme) VALUES (%s, 99, 'CONFIRMED', 'u_fold_buyer', %s, now(), repeat('a', 64), "
             "repeat('b', 64), '2')", (c["id"], CP), "row-level security"),
            ("INSERT INTO project_contract_event (contract_id, project_id, seq, event_type, actor, event_hash) "
             "SELECT id, project_id, 99, 'CONFIRMED', 'x', 'x' FROM project_contract LIMIT 1", (), "permission denied")):
        cur.execute("SET app.current_company_id = %s", (CP,))
        with pytest.raises(Exception, match=refused):
            cur.execute(sql, params)
        conn.rollback()
    conn.close()


def test_the_engine_view_follows_the_projects_companies(folded):
    conn = connect_dsn(folded["dsn"])
    cur = conn.cursor()
    seen = {}
    for company in (OWNER, CP, OUTSIDER, "__no_tenant_context__"):
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute("SELECT count(*) AS n FROM v_engine_contract_terms WHERE project_id = %s", (PID,))
        seen[company] = cur.fetchone()["n"]
    conn.close()
    assert seen == {OWNER: 1, CP: 1, OUTSIDER: 0, "__no_tenant_context__": 0}
