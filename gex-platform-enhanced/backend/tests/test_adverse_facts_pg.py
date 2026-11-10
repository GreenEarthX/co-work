"""
Adverse facts as events on the contract record (Phase 3 of "One contract record",
Phase 0 Q10, JML 2026-11-06).

Before: an adverse fact (contractor insolvent, PPA or support revoked, certification
suspended) was a field the owner set on a card. Now it is an ADVERSE_FACT_REPORTED
event on the contract it concerns — or on one buyer's sub-leg of the offtake frame,
so a buyer's insolvency drops only that buyer's volume. Reporting needs a document
and applies at once. Clearing needs a document and two parties of different
companies, neither the reporter's; the party a fact is about never clears it, and
GEX neither reports nor clears. A card that still says true keeps applying.

Pure tests need nothing; the rest run in the throwaway PostgreSQL database
(conftest.pg_store) with the engine faked.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import contract_tokens as ct
from pg_support import connect_dsn

OWNER, EPC, BANK, ADV, A, B = ("test_af_owner", "test_af_epc", "test_af_bank", "test_af_adv", "test_af_buyer_a",
                              "test_af_buyer_b")
PID = "proj_TEST_adverse_facts"
DOC, DOC2 = "d" * 64, "e" * 64
FRAME = {"offtake": {"certification_scheme": "RFNBO", "buyers": [
    {"company_id": A, "contracted_tonnes_per_year": 30000, "tenor_years": 15},
    {"company_id": B, "contracted_tonnes_per_year": 20000, "tenor_years": 12}]},
    "epc": {"contracting_model": "LSTK", "contract_price_eur": 100000000}}


# ── pure ─────────────────────────────────────────────────────────────────────

def _conf(company, cards=FRAME):
    shared, buyers = ct.frame_terms(cards)
    return {"buyer_company_id": company, "shared_terms": shared, "sub_leg_terms": dict(buyers)[company]}


def test_an_open_fact_applies_at_once_whatever_the_card_says():
    used, _ = ct.engine_terms({"epc": {"contracting_model": "LSTK"}}, {},
                              facts=[{"fact": "COUNTERPARTY_INSOLVENT", "subject_company_id": None}])
    assert used["epc"] == {"counterparty_insolvent": True}


def test_a_buyers_insolvency_drops_only_that_buyers_volume():
    confs = [_conf(A), _conf(B)]
    used, _ = ct.engine_terms(FRAME, {}, confs)
    assert used["offtake"]["contracted_tonnes_per_year"] == 50000
    used, _ = ct.engine_terms(FRAME, {}, confs, facts=[{"fact": "BUYER_INSOLVENT", "subject_company_id": A}])
    assert used["offtake"]["contracted_tonnes_per_year"] == 20000
    assert "tenor_years" not in used["offtake"]                   # no longer every buyer's


# ── PostgreSQL: who reports, who clears ─────────────────────────────────────

NAMES = {OWNER: "Test AF Owner", EPC: "Test AF EPC", BANK: "Test AF Bank", ADV: "Test AF Adv",
         A: "Test AF Buyer A", B: "Test AF Buyer B", "greenearthx": "GreenEarthX"}
USERS = {"u_af_exec": (OWNER, "EXECUTIVE", False), "u_af_epc": (EPC, "COMMERCIAL", False),
         "u_af_bank": (BANK, "FINANCE_TREASURY", False), "u_af_adv": (ADV, "FINANCE_TREASURY", False),
         "u_af_a": (A, "COMMERCIAL", False), "u_af_b": (B, "COMMERCIAL", False),
         "u_af_gex": ("greenearthx", "EXECUTIVE", True)}
ACCESS = {EPC: "EPC_CONTRACTOR", BANK: "COMMERCIAL_BANKER", ADV: "LENDERS_ADVISER", A: "OFFTAKER", B: "OFFTAKER"}
STATE: dict = {}


def _h(uid):
    company, fn, gex = USERS[uid]
    return {"x-test-payload": json.dumps({"user_id": uid, "company_id": company, "company_name": NAMES[company],
                                          "business_function": fn, "is_platform_admin": gex})}


@pytest.fixture(scope="module")
def client(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, EPC, BANK, ADV, A, B):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST adverse facts plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    for company, actor in ACCESS.items():
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, %s, 'STAKEHOLDER')", (PID, company, actor))
    for uid, (company, fn, _) in USERS.items():
        if company == "greenearthx":
            continue
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    cur.execute("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES (%s, %s, "
                "'LENDERS_ADVISER') ON CONFLICT DO NOTHING", ("u_af_adv", PID))
    for sha in (DOC, DOC2):
        cur.execute("INSERT INTO evidence_documents (project_id, evidence_key, filename, sha256, size_bytes, "
                    "stored_path, uploaded_by, uploaded_at) VALUES (%s, 'TEST', 'TEST.pdf', %s, 1, 'TEST', "
                    "'u_af_exec', '2026-11-10')", (PID, sha))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_bankability_proxy as proxy, routes_contract_tokens
    from app.db import session

    async def engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "t", "persona_gates": {"EXECUTIVE": []}}
        return {"current_state": "SPECULATIVE", "rules_version": "t", "gate_evaluations": []}

    saved_engine, saved_session, saved_raw = proxy._call_engine, session._sync_engine, proxy._load_terms_raw
    proxy._call_engine = engine
    proxy._load_terms_raw = lambda pid: FRAME if pid == PID else saved_raw(pid)
    session._sync_engine = None
    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        from app.core.request_tenant import (reset_current_company, reset_current_user, set_current_company,
                                             set_current_user)
        payload = json.loads(request.headers["x-test-payload"])
        request.state.user_payload = payload
        t1 = set_current_company("PLATFORM_ADMIN" if payload["is_platform_admin"] else payload["company_id"])
        t2 = set_current_user(payload["user_id"])
        try:
            return await call_next(request)
        finally:
            reset_current_company(t1)
            reset_current_user(t2)

    app.include_router(routes_contract_tokens.router, prefix="/api/v1")
    from app.core.request_tenant import reset_current_company, set_current_company
    t = set_current_company(OWNER)
    try:
        ct.record_versions(PID, FRAME, "u_af_exec", OWNER)
    finally:
        reset_current_company(t)
    tc = TestClient(app)
    r = tc.put(f"/api/v1/contract-tokens/{PID}/epc/counterparty", headers=_h("u_af_exec"), json={"company_id": EPC})
    assert r.status_code == 200, r.text
    yield tc
    proxy._call_engine, proxy._load_terms_raw = saved_engine, saved_raw
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved_session


def _report(client, uid, fact, doc=DOC, subject=None):
    return client.post(f"/api/v1/contract-tokens/{PID}/adverse-facts", headers=_h(uid),
                       json={"fact": fact, "document_sha256": doc, "subject_company_id": subject})


def _clear(client, uid, report, doc=DOC2):
    return client.post(f"/api/v1/contract-tokens/{PID}/adverse-facts/{report}/clear", headers=_h(uid),
                       json={"document_sha256": doc})


def _code(r):
    return r.json()["detail"]["code"]


def _engine():
    from app.api.v1.routes_bankability_proxy import _load_terms
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(OWNER)
    try:
        return _load_terms(PID)
    finally:
        reset_current_company(t)


def test_a_report_needs_a_reporting_party_and_a_document_on_file(client):
    assert _code(_report(client, "u_af_gex", "COUNTERPARTY_INSOLVENT")) == "GEX_REPORTS_NO_FACT"
    assert _code(_report(client, "u_af_a", "COUNTERPARTY_INSOLVENT")) == "NOT_A_REPORTING_PARTY"   # a buyer, on EPC
    assert _code(_report(client, "u_af_exec", "COUNTERPARTY_INSOLVENT", doc="0" * 64)) == "DOCUMENT_REQUIRED"
    assert _code(_report(client, "u_af_exec", "NOT_A_FACT")) == "UNKNOWN_FACT"
    assert "epc" not in _engine() or "counterparty_insolvent" not in _engine()["epc"]


def test_the_owners_report_applies_at_once_and_cannot_be_made_twice(client):
    r = _report(client, "u_af_exec", "COUNTERPARTY_INSOLVENT")
    assert r.status_code == 200, r.text
    STATE["epc_report"] = r.json()["event"]["event_hash"]
    assert _engine()["epc"]["counterparty_insolvent"] is True
    assert _code(_report(client, "u_af_bank", "COUNTERPARTY_INSOLVENT")) == "ALREADY_REPORTED"


def test_clearing_needs_two_other_companies_and_never_the_affected_party(client):
    report = STATE["epc_report"]
    assert _code(_clear(client, "u_af_exec", report)) == "REPORTER_CANNOT_CLEAR"
    assert _code(_clear(client, "u_af_epc", report)) == "AFFECTED_PARTY_CANNOT_CLEAR"
    assert _code(_clear(client, "u_af_gex", report)) == "GEX_CLEARS_NO_FACT"
    assert _code(_clear(client, "u_af_a", report)) == "NOT_A_CLEARING_PARTY"
    assert _code(_clear(client, "u_af_bank", report, doc="0" * 64)) == "DOCUMENT_REQUIRED"
    first = _clear(client, "u_af_bank", report)
    assert first.status_code == 200 and first.json()["cleared"] is False        # one company is not enough
    assert _engine()["epc"]["counterparty_insolvent"] is True
    assert _code(_clear(client, "u_af_bank", report)) == "ALREADY_CONFIRMED_BY_YOUR_COMPANY"
    second = _clear(client, "u_af_adv", report)
    assert second.status_code == 200 and second.json()["cleared"] is True
    assert "counterparty_insolvent" not in _engine().get("epc", {})


def test_a_buyer_reports_about_its_own_sub_leg_never_another_buyers(client):
    assert _code(_report(client, "u_af_a", "BUYER_INSOLVENT", subject=B)) == "NOT_ABOUT_ANOTHER_BUYER"
    assert _code(_report(client, "u_af_bank", "BUYER_INSOLVENT")) == "SUBJECT_REQUIRED"
    assert _code(_report(client, "u_af_bank", "BUYER_INSOLVENT", subject=BANK)) == "NOT_A_BUYER_OF_THIS_FRAME"
    r = _report(client, "u_af_bank", "BUYER_INSOLVENT", subject=A)
    assert r.status_code == 200, r.text
    facts = client.get(f"/api/v1/contract-tokens/{PID}", headers=_h("u_af_exec")).json()["adverse_facts"]
    open_ = [(f["fact"], f["subject_company_id"]) for f in facts if f["open"]]
    assert open_ == [("BUYER_INSOLVENT", A)]
    # the insolvent buyer itself may not clear it; the owner and a reviewer can
    report = r.json()["event"]["event_hash"]
    assert _code(_clear(client, "u_af_a", report)) == "AFFECTED_PARTY_CANNOT_CLEAR"
    assert _clear(client, "u_af_exec", report).json()["cleared"] is False
    assert _clear(client, "u_af_adv", report).json()["cleared"] is True


def test_the_facts_are_events_on_an_intact_chain(client):
    from app.core import market_engine as me
    from app.trading_book import record

    conn = me._conn()
    try:
        for kind in ("epc", "offtake"):
            row = record.by_origin(conn, f"project:{PID}:{kind}")
            assert record.chain_intact(conn, str(row["id"]))
            types = [e["event_type"] for e in record.events(conn, str(row["id"]))]
            assert "ADVERSE_FACT_REPORTED" in types and types.count("ADVERSE_FACT_CLEARED") == 2
    finally:
        conn.close()
