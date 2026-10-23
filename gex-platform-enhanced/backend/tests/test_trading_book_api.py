"""
Trading book create/update (gap register G-05) — who may book what.

Through the REAL ABAC middleware and the REAL /api/v1/trading-book routes, in a
throwaway PostgreSQL database (conftest.pg_store) — the trading book is
PostgreSQL only (JML, 2026-10-23), so the same request also passes alembic
064's policies as gex_app. One synthetic TEST project: its owner registers the
asset and books a contract, its lender (an associated company) reads both, a
bystander sees nothing, and GEX maintains the price indices and books nothing.
The PostgreSQL side of the same rules (alembic 064) is tests/test_trading_book_pg.py.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from app.trading_book import api as tb

PID = "proj_TEST_trading_book"
OWNER, LENDER, OTHER = "TEST Book Owner", "TEST Book Lender", "TEST Book Bystander"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST trading book plant",
                                   owner_company_name=OWNER, associated_company_names=(LENDER,),
                                   jurisdiction="NL")
USERS = {"u_owner": (OWNER, False), "u_lender": (LENDER, False),
         "u_other": (OTHER, False), "u_gex": ("GreenEarthX", True)}
URL = "/api/v1/trading-book"


def _auth(uid: str) -> dict:
    company, admin = USERS[uid]
    token = create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": "PRODUCER", "service_type": None,
        "business_function": "EXECUTIVE", "user_name": f"TEST {uid}", "clearance_level": "STANDARD",
        "jurisdiction": "NL", "kyc_status": "VERIFIED", "nda_signed_with": [], "assigned_audits": [],
        "actor_type_per_project": {}, "is_platform_admin": admin})[0]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def session_factory(pg_store):
    from pg_support import connect_dsn

    # The project and the lender's access exist in the database, not only in
    # the registry stand-in: 064's policies resolve ownership and access there.
    conn = connect_dsn(pg_store)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        for company, kind in ((OWNER, "PRODUCER"), (LENDER, "LENDER")):
            cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, %s)",
                        (reg.company_slug(company), company, kind))
        cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                    "VALUES (%s, %s, %s, 'H2')", (PID, "TEST trading book plant", reg.company_slug(OWNER)))
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type) VALUES (%s, %s, 'LENDER')",
                    (PID, reg.company_slug(LENDER)))
        conn.commit()
    finally:
        conn.close()
    return sessionmaker(bind=create_engine(pg_store), autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory, monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)

    api = FastAPI()
    api.include_router(tb.router, prefix=URL)
    api.dependency_overrides[tb.get_db] = tb.tenant_session_dependency(session_factory)
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api)


def _code(r):
    return r.json()["detail"]["code"]


STATE: dict = {}
ASSET = {"project_id": PID, "name": "TEST Book Plant", "location": "TEST Rotterdam", "country_code": "nl",
         "technology": "PEM_ELECTROLYSIS", "capacity_mw": "100"}


def test_1_only_the_project_owner_registers_its_asset(client):
    assert _code(client.post(f"{URL}/assets", headers=_auth("u_lender"), json=ASSET)) == "NOT_YOUR_PROJECT"
    assert _code(client.post(f"{URL}/assets", headers=_auth("u_gex"), json=ASSET)) == "GEX_DOES_NOT_TRADE"
    r = client.post(f"{URL}/assets", headers=_auth("u_owner"), json=ASSET)
    assert r.status_code == 201, r.text
    STATE["asset"] = r.json()["id"]
    assert r.json()["project_id"] == PID and r.json()["country_code"] == "NL"


def test_2_the_projects_companies_read_the_asset_a_bystander_does_not(client):
    a = STATE["asset"]
    assert [x["id"] for x in client.get(f"{URL}/assets", headers=_auth("u_lender")).json()] == [a]
    assert client.get(f"{URL}/assets", headers=_auth("u_other")).json() == []
    assert client.get(f"{URL}/assets/{a}", headers=_auth("u_other")).status_code == 404
    assert _code(client.patch(f"{URL}/assets/{a}", headers=_auth("u_lender"),
                              json={"capacity_mw": "1"})) == "NOT_YOUR_PROJECT"
    r = client.patch(f"{URL}/assets/{a}", headers=_auth("u_owner"), json={"capacity_mw": "120"})
    assert r.status_code == 200 and float(r.json()["capacity_mw"]) == 120.0


def test_3_indices_are_reference_data_gex_writes_everyone_reads(client):
    idx = {"provider": "Argus", "index_code": "TEST_GREEN_H2_NWE", "currency": "eur", "unit_basis": "MWh"}
    assert _code(client.post(f"{URL}/indices", headers=_auth("u_owner"), json=idx)) == "GEX_REFERENCE_DATA"
    r = client.post(f"{URL}/indices", headers=_auth("u_gex"), json=idx)
    assert r.status_code == 201, r.text
    STATE["index"] = r.json()["id"]
    obs = {"index_definition_id": STATE["index"], "observation_date": "2026-10-01", "value": "101.5"}
    assert _code(client.post(f"{URL}/indices/{STATE['index']}/history", headers=_auth("u_owner"),
                             json=obs)) == "GEX_REFERENCE_DATA"
    assert client.post(f"{URL}/indices/{STATE['index']}/history", headers=_auth("u_gex"),
                       json=obs).status_code == 201
    assert [i["index_code"] for i in client.get(f"{URL}/indices", headers=_auth("u_other")).json()] \
        == ["TEST_GREEN_H2_NWE"]


def test_4_counterparties_are_a_shared_register(client):
    ids = []
    for name in ("TEST Offtaker plc", "TEST Plant OpCo BV"):
        r = client.post(f"{URL}/counterparties", headers=_auth("u_owner"),
                        json={"legal_name": name, "country_code": "NL"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    STATE["buy"], STATE["sell"] = ids
    assert _code(client.patch(f"{URL}/counterparties/{ids[0]}", headers=_auth("u_owner"),
                              json={"country_code": "GB"})) == "SHARED_REGISTER"
    assert client.patch(f"{URL}/counterparties/{ids[0]}", headers=_auth("u_gex"),
                        json={"country_code": "GB"}).json()["country_code"] == "GB"
    dup = client.post(f"{URL}/counterparties", headers=_auth("u_other"),
                      json={"legal_name": "TEST Offtaker plc", "country_code": "NL"})
    assert _code(dup) == "CONFLICT"


def _contract_body(**extra):
    return {"contract_number": "TEST-BOOK-001", "buy_side_id": STATE["buy"], "sell_side_id": STATE["sell"],
            "fuel_type": "green-h2", "trade_date": "2026-10-23", "effective_date": "2027-06-01",
            "termination_date": "2042-05-31", "notional_quantity": "7500000", "quantity_unit": "MWh",
            "currency": "eur", **extra}


def test_5_a_contract_is_booked_in_the_callers_book(client):
    body = _contract_body(index_definition_id=STATE["index"], spread="15.5", floor="80", cap="250")
    assert _code(client.post(f"{URL}/contracts/index-linked", headers=_auth("u_gex"), json=body)) \
        == "GEX_DOES_NOT_TRADE"
    r = client.post(f"{URL}/contracts/index-linked", headers=_auth("u_owner"),
                    json={**body, "owner_company_id": reg.company_slug(OTHER)})
    assert r.status_code == 201, r.text
    STATE["contract"] = r.json()["id"]
    assert r.json()["owner_company_id"] == reg.company_slug(OWNER)      # the body cannot name the book
    assert r.json()["fuel_type"] == "GREEN_H2" and r.json()["contract_type"] == "index_linked"
    bad = _contract_body(contract_number="TEST-BOOK-002", index_definition_id="00000000-0000-0000-0000-000000000000")
    assert _code(client.post(f"{URL}/contracts/index-linked", headers=_auth("u_owner"), json=bad)) == "UNKNOWN_INDEX"


def test_6_status_moves_through_the_lifecycle_only_in_its_own_book(client):
    c = f"{URL}/contracts/{STATE['contract']}/status"
    assert client.patch(c, headers=_auth("u_lender"), json={"status": "proposed"}).status_code == 404
    assert _code(client.patch(c, headers=_auth("u_owner"), json={"status": "committed"})) == "INVALID_TRANSITION"
    assert client.patch(c, headers=_auth("u_owner"), json={"status": "proposed"}).json()["status"] == "proposed"
    assert client.patch(c, headers=_auth("u_owner"), json={"status": "committed"}).json()["status"] == "committed"


def test_7_the_owner_links_the_contract_to_its_asset_and_the_lender_then_sees_it(client):
    cid, aid = STATE["contract"], STATE["asset"]
    assert client.get(f"{URL}/contracts/{cid}", headers=_auth("u_lender")).status_code == 404
    link = {"project_asset_id": aid, "contract_id": cid, "line_item_type": "revenue"}
    assert _code(client.post(f"{URL}/links", headers=_auth("u_lender"), json=link)) == "NOT_YOUR_PROJECT"
    r = client.post(f"{URL}/links", headers=_auth("u_owner"), json=link)
    assert r.status_code == 201, r.text
    STATE["link"] = r.json()["id"]
    assert client.get(f"{URL}/contracts/{cid}", headers=_auth("u_lender")).status_code == 200
    assert client.get(f"{URL}/contracts", headers=_auth("u_other")).json() == []
    listed = client.get(f"{URL}/projects/{aid}/contracts", headers=_auth("u_lender")).json()
    assert [x["contract_id"] for x in listed] == [cid]
    assert client.get(f"{URL}/projects/{aid}/cashflows", headers=_auth("u_other")).status_code == 404
    flows = client.get(f"{URL}/projects/{aid}/cashflows?from_date=2027-06-01&to_date=2027-12-31",
                       headers=_auth("u_lender"))
    assert flows.status_code == 200, flows.text
    r = client.patch(f"{URL}/links/{STATE['link']}", headers=_auth("u_owner"), json={"allocation_share": "0.5"})
    assert float(r.json()["allocation_share"]) == 0.5
