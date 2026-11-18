"""
D-B (JML 2026-11-14): Commercial acts in the market; the CEO and the CFO approve trade
confirmations; Engineering and Operations read. One table, core/market_policy.

Discovery review F04 (probe 03): a producer CFO and an engineer created RFQs through the API
although the menu hid RFQs from them. These tests pin the server rule, the endpoint the screens
read, and the approver rule of TRADE_CONFIRM.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import capacity_sqlite, routes_market, tokens_sqlite
from app.core import abac_middleware as mw
from app.core import market_policy as mp
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID = "proj_TEST_policy"
CO = "TEST Policy Co"
CO_ID = reg.company_slug(CO)
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST policy plant", owner_company_name=CO,
                                   associated_company_names=(), jurisdiction="DE")
RFQ = {"molecule": "e-Methanol", "volume_mtpd": 5, "delivery_start": "2029-01-01", "delivery_end": "2029-06-30"}
DSN: dict = {}


def _auth(function, admin=False):
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": f"pol_{function.lower()}", "email": f"pol_{function.lower()}@test.invalid", "company_id": CO_ID,
        "company_name": CO, "company_type": "PRODUCER", "service_type": None, "business_function": function,
        "user_name": function, "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": admin})[0]}


def _q(sql, params=()):
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,'PRODUCER','DE') "
       "ON CONFLICT DO NOTHING", (CO_ID, CO))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,'TEST policy plant',%s,"
       "'e-Methanol') ON CONFLICT DO NOTHING", (PID, CO_ID))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    mine = "SELECT id FROM tb_counterparty WHERE company_id = %s"
    _q(f"UPDATE tb_rfq SET status = 'withdrawn' WHERE status = 'published' AND requester_id IN ({mine})", (CO_ID,))
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(routes_market.router, prefix="/api/v1/market")
    api.include_router(tokens_sqlite.router, prefix="/api/v1/tokens")
    api.include_router(capacity_sqlite.router, prefix="/api/v1/capacities")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


# ── the table ───────────────────────────────────────────────────────────────

def test_commercial_acts_and_the_ceo_and_cfo_approve():
    acts = [a for a in mp.POLICY if a not in ("trade.confirm.approve", "capacity.create", "product.declare")]
    for a in acts:
        assert mp.allows("COMMERCIAL", a), a
        for f in ("EXECUTIVE", "FINANCE_TREASURY", "ENGINEERING", "OPERATIONS", None):
            assert not mp.allows(f, a), (f, a)
    for f in ("EXECUTIVE", "FINANCE_TREASURY"):
        assert mp.allows(f, "trade.confirm.approve")
    assert not mp.allows("COMMERCIAL", "trade.confirm.approve")
    assert mp.allows("OPERATIONS", "capacity.create") and not mp.allows("ENGINEERING", "capacity.create")
    for f in ("COMMERCIAL", "OPERATIONS", "ENGINEERING", "COMPLIANCE_LEGAL"):
        assert mp.allows(f, "product.declare")
    for f in ("EXECUTIVE", "FINANCE_TREASURY", None):
        assert not mp.allows(f, "product.declare")


# ── the server ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("function", ["FINANCE_TREASURY", "ENGINEERING", "EXECUTIVE", "OPERATIONS"])
def test_only_commercial_raises_an_rfq(client, function):
    r = client.post("/api/v1/market/rfqs", headers=_auth(function), json=RFQ)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ROLE_NOT_ALLOWED", r.text
    assert "Commercial" in r.json()["detail"]["message"]


def test_commercial_raises_an_rfq(client):
    assert client.post("/api/v1/market/rfqs", headers=_auth("COMMERCIAL"), json=RFQ).status_code == 201


def test_gex_is_refused_as_gex_not_as_a_role(client):
    r = client.post("/api/v1/market/rfqs", headers=_auth("EXECUTIVE", admin=True), json=RFQ)
    assert r.json()["detail"]["code"] == "GEX_DOES_NOT_TRADE"


def test_minting_and_declaring_capacity_follow_the_table(client):
    body = {"project_id": PID, "project_name": "TEST policy plant", "molecule": "e-Methanol", "capacity_mtpd": 10}
    assert client.post("/api/v1/capacities/", headers=_auth("ENGINEERING"), json=body).status_code == 403
    r = client.post("/api/v1/capacities/", headers=_auth("OPERATIONS"), json=body)
    assert r.status_code == 201, r.text
    mint = {"capacity_id": r.json()["id"], "tokenised_mtpd": 1, "delivery_start": "2029-01-01", "delivery_end": "2029-12-31"}
    assert client.post("/api/v1/tokens/", headers=_auth("OPERATIONS"), json=mint).json()["detail"]["code"] == "ROLE_NOT_ALLOWED"
    assert client.post("/api/v1/tokens/", headers=_auth("COMMERCIAL"), json=mint).status_code == 201


def test_the_screens_read_the_same_table(client):
    com = client.get("/api/v1/market/policy", headers=_auth("COMMERCIAL")).json()
    cfo = client.get("/api/v1/market/policy", headers=_auth("FINANCE_TREASURY")).json()
    gex = client.get("/api/v1/market/policy", headers=_auth("EXECUTIVE", admin=True)).json()
    assert com["allowed"] == mp.allowed_actions("COMMERCIAL") and "rfq.create" in com["allowed"]
    assert cfo["allowed"] == ["trade.confirm.approve"]
    assert gex["allowed"] == []


# ── TRADE_CONFIRM: the second pair of eyes ─────────────────────────────────

def _decide(monkeypatch, initiator_fn, approver_fn, action="TRADE_CONFIRM"):
    from app.core import wae
    accounts = {"i": {"user_id": "i", "company_id": CO_ID, "account_state": "ACTIVE", "business_function": initiator_fn,
                      "is_platform_admin": 0},
                "a": {"user_id": "a", "company_id": CO_ID, "account_state": "ACTIVE", "business_function": approver_fn,
                      "is_platform_admin": 0}}
    monkeypatch.setattr(wae, "_account", lambda uid: accounts.get(uid))
    req = {"action_type": action, "initiator_user_id": "i", "payload_json": json.dumps({"party_company_id": CO_ID})}
    return wae._trade_confirm_refusal(req, "a")


@pytest.mark.parametrize("approver", ["EXECUTIVE", "FINANCE_TREASURY"])
def test_the_ceo_or_the_cfo_approves_a_trade_confirmation(monkeypatch, approver):
    assert _decide(monkeypatch, "COMMERCIAL", approver) is None


@pytest.mark.parametrize("approver", ["COMMERCIAL", "ENGINEERING"])
def test_nobody_else_approves_it(monkeypatch, approver):
    assert _decide(monkeypatch, "COMMERCIAL", approver)["code"] == "APPROVER_ROLE"


def test_delivery_confirmations_keep_their_own_rule(monkeypatch):
    """D-B is about trading. DELIVERY_CONFIRM keeps 107's rule: one of the two is an executive."""
    assert _decide(monkeypatch, "EXECUTIVE", "COMMERCIAL", action="DELIVERY_CONFIRM") is None
    assert _decide(monkeypatch, "COMMERCIAL", "COMMERCIAL", action="DELIVERY_CONFIRM")["code"] == "EXECUTIVE_REQUIRED"
