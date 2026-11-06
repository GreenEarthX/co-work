"""
Only terms confirmed on the contract token reach the engine; the counterparty's
confirmation verifies the contract's evidence (JML 2026-10-28; alembic 078).

Before: the cross-contract checks compared terms the OWNER typed — a volume
could be adjusted until C2 passed, and nobody else ever saw it.

Unit tests need nothing; the rest run in the throwaway PostgreSQL database
(conftest.pg_store) with the engine faked.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import contract_tokens as ct
from pg_support import connect_dsn

CARDS = {"offtake": {"contracted_tonnes_per_year": 40000, "tenor_years": 15, "planned_output_tonnes_per_year": 50000},
         "supply": {"support_or_ppa_revoked": True, "feedstock_contracted_tonnes_per_year": 60000}}


def test_unconfirmed_terms_are_held_back_but_adverse_facts_apply():
    used, held = ct.engine_terms(CARDS, {})
    assert used == {"supply": {"support_or_ppa_revoked": True}}
    assert "offtake.contracted_tonnes_per_year" in held["offtake"]
    assert "offtake.planned_output_tonnes_per_year" in held["technical"]


def test_a_confirmed_value_counts_and_a_changed_one_is_held_again():
    confirmed = {"offtake": ct.kind_terms(CARDS, "offtake")}
    used, _ = ct.engine_terms(CARDS, confirmed)
    assert used["offtake"] == {"contracted_tonnes_per_year": 40000, "tenor_years": 15}
    edited = {**CARDS, "offtake": {**CARDS["offtake"], "contracted_tonnes_per_year": 45000}}
    used, held = ct.engine_terms(edited, confirmed)
    assert "contracted_tonnes_per_year" not in used["offtake"]
    assert "offtake.contracted_tonnes_per_year" in held["offtake"]


def test_every_card_field_belongs_to_a_contract_kind():
    from app.core.bankability_engine import COMMITMENT_CARD_FIELDS

    for card, fields in COMMITMENT_CARD_FIELDS.items():
        for field in fields:
            assert ct.FIELD_KIND.get(card, {}).get(field), f"{card}.{field} has no contract kind"


# ── PostgreSQL ──────────────────────────────────────────────────────────────

OWNER, BUYER, OUTSIDER, ADVISER = "test_ct_owner", "test_ct_buyer", "test_ct_outsider", "test_ct_adviser"
NAMES = {OWNER: "Test CT Owner", BUYER: "Test CT Buyer", OUTSIDER: "Test CT Outsider",
         ADVISER: "Test CT Adviser", "greenearthx": "GreenEarthX"}
PID = "proj_TEST_contract_tokens"
USERS = {"u_ct_exec": (OWNER, "EXECUTIVE", False), "u_ct_buyer": (BUYER, "COMMERCIAL", False),
         "u_ct_out": (OUTSIDER, "EXECUTIVE", False), "u_ct_adv": (ADVISER, "FINANCE_TREASURY", False),
         "u_ct_gex": ("greenearthx", "EXECUTIVE", True)}


def _h(uid):
    company, fn, gex = USERS[uid]
    return {"x-test-payload": json.dumps({"user_id": uid, "company_id": company, "company_name": NAMES[company],
                                          "business_function": fn, "is_platform_admin": gex})}


@pytest.fixture(scope="module")
def client(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, BUYER, OUTSIDER, ADVISER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST tokens plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    for company, actor in ((BUYER, "OFFTAKER"), (ADVISER, "LENDERS_ADVISER")):
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, %s, 'STAKEHOLDER')", (PID, company, actor))
    for uid, (company, fn, _) in USERS.items():
        if company == "greenearthx":
            continue
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    cur.execute("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES (%s, %s, "
                "'LENDERS_ADVISER') ON CONFLICT DO NOTHING", ("u_ct_adv", PID))
    cur.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, document_hash, "
                "maturity) VALUES (%s, 'binding_offtake_contract_executed', 'SUBMITTED', 'u_ct_exec', %s, 'EXECUTED')",
                (PID, "a" * 64))
    cur.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, document_hash, "
                "maturity) VALUES (%s, 'credit_support_package', 'SUBMITTED', 'u_ct_exec', %s, 'EXECUTED')",
                (PID, "b" * 64))
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
    yield TestClient(app)
    proxy._call_engine = saved_engine
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved_session


def _as_owner(fn):
    from app.core.request_tenant import reset_current_company, set_current_company
    t = set_current_company(OWNER)
    try:
        return fn()
    finally:
        reset_current_company(t)


def _token(client, kind, uid="u_ct_exec"):
    return next(t for t in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h(uid)).json()["tokens"]
                if t["kind"] == kind)


def test_the_counterparty_confirms_the_latest_version_and_verifies_the_contract(client):
    cards = {"offtake": {"contracted_tonnes_per_year": 40000, "tenor_years": 15}}
    _as_owner(lambda: ct.record_versions(PID, cards, "u_ct_exec", OWNER))
    tok = _token(client, "offtake")
    assert tok["latest_version_sha256"] and not tok["confirmed"]
    assert client.put(f"/api/v1/contract-tokens/{PID}/offtake/counterparty", headers=_h("u_ct_buyer"),
                      json={"company_id": BUYER}).status_code == 403
    assert client.put(f"/api/v1/contract-tokens/{PID}/offtake/counterparty", headers=_h("u_ct_exec"),
                      json={"company_id": OUTSIDER}).json()["detail"]["code"] == "NOT_A_PROJECT_PARTY"
    assert client.put(f"/api/v1/contract-tokens/{PID}/offtake/counterparty", headers=_h("u_ct_exec"),
                      json={"company_id": BUYER}).status_code == 200
    sha = tok["latest_version_sha256"]
    own = client.post(f"/api/v1/contract-tokens/{PID}/offtake/confirm", headers=_h("u_ct_exec"),
                      json={"terms_sha256": sha})
    assert own.json()["detail"]["code"] == "COUNTERPARTY_ONLY"
    assert client.post(f"/api/v1/contract-tokens/{PID}/offtake/confirm", headers=_h("u_ct_gex"),
                       json={"terms_sha256": sha}).json()["detail"]["code"] == "GEX_DOES_NOT_CONFIRM"
    stale = client.post(f"/api/v1/contract-tokens/{PID}/offtake/confirm", headers=_h("u_ct_buyer"),
                        json={"terms_sha256": "0" * 64})
    assert stale.json()["detail"]["code"] == "NOT_THE_LATEST_VERSION"
    ok = client.post(f"/api/v1/contract-tokens/{PID}/offtake/confirm", headers=_h("u_ct_buyer"),
                     json={"terms_sha256": sha})
    assert ok.status_code == 200, ok.text
    assert ok.json()["evidence_verified"] == ["binding_offtake_contract_executed"]
    from app.api.v1.routes_bankability_proxy import _load_evidence, _load_terms
    row = _as_owner(lambda: next(e for e in _load_evidence(PID) if e["key"] == "binding_offtake_contract_executed"))
    assert row["status"] == "VERIFIED" and row["verified_by"] == "u_ct_buyer"
    # The buyer agreeing it posted a letter of credit does not authenticate the instrument (rules 4.3.0
    # review, 2026-10-30): that stays an independent reviewer's item. Negative-verified: restoring
    # credit_support_package to CONTRACT_EVIDENCE["offtake"] fails here.
    credit = _as_owner(lambda: next(e for e in _load_evidence(PID) if e["key"] == "credit_support_package"))
    assert credit["status"] == "SUBMITTED" and not credit.get("verified_by")
    import app.api.v1.routes_bankability_proxy as proxy
    saved = proxy._load_terms_raw
    proxy._load_terms_raw = lambda pid: cards
    try:
        assert _as_owner(lambda: _load_terms(PID)) == cards
    finally:
        proxy._load_terms_raw = saved


def test_an_owner_edit_is_held_until_confirmed_again(client):
    from app.api.v1.routes_bankability_proxy import _load_terms

    edited = {"offtake": {"contracted_tonnes_per_year": 45000, "tenor_years": 15}}
    _as_owner(lambda: ct.record_versions(PID, edited, "u_ct_exec", OWNER))
    monkey = {"offtake": edited["offtake"]}
    import app.api.v1.routes_bankability_proxy as proxy
    saved = proxy._load_terms_raw
    proxy._load_terms_raw = lambda pid: monkey
    try:
        assert _as_owner(lambda: _load_terms(PID)) == {"offtake": {"tenor_years": 15}}
    finally:
        proxy._load_terms_raw = saved
    assert _token(client, "offtake")["latest_version_sha256"] != ct.terms_hash(
        {"offtake.contracted_tonnes_per_year": 40000, "offtake.tenor_years": 15})


def test_the_producers_own_plan_is_confirmed_by_an_appointed_reviewer(client):
    _as_owner(lambda: ct.record_versions(PID, {"model": {"debt_tenor_years": 12}}, "u_ct_exec", OWNER))
    sha = _token(client, "model")["latest_version_sha256"]
    assert client.post(f"/api/v1/contract-tokens/{PID}/model/confirm", headers=_h("u_ct_exec"),
                       json={"terms_sha256": sha}).json()["detail"]["code"] == "OWNER_CANNOT_CONFIRM"
    assert client.post(f"/api/v1/contract-tokens/{PID}/model/confirm", headers=_h("u_ct_buyer"),
                       json={"terms_sha256": sha}).json()["detail"]["code"] == "NOT_APPOINTED_REVIEWER"
    ok = client.post(f"/api/v1/contract-tokens/{PID}/model/confirm", headers=_h("u_ct_adv"),
                     json={"terms_sha256": sha})
    assert ok.status_code == 200, ok.text


def test_a_dispute_withdraws_the_confirmation(client):
    sha = _token(client, "model")["latest_version_sha256"]
    assert _token(client, "model")["confirmed"]
    client.post(f"/api/v1/contract-tokens/{PID}/model/dispute", headers=_h("u_ct_adv"),
                json={"note": "Debt tenor in the model is not the term sheet's"})
    assert not _token(client, "model")["confirmed"] and sha


def test_the_token_is_append_only_and_its_chain_detects_tampering(client, pg_store):
    """Negative-verified: the runtime role cannot rewrite an event; a superuser
    rewrite breaks the hash chain."""
    from app.core.request_tenant import reset_current_company, set_current_company

    assert _token(client, "offtake")["chain_intact"]
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    with pytest.raises(Exception, match="permission denied"):
        cur.execute("UPDATE project_contract_event SET note = 'x' WHERE project_id = %s", (PID,))
    conn.rollback()
    conn.close()
    t = set_current_company(OWNER)
    try:
        c = ct.contract(PID, "offtake", create=False)
        evs = ct.events(c["id"])
        assert ct.chain_intact(c["id"], evs)
        evs[0] = {**evs[0], "note": "rewritten"}
        assert not ct.chain_intact(c["id"], evs)
        assert not ct.chain_intact(c["id"], evs[1:])        # a removed event breaks it too
    finally:
        reset_current_company(t)


def test_a_counterparty_never_verifies_an_instrument_a_third_party_issues():
    """Letter of credit (offtake) and performance bond / parent guarantee (EPC): the counterparty
    confirms the contract, an independent reviewer assesses the instrument. Negative-verified
    2026-10-30: restoring either key to CONTRACT_EVIDENCE fails this."""
    verified_by_counterparty = {k for keys in ct.CONTRACT_EVIDENCE.values() for k in keys}
    assert not verified_by_counterparty & {"credit_support_package", "epc_security_package"}
    assert "epc_contract_fixed_price_or_capped_gmp" in ct.CONTRACT_EVIDENCE["epc"]


def test_an_appointed_reviewer_reads_the_contracts_of_its_own_gates_only(client):
    """Phase 0 Q5 (JML 2026-11-06). The lenders' adviser reviews G0, G4, G7–G10: it
    reads the offtake (G4) and model (G8) contracts and no other; the owner reads all."""
    owner = [t["kind"] for t in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h("u_ct_exec")).json()["tokens"]]
    adviser = [t["kind"] for t in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h("u_ct_adv")).json()["tokens"]]
    assert owner == list(ct.COUNTERPARTY_KINDS) + list(ct.REVIEWER_KINDS)
    assert adviser == ["offtake", "model"]


def test_changing_the_counterparty_is_one_transaction(client, monkeypatch):
    """Phase 0 §4 gap 4: 078 updated the counterparty, then appended COUNTERPARTY_SET,
    then DISPUTED, in three transactions; a failure between them left the new
    counterparty with the old confirmations standing."""
    from app.trading_book import record

    c = ct.contract(PID, "offtake", create=False)
    before = [e["event_type"] for e in ct.events(c["id"])]
    real = record.append_event

    def fail_on_dispute(conn, contract_id, event_type, *a, **k):
        if event_type == "DISPUTED":
            raise RuntimeError("TEST: failure between the two events")
        return real(conn, contract_id, event_type, *a, **k)

    monkeypatch.setattr(record, "append_event", fail_on_dispute)
    with pytest.raises(RuntimeError):
        client.put(f"/api/v1/contract-tokens/{PID}/offtake/counterparty", headers=_h("u_ct_exec"),
                   json={"company_id": ADVISER})
    monkeypatch.setattr(record, "append_event", real)
    after = ct.contract(PID, "offtake", create=False)
    assert after["counterparty_company_id"] == BUYER                  # unchanged
    assert [e["event_type"] for e in ct.events(c["id"])] == before    # nothing half-written
