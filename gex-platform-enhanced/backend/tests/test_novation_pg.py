"""
Novation of a frame buyer's sub-leg — three confirmations, no token (Phase 3 of
"One contract record", Phase 0 Q13, JML 2026-11-06).

Rule 3 stands: the contract record is not a transferable asset. A buyer's sub-leg
changes hands only by NOVATION events on the frame's chain, valid once the producer,
the outgoing buyer and the incoming buyer have each confirmed it. Until then the
outgoing buyer's confirmed terms keep counting; once complete the incoming buyer is
the sub-leg's buyer on the same terms and its volume counts at once. Refused: GEX as
a party, the producer as the incoming buyer, an incoming buyer that is not a vetted
project party, a restricted pair, a disputed sub-leg, a sub-leg that changed.

In the throwaway PostgreSQL database (conftest.pg_store) with the engine faked.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import contract_tokens as ct
from pg_support import connect_dsn

OWNER, A, B, N, R, P = ("test_nv_owner", "test_nv_buyer_a", "test_nv_buyer_b", "test_nv_incoming",
                        "test_nv_restricted", "test_nv_pending")
PID = "proj_TEST_novation"
NAMES = {OWNER: "Test NV Owner", A: "Test NV Buyer A", B: "Test NV Buyer B", N: "Test NV Incoming",
         R: "Test NV Restricted", P: "Test NV Pending", "greenearthx": "GreenEarthX"}
USERS = {"u_nv_exec": (OWNER, "EXECUTIVE", False), "u_nv_a": (A, "COMMERCIAL", False),
         "u_nv_b": (B, "COMMERCIAL", False), "u_nv_n": (N, "COMMERCIAL", False), "u_nv_r": (R, "COMMERCIAL", False),
         "u_nv_gex": ("greenearthx", "EXECUTIVE", True)}
SHARED = {"certification_scheme": "RFNBO", "product_spec_standard": "IMPCA 2021"}
FRAME = {"offtake": {**SHARED, "buyers": [
    {"company_id": A, "contracted_tonnes_per_year": 30000, "tenor_years": 15},
    {"company_id": B, "contracted_tonnes_per_year": 20000, "tenor_years": 12}]}}
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
    for company in (OWNER, A, B, N, R, P):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST novation plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    for company in (A, B, N, R, P):
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (PID, company))
    for uid, (company, fn, _) in USERS.items():
        if company == "greenearthx":
            continue
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    # P is a project party with no vetted account (PENDING only).
    cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                "business_function, user_name, account_state) VALUES ('u_nv_p', 'u_nv_p@test.invalid', 'TEST', %s, "
                "%s, 'PRODUCER', 'COMMERCIAL', 'u_nv_p', 'PENDING') ON CONFLICT DO NOTHING", (P, NAMES[P]))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_bankability_proxy as proxy, routes_contract_tokens
    from app.db import session

    async def engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "t", "persona_gates": {"EXECUTIVE": []}}
        return {"current_state": "SPECULATIVE", "rules_version": "t", "gate_evaluations": []}

    saved_engine, saved_session = proxy._call_engine, session._sync_engine
    proxy._call_engine = engine
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
    _save(FRAME)
    tc = TestClient(app)
    for uid, company, n in (("u_nv_a", A, 0), ("u_nv_b", B, 1)):
        h = _frame(tc)["buyers"][n]["sub_leg_hash"]
        assert tc.post(f"/api/v1/contract-tokens/{PID}/offtake/buyers/{company}/confirm", headers=_h(uid),
                       json={"sub_leg_hash": h}).status_code == 200
    # the producer and R are a restricted pair
    from app.core import market_engine as me
    from app.trading_book import record
    mc = me._conn()
    try:
        mc.execute("INSERT INTO tb_counterparty_restriction (counterparty_id, restricted_counterparty_id, reason, "
                   "set_by, active) VALUES (?, ?, 'TEST', 'TEST', true)",
                   (record.counterparty_for(mc, OWNER), record.counterparty_for(mc, R)))
        mc.commit()
    finally:
        mc.close()
    yield tc
    proxy._call_engine = saved_engine
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved_session


def _save(cards):
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(OWNER)
    try:
        return ct.record_versions(PID, cards, "u_nv_exec", OWNER, card_type="offtake")
    finally:
        reset_current_company(t)


def _frame(client, uid="u_nv_exec"):
    return next(t for t in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h(uid)).json()["tokens"]
                if t["kind"] == "offtake")["frame"]


def _volume():
    from app.api.v1.routes_bankability_proxy import _load_terms

    return _load_terms(PID).get("offtake", {}).get("contracted_tonnes_per_year")


def _propose(client, uid, outgoing, incoming, doc=None):
    return client.post(f"/api/v1/contract-tokens/{PID}/offtake/buyers/{outgoing}/novation", headers=_h(uid),
                       json={"incoming_company_id": incoming, "document_sha256": doc})


def _confirm(client, uid, proposal):
    return client.post(f"/api/v1/contract-tokens/{PID}/offtake/novations/{proposal}/confirm", headers=_h(uid))


def _code(r):
    return r.json()["detail"]["code"]


def test_who_may_propose_and_to_whom(client):
    assert _volume() == 50000
    assert _code(_propose(client, "u_nv_gex", A, N)) == "GEX_IS_NO_PARTY"
    assert _code(_propose(client, "u_nv_b", A, N)) == "NOT_A_NOVATION_PARTY"        # another buyer
    assert _code(_propose(client, "u_nv_a", A, OWNER)) == "PRODUCER_CANNOT_BUY_ITS_OWN"
    assert _code(_propose(client, "u_nv_a", A, "test_nv_nobody")) == "NOT_A_PROJECT_PARTY"
    assert _code(_propose(client, "u_nv_a", A, P)) == "INCOMING_NOT_VETTED"
    assert _code(_propose(client, "u_nv_a", A, B)) == "ALREADY_A_BUYER"
    assert _code(_propose(client, "u_nv_a", A, R)) == "RESTRICTED_COUNTERPARTY"


def test_three_confirmations_and_the_incoming_buyers_volume_counts_at_once(client):
    r = _propose(client, "u_nv_a", A, N)
    assert r.status_code == 200, r.text
    proposal = r.json()["proposal_event_hash"]
    assert r.json()["awaiting"] == ["producer", "incoming"]
    assert _code(_propose(client, "u_nv_exec", A, N)) == "NOVATION_PENDING"
    assert _code(_confirm(client, "u_nv_a", proposal)) == "ALREADY_CONFIRMED"
    assert _code(_confirm(client, "u_nv_b", proposal)) == "NOT_A_NOVATION_PARTY"
    assert _code(_confirm(client, "u_nv_gex", proposal)) == "GEX_IS_NO_PARTY"
    assert _confirm(client, "u_nv_n", proposal).json()["completed"] is False
    assert _volume() == 50000 and [b["company_id"] for b in _frame(client)["buyers"]] == [A, B]   # A still counts
    done = _confirm(client, "u_nv_exec", proposal)
    assert done.status_code == 200 and done.json()["completed"] is True, done.text
    frame = _frame(client)
    assert [(b["company_id"], b["confirmed"]) for b in frame["buyers"]] == [(N, True), (B, True)]
    assert _volume() == 50000                                # the same terms, now N's: counted at once
    assert _code(_confirm(client, "u_nv_b", proposal)) == "NOVATION_COMPLETED"
    view = ct.card_view(PID)["offtake"]["terms"]["buyers"]
    assert [b["company_id"] for b in view] == [N, B] and view[0]["contracted_tonnes_per_year"] == 30000
    STATE["proposal"] = proposal


def test_the_novation_is_events_on_an_intact_chain(client):
    from app.core import market_engine as me
    from app.trading_book import record

    conn = me._conn()
    try:
        row = record.by_origin(conn, f"project:{PID}:offtake")
        assert record.chain_intact(conn, str(row["id"]))
        evs = record.events(conn, str(row["id"]))
        steps = [json.loads(e["note"])["step"] for e in evs if e["event_type"] == "NOVATION"]
        assert steps == ["proposed", "confirmed", "confirmed", "completed"]
        assert evs[-1]["event_type"] == "CONFIRMED" and evs[-1]["company_id"] == N
    finally:
        conn.close()


def test_a_disputed_or_changed_sub_leg_does_not_change_hands(client):
    r = _propose(client, "u_nv_b", B, A)                  # A left the frame: it may come back in B's place
    assert r.status_code == 200, r.text
    edited = {"offtake": {**SHARED, "buyers": [
        {"company_id": N, "contracted_tonnes_per_year": 30000, "tenor_years": 15},
        {"company_id": B, "contracted_tonnes_per_year": 25000, "tenor_years": 12}]}}
    _save(edited)
    assert _code(_confirm(client, "u_nv_exec", r.json()["proposal_event_hash"])) == "SUB_LEG_CHANGED"
    lapsed = next(n for n in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h("u_nv_exec")).json()["novations"]
                  if n["proposal_event_hash"] == r.json()["proposal_event_hash"])
    assert lapsed["state"] == "lapsed"                    # it blocks nothing now
    h = client.post(f"/api/v1/contract-tokens/{PID}/offtake/buyers/{B}/dispute", headers=_h("u_nv_b"),
                    json={"note": "TEST: not the volume we signed"})
    assert h.status_code == 200
    assert _code(_propose(client, "u_nv_exec", B, A)) == "SUB_LEG_DISPUTED"
